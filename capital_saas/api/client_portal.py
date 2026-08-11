import hashlib
import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.access_scope import get_access_scope
from core.config import BASE_DIR, settings
from core.pricing_engine import PRODUCT_RANK, products
from core.data_masking import mask_phone
from core.capital_health_report import ensure_capital_health_snapshot, report_entitlements
from db.database import get_db
from db.models import (AdvisorBooking, ConsultingCase, CustomerAccessToken, CustomerAccount,
    CustomerConfirmation, CustomerMessage, CustomerTask, Event, FinancingProject,
    FundingApplication, Lead, NotificationJob, Order, ProjectTimelineEvent, Report, ReportVersion, UploadedDocument, User)
from services.auth_service import require_roles
from services.customer_portal_service import (advisor_context, complete_document_tasks,
    backfill_customer_account_links, customer_from_session, customer_owns_report, ensure_customer_account, ensure_document_tasks,
    generate_login_token, normalize_customer_phone, portal_completeness, reports_for_customer,
    require_customer, send_customer_message)
from services.document_parse_service import classify_document, run_parse_task
from services.event_service import track_event
from services.pilot_service import set_pilot_stage
from services.report_access_service import (
    build_bank_product_detail_context,
    build_report_access_context,
)
from services.report_service import generate_full_report, parse_customer_report, parse_report
from services.settings_service import get_setting
from services.customer_auth_service import (
    CUSTOMER_REMEMBER_COOKIE, authenticate_customer, create_customer_session,
    normalize_login_phone, revoke_customer_session, set_customer_password,
)
from services.audit_service import write_audit_log
from utils.rate_limiter import allow_rate_action

router=APIRouter();templates=Jinja2Templates(directory=str(BASE_DIR/"templates"))
UPLOAD_DIR=BASE_DIR/"data"/"uploads"
ALLOWED={".pdf",".doc",".docx",".xls",".xlsx",".png",".jpg",".jpeg"}
BACKEND=("admin","super_admin","city_manager","sales_manager","sales","consultant_manager","consultant","viewer")
WRITE=("admin","super_admin","city_manager","sales_manager","sales","consultant_manager","consultant")
CLIENT_PROJECT_STATUS={"draft":"服务准备中","preparing":"资料准备中","submitted":"已提交申请",
 "bank_review":"金融机构审核中","supplement_required":"需要补充资料","approved":"已获得批复",
 "rejected":"暂未通过，正在优化方案","disbursed":"已放款","cancelled":"服务已取消","archived":"已归档"}

def _lead(db,id):
    x=db.get(Lead,id)
    if not x:raise HTTPException(404,"线索不存在")
    return x
def _customer(db,id):
    x=db.get(CustomerAccount,id)
    if not x:raise HTTPException(404,"客户门户不存在")
    return x
def _customer_access(db,user,customer):
    lead=_lead(db,customer.lead_id);scope=get_access_scope(db,user)
    if scope.can_view_all:return lead
    if scope.role=="sales" and lead.owner_user_id!=user.id:raise HTTPException(403,"无权查看该客户")
    if scope.role=="consultant":
        case=db.query(ConsultingCase).filter(ConsultingCase.lead_id==lead.id,
            or_(ConsultingCase.consultant_user_id==user.id,ConsultingCase.consultant_id==user.id)).first()
        if not case:raise HTTPException(403,"无权查看该客户")
    elif lead.owner_org_id not in scope.allowed_org_ids:raise HTTPException(403,"无权查看该客户")
    return lead
def _latest_product(orders):
    paid=[x for x in orders if x.status=="paid"]
    return max((x.product_code for x in paid),key=lambda x:PRODUCT_RANK.get(x,0),default="未购买")
def _capital_grade(score):
    value=float(score or 0)
    return 'A' if value>=80 else 'B+' if value>=70 else 'B' if value>=60 else 'C' if value>=50 else 'D'
def _client_context(db,customer):
    lead=db.get(Lead,customer.lead_id) if customer.lead_id else None
    orders=db.query(Order).filter(Order.customer_id==customer.id).order_by(Order.created_at.desc()).all()
    project=db.query(FinancingProject).filter(FinancingProject.customer_id==customer.id).order_by(FinancingProject.id.desc()).first()
    report=db.query(Report).filter(Report.customer_id==customer.id).order_by(Report.created_at.desc()).first()
    completeness=portal_completeness(db,customer)
    advisor=advisor_context(db,lead.id) if lead else {
        "name":"尚未分配顾问","organization":"沪上银 · 企业资本健康管理中心",
        "phone":"","wechat":"","show_contact":False,
    }
    return {"customer":customer,"lead":lead,"assessment":lead.assessment if lead else None,"orders":orders,
        "product":_latest_product(orders),"project":project,"report_item":report,"completeness":completeness,
        "advisor":advisor,"project_status":CLIENT_PROJECT_STATUS,
        "report_count":db.query(Report).filter(Report.customer_id==customer.id).count(),
        "order_count":db.query(Order).filter(Order.customer_id==customer.id).count(),
        "booking_count":db.query(AdvisorBooking).filter(AdvisorBooking.customer_id==customer.id).count(),
        "project_count":db.query(FinancingProject).filter(FinancingProject.customer_id==customer.id).count(),
        "unread_count":db.query(CustomerMessage).filter(CustomerMessage.customer_id==customer.id,
            CustomerMessage.status=='unread').count()}


def _customer_login_response(request: Request, db: Session, customer: CustomerAccount,
                             target: str = "/client/dashboard", remember_me: bool = False):
    request.session["customer_id"] = customer.id
    request.session["customer_authenticated"] = True
    request.session["customer_lead_id"] = customer.lead_id
    request.session.pop("pending_customer_id", None)
    request.session.pop("pending_assessment_id", None)
    response = RedirectResponse(target if target.startswith("/client/") else "/client/dashboard", 303)
    token = create_customer_session(db, customer, remember_me)
    response.set_cookie(
        CUSTOMER_REMEMBER_COOKIE, token,
        max_age=30 * 24 * 60 * 60 if remember_me else 12 * 60 * 60,
        httponly=True, secure=settings.app_env == "production", samesite="lax", path="/",
    )
    return response


@router.get("/client/login", response_class=HTMLResponse)
def customer_login_page(request: Request, next: str = "/client/dashboard", password_reset: int = 0,
                        phone: str = "",
                        db: Session = Depends(get_db)):
    if customer_from_session(request, db):
        return RedirectResponse("/client/dashboard", 303)
    return templates.TemplateResponse(request=request, name="client_login.html", context={
        "error": "", "phone": normalize_login_phone(phone) if phone else "", "password_reset": bool(password_reset),
        "next_url": next if next.startswith("/client/") else "/client/dashboard",
    })


