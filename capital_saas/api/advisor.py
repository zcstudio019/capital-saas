import json
import hashlib
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from core.bank_product_matcher import match_bank_products
from core.access_scope import get_access_scope
from core.config import BASE_DIR, settings
from core.document_checklist_engine import generate_document_checklist
from core.document_completeness_engine import check_document_completeness
from core.document_request_script_engine import generate_document_request_script
from db.database import get_db
from db.models import (
    AdvisorBooking, AIGenerationLog, Assessment, BankProduct, ConsultingCase, CustomerTask,
    DocumentParseTask, FollowTask, Lead, LeadFollowLog, Report, ReportVersion, UploadedDocument, User,
)
from services.auth_service import require_roles
from services.bank_product_import_service import disable_mock_products, import_bank_products, parse_bank_product_file
from services.consulting_service import ensure_consulting_case
from services.event_service import track_event
from services.follow_log_service import add_follow_log
from services.notification_service import (
    notify_advisor_booking_assigned,
    notify_advisor_booking_submitted,
    notify_document_uploaded,
)
from services.report_service import generate_full_report
from services.settings_service import get_setting
from services.document_parse_service import run_parse_task
from utils.logger import logger
from utils.pagination import paginate_query


router = APIRouter()
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
UPLOAD_DIR = BASE_DIR / "data" / "uploads"
ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".png", ".jpg", ".jpeg"}
ADVISOR_BOOKING_STATUSES = {"submitted", "contacted", "scheduled", "completed", "cancelled", "invalid"}
ADVISOR_CONTACT_SCRIPT = (
    "您好，我是沪上银企业融资顾问。您刚刚提交了1对1融资顾问服务预约，"
    "我这边想先和您确认几个信息：企业目前主要是想了解银行产品匹配、融资结构设计，"
    "还是资料准备和申请推进？方便的话我先加您微信，帮您看一下下一步怎么安排。"
)


def _report_or_404(db: Session, report_id: int) -> Report:
    report = db.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")
    return report


def _parse_datetime_local(value: str | None) -> datetime | None:
    value = (value or "").strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(value, fmt)
            if fmt == "%Y-%m-%d":
                return parsed.replace(hour=9, minute=0)
            return parsed
        except ValueError:
            continue
    return None


def _advisor_booking_or_404(db: Session, booking_id: int) -> AdvisorBooking:
    booking = db.get(AdvisorBooking, booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="顾问预约不存在")
    return booking


def _assert_booking_access(db: Session, booking: AdvisorBooking, user: User, *, write: bool = False) -> Lead | None:
    if write and user.role == "viewer":
        raise HTTPException(status_code=403, detail="只读账号不能修改预约")
    scope = get_access_scope(db, user)
    lead = db.get(Lead, booking.lead_id) if booking.lead_id else None
    if scope.role == "sales" and not (
        booking.owner_user_id == user.id
        or (lead and (lead.owner_user_id == user.id or lead.assigned_sales_id == user.id))
    ):
        raise HTTPException(status_code=403, detail="无权查看该预约")
    if scope.role == "consultant" and booking.consultant_user_id != user.id:
        raise HTTPException(status_code=403, detail="无权查看该预约")
    if scope.role not in {"sales", "consultant"} and not scope.can_view_all:
        if not lead or lead.owner_org_id not in (scope.allowed_org_ids or []):
            raise HTTPException(status_code=403, detail="无权查看该预约")
    return lead


def _create_booking_task(
    db: Session,
    booking: AdvisorBooking,
    lead: Lead | None,
    title: str,
    content: str,
    due_time: datetime | None = None,
) -> FollowTask | None:
    if not lead:
        return None
    task = FollowTask(
        lead_id=lead.id,
        assessment_id=lead.assessment_id,
        task_type="advisor_booking",
        task_title=title,
        task_content=content,
        priority="high",
        due_time=due_time or datetime.now() + timedelta(hours=24),
        status="pending",
    )
    db.add(task)
    db.flush()
    booking.follow_task_id = task.id
    lead.next_follow_time = task.due_time
    lead.last_follow_note = content
    return task


def _record_booking_follow(
    db: Session,
    booking: AdvisorBooking,
    lead: Lead | None,
    user: User,
    old_status: str,
    new_status: str,
    content: str,
):
    if lead:
        add_follow_log(db, lead.id, user, "advisor_booking", content, old_status, new_status)
    track_event(
        db,
        "advisor_booking_followed",
        assessment_id=booking.assessment_id,
        lead_id=booking.lead_id,
        data={"booking_id": booking.id, "old_status": old_status, "new_status": new_status, "operator": user.username},
        commit=False,
    )


