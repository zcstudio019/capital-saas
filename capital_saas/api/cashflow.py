from pathlib import Path
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from db.database import get_db
from db.models import CashflowActionItem, CashflowAssessment, CashflowReport, CustomerAccount, Lead
from services.cashflow_service import create_diagnosis, report_content
from services.customer_portal_service import customer_from_session, require_customer
from services.auth_service import require_roles
from db.models import User

router = APIRouter(); templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))
NUMBERS = {"years","employee_count","current_assets","current_liabilities","inventory","cash","monthly_operating_expense","revenue","net_profit","operating_cashflow","cash_received_sales","capex","total_assets","total_debt","interest_bearing_debt","short_interest_debt","interest_expense","ebit","receivables_balance","dso","dso_yoy","dio","dio_yoy","payables_balance","dpo","dpo_yoy","credit_limit","credit_used","negative_operating_cf_months","compressible_expense","idle_assets_cash","inventory_stagnant_ratio"}
NUMBERS.update({f"forecast_{part}_{n}" for part in ("in", "out") for n in range(1, 7)})
BOOLS = {"gross_margin_declining","loan_overdue","credit_withdrawal","major_lawsuit","tax_arrears","financing_cost_rising","bridge_funding_high","supplier_customer_risk","payroll_social_security_delayed","capex_deferrable"}
OTHER_FIELDS = {"industry":"industry_other", "business_scope":"business_scope_other", "company_type":"company_type_other"}

def _number(value):
    if value is None or str(value).strip() in {"", "暂不清楚"}: return None
    try: return float(str(value).replace(",", ""))
    except ValueError: return None

def _data(form):
    data = {key: form.get(key, "").strip() if isinstance(form.get(key, ""), str) else form.get(key) for key in form.keys()}
    for field, other_field in OTHER_FIELDS.items():
        if data.get(field) == "其他":
            data[field] = data.get(other_field) or "其他"
    for key in NUMBERS: data[key] = _number(data.get(key))
    for key in BOOLS: data[key] = str(data.get(key, "")).lower() in {"1", "true", "on", "yes"}
    return data

@router.get("/cashflow-assessment", response_class=HTMLResponse)
def form(request: Request, db: Session = Depends(get_db)):
    customer = customer_from_session(request, db); values = {}
    if customer: values = {"company_name": customer.company_name, "phone": customer.login_phone or customer.phone, "finance_contact": customer.name}
    return templates.TemplateResponse(request=request, name="cashflow_assessment.html", context={"customer":customer,"form_values":values})

@router.post("/cashflow-assessment/submit")
async def submit(request: Request, db: Session = Depends(get_db)):
    form_data = await request.form(); data = _data(form_data)
    if not data.get("company_name"):
        return templates.TemplateResponse(request=request, name="cashflow_assessment.html", context={"form_values":data,"submit_error":"请至少填写企业名称。"}, status_code=422)
    customer = customer_from_session(request, db)
    if not customer and data.get("phone"):
        customer = db.query(CustomerAccount).filter(CustomerAccount.login_phone == data["phone"]).first()
    lead = db.get(Lead, customer.lead_id) if customer and customer.lead_id else None
    assessment, report, _ = create_diagnosis(db, data, customer, lead)
    return RedirectResponse(f"/cashflow-result/{assessment.id}", status_code=303)

@router.get("/cashflow-result/{assessment_id}", response_class=HTMLResponse)
def result(request: Request, assessment_id: int, db: Session = Depends(get_db)):
    assessment = db.get(CashflowAssessment, assessment_id)
    if not assessment: raise HTTPException(404, "诊断不存在")
    customer = customer_from_session(request, db)
    if assessment.customer_id and (not customer or customer.id != assessment.customer_id): raise HTTPException(403, "无权查看该诊断")
    report = db.query(CashflowReport).filter(CashflowReport.assessment_id == assessment.id).first()
    return templates.TemplateResponse(request=request, name="cashflow_report.html", context={"assessment":assessment,"report":report_content(report),"customer":customer,"save_prompt":not assessment.customer_id})

@router.get("/client/cashflow-reports", response_class=HTMLResponse)
def client_reports(request: Request, db: Session = Depends(get_db), customer: CustomerAccount = Depends(require_customer)):
    reports = db.query(CashflowReport).filter(CashflowReport.customer_id == customer.id).order_by(CashflowReport.created_at.desc()).all()
    return templates.TemplateResponse(request=request, name="client_cashflow_reports.html", context={"customer":customer,"reports":reports})

@router.get("/client/cashflow-reports/{report_id}", response_class=HTMLResponse)
def client_report(request: Request, report_id: int, db: Session = Depends(get_db), customer: CustomerAccount = Depends(require_customer)):
    report = db.get(CashflowReport, report_id)
    if not report or report.customer_id != customer.id: raise HTTPException(404, "报告不存在")
    assessment = db.get(CashflowAssessment, report.assessment_id)
    return templates.TemplateResponse(request=request, name="cashflow_report.html", context={"assessment":assessment,"report":report_content(report),"customer":customer,"save_prompt":False})

@router.get("/admin/cashflow-assessments", response_class=HTMLResponse)
def admin_list(request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "super_admin", "consultant", "consultant_manager", "sales", "sales_manager", "city_manager", "viewer"))):
    rows = db.query(CashflowAssessment).order_by(CashflowAssessment.created_at.desc()).all()
    return templates.TemplateResponse(request=request, name="admin_cashflow_assessments.html", context={"rows":rows,"current_user":user})

@router.get("/admin/cashflow-assessments/{assessment_id}", response_class=HTMLResponse)
def admin_detail(request: Request, assessment_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "super_admin", "consultant", "consultant_manager", "sales", "sales_manager", "city_manager", "viewer"))):
    assessment = db.get(CashflowAssessment, assessment_id)
    if not assessment: raise HTTPException(404, "诊断不存在")
    report = db.query(CashflowReport).filter(CashflowReport.assessment_id == assessment_id).first()
    return templates.TemplateResponse(request=request, name="cashflow_report.html", context={"assessment":assessment,"report":report_content(report),"customer":None,"admin_view":True,"save_prompt":False})

@router.post("/admin/cashflow-assessments/{assessment_id}/recalculate")
def recalculate(assessment_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "super_admin", "consultant", "consultant_manager"))):
    """重新计算会生成新诊断和新报告，保留原报告版本与历史记录。"""
    old = db.get(CashflowAssessment, assessment_id)
    if not old: raise HTTPException(404, "诊断不存在")
    try: data = json.loads(old.input_json)
    except (TypeError, ValueError): raise HTTPException(422, "原始诊断资料不可用")
    customer = db.get(CustomerAccount, old.customer_id) if old.customer_id else None
    lead = db.get(Lead, old.lead_id) if old.lead_id else None
    new, _, _ = create_diagnosis(db, data, customer, lead)
    return RedirectResponse(f"/admin/cashflow-assessments/{new.id}", status_code=303)

@router.post("/admin/cashflow-actions/{action_id}")
async def update_action(action_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "super_admin", "consultant", "consultant_manager"))):
    action = db.get(CashflowActionItem, action_id)
    if not action: raise HTTPException(404, "行动项不存在")
    form = await request.form()
    for field in ("task", "owner", "due_text", "goal", "status"):
        if field in form: setattr(action, field, str(form[field]).strip())
    if "expected_cash" in form: action.expected_cash = _number(form["expected_cash"])
    db.commit()
    return RedirectResponse(f"/admin/cashflow-assessments/{action.assessment_id}", status_code=303)