@router.post("/client/login", response_class=HTMLResponse)
def customer_login_submit(
    request: Request,
    phone: str = Form(...),
    password: str = Form(...),
    remember_me: str = Form(""),
    next_url: str = Form("/client/dashboard"),
    db: Session = Depends(get_db),
):
    ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (
        request.client.host if request.client else "unknown"
    )
    if not allow_rate_action(f"customer-login:{ip}:{normalize_login_phone(phone)}", 10, 300):
        return templates.TemplateResponse(request=request, name="client_login.html", context={
            "error": "登录尝试过于频繁，请稍后再试", "phone": normalize_login_phone(phone),
            "password_reset": False,
            "next_url": next_url if next_url.startswith("/client/") else "/client/dashboard",
        }, status_code=429)
    customer = authenticate_customer(db, phone, password)
    if not customer:
        return templates.TemplateResponse(request=request, name="client_login.html", context={
            "error": "手机号或密码不正确", "phone": phone,
            "password_reset": False,
            "next_url": next_url if next_url.startswith("/client/") else "/client/dashboard",
        }, status_code=400)
    backfill_customer_account_links(db, customer)
    track_event(db, "customer_password_login", customer.assessment_id, customer.lead_id,
                {"customer_id": customer.id, "login_method": "password"})
    return _customer_login_response(request, db, customer, next_url, bool(remember_me))


def _registration_phone(value: str) -> str:
    normalized = normalize_login_phone(value)
    if normalized.startswith("+86"):
        normalized = normalized[3:]
    return normalized


def _registration_context(*, phone: str = "", next_url: str = "/client/dashboard",
                          error: str = "", values: dict | None = None,
                          existing_account: bool = False, historical_account: bool = False) -> dict:
    return {
        "phone": phone,
        "next_url": next_url if next_url.startswith("/client/") else "/client/dashboard",
        "error": error,
        "values": values or {},
        "existing_account": existing_account,
        "historical_account": historical_account,
    }


@router.get("/client/register", response_class=HTMLResponse)
def customer_register_page(request: Request, phone: str = "", next: str = "/client/dashboard",
                           db: Session = Depends(get_db)):
    if customer_from_session(request, db):
        return RedirectResponse("/client/dashboard", 303)
    normalized = _registration_phone(phone)
    return templates.TemplateResponse(request=request, name="client_register.html", context=_registration_context(
        phone=normalized, next_url=next,
    ))


@router.post("/client/register", response_class=HTMLResponse)
def customer_register_submit(
    request: Request,
    phone: str = Form(...),
    contact_name: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    company_name: str = Form(""),
    wechat_id: str = Form(""),
    city: str = Form(""),
    agree_legal: str = Form(""),
    registration_method: str = Form("password"),
    next_url: str = Form("/client/dashboard"),
    db: Session = Depends(get_db),
):
    normalized = _registration_phone(phone)
    values = {
        "contact_name": contact_name.strip(), "company_name": company_name.strip(),
        "wechat_id": wechat_id.strip(), "city": city.strip(),
    }
    error = ""
    if not normalized:
        error = "请输入手机号"
    elif len(normalized) != 11 or not normalized.isdigit() or not normalized.startswith("1"):
        error = "请输入正确的11位手机号"
    elif not contact_name.strip():
        error = "请输入联系人姓名"
    elif len(password) < 8:
        error = "登录密码至少需要8位"
    elif password != confirm_password:
        error = "两次输入的密码不一致"
    elif agree_legal != "1":
        error = "请先阅读并同意用户协议和隐私政策"
    elif registration_method != "password":
        error = "当前仅支持手机号和密码注册"
    ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (
        request.client.host if request.client else "unknown"
    )
    if not error and not allow_rate_action(f"customer-register:{ip}:{normalized}", 5, 300):
        error = "注册操作过于频繁，请5分钟后再试"
    if error:
        return templates.TemplateResponse(request=request, name="client_register.html", context=_registration_context(
            phone=normalized, next_url=next_url, error=error, values=values,
        ), status_code=429 if "频繁" in error else 400)

    existing = db.query(CustomerAccount).filter(CustomerAccount.login_phone == normalized).first()
    if not existing:
        # 兼容历史数据中带 +86、空格或短横线的手机号，避免重复创建客户身份。
        for candidate in db.query(CustomerAccount).filter(CustomerAccount.deleted_at.is_(None)).all():
            if _registration_phone(candidate.login_phone or candidate.phone) == normalized:
                existing = candidate
                break
    if existing and (not existing.is_active or existing.status == "disabled"):
        return templates.TemplateResponse(request=request, name="client_register.html", context=_registration_context(
            phone=normalized, next_url=next_url, values=values,
            error="该账号已停用，请联系服务人员处理。",
        ), status_code=403)
    if existing and existing.password_hash:
        return templates.TemplateResponse(request=request, name="client_register.html", context=_registration_context(
            phone=normalized, next_url=next_url, values=values, existing_account=True,
            error="该手机号已注册，请直接登录。",
        ), status_code=409)
    if existing and not existing.password_hash:
        pending_id = request.session.get("pending_customer_id")
        if not pending_id or int(pending_id) != existing.id:
            return templates.TemplateResponse(request=request, name="client_register.html", context=_registration_context(
                phone=normalized, next_url=next_url, values=values, historical_account=True,
            ), status_code=409)
        customer = existing
        customer.name = contact_name.strip() or customer.name
        customer.contact_name = customer.name
        customer.wechat_id = wechat_id.strip() or customer.wechat_id
        customer.city = city.strip() or customer.city
        customer.company_name = company_name.strip() or customer.company_name
    else:
        customer = CustomerAccount(
            lead_id=None, assessment_id=None, company_name=company_name.strip(),
            name=contact_name.strip(), contact_name=contact_name.strip(),
            phone=normalized, login_phone=normalized, wechat_id=wechat_id.strip(), city=city.strip(),
            status="active", is_active=True, client_login_method="password",
            registration_method=registration_method, registration_source="self_registration",
        )
        db.add(customer)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return templates.TemplateResponse(request=request, name="client_register.html",
                context=_registration_context(
                    phone=normalized, next_url=next_url, values=values, existing_account=True,
                    error="该手机号已注册，请直接登录。",
                ), status_code=409)

    now = datetime.now()
    set_customer_password(db, customer, password)
    customer.status = "active"
    customer.is_active = True
    customer.last_login_at = now
    customer.activated_at = customer.activated_at or now
    customer.terms_accepted_at = now
    customer.privacy_accepted_at = now
    track_event(db, "customer_registered", customer.assessment_id, customer.lead_id, {
        "customer_id": customer.id,
        "registration_source": customer.registration_source,
        "registration_method": customer.registration_method,
    }, commit=False)
    write_audit_log(
        db, "customer_registered", "customer_account", customer.id,
        customer_id=customer.id, actor_type="customer", request=request,
        after={"registration_source": customer.registration_source, "legal_accepted": True},
    )
    db.commit()
    return _customer_login_response(request, db, customer, next_url, True)


@router.get("/client/setup-account", response_class=HTMLResponse)
def customer_setup_page(request: Request, db: Session = Depends(get_db)):
    customer = customer_from_session(request, db)
    if not customer:
        pending_id = request.session.get("pending_customer_id")
        customer = db.get(CustomerAccount, int(pending_id)) if pending_id else None
    if not customer:
        return RedirectResponse("/client/login", 303)
    if not customer.is_active or customer.status == "disabled":
        raise HTTPException(403, "客户账号已停用")
    if customer.password_hash:
        return RedirectResponse("/client/account" if request.session.get("customer_authenticated") else "/client/login", 303)
    return templates.TemplateResponse(request=request, name="client_setup_account.html", context={
        "customer": customer, "error": "",
    })