def _apply_booking_status(
    db: Session,
    booking: AdvisorBooking,
    lead: Lead | None,
    user: User,
    status: str,
    *,
    note: str = "",
    next_follow_time: datetime | None = None,
    scheduled_time_text: str = "",
    service_result: str = "",
    create_case: bool = False,
):
    if status not in ADVISOR_BOOKING_STATUSES:
        raise HTTPException(status_code=400, detail="预约状态不合法")
    old_status = booking.booking_status or "submitted"
    booking.booking_status = status
    booking.updated_at = datetime.now()
    if note:
        booking.internal_note = note
    if scheduled_time_text:
        booking.preferred_time = scheduled_time_text
    status_text = {
        "submitted": "已提交",
        "contacted": "已联系",
        "scheduled": "已安排",
        "completed": "已完成",
        "cancelled": "已取消",
        "invalid": "无效预约",
    }.get(status, status)
    content_parts = [f"顾问预约状态更新为{status_text}"]
    if note:
        content_parts.append(f"内部备注：{note}")
    if scheduled_time_text:
        content_parts.append(f"预约沟通时间：{scheduled_time_text}")
    if service_result:
        content_parts.append(f"服务结果：{service_result}")
    content = "；".join(content_parts)
    _record_booking_follow(db, booking, lead, user, old_status, status, content)
    if status == "contacted":
        _create_booking_task(db, booking, lead, "确认顾问沟通时间", "客户预约已联系，请确认具体顾问沟通时间。", next_follow_time)
    elif status == "scheduled":
        _create_booking_task(db, booking, lead, "按预约时间联系客户", "顾问沟通时间已安排，请按预约时间联系客户。", next_follow_time)
    elif status == "completed":
        if service_result and lead:
            lead.last_follow_note = service_result
        if create_case:
            report = db.get(Report, booking.report_id) if booking.report_id else None
            assessment = report.assessment if report else (lead.assessment if lead else None)
            if assessment:
                case = ensure_consulting_case(db, assessment, "1999_structure_plan")
                if case:
                    case.case_summary = f"{booking.company_name or assessment.company_name}顾问预约完成后转入顾问案件。"
                    case.service_goal = service_result or booking.consultation_focus or "继续推进融资结构设计与银行申请执行。"
                    case.consultant_user_id = booking.consultant_user_id
                    case.consultant_id = booking.consultant_user_id
                    case.owner_user_id = booking.owner_user_id
                    case.case_status = "in_progress"


@router.get("/advisor/book/{report_id}", response_class=HTMLResponse)
def advisor_booking_form(
    request: Request,
    report_id: int,
    db: Session = Depends(get_db),
):
    report = _report_or_404(db, report_id)
    assessment = report.assessment
    return templates.TemplateResponse(
        request=request,
        name="advisor_booking.html",
        context={
            "report": report,
            "assessment": assessment,
            "lead": assessment.lead,
            "submitted": False,
        },
    )


@router.post("/advisor/book/{report_id}", response_class=HTMLResponse)
def submit_advisor_booking(
    request: Request,
    report_id: int,
    company_name: str = Form(""),
    contact_name: str = Form(""),
    phone: str = Form(""),
    wechat_id: str = Form(""),
    city: str = Form(""),
    service_type: str = Form("high_ticket_consulting"),
    urgency: str = Form("normal"),
    consultation_focus: str = Form(""),
    preferred_time: str = Form(""),
    note: str = Form(""),
    db: Session = Depends(get_db),
):
    report = _report_or_404(db, report_id)
    assessment = report.assessment
    lead = assessment.lead
    company_name = (company_name or assessment.company_name or "").strip()
    contact_name = (contact_name or assessment.contact_name or (lead.contact_name if lead else "") or "").strip()
    phone = (phone or assessment.phone or (lead.phone if lead else "") or "").strip()
    wechat_id = (wechat_id or assessment.wechat_id or (lead.wechat_id if lead else "") or "").strip()
    city = (city or assessment.city or (lead.city if lead else "") or "").strip()
    service_type = service_type if service_type in {
        "financing_structure_consulting",
        "bank_product_matching",
        "document_review",
        "project_delivery",
        "high_ticket_consulting",
    } else "high_ticket_consulting"
    urgency = urgency if urgency in {"normal", "urgent", "very_urgent"} else "normal"
    focus = consultation_focus.strip()
    preferred_time = preferred_time.strip()
    note = note.strip()
    if not contact_name or not phone:
        return templates.TemplateResponse(
            request=request,
            name="advisor_booking.html",
            context={
                "report": report,
                "assessment": assessment,
                "lead": lead,
                "submitted": False,
                "error": "请填写联系人和手机，方便顾问联系您。",
                "form": {
                    "company_name": company_name,
                    "contact_name": contact_name,
                    "phone": phone,
                    "wechat_id": wechat_id,
                    "city": city,
                    "service_type": service_type,
                    "urgency": urgency,
                    "consultation_focus": focus,
                    "preferred_time": preferred_time,
                    "note": note,
                },
            },
            status_code=400,
        )
    task = None
    if lead:
        task = FollowTask(
            lead_id=lead.id,
            assessment_id=assessment.id,
            task_type="advisor_booking",
            task_title="预约1对1融资顾问服务",
            task_content=f"客户提交顾问预约。咨询重点：{focus or '未填写'}；希望沟通时间：{preferred_time or '未填写'}；补充说明：{note or '无'}",
            priority="high",
            due_time=datetime.now() + timedelta(hours=2),
            status="pending",
        )
        db.add(task)
        db.flush()
        lead.follow_status = "跟进中"
        lead.next_follow_time = task.due_time
        lead.last_follow_note = "客户提交了1对1融资顾问预约。"
    booking = AdvisorBooking(
        assessment_id=assessment.id,
        report_id=report.id,
        lead_id=lead.id if lead else None,
        company_name=company_name,
        contact_name=contact_name,
        phone=phone,
        wechat_id=wechat_id,
        city=city,
        service_type=service_type,
        urgency=urgency,
        consultation_focus=focus,
        preferred_time=preferred_time,
        note=note,
        booking_status="submitted",
        owner_user_id=(lead.owner_user_id or lead.assigned_sales_id) if lead else None,
        consultant_user_id=None,
        follow_task_id=task.id if task else None,
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)
    notify_advisor_booking_submitted(db, booking, commit=True)
    track_event(
        db,
        "advisor_booking_submitted",
        assessment_id=assessment.id,
        lead_id=lead.id if lead else None,
        data={"booking_id": booking.id, "report_id": report.id},
    )
    return templates.TemplateResponse(
        request=request,
        name="advisor_booking.html",
        context={
            "report": report,
            "assessment": assessment,
            "lead": lead,
            "submitted": True,
            "booking": booking,
        },
    )