@router.post("/client/setup-account", response_class=HTMLResponse)
def customer_setup_submit(
    request: Request,
    name: str = Form(""),
    password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db),
):
    pending_id = request.session.get("pending_customer_id") or request.session.get("customer_id")
    customer = db.get(CustomerAccount, int(pending_id)) if pending_id else None
    if not customer:
        return RedirectResponse("/client/login", 303)
    error = ""
    if len(password) < 8:
        error = "密码至少需要8位"
    elif password != confirm_password:
        error = "两次输入的密码不一致"
    elif customer.password_hash:
        error = "该手机号已有账号，请直接登录"
    if error:
        return templates.TemplateResponse(request=request, name="client_setup_account.html", context={
            "customer": customer, "error": error,
        }, status_code=400)
    customer.name = name.strip() or customer.name or customer.contact_name
    set_customer_password(db, customer, password)
    backfill_customer_account_links(db, customer)
    db.commit()
    track_event(db, "customer_account_password_set", customer.assessment_id, customer.lead_id,
                {"customer_id": customer.id})
    return _customer_login_response(request, db, customer, "/client/reports", True)


def _valid_customer_token(db: Session, token: str, token_type: str) -> CustomerAccessToken | None:
    return db.query(CustomerAccessToken).filter(
        CustomerAccessToken.token == token,
        CustomerAccessToken.token_type == token_type,
        CustomerAccessToken.is_active.is_(True),
        CustomerAccessToken.expired_at > datetime.now(),
    ).first()


@router.get("/client/activate", response_class=HTMLResponse)
def customer_activate_page(request: Request, phone: str = ""):
    return templates.TemplateResponse(request=request, name="client_activate.html", context={
        "phone": phone, "submitted": False, "development_link": "",
    })


@router.post("/client/activate", response_class=HTMLResponse)
def customer_activate_request(request: Request, phone: str = Form(...), db: Session = Depends(get_db)):
    normalized = normalize_login_phone(phone)
    customer = db.query(CustomerAccount).filter(
        CustomerAccount.login_phone == normalized,
        CustomerAccount.is_active.is_(True),
    ).first()
    development_link = ""
    if customer and not customer.password_hash and customer.status != "disabled":
        customer.status = "pending_activation"
        token = generate_login_token(db, customer, token_type="account_activation", days=1)
        activation_path = f"/client/activate/{token.token}"
        from services.notification_service import safe_create_notification
        safe_create_notification(db, "customer_account_activation", {
            "activation_url": f"{str(request.base_url).rstrip('/')}{activation_path}",
        }, recipient_customer_id=customer.id, related_type="customer_access_token", related_id=token.id)
        track_event(db, "customer_account_activation_requested", customer.assessment_id, customer.lead_id,
                    {"customer_id": customer.id}, commit=False)
        db.commit()
        if settings.app_env != "production":
            development_link = activation_path
    return templates.TemplateResponse(request=request, name="client_activate.html", context={
        "phone": phone, "submitted": True, "development_link": development_link,
    })


@router.get("/client/activate/{token}", response_class=HTMLResponse)
def customer_activation_password_page(request: Request, token: str, db: Session = Depends(get_db)):
    item = _valid_customer_token(db, token, "account_activation")
    if not item:
        raise HTTPException(401, "账号激活链接不存在或已过期")
    customer = _customer(db, item.customer_id)
    if not customer.is_active or customer.status == "disabled":
        raise HTTPException(403, "客户账号已停用")
    if customer.password_hash:
        return RedirectResponse("/client/login", 303)
    return templates.TemplateResponse(request=request, name="client_activate_password.html", context={
        "token": token, "phone": customer.login_phone, "error": "",
    })


@router.post("/client/activate/{token}", response_class=HTMLResponse)
def customer_activation_password_submit(request: Request, token: str, password: str = Form(...),
                                        confirm_password: str = Form(...), db: Session = Depends(get_db)):
    item = _valid_customer_token(db, token, "account_activation")
    if not item:
        raise HTTPException(401, "账号激活链接不存在或已过期")
    customer = _customer(db, item.customer_id)
    error = ""
    if len(password) < 8:
        error = "密码至少需要8位"
    elif password != confirm_password:
        error = "两次输入的密码不一致"
    elif not customer.is_active or customer.status == "disabled":
        error = "客户账号已停用"
    if error:
        return templates.TemplateResponse(request=request, name="client_activate_password.html", context={
            "token": token, "phone": customer.login_phone, "error": error,
        }, status_code=400)
    set_customer_password(db, customer, password)
    item.is_active = False
    item.used_at = datetime.now()
    track_event(db, "customer_account_activated", customer.assessment_id, customer.lead_id,
                {"customer_id": customer.id}, commit=False)
    db.commit()
    return _customer_login_response(request, db, customer, "/client/reports", True)


@router.get("/client/forgot-password", response_class=HTMLResponse)
def customer_forgot_page(request: Request):
    return templates.TemplateResponse(request=request, name="client_forgot_password.html", context={"submitted": False})


@router.post("/client/forgot-password", response_class=HTMLResponse)
def customer_forgot_submit(request: Request, phone: str = Form(...), db: Session = Depends(get_db)):
    normalized = normalize_login_phone(phone)
    customer = db.query(CustomerAccount).filter(
        CustomerAccount.login_phone == normalized,
        CustomerAccount.is_active.is_(True),
    ).first()
    if customer:
        token = generate_login_token(db, customer, token_type="password_reset", days=1)
        from services.notification_service import safe_create_notification
        safe_create_notification(db, "customer_password_reset", {
            "reset_url": f"{str(request.base_url).rstrip('/')}/client/reset-password/{token.token}",
        }, recipient_customer_id=customer.id, related_type="customer_access_token", related_id=token.id)
        db.commit()
    return templates.TemplateResponse(request=request, name="client_forgot_password.html", context={"submitted": True})


@router.get("/client/reset-password/{token}", response_class=HTMLResponse)
def customer_reset_page(request: Request, token: str, db: Session = Depends(get_db)):
    item = db.query(CustomerAccessToken).filter(
        CustomerAccessToken.token == token,
        CustomerAccessToken.token_type == "password_reset",
        CustomerAccessToken.is_active.is_(True),
        CustomerAccessToken.expired_at > datetime.now(),
    ).first()
    if not item:
        raise HTTPException(401, "密码重置链接不存在或已过期")
    return templates.TemplateResponse(request=request, name="client_reset_password.html", context={"token": token, "error": ""})


@router.post("/client/reset-password/{token}", response_class=HTMLResponse)
def customer_reset_submit(request: Request, token: str, password: str = Form(...),
                          confirm_password: str = Form(...), db: Session = Depends(get_db)):
    item = db.query(CustomerAccessToken).filter(
        CustomerAccessToken.token == token,
        CustomerAccessToken.token_type == "password_reset",
        CustomerAccessToken.is_active.is_(True),
        CustomerAccessToken.expired_at > datetime.now(),
    ).first()
    if not item:
        raise HTTPException(401, "密码重置链接不存在或已过期")
    if len(password) < 8 or password != confirm_password:
        error = "密码至少需要8位" if len(password) < 8 else "两次输入的密码不一致"
        return templates.TemplateResponse(request=request, name="client_reset_password.html",
            context={"token": token, "error": error}, status_code=400)
    customer = _customer(db, item.customer_id)
    set_customer_password(db, customer, password)
    item.is_active = False
    item.used_at = datetime.now()
    db.commit()
    return RedirectResponse("/client/login?password_reset=1", 303)

@router.get('/client/login-token/{token}')
def client_token_login(request:Request,token:str,next:str="/client/reports",db:Session=Depends(get_db)):
    item=db.query(CustomerAccessToken).filter(CustomerAccessToken.token==token,
        CustomerAccessToken.token_type.in_(["portal_login", "report_access"]),
        CustomerAccessToken.is_active.is_(True)).first()
    if not item or item.expired_at<datetime.now():raise HTTPException(401,"客户登录链接不存在或已过期")
    customer=_customer(db,item.customer_id)
    if not customer.is_active or customer.status not in {"active", "pending_activation"}:
        raise HTTPException(403, "客户账号已停用")
    if not customer.is_active:raise HTTPException(403,"客户门户已停用")
    request.session['customer_id']=customer.id;request.session['customer_authenticated']=True;request.session['customer_lead_id']=customer.lead_id
    request.session['token_login_notice']=True
    item.used_at=datetime.now();customer.last_login_at=datetime.now()
    track_event(db,'customer_logged_in',customer.assessment_id,customer.lead_id,{"customer_id":customer.id},commit=False)
    target = next if next.startswith("/client/") else "/client/reports"
    db.commit();return RedirectResponse(target,303)

@router.get('/my-reports',response_class=HTMLResponse)
def my_reports_entry(request:Request,next:str="/client/reports",db:Session=Depends(get_db)):
    customer=customer_from_session(request,db)
    if customer:return RedirectResponse('/client/reports',303)
    return templates.TemplateResponse(request=request,name='client_report_access.html',context={
        'next_url':next if next.startswith('/') else '/client/reports','submitted':False,
    })

@router.post('/my-reports/access',response_class=HTMLResponse)
def request_report_access(request:Request,phone:str=Form(...),next_url:str=Form('/client/reports'),db:Session=Depends(get_db)):
    normalized=normalize_customer_phone(phone)
    candidates=db.query(CustomerAccount).filter(CustomerAccount.is_active.is_(True)).all()
    customer=next((item for item in candidates if normalize_customer_phone(item.login_phone or item.phone)==normalized),None)
    if customer and normalized:
        token=generate_login_token(db,customer,days=7)
        access_path=f"/client/login-token/{token.token}?next=/client/reports"
        from services.notification_service import safe_create_notification
        safe_create_notification(db,'customer_portal_access_link',{
            'access_url':f"{str(request.base_url).rstrip('/')}{access_path}",
        },recipient_customer_id=customer.id,related_type='customer_access_token',related_id=token.id)
        db.commit()
    return templates.TemplateResponse(request=request,name='client_report_access.html',context={
        'next_url':next_url if next_url.startswith('/') else '/client/reports','submitted':True,
    })

@router.get('/client/logout')
def client_logout(request:Request,db:Session=Depends(get_db)):
    revoke_customer_session(request,db)
    for key in ('customer_id','customer_authenticated','customer_lead_id','token_login_notice',
                'pending_customer_id','pending_assessment_id','assessment_id','report_public_token'):
        request.session.pop(key,None)
    request.session.pop('assessment_access_ids', None)
    response=RedirectResponse('/client/login',303);response.delete_cookie(CUSTOMER_REMEMBER_COOKIE,path='/')
    return response

@router.get('/client/dashboard',response_class=HTMLResponse)
def client_dashboard(request:Request,db:Session=Depends(get_db),customer:CustomerAccount=Depends(require_customer)):
    from services.legal_service import missing_acceptances
    legal_pending=missing_acceptances(db,customer,['user_agreement','privacy_policy'])
    if settings.app_env=='production' and legal_pending:return RedirectResponse('/client/legal',303)
    ensure_document_tasks(db,customer);ctx=_client_context(db,customer)
    ctx.update({"legal_pending":legal_pending,"tasks":db.query(CustomerTask).filter(CustomerTask.customer_id==customer.id,CustomerTask.status=='pending').order_by(CustomerTask.due_time).limit(8).all(),
        "messages":db.query(CustomerMessage).filter(CustomerMessage.customer_id==customer.id).order_by(CustomerMessage.created_at.desc()).limit(5).all(),
        "confirmations":db.query(CustomerConfirmation).filter(CustomerConfirmation.customer_id==customer.id,CustomerConfirmation.status=='pending').all()})
    track_event(db,'client_dashboard_viewed',customer.assessment_id,customer.lead_id,{"customer_id":customer.id})
    return templates.TemplateResponse(request=request,name='client_dashboard.html',context=ctx)

@router.get('/client/reports',response_class=HTMLResponse)
def client_reports(request:Request,db:Session=Depends(get_db),customer:CustomerAccount=Depends(require_customer)):
    report_items=reports_for_customer(db,customer)
    rows=[]
    for report in report_items:
        assessment=report.assessment
        orders=db.query(Order).filter(Order.assessment_id==assessment.id,Order.status=='paid').all()
        highest=max((item.product_code for item in orders),key=lambda code:PRODUCT_RANK.get(code,0),default='free_assessment')
        if PRODUCT_RANK.get(highest,0)>=PRODUCT_RANK.get('1999_structure_plan',0):
            report_name='企业融资结构优化方案';level='融资结构优化方案'
        elif highest=='980_capital_health_report':
            report_name='企业资本健康体检报告';level='完整体检报告'
        elif highest=='699_bank_match':
            report_name='银行产品专项匹配报告';level='历史专项报告'
        elif highest=='299_report':
            report_name='企业资本健康简版报告';level='历史简版报告'
        else:
            report_name='企业资本健康摘要';level='免费摘要'
        review_label='已完成'
        if PRODUCT_RANK.get(highest,0)>=PRODUCT_RANK.get('1999_structure_plan',0) and report.review_status in {'pending_review','draft'}:review_label='待复核'
        elif report.review_status=='rejected':review_label='已驳回'
        expired=datetime.now()>report.created_at+timedelta(days=int(get_setting(db,'capital_health_report_validity_days','90')))
        if expired:review_label='已过有效期'
        rows.append({
            'report':report,'assessment':assessment,'report_name':report_name,'level_label':level,
            'review_label':review_label,'expired':expired,'highest_product':highest,
            'display_grade':_capital_grade(assessment.score),
            'version_count':max(1,db.query(ReportVersion).filter(ReportVersion.report_id==report.id).count()),
        })
    return templates.TemplateResponse(request=request,name='client_reports.html',context={'customer':customer,'report_rows':rows})

def _client_report(db,customer,report_id):
    report=db.get(Report,report_id)
    if not report or not customer_owns_report(db,customer,report):raise HTTPException(404,"报告不存在")
    db.commit()
    return report