@router.get("/admin/advisor-bookings", response_class=HTMLResponse)
def admin_advisor_bookings(
    request: Request,
    status: str = "",
    urgency: str = "",
    service_type: str = "",
    owner_user_id: int = 0,
    consultant_user_id: int = 0,
    city: str = "",
    page: int = 1,
    page_size: int = 10,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "super_admin", "city_manager", "sales_manager", "sales", "consultant_manager", "consultant", "viewer")),
):
    scope = get_access_scope(db, user)
    query = db.query(AdvisorBooking)
    if status:
        query = query.filter(AdvisorBooking.booking_status == status)
    if urgency:
        query = query.filter(AdvisorBooking.urgency == urgency)
    if service_type:
        query = query.filter(AdvisorBooking.service_type == service_type)
    if owner_user_id:
        query = query.filter(AdvisorBooking.owner_user_id == owner_user_id)
    if consultant_user_id:
        query = query.filter(AdvisorBooking.consultant_user_id == consultant_user_id)
    if city:
        query = query.filter(AdvisorBooking.city == city)
    if scope.role == "sales":
        lead_ids = [
            lead.id for lead in db.query(Lead)
            .filter((Lead.owner_user_id == user.id) | (Lead.assigned_sales_id == user.id))
            .all()
        ]
        query = query.filter((AdvisorBooking.owner_user_id == user.id) | (AdvisorBooking.lead_id.in_(lead_ids or [-1])))
    elif scope.role == "consultant":
        query = query.filter(AdvisorBooking.consultant_user_id == user.id)
    elif scope.role == "sales_manager":
        lead_ids = [lead.id for lead in db.query(Lead).filter(Lead.owner_org_id.in_(scope.allowed_org_ids or [-1])).all()]
        query = query.filter(
            (AdvisorBooking.owner_user_id.in_(scope.allowed_user_ids or [-1]))
            | (AdvisorBooking.owner_user_id.is_(None))
            | (AdvisorBooking.lead_id.in_(lead_ids or [-1]))
        )
    elif not scope.can_view_all:
        lead_ids = [lead.id for lead in db.query(Lead).filter(Lead.owner_org_id.in_(scope.allowed_org_ids or [-1])).all()]
        query = query.filter(AdvisorBooking.lead_id.in_(lead_ids or [-1]))
    pagination = paginate_query(query.order_by(AdvisorBooking.created_at.desc()), page, page_size)
    bookings = pagination["items"]
    leads = {item.lead_id: db.get(Lead, item.lead_id) for item in bookings if item.lead_id}
    tasks = {item.follow_task_id: db.get(FollowTask, item.follow_task_id) for item in bookings if item.follow_task_id}
    user_ids = {
        user_id for item in bookings
        for user_id in [item.owner_user_id, item.consultant_user_id]
        if user_id
    }
    users = {user_id: db.get(User, user_id) for user_id in user_ids}

    pagination_params = {"page_size": pagination["page_size"]}
    for key, value in {
        "status": status,
        "urgency": urgency,
        "service_type": service_type,
        "owner_user_id": owner_user_id or "",
        "consultant_user_id": consultant_user_id or "",
        "city": city,
    }.items():
        if value not in {"", 0, None}:
            pagination_params[key] = value

    def build_booking_pagination_url(target_page: int) -> str:
        return f"/admin/advisor-bookings?{urlencode({**pagination_params, 'page': target_page})}"

    return templates.TemplateResponse(
        request=request,
        name="admin_advisor_bookings.html",
        context={
            "bookings": bookings,
            "leads": leads,
            "tasks": tasks,
            "users": users,
            "filters": {
                "status": status, "urgency": urgency, "service_type": service_type,
                "owner_user_id": owner_user_id, "consultant_user_id": consultant_user_id,
                "city": city, "page_size": pagination["page_size"],
            },
            "pagination": pagination,
            "build_pagination_url": build_booking_pagination_url,
            "current_booking_url": build_booking_pagination_url(pagination["page"]),
            "sales_users": db.query(User).filter(User.role.in_(["admin", "super_admin", "sales_manager", "sales"]), User.is_active.is_(True)).order_by(User.id).all(),
            "consultant_users": db.query(User).filter(User.role.in_(["consultant_manager", "consultant"]), User.is_active.is_(True)).order_by(User.id).all(),
            "cities": [row[0] for row in db.query(AdvisorBooking.city).distinct().all() if row[0]],
            "pagination_label": "顾问预约",
            "pagination_unit": "条预约",
            "current_user": user,
        },
    )


@router.get("/admin/advisor-bookings/{booking_id}", response_class=HTMLResponse)
def admin_advisor_booking_follow_detail(
    request: Request,
    booking_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "super_admin", "city_manager", "sales_manager", "sales", "consultant_manager", "consultant", "viewer")),
):
    booking = _advisor_booking_or_404(db, booking_id)
    lead = _assert_booking_access(db, booking, user)
    report = db.get(Report, booking.report_id) if booking.report_id else None
    assessment = report.assessment if report else None
    follow_logs = []
    if lead:
        follow_logs = db.query(LeadFollowLog).filter(
            LeadFollowLog.lead_id == lead.id,
            LeadFollowLog.action_type == "advisor_booking",
        ).order_by(LeadFollowLog.created_at.desc()).all()
    sales_users = db.query(User).filter(User.role.in_(["admin", "super_admin", "sales_manager", "sales"])).order_by(User.id).all()
    consultant_users = db.query(User).filter(User.role.in_(["consultant_manager", "consultant"])).order_by(User.id).all()
    return templates.TemplateResponse(
        request=request,
        name="admin_advisor_booking_detail.html",
        context={
            "booking": booking,
            "lead": lead,
            "assessment": assessment,
            "task": db.get(FollowTask, booking.follow_task_id) if booking.follow_task_id else None,
            "owner": db.get(User, booking.owner_user_id) if booking.owner_user_id else None,
            "consultant": db.get(User, booking.consultant_user_id) if booking.consultant_user_id else None,
            "follow_logs": follow_logs,
            "sales_users": sales_users,
            "consultant_users": consultant_users,
            "contact_script": ADVISOR_CONTACT_SCRIPT,
            "can_edit": user.role != "viewer",
            "current_user": user,
        },
    )


@router.post("/admin/advisor-bookings/{booking_id}/quick-status")
def admin_advisor_booking_quick_status(
    booking_id: int,
    status: str = Form(...),
    next_url: str = Form("/admin/advisor-bookings"),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "super_admin", "city_manager", "sales_manager", "sales", "consultant_manager", "consultant")),
):
    booking = _advisor_booking_or_404(db, booking_id)
    lead = _assert_booking_access(db, booking, user, write=True)
    _apply_booking_status(db, booking, lead, user, status)
    db.commit()
    return RedirectResponse(url=next_url, status_code=303)


@router.post("/admin/advisor-bookings/{booking_id}/follow-up")
def admin_advisor_booking_follow_up(
    booking_id: int,
    booking_status: str = Form(...),
    owner_user_id: int = Form(0),
    consultant_user_id: int = Form(0),
    internal_note: str = Form(""),
    next_follow_time: str = Form(""),
    scheduled_time: str = Form(""),
    service_result: str = Form(""),
    create_consulting_case: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "super_admin", "city_manager", "sales_manager", "sales", "consultant_manager", "consultant")),
):
    booking = _advisor_booking_or_404(db, booking_id)
    lead = _assert_booking_access(db, booking, user, write=True)
    old_owner_user_id = booking.owner_user_id
    old_consultant_user_id = booking.consultant_user_id
    if owner_user_id:
        booking.owner_user_id = owner_user_id
        if lead:
            lead.owner_user_id = owner_user_id
            lead.assigned_sales_id = owner_user_id
    if consultant_user_id:
        booking.consultant_user_id = consultant_user_id
    _apply_booking_status(
        db,
        booking,
        lead,
        user,
        booking_status,
        note=internal_note.strip(),
        next_follow_time=_parse_datetime_local(next_follow_time),
        scheduled_time_text=scheduled_time.strip(),
        service_result=service_result.strip(),
        create_case=create_consulting_case == "true",
    )
    if owner_user_id and owner_user_id != old_owner_user_id:
        notify_advisor_booking_assigned(db, booking, owner_user_id, commit=False)
    if consultant_user_id and consultant_user_id != old_consultant_user_id:
        notify_advisor_booking_assigned(db, booking, consultant_user_id, commit=False)
    db.commit()
    return RedirectResponse(url=f"/admin/advisor-bookings/{booking.id}", status_code=303)


@router.get("/admin/advisor-bookings-legacy/{booking_id}", response_class=HTMLResponse)
def admin_advisor_booking_detail(
    request: Request,
    booking_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "super_admin", "city_manager", "sales_manager", "sales", "consultant_manager", "consultant", "viewer")),
):
    booking = db.get(AdvisorBooking, booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="顾问预约不存在")
    scope = get_access_scope(db, user)
    lead = db.get(Lead, booking.lead_id) if booking.lead_id else None
    if scope.role == "sales" and not (
        booking.owner_user_id == user.id
        or (lead and (lead.owner_user_id == user.id or lead.assigned_sales_id == user.id))
    ):
        raise HTTPException(status_code=403, detail="无权查看该预约")
    if scope.role == "consultant" and booking.consultant_user_id != user.id:
        raise HTTPException(status_code=403, detail="无权查看该预约")
    if scope.role not in {"sales", "consultant"} and not scope.can_view_all:
        if not lead or lead.owner_org_id not in (scope.allowed_org_ids or []):
            raise HTTPException(status_code=403, detail="无权查看该预约")
    report = db.get(Report, booking.report_id) if booking.report_id else None
    assessment = report.assessment if report else None
    return templates.TemplateResponse(
        request=request,
        name="admin_advisor_booking_detail.html",
        context={
            "booking": booking,
            "lead": lead,
            "assessment": assessment,
            "task": db.get(FollowTask, booking.follow_task_id) if booking.follow_task_id else None,
            "owner": db.get(User, booking.owner_user_id) if booking.owner_user_id else None,
            "consultant": db.get(User, booking.consultant_user_id) if booking.consultant_user_id else None,
            "current_user": user,
        },
    )