@router.get('/client/reports/{report_id}/versions',response_class=HTMLResponse)
def client_report_versions(request:Request,report_id:int,db:Session=Depends(get_db),customer:CustomerAccount=Depends(require_customer)):
    report=_client_report(db,customer,report_id)
    ensure_capital_health_snapshot(db,report.assessment)
    versions=db.query(ReportVersion).filter(ReportVersion.report_id==report.id).order_by(ReportVersion.version_no.desc()).all()
    rows=[]
    for version in versions:
        try:content=json.loads(version.report_json or '{}')
        except (TypeError,ValueError):content={}
        meta=content.get('report_meta') or {}
        approved=version.access_level=='free' or meta.get('review_status')=='approved' or (version.id==report.current_version_id and report.review_status=='approved')
        if not approved:continue
        rows.append({'version':version,'meta':meta,'is_current':version.id==report.current_version_id})
    return templates.TemplateResponse(request=request,name='client_report_versions.html',context={'customer':customer,'report_item':report,'versions':rows})
@router.get('/client/reports/{report_id}',response_class=HTMLResponse)
def client_report(request:Request,report_id:int,db:Session=Depends(get_db),customer:CustomerAccount=Depends(require_customer)):
    report=_client_report(db,customer,report_id)
    paid_orders=db.query(Order).filter(Order.assessment_id==report.assessment_id,Order.status=='paid').all()
    entitlements=report_entitlements(db,report.assessment_id)
    if not paid_orders:
        health_report=ensure_capital_health_snapshot(db,report.assessment)
        return templates.TemplateResponse(request=request,name='result_free.html',context={
            'customer':customer,'assessment':report.assessment,'result':{},'health_report':health_report,
            'variant':'portal','conversion_copy':{},'client_view':True,
        })
    if entitlements['structure_unlocked'] and report.review_status!='approved':
        version=db.get(ReportVersion,report.current_version_id) if report.current_version_id else None
        return templates.TemplateResponse(request=request,name='client_report_pending.html',context={
            'customer':customer,'report_item':report,
            'submitted_at':version.created_at if version else report.created_at,
        })
    generate_full_report(db, report.assessment)
    full=parse_customer_report(report);health_report=ensure_capital_health_snapshot(db,report.assessment);track_event(db,'client_report_viewed',report.assessment_id,report.assessment.lead.id if report.assessment.lead else customer.lead_id,{'report_id':report.id});set_pilot_stage(db,report.assessment.lead,'report_viewed',commit=True)
    access_context=build_report_access_context(db,report.assessment,full,base_path=f'/client/reports/{report.id}')
    return templates.TemplateResponse(request=request,name='client_report.html',context={'customer':customer,'assessment':report.assessment,'report':full,'health_report':health_report,'print_mode':False,**access_context})
@router.get('/client/reports/{report_id}/print',response_class=HTMLResponse)
def client_report_print(request:Request,report_id:int,db:Session=Depends(get_db),customer:CustomerAccount=Depends(require_customer)):
    report=_client_report(db,customer,report_id)
    if report.review_status!='approved' or not db.query(Order).filter(Order.assessment_id==report.assessment_id,Order.status=='paid').first():raise HTTPException(403,"报告尚不可打印")
    generate_full_report(db, report.assessment)
    full=parse_customer_report(report);health_report=ensure_capital_health_snapshot(db,report.assessment);access_context=build_report_access_context(db,report.assessment,full,base_path=f'/client/reports/{report.id}')
    return templates.TemplateResponse(request=request,name='client_report.html',context={'customer':customer,'assessment':report.assessment,'report':full,'health_report':health_report,'print_mode':True,**access_context})

@router.get('/client/reports/{report_id}/bank-products/{product_id}',response_class=HTMLResponse)
def client_bank_product_detail(request:Request,report_id:int,product_id:int,db:Session=Depends(get_db),customer:CustomerAccount=Depends(require_customer)):
    report=_client_report(db,customer,report_id)
    paid=db.query(Order).filter(Order.assessment_id==report.assessment_id,Order.status=='paid').first()
    if not paid:return templates.TemplateResponse(request=request,name='client_notice.html',context={'customer':customer,'title':'报告尚未解锁','message':'该报告尚未解锁。'})
    if report.review_status!='approved':return templates.TemplateResponse(request=request,name='client_notice.html',context={'customer':customer,'title':'报告审核中','message':'报告正在生成/审核中，请稍后查看。'})
    generate_full_report(db, report.assessment)
    full=parse_customer_report(report)
    detail_context=build_bank_product_detail_context(db,report.assessment,full,product_id)
    if detail_context is None:raise HTTPException(404,'银行产品不存在')
    return templates.TemplateResponse(request=request,name='report_bank_product_detail.html',context={'customer':customer,'assessment':report.assessment,'report':full,'back_url':f'/client/reports/{report.id}','checkout_base':f'/checkout/{customer.assessment_id}',**detail_context})

@router.get('/client/documents',response_class=HTMLResponse)
def client_documents(request:Request,db:Session=Depends(get_db),customer:CustomerAccount=Depends(require_customer)):
    ensure_document_tasks(db,customer);ctx=_client_context(db,customer);ctx['documents']=db.query(UploadedDocument).filter(UploadedDocument.customer_id==customer.id,UploadedDocument.deleted_at.is_(None)).order_by(UploadedDocument.created_at.desc()).all()
    ctx['max_mb']=int(get_setting(db,'upload_max_mb',str(settings.upload_max_mb)))
    return templates.TemplateResponse(request=request,name='client_documents.html',context=ctx)

@router.post('/client/documents/upload')
async def client_document_upload(request:Request,document_category:str=Form('其他资料'),note:str=Form(''),files:list[UploadFile]=File(...),
    db:Session=Depends(get_db),customer:CustomerAccount=Depends(require_customer)):
    if not customer.lead_id or not customer.assessment_id:
        raise HTTPException(400,'请先完成企业资本健康测评，再上传企业资料')
    from services.legal_service import missing_acceptances
    if settings.app_env=='production' and missing_acceptances(db,customer,['document_submission_authorization']):raise HTTPException(403,'上传资料前请先确认资料提交授权')
    from utils.file_security import enforce_lead_total,validate_upload_metadata
    from services.audit_service import write_audit_log
    root=UPLOAD_DIR/str(customer.lead_id);root.mkdir(parents=True,exist_ok=True);max_size=int(get_setting(db,'upload_max_mb',str(settings.upload_max_mb)))*1024*1024
    for upload in files:
        try:original,ext=validate_upload_metadata(upload)
        except HTTPException as exc:track_event(db,'file_security_rejected',customer.assessment_id,customer.lead_id,{'reason':str(exc.detail)});raise
        data=await upload.read(max_size+1)
        if not data:raise HTTPException(400,'文件内容为空')
        if len(data)>max_size:raise HTTPException(400,'文件超过上传大小限制')
        enforce_lead_total(db,customer.lead_id,len(data),int(get_setting(db,'max_lead_upload_mb',str(settings.max_lead_upload_mb))))
        saved=root/f'{uuid.uuid4().hex}{ext}';saved.write_bytes(data)
        doc=UploadedDocument(lead_id=customer.lead_id,assessment_id=customer.assessment_id,
            file_name=original,file_path=str(saved.relative_to(BASE_DIR)).replace('\\','/'),
            file_type=ext.lstrip('.'),document_category=classify_document(upload.filename or '',document_category),
            uploaded_by=None,customer_id=customer.id,uploaded_source='customer',file_size=len(data),
            file_hash=hashlib.sha256(data).hexdigest(),note=note.strip())
        db.add(doc);db.flush();complete_document_tasks(db,customer,doc)
        from services.notification_service import notify_document_uploaded, safe_create_notification
        lead=db.get(Lead,customer.lead_id);case=db.query(ConsultingCase).filter(ConsultingCase.lead_id==lead.id).order_by(ConsultingCase.id.desc()).first()
        recipients={lead.owner_user_id,(case.consultant_user_id or case.consultant_id) if case else None}
        for user_id in recipients:
            if user_id:safe_create_notification(db,'document_uploaded_consultant',{'company_name':customer.company_name,'document_name':doc.file_name},recipient_user_id=user_id,related_type='uploaded_document',related_id=doc.id)
        notify_document_uploaded(db, lead, doc, commit=False)
        write_audit_log(db,'customer_document_uploaded','uploaded_document',doc.id,customer_id=customer.id,actor_type='customer',after={'file_name':doc.file_name,'size':doc.file_size},request=request,risk_level='medium')
        track_event(db,'client_document_uploaded',customer.assessment_id,customer.lead_id,{'document_id':doc.id,'customer_id':customer.id},commit=False);set_pilot_stage(db,db.get(Lead,customer.lead_id),'documents_uploaded',commit=False);db.commit();run_parse_task(db,doc)
    return RedirectResponse('/client/documents',303)

@router.get('/client/tasks',response_class=HTMLResponse)
def client_tasks(request:Request,db:Session=Depends(get_db),customer:CustomerAccount=Depends(require_customer)):
    ensure_document_tasks(db,customer);items=db.query(CustomerTask).filter(CustomerTask.customer_id==customer.id).order_by(CustomerTask.status,CustomerTask.due_time).all()
    return templates.TemplateResponse(request=request,name='client_tasks.html',context={'customer':customer,'tasks':items})
@router.post('/client/tasks/{task_id}/complete')
def client_task_complete(task_id:int,db:Session=Depends(get_db),customer:CustomerAccount=Depends(require_customer)):
    task=db.get(CustomerTask,task_id)
    if not task or task.customer_id!=customer.id:raise HTTPException(404,'任务不存在')
    task.status='done';task.completed_at=task.updated_at=datetime.now();track_event(db,'client_task_completed',customer.assessment_id,customer.lead_id,{'task_id':task.id},commit=False);db.commit();return RedirectResponse('/client/tasks',303)

@router.get('/client/projects',response_class=HTMLResponse)
def client_projects(request:Request,db:Session=Depends(get_db),customer:CustomerAccount=Depends(require_customer)):
    items=db.query(FinancingProject).filter(FinancingProject.customer_id==customer.id).order_by(FinancingProject.updated_at.desc()).all()
    return templates.TemplateResponse(request=request,name='client_projects.html',context={'customer':customer,'projects':items,'status_map':CLIENT_PROJECT_STATUS})
@router.get('/client/projects/{project_id}',response_class=HTMLResponse)
def client_project(request:Request,project_id:int,db:Session=Depends(get_db),customer:CustomerAccount=Depends(require_customer)):
    project=db.get(FinancingProject,project_id)
    if not project or project.customer_id!=customer.id:raise HTTPException(404,'项目不存在')
    apps=db.query(FundingApplication).filter(FundingApplication.project_id==project.id).all();timeline=db.query(ProjectTimelineEvent).filter(ProjectTimelineEvent.project_id==project.id).order_by(ProjectTimelineEvent.created_at.desc()).limit(12).all()
    track_event(db,'client_project_viewed',customer.assessment_id,customer.lead_id,{'project_id':project.id})
    return templates.TemplateResponse(request=request,name='client_project_detail.html',context={'customer':customer,'project':project,'applications':apps,'timeline':timeline,'status_map':CLIENT_PROJECT_STATUS,'advisor':advisor_context(db,customer.lead_id)})

@router.get('/client/messages',response_class=HTMLResponse)
def client_messages(request:Request,db:Session=Depends(get_db),customer:CustomerAccount=Depends(require_customer)):
    items=db.query(CustomerMessage).filter(CustomerMessage.customer_id==customer.id,CustomerMessage.status!='archived').order_by(CustomerMessage.created_at.desc()).all()
    jobs=db.query(NotificationJob).filter(NotificationJob.recipient_customer_id==customer.id,NotificationJob.channel=='in_app').order_by(NotificationJob.created_at.desc()).limit(100).all()
    notices=[]
    for job in jobs:
        try:payload=json.loads(job.payload_json or '{}')
        except (TypeError,ValueError):payload={}
        action_url=payload.get('action_url') or (f'/client/reports/{job.related_id}' if job.related_type=='report' and job.related_id else '')
        notices.append({'title':job.title,'content':job.content,'created_at':job.created_at,'action_url':action_url})
    return templates.TemplateResponse(request=request,name='client_messages.html',context={'customer':customer,'messages':items,'notices':notices})
@router.get('/client/messages/{message_id}',response_class=HTMLResponse)
def client_message(request:Request,message_id:int,db:Session=Depends(get_db),customer:CustomerAccount=Depends(require_customer)):
    item=db.get(CustomerMessage,message_id)
    if not item or item.customer_id!=customer.id:raise HTTPException(404,'消息不存在')
    if item.status=='unread':item.status='read';item.read_at=datetime.now();track_event(db,'customer_message_read',customer.assessment_id,customer.lead_id,{'message_id':item.id},commit=False);db.commit()
    return templates.TemplateResponse(request=request,name='client_message_detail.html',context={'customer':customer,'message':item})

@router.get('/client/confirmations',response_class=HTMLResponse)
def client_confirmations(request:Request,db:Session=Depends(get_db),customer:CustomerAccount=Depends(require_customer)):
    items=db.query(CustomerConfirmation).filter(CustomerConfirmation.customer_id==customer.id).order_by(CustomerConfirmation.created_at.desc()).all();return templates.TemplateResponse(request=request,name='client_confirmations.html',context={'customer':customer,'confirmations':items})
def _confirmation_action(request,db,customer,id,status):
    item=db.get(CustomerConfirmation,id)
    if not item or item.customer_id!=customer.id:raise HTTPException(404,'确认事项不存在')
    item.status=status;item.confirmed_at=datetime.now();item.ip_address=request.client.host if request.client else '';item.user_agent=request.headers.get('user-agent','')[:500]
    track_event(db,f'customer_confirmation_{status}',customer.assessment_id,customer.lead_id,{'confirmation_id':item.id},commit=False);db.commit();return RedirectResponse('/client/confirmations',303)
@router.post('/client/confirmations/{confirmation_id}/confirm')
def confirmation_confirm(request:Request,confirmation_id:int,db:Session=Depends(get_db),customer:CustomerAccount=Depends(require_customer)):return _confirmation_action(request,db,customer,confirmation_id,'confirmed')
@router.post('/client/confirmations/{confirmation_id}/reject')
def confirmation_reject(request:Request,confirmation_id:int,db:Session=Depends(get_db),customer:CustomerAccount=Depends(require_customer)):return _confirmation_action(request,db,customer,confirmation_id,'rejected')