@router.get("/admin/reports/{report_id}/versions", response_class=HTMLResponse)
def report_versions(
    request: Request,
    report_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "viewer")),
):
    report = _report_or_404(db, report_id)
    versions = db.query(ReportVersion).filter(
        ReportVersion.report_id == report.id
    ).order_by(ReportVersion.version_no.desc()).all()
    version_views = []
    for version in versions:
        try:
            metadata = json.loads(version.report_json).get("report_meta", {})
        except (TypeError, ValueError):
            metadata = {}
        version_views.append({"version": version, "metadata": metadata})
    return templates.TemplateResponse(
        request=request, name="admin_report_versions.html",
        context={"report_item": report, "versions": versions, "version_views": version_views, "current_user": user},
    )


@router.get("/admin/reports/{report_id}/versions/{version_id}", response_class=HTMLResponse)
def report_version_detail(
    request: Request,
    report_id: int,
    version_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "sales", "viewer")),
):
    report = _report_or_404(db, report_id)
    version = db.query(ReportVersion).filter(
        ReportVersion.id == version_id, ReportVersion.report_id == report.id
    ).first()
    if not version:
        raise HTTPException(status_code=404, detail="报告版本不存在")
    version_payload = json.loads(version.report_json)
    return templates.TemplateResponse(
        request=request, name="admin_report_version_detail.html",
        context={
            "report_item": report, "version": version,
            "report": version_payload, "version_meta": version_payload.get("report_meta", {}), "current_user": user,
        },
    )


@router.post("/admin/reports/{report_id}/versions/{version_id}/set-current")
def set_current_version(
    report_id: int,
    version_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
):
    report = _report_or_404(db, report_id)
    version = db.query(ReportVersion).filter(
        ReportVersion.id == version_id, ReportVersion.report_id == report.id
    ).first()
    if not version:
        raise HTTPException(status_code=404, detail="报告版本不存在")
    report.full_report_json = version.report_json
    report.html_content = version.html_content
    report.current_version_id = version.id
    report.review_status = "pending_review"
    report.reviewed_by = None
    report.reviewed_at = None
    report.review_note = "切换历史版本后需重新审核。"
    db.commit()
    logger.info("切换报告版本 report_id=%s version_id=%s operator=%s", report.id, version.id, user.username)
    return RedirectResponse(url=f"/admin/reports/{report.id}", status_code=303)


@router.post("/admin/reports/{report_id}/regenerate")
def regenerate_report(
    report_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
):
    report = _report_or_404(db, report_id)
    generate_full_report(db, report.assessment, force=True, created_by=user.username)
    logger.info("重新生成报告 report_id=%s operator=%s", report.id, user.username)
    return RedirectResponse(url=f"/admin/reports/{report.id}", status_code=303)


@router.post("/admin/reports/{report_id}/rematch-products")
def rematch_report_products(
    report_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
):
    report = _report_or_404(db, report_id)
    generate_full_report(db, report.assessment, force=True, created_by=f"{user.username}（重新匹配产品）")
    logger.info("重新匹配报告产品 report_id=%s operator=%s", report.id, user.username)
    return RedirectResponse(url=f"/admin/reports/{report.id}", status_code=303)


@router.post("/admin/reports/{report_id}/approve")
def approve_report(
    request: Request,
    report_id: int,
    review_note: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
):
    report = _report_or_404(db, report_id)
    report.review_status = "approved"
    report.reviewed_by = user.id
    report.reviewed_at = datetime.now()
    report.review_note = review_note.strip()
    current_version = db.get(ReportVersion, report.current_version_id) if report.current_version_id else None
    if current_version:
        try:
            version_content = json.loads(current_version.report_json)
        except (TypeError, ValueError):
            version_content = {}
        version_content.setdefault("report_meta", {}).update({
            "review_status": "approved",
            "reviewer": user.username,
            "reviewed_at": report.reviewed_at.isoformat(),
            "review_note": report.review_note,
        })
        current_version.report_json = json.dumps(version_content, ensure_ascii=False)
    from db.models import CustomerAccount
    from services.notification_service import safe_create_notification
    customer = db.query(CustomerAccount).filter(CustomerAccount.assessment_id == report.assessment_id,
        CustomerAccount.is_active.is_(True)).first()
    if customer:
        safe_create_notification(db,"report_approved_customer",{"company_name":customer.company_name},
            recipient_customer_id=customer.id,related_type="report",related_id=report.id)
        lead = db.get(Lead, customer.lead_id)
        for user_id in {lead.owner_user_id if lead else None}:
            if user_id:safe_create_notification(db,"report_approved_customer",{"company_name":customer.company_name},
                recipient_user_id=user_id,channel="in_app",related_type="report",related_id=report.id)
    from services.audit_service import write_audit_log
    write_audit_log(db,"report_approved","report",report.id,user_id=user.id,after={"review_status":"approved"},request=request,risk_level="high")
    db.commit()
    logger.info("审核通过报告 report_id=%s operator=%s", report.id, user.username)
    return RedirectResponse(url=f"/admin/reports/{report.id}", status_code=303)


@router.post("/admin/reports/{report_id}/reject")
def reject_report(
    request: Request,
    report_id: int,
    review_note: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
):
    report = _report_or_404(db, report_id)
    report.review_status = "rejected"
    report.reviewed_by = user.id
    report.reviewed_at = datetime.now()
    report.review_note = review_note.strip()
    report.public_token = None
    report.token_expired_at = None
    current_version = db.get(ReportVersion, report.current_version_id) if report.current_version_id else None
    if current_version:
        try:
            version_content = json.loads(current_version.report_json)
        except (TypeError, ValueError):
            version_content = {}
        version_content.setdefault("report_meta", {}).update({
            "review_status": "rejected",
            "reviewer": user.username,
            "reviewed_at": report.reviewed_at.isoformat(),
            "review_note": report.review_note,
        })
        current_version.report_json = json.dumps(version_content, ensure_ascii=False)
    from services.audit_service import write_audit_log
    write_audit_log(db,"report_rejected","report",report.id,user_id=user.id,after={"review_status":"rejected","note":report.review_note},request=request,risk_level="high")
    db.commit()
    logger.info("驳回报告 report_id=%s operator=%s", report.id, user.username)
    return RedirectResponse(url=f"/admin/reports/{report.id}", status_code=303)


@router.get("/admin/bank-products", response_class=HTMLResponse)
def bank_products_page(
    request: Request,
    data_source: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "sales", "viewer")),
):
    query = db.query(BankProduct)
    if data_source in {"imported", "manual", "mock"}:
        query = query.filter(BankProduct.data_source == data_source)
    else:
        query = query.filter(~((BankProduct.data_source == "mock") & (BankProduct.is_active.is_(False))))
    return templates.TemplateResponse(
        request=request, name="admin_bank_products.html",
        context={
            "bank_products": query.order_by(BankProduct.id).all(),
            "current_user": user, "edit_item": None, "data_source": data_source,
        },
    )


@router.get("/admin/bank-products/import-template")
def download_bank_product_markdown_template(
    _: User = Depends(require_roles("admin")),
):
    path = BASE_DIR / "data" / "import_templates" / "bank_products_template.md"
    return FileResponse(path, media_type="text/markdown; charset=utf-8", filename="bank_products_template.md")

@router.get("/admin/bank-products/import", response_class=HTMLResponse)
def bank_products_import_page(
    request: Request,
    user: User = Depends(require_roles("admin")),
):
    return templates.TemplateResponse(
        request=request, name="admin_bank_product_import.html",
        context={"current_user": user, "result": None},
    )


@router.post("/admin/bank-products/import", response_class=HTMLResponse)
async def import_bank_products_file(
    request: Request,
    upload: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
):
    filename = Path(upload.filename or "").name
    suffix = Path(filename).suffix.lower()
    if suffix not in {".csv", ".xlsx", ".md"}:
        raise HTTPException(status_code=400, detail="仅支持 CSV、Excel（.xlsx）或 Markdown（.md）文件")
    content = await upload.read(10 * 1024 * 1024 + 1)
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="导入文件不能超过10MB")
    try:
        rows = parse_bank_product_file(filename, content)
        result = import_bank_products(db, rows, source_file_name=filename)
    except (ValueError, UnicodeDecodeError) as exc:
        result = {"parsed": 0, "success": 0, "failed": 1, "errors": [str(exc)]}
    return templates.TemplateResponse(
        request=request, name="admin_bank_product_import.html",
        context={"current_user": user, "result": result},
    )

@router.get("/admin/bank-products/{product_id}/edit", response_class=HTMLResponse)
def edit_bank_product_page(
    request: Request,
    product_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
):
    item = db.get(BankProduct, product_id)
    if not item:
        raise HTTPException(status_code=404, detail="银行产品不存在")
    return templates.TemplateResponse(
        request=request, name="admin_bank_products.html",
        context={
            "bank_products": db.query(BankProduct).order_by(BankProduct.id).all(),
            "current_user": user, "edit_item": item,
        },
    )