@router.get('/client/orders',response_class=HTMLResponse)
def client_orders(request:Request,db:Session=Depends(get_db),customer:CustomerAccount=Depends(require_customer)):
    items=db.query(Order).filter(Order.customer_id==customer.id).order_by(Order.created_at.desc()).all();return templates.TemplateResponse(request=request,name='client_orders.html',context={'customer':customer,'orders':items})

@router.get('/client/advisor-bookings',response_class=HTMLResponse)
def client_advisor_bookings(request:Request,db:Session=Depends(get_db),customer:CustomerAccount=Depends(require_customer)):
    items=db.query(AdvisorBooking).filter(AdvisorBooking.customer_id==customer.id).order_by(AdvisorBooking.created_at.desc()).all()
    latest_report=db.query(Report).filter(Report.customer_id==customer.id).order_by(Report.created_at.desc()).first()
    return templates.TemplateResponse(request=request,name='client_advisor_bookings.html',context={
        'customer':customer,'bookings':items,'latest_report':latest_report})

@router.get('/client/account',response_class=HTMLResponse)
def client_account(request:Request,db:Session=Depends(get_db),customer:CustomerAccount=Depends(require_customer)):
    return templates.TemplateResponse(request=request,name='client_account.html',context={'customer':customer,'saved':False,'error':''})

@router.post('/client/account',response_class=HTMLResponse)
def client_account_update(request:Request,name:str=Form(''),wechat_id:str=Form(''),email:str=Form(''),
                          db:Session=Depends(get_db),customer:CustomerAccount=Depends(require_customer)):
    customer.name=name.strip();customer.contact_name=customer.name or customer.contact_name
    customer.wechat_id=wechat_id.strip();customer.email=email.strip();db.commit()
    return templates.TemplateResponse(request=request,name='client_account.html',context={'customer':customer,'saved':True,'error':''})

@router.post('/client/account/password',response_class=HTMLResponse)
def client_account_password(request:Request,current_password:str=Form(...),password:str=Form(...),
                            confirm_password:str=Form(...),db:Session=Depends(get_db),
                            customer:CustomerAccount=Depends(require_customer)):
    from services.auth_service import verify_password
    error=''
    if not verify_password(current_password,customer.password_hash):error='当前密码不正确'
    elif len(password)<8:error='新密码至少需要8位'
    elif password!=confirm_password:error='两次输入的新密码不一致'
    if error:return templates.TemplateResponse(request=request,name='client_account.html',context={'customer':customer,'saved':False,'error':error},status_code=400)
    set_customer_password(db,customer,password);db.commit()
    return templates.TemplateResponse(request=request,name='client_account.html',context={'customer':customer,'saved':True,'error':''})
@router.get('/client/upgrade',response_class=HTMLResponse)
def client_upgrade(request:Request,db:Session=Depends(get_db),customer:CustomerAccount=Depends(require_customer)):
    track_event(db,'client_upgrade_viewed',customer.assessment_id,customer.lead_id,{'customer_id':customer.id});return templates.TemplateResponse(request=request,name='client_upgrade.html',context={'customer':customer,'products':products})
@router.get('/client/upgrade/{product_code}')
def client_upgrade_click(product_code:str,db:Session=Depends(get_db),customer:CustomerAccount=Depends(require_customer)):
    if product_code not in products:raise HTTPException(404,'产品不存在')
    track_event(db,'client_upgrade_clicked',customer.assessment_id,customer.lead_id,{'product_code':product_code});return RedirectResponse(f'/checkout/{customer.assessment_id}?product={product_code}&upgrade=1&from_product=client_portal',303)

@router.get('/admin/client-portals',response_class=HTMLResponse)
def admin_portals(request:Request,db:Session=Depends(get_db),user:User=Depends(require_roles(*BACKEND))):
    scope=get_access_scope(db,user);q=db.query(CustomerAccount).join(Lead,Lead.id==CustomerAccount.lead_id)
    if not scope.can_view_all:
        if scope.role=='sales':q=q.filter(Lead.owner_user_id==user.id)
        elif scope.role=='consultant':q=q.join(ConsultingCase,ConsultingCase.lead_id==Lead.id).filter(or_(ConsultingCase.consultant_user_id==user.id,ConsultingCase.consultant_id==user.id))
        else:q=q.filter(Lead.owner_org_id.in_(scope.allowed_org_ids or [-1]))
    customers=q.order_by(CustomerAccount.created_at.desc()).all();stats={c.id:{'tasks':db.query(CustomerTask).filter_by(customer_id=c.id,status='pending').count(),'messages':db.query(CustomerMessage).filter_by(customer_id=c.id,status='unread').count(),'documents':db.query(UploadedDocument).filter_by(lead_id=c.lead_id).count()} for c in customers};role=get_access_scope(db,user).role;phones={c.id:(c.phone if role=='super_admin' or db.get(Lead,c.lead_id).owner_user_id==user.id else mask_phone(c.phone)) for c in customers}
    return templates.TemplateResponse(request=request,name='admin_client_portals.html',context={'customers':customers,'stats':stats,'phones':phones,'current_user':user})

@router.get('/admin/customers',response_class=HTMLResponse)
def admin_customers(request:Request,status:str='',db:Session=Depends(get_db),
                    user:User=Depends(require_roles('admin','super_admin'))):
    query=db.query(CustomerAccount)
    if status == 'unactivated':query=query.filter(CustomerAccount.password_hash=='')
    elif status == 'active':query=query.filter(CustomerAccount.status=='active',CustomerAccount.password_hash!='')
    elif status:query=query.filter(CustomerAccount.status==status)
    customers=query.order_by(CustomerAccount.created_at.desc()).all()
    stats={item.id:{
        'reports':db.query(Report).filter(Report.customer_id==item.id).count(),
        'orders':db.query(Order).filter(Order.customer_id==item.id).count(),
        'documents':db.query(UploadedDocument).filter(UploadedDocument.customer_id==item.id).count(),
    } for item in customers}
    phones={item.id:mask_phone(item.login_phone or item.phone) for item in customers}
    return templates.TemplateResponse(request=request,name='admin_customers.html',context={
        'customers':customers,'stats':stats,'phones':phones,'status_filter':status,'current_user':user})

@router.get('/admin/customers/{customer_id}',response_class=HTMLResponse)
def admin_customer_detail(request:Request,customer_id:int,db:Session=Depends(get_db),
                          user:User=Depends(require_roles('admin','super_admin'))):
    customer=_customer(db,customer_id);backfill_customer_account_links(db,customer)
    return templates.TemplateResponse(request=request,name='admin_customer_detail.html',context={
        'customer':customer,'reports':db.query(Report).filter(Report.customer_id==customer.id).order_by(Report.created_at.desc()).all(),
        'orders':db.query(Order).filter(Order.customer_id==customer.id).order_by(Order.created_at.desc()).all(),
        'documents':db.query(UploadedDocument).filter(UploadedDocument.customer_id==customer.id).order_by(UploadedDocument.created_at.desc()).all(),
        'bookings':db.query(AdvisorBooking).filter(AdvisorBooking.customer_id==customer.id).order_by(AdvisorBooking.created_at.desc()).all(),
        'projects':db.query(FinancingProject).filter(FinancingProject.customer_id==customer.id).order_by(FinancingProject.created_at.desc()).all(),
        'current_user':user})

@router.post('/admin/customers/{customer_id}/status')
def admin_customer_status(customer_id:int,status:str=Form(...),db:Session=Depends(get_db),
                          user:User=Depends(require_roles('admin','super_admin'))):
    if status not in {'pending_activation','active','disabled','locked'}:raise HTTPException(400,'账号状态无效')
    customer=_customer(db,customer_id);customer.status=status;customer.is_active=status!='disabled'
    if status=='active':customer.failed_login_count=0;customer.locked_until=None
    track_event(db,'customer_account_status_changed',customer.assessment_id,customer.lead_id,
                {'customer_id':customer.id,'status':status,'operator_user_id':user.id},commit=False)
    db.commit();return RedirectResponse(f'/admin/customers/{customer.id}',303)

@router.post('/admin/customers/{customer_id}/reset-password')
def admin_customer_reset_password(request:Request,customer_id:int,db:Session=Depends(get_db),
                                  user:User=Depends(require_roles('admin','super_admin'))):
    customer=_customer(db,customer_id);token=generate_login_token(db,customer,token_type='password_reset',days=1)
    track_event(db,'customer_password_reset_issued',customer.assessment_id,customer.lead_id,
                {'customer_id':customer.id,'operator_user_id':user.id})
    return RedirectResponse(f'/admin/customers/{customer.id}?reset_link=/client/reset-password/{token.token}',303)

@router.post('/admin/customers/{customer_id}/send-activation')
def admin_customer_send_activation(request:Request,customer_id:int,db:Session=Depends(get_db),
                                   user:User=Depends(require_roles('admin','super_admin'))):
    customer=_customer(db,customer_id)
    if customer.password_hash:
        return RedirectResponse(f'/admin/customers/{customer.id}',303)
    customer.status='pending_activation';customer.is_active=True
    token=generate_login_token(db,customer,token_type='account_activation',days=1)
    activation_path=f'/client/activate/{token.token}'
    from services.notification_service import safe_create_notification
    safe_create_notification(db,'customer_account_activation',{
        'activation_url':f"{str(request.base_url).rstrip('/')}{activation_path}",
    },recipient_customer_id=customer.id,related_type='customer_access_token',related_id=token.id)
    track_event(db,'customer_account_activation_issued',customer.assessment_id,customer.lead_id,
                {'customer_id':customer.id,'operator_user_id':user.id})
    db.commit()
    return RedirectResponse(f'/admin/customers/{customer.id}?activation_link={activation_path}',303)
@router.get('/admin/client-portals/{customer_id}',response_class=HTMLResponse)
def admin_portal_detail(request:Request,customer_id:int,db:Session=Depends(get_db),user:User=Depends(require_roles(*BACKEND))):
    customer=_customer(db,customer_id);lead=_customer_access(db,user,customer);ctx=_client_context(db,customer);ctx.update({'current_user':user,'documents':db.query(UploadedDocument).filter_by(lead_id=lead.id).all(),'tasks':db.query(CustomerTask).filter_by(customer_id=customer.id).all(),'messages':db.query(CustomerMessage).filter_by(customer_id=customer.id).order_by(CustomerMessage.created_at.desc()).all(),'confirmations':db.query(CustomerConfirmation).filter_by(customer_id=customer.id).all(),'events':db.query(Event).filter(Event.lead_id==lead.id,Event.event_type.like('client_%')).order_by(Event.created_at.desc()).limit(20).all()});return templates.TemplateResponse(request=request,name='admin_client_portal_detail.html',context=ctx)
@router.post('/admin/leads/{lead_id}/client-portal/open')
def open_portal(lead_id:int,db:Session=Depends(get_db),user:User=Depends(require_roles(*WRITE))):
    customer=ensure_customer_account(db,_lead(db,lead_id));customer.is_active=True;db.commit();return RedirectResponse(f'/admin/client-portals/{customer.id}',303)
@router.post('/admin/client-portals/{customer_id}/generate-token')
def admin_generate_token(customer_id:int,db:Session=Depends(get_db),user:User=Depends(require_roles(*WRITE))):
    customer=_customer(db,customer_id);_customer_access(db,user,customer);token=generate_login_token(db,customer);return RedirectResponse(f'/admin/client-portals/{customer.id}?login_link=/client/login-token/{token.token}',303)
@router.post('/admin/client-portals/{customer_id}/toggle')
def toggle_portal(customer_id:int,db:Session=Depends(get_db),user:User=Depends(require_roles(*WRITE))):
    customer=_customer(db,customer_id);_customer_access(db,user,customer);customer.is_active=not customer.is_active;db.commit();return RedirectResponse(f'/admin/client-portals/{customer.id}',303)
@router.post('/admin/leads/{lead_id}/messages/send')
def admin_send_message(lead_id:int,title:str=Form(...),content:str=Form(...),message_type:str=Form('advisor'),db:Session=Depends(get_db),user:User=Depends(require_roles(*WRITE))):
    customer=ensure_customer_account(db,_lead(db,lead_id));_customer_access(db,user,customer);send_customer_message(db,customer,title.strip(),content.strip(),message_type,user.id);return RedirectResponse(f'/admin/client-portals/{customer.id}',303)
@router.post('/admin/leads/{lead_id}/customer-tasks/create')
def admin_create_customer_task(lead_id:int,task_type:str=Form('other'),task_title:str=Form(...),task_content:str=Form(''),priority:str=Form('medium'),due_time:str=Form(''),related_project_id:int=Form(0),db:Session=Depends(get_db),user:User=Depends(require_roles(*WRITE))):
    customer=ensure_customer_account(db,_lead(db,lead_id));_customer_access(db,user,customer);db.add(CustomerTask(customer_id=customer.id,lead_id=lead_id,assessment_id=customer.assessment_id,related_project_id=related_project_id or None,task_type=task_type,task_title=task_title.strip(),task_content=task_content.strip(),priority=priority,due_time=datetime.fromisoformat(due_time) if due_time else datetime.now()+timedelta(days=3)));db.commit();return RedirectResponse(f'/admin/client-portals/{customer.id}',303)
@router.post('/admin/leads/{lead_id}/confirmations/create')
def admin_create_confirmation(lead_id:int,confirmation_type:str=Form(...),title:str=Form(...),content:str=Form(...),related_project_id:int=Form(0),db:Session=Depends(get_db),user:User=Depends(require_roles(*WRITE))):
    customer=ensure_customer_account(db,_lead(db,lead_id));_customer_access(db,user,customer);item=CustomerConfirmation(customer_id=customer.id,lead_id=lead_id,assessment_id=customer.assessment_id,related_project_id=related_project_id or None,confirmation_type=confirmation_type,title=title.strip(),content=content.strip());db.add(item);db.flush();track_event(db,'customer_confirmation_created',customer.assessment_id,lead_id,{'confirmation_id':item.id},commit=False);db.commit();return RedirectResponse(f'/admin/client-portals/{customer.id}',303)