@router.post("/admin/bank-products/save")
def save_bank_product(
    product_id: int = Form(0),
    bank_name: str = Form(...),
    bank_type: str = Form(...),
    product_name: str = Form(...),
    product_type: str = Form(...),
    suitable_industry: str = Form("通用"),
    min_revenue: float = Form(0),
    min_years: int = Form(1),
    requires_tax_normal: bool = Form(False),
    requires_credit_normal: bool = Form(False),
    requires_collateral: bool = Form(False),
    max_amount: float = Form(0),
    interest_rate_range: str = Form("以审批为准"),
    loan_term: str = Form("12-36个月"),
    application_requirements: str = Form(""),
    risk_notes: str = Form(""),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin")),
):
    item = db.get(BankProduct, product_id) if product_id else BankProduct()
    if not item:
        raise HTTPException(status_code=404, detail="银行产品不存在")
    for key, value in {
        "bank_name": bank_name, "bank_type": bank_type, "product_name": product_name,
        "product_type": product_type, "suitable_industry": suitable_industry,
        "min_revenue": min_revenue, "min_years": min_years,
        "requires_tax_normal": requires_tax_normal,
        "requires_credit_normal": requires_credit_normal,
        "requires_collateral": requires_collateral, "max_amount": max_amount,
        "interest_rate_range": interest_rate_range, "loan_term": loan_term,
        "application_requirements": application_requirements, "risk_notes": risk_notes,
    }.items():
        setattr(item, key, value)
    if not product_id:
        item.data_source = "manual"
        db.add(item)
    db.commit()
    return RedirectResponse(url="/admin/bank-products", status_code=303)


@router.post("/admin/bank-products/{product_id}/toggle")
def toggle_bank_product(
    product_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin")),
):
    item = db.get(BankProduct, product_id)
    if not item:
        raise HTTPException(status_code=404, detail="银行产品不存在")
    item.is_active = not item.is_active
    db.commit()
    return RedirectResponse(url="/admin/bank-products", status_code=303)

@router.post("/admin/bank-products/disable-mock")
def disable_mock_bank_products(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin")),
):
    disable_mock_products(db)
    return RedirectResponse(url="/admin/bank-products", status_code=303)


@router.get("/admin/consulting-cases", response_class=HTMLResponse)
def consulting_cases(
    request: Request,
    case_status: str = "",
    consultant_user_id: int = 0,
    company_keyword: str = "",
    product_code: str = "",
    page: int = 1,
    page_size: int = 10,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "super_admin", "city_manager", "consultant_manager", "consultant", "sales_manager", "sales", "viewer")),
):
    scope = get_access_scope(db, user)
    query = db.query(ConsultingCase).join(Assessment)
    if not scope.can_view_all:
        query = query.filter(ConsultingCase.owner_org_id.in_(scope.allowed_org_ids or [-1]))
        if scope.role == "consultant":
            query = query.filter(ConsultingCase.consultant_user_id == user.id)
    if case_status:
        query = query.filter(ConsultingCase.case_status == case_status)
    if consultant_user_id:
        query = query.filter(ConsultingCase.consultant_user_id == consultant_user_id)
    if product_code:
        query = query.filter(ConsultingCase.product_code == product_code)
    if company_keyword:
        query = query.filter(Assessment.company_name.ilike(f"%{company_keyword.strip()}%"))
    pagination = paginate_query(query.order_by(ConsultingCase.created_at.desc()), page, page_size)
    cases = pagination["items"]

    pagination_params = {"page_size": pagination["page_size"]}
    for key, value in {
        "case_status": case_status,
        "consultant_user_id": consultant_user_id or "",
        "company_keyword": company_keyword,
        "product_code": product_code,
    }.items():
        if value not in {"", 0, None}:
            pagination_params[key] = value

    def build_case_pagination_url(target_page: int) -> str:
        return f"/admin/consulting-cases?{urlencode({**pagination_params, 'page': target_page})}"

    assessment_items = {case.assessment_id: db.get(Assessment, case.assessment_id) for case in cases}
    consultant_ids = {case.consultant_user_id for case in cases if case.consultant_user_id}
    return templates.TemplateResponse(
        request=request, name="admin_consulting_cases.html",
        context={
            "cases": cases,
            "assessments": assessment_items,
            "consultants": {item.id: item for item in db.query(User).filter(User.id.in_(consultant_ids or {-1})).all()},
            "consultant_users": db.query(User).filter(User.role.in_(["consultant_manager", "consultant"]), User.is_active.is_(True)).order_by(User.id).all(),
            "filters": {
                "case_status": case_status, "consultant_user_id": consultant_user_id,
                "company_keyword": company_keyword, "product_code": product_code,
                "page_size": pagination["page_size"],
            },
            "pagination": pagination,
            "build_pagination_url": build_case_pagination_url,
            "pagination_label": "顾问案件",
            "pagination_unit": "个案件",
            "current_user": user,
        },
    )


@router.get("/admin/consulting-cases/{case_id}", response_class=HTMLResponse)
def consulting_case_detail(
    request: Request,
    case_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "super_admin", "city_manager", "consultant_manager", "consultant", "sales_manager", "sales", "viewer")),
):
    case = db.get(ConsultingCase, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="顾问案件不存在")
    scope = get_access_scope(db, user)
    if not scope.can_view_all and case.owner_org_id not in scope.allowed_org_ids:
        raise HTTPException(status_code=403, detail="无权查看该顾问案件")
    if scope.role == "consultant" and case.consultant_user_id != user.id:
        raise HTTPException(status_code=403, detail="无权查看该顾问案件")
    assessment = db.get(Report, case.report_id).assessment if case.report_id else None
    if not assessment:
        from db.models import Assessment
        assessment = db.get(Assessment, case.assessment_id)
    lead = db.get(Lead, case.lead_id) if case.lead_id else None
    documents = db.query(UploadedDocument).filter(
        UploadedDocument.lead_id == lead.id
    ).all() if lead else []
    matches = match_bank_products(db, assessment)
    completeness = check_document_completeness(
        lead, assessment, documents, case.product_code, matches
    ) if lead else {
        "completeness_score": 0, "level": "weak",
        "missing_required_documents": [], "next_collect_actions": [],
    }
    return templates.TemplateResponse(
        request=request, name="admin_consulting_case_detail.html",
        context={
            "case": case, "assessment": assessment,
            "lead": lead,
            "bank_matches": matches,
            "checklist": generate_document_checklist(assessment, case.product_code),
            "completeness": completeness,
            "request_script": generate_document_request_script(
                assessment.company_name, lead.contact_name if lead else "",
                completeness["missing_required_documents"],
            ),
            "current_user": user,
            "can_edit": user.role in {"admin", "sales"},
            "can_delete": user.role == "admin",
            "customer_tasks": db.query(CustomerTask).filter(CustomerTask.lead_id==lead.id).order_by(CustomerTask.created_at.desc()).all() if lead else [],
        },
    )


@router.post("/admin/consulting-cases/{case_id}/update")
def update_consulting_case(
    case_id: int,
    case_status: str = Form(...),
    consultant_id: int = Form(0),
    case_summary: str = Form(""),
    service_goal: str = Form(""),
    next_meeting_time: str = Form(""),
    show_consultant_contact: bool = Form(False),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin", "sales")),
):
    case = db.get(ConsultingCase, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="顾问案件不存在")
    case.case_status = case_status
    case.consultant_id = consultant_id or None
    case.case_summary = case_summary.strip()
    case.service_goal = service_goal.strip()
    case.next_meeting_time = datetime.fromisoformat(next_meeting_time) if next_meeting_time else None
    case.show_consultant_contact = show_consultant_contact
    case.updated_at = datetime.now()
    db.commit()
    return RedirectResponse(url=f"/admin/consulting-cases/{case.id}", status_code=303)


@router.get("/admin/leads/{lead_id}/documents", response_class=HTMLResponse)
def lead_documents(
    request: Request,
    lead_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "sales", "viewer")),
):
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="线索不存在")
    documents = db.query(UploadedDocument).filter(
        UploadedDocument.lead_id == lead.id
    ).order_by(UploadedDocument.created_at.desc()).all()
    return templates.TemplateResponse(
        request=request, name="admin_lead_documents.html",
        context={
            "lead": lead, "documents": documents, "current_user": user,
            "can_edit": user.role in {"admin", "sales"},
            "can_delete": user.role == "admin",
            "max_mb": int(get_setting(db, "upload_max_mb", str(settings.upload_max_mb))),
        },
    )


@router.post("/admin/leads/{lead_id}/documents")
async def upload_lead_document(
    lead_id: int,
    document_category: str = Form(...),
    upload: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "sales")),
):
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="线索不存在")
    suffix = Path(upload.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="不支持的文件类型")
    max_bytes = int(get_setting(db, "upload_max_mb", str(settings.upload_max_mb))) * 1024 * 1024
    content = await upload.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise HTTPException(status_code=400, detail="文件超过大小限制")
    lead_dir = UPLOAD_DIR / str(lead.id)
    lead_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}{suffix}"
    path = lead_dir / stored_name
    path.write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()
    item = UploadedDocument(
        lead_id=lead.id, assessment_id=lead.assessment_id,
        file_name=Path(upload.filename or stored_name).name,
        file_path=str(path.relative_to(BASE_DIR)), file_type=suffix.lstrip("."),
        document_category=document_category, uploaded_by=user.id,
        file_size=len(content), file_hash=digest, parse_status="pending_parse",
    )
    db.add(item)
    db.flush()
    track_event(db, "document_uploaded", lead.assessment_id, lead.id,
                {"document_id": item.id, "file_name": item.file_name}, commit=False)
    notify_document_uploaded(db, lead, item, commit=False)
    db.commit()
    run_parse_task(db, item)
    logger.info("上传客户资料 lead_id=%s file=%s operator=%s", lead.id, item.file_name, user.username)
    return RedirectResponse(url=f"/admin/leads/{lead.id}/documents", status_code=303)


@router.post("/admin/leads/{lead_id}/documents/{document_id}/delete")
def delete_lead_document(
    request: Request,
    lead_id: int,
    document_id: int,
    delete_reason: str = Form("后台资料删除"),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin")),
):
    item = db.query(UploadedDocument).filter(
        UploadedDocument.id == document_id, UploadedDocument.lead_id == lead_id
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="文件记录不存在")
    item.deleted_at=datetime.now();item.deleted_by=_.id;item.delete_reason=delete_reason.strip()
    from services.audit_service import write_audit_log
    write_audit_log(db,"data_soft_deleted","uploaded_document",item.id,user_id=_.id,after={"reason":item.delete_reason},request=request,risk_level="critical");track_event(db,"data_soft_deleted",item.assessment_id,item.lead_id,{"document_id":item.id},commit=False);db.commit()
    return RedirectResponse(url=f"/admin/leads/{lead_id}/documents", status_code=303)
