import csv
import io
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from core.config import BASE_DIR, settings
from core.dropoff_analysis_engine import analyze_dropoff
from core.pilot_sop_engine import pilot_sop_recommendation
from db.database import get_db
from db.models import (
    CustomerAccount,
    CustomerFeedback,
    Event,
    FinancingProject,
    Lead,
    OperationDailyReport,
    OperationIssue,
    OperationWeeklyReport,
    Order,
    PilotBatch,
    PilotInviteCode,
    UploadedDocument,
    User,
)
from services.auth_service import require_roles
from services.customer_portal_service import require_customer
from services.event_service import track_event
from services.pilot_service import (
    bind_lead_to_pilot,
    create_invite_code,
    funnel_counts,
    generate_daily_report,
    generate_weekly_report,
    pilot_counts,
    set_pilot_stage,
)
from services.tag_service import add_named_tag

router = APIRouter()
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
ADMIN_ROLES = ("admin", "super_admin", "city_manager", "sales_manager", "sales", "consultant", "viewer")
WRITE_ROLES = ("admin", "super_admin", "city_manager", "sales_manager", "sales", "consultant")


def _batch(db: Session, batch_id: int) -> PilotBatch:
    item = db.get(PilotBatch, batch_id)
    if not item:
        raise HTTPException(404, "试运营批次不存在")
    return item


@router.get("/admin/pilot-batches", response_class=HTMLResponse)
def pilot_batches(request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles(*ADMIN_ROLES))):
    return templates.TemplateResponse(request=request, name="admin_pilot_batches.html", context={
        "items": db.query(PilotBatch).order_by(PilotBatch.id.desc()).all(),
        "users": db.query(User).filter(User.is_active.is_(True)).all(),
        "current_user": user,
        "can_edit": user.role in WRITE_ROLES,
    })


@router.post("/admin/pilot-batches/create")
def pilot_batch_create(
    batch_name: str = Form(...), start_date: str = Form(""), end_date: str = Form(""),
    target_customer_count: int = Form(0), target_paid_count: int = Form(0),
    target_revenue: float = Form(0), target_document_upload_count: int = Form(0),
    target_project_count: int = Form(0), owner_user_id: int = Form(0), note: str = Form(""),
    db: Session = Depends(get_db), user: User = Depends(require_roles(*WRITE_ROLES)),
):
    item = PilotBatch(
        batch_name=batch_name.strip(), batch_status="planning",
        start_date=datetime.fromisoformat(start_date) if start_date else None,
        end_date=datetime.fromisoformat(end_date) if end_date else None,
        target_customer_count=target_customer_count, target_paid_count=target_paid_count,
        target_revenue=target_revenue, target_document_upload_count=target_document_upload_count,
        target_project_count=target_project_count, owner_user_id=owner_user_id or user.id,
        note=note.strip(),
    )
    db.add(item); db.flush()
    track_event(db, "pilot_batch_created", data={"batch_id": item.id}, commit=False)
    db.commit()
    return RedirectResponse("/admin/pilot-batches", 303)


@router.post("/admin/pilot-batches/{batch_id}/update")
def pilot_batch_update(batch_id: int, batch_status: str = Form(...), note: str = Form(""), db: Session = Depends(get_db), user: User = Depends(require_roles(*WRITE_ROLES))):
    item = _batch(db, batch_id)
    item.batch_status = batch_status
    item.note = note.strip()
    item.updated_at = datetime.now()
    event = "pilot_batch_started" if batch_status == "running" else "pilot_batch_completed" if batch_status == "completed" else "pilot_batch_updated"
    track_event(db, event, data={"batch_id": item.id}, commit=False)
    db.commit()
    return RedirectResponse(f"/admin/pilot-batches/{batch_id}", 303)


@router.get("/admin/pilot-batches/{batch_id}", response_class=HTMLResponse)
def pilot_batch_detail(request: Request, batch_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles(*ADMIN_ROLES))):
    item = _batch(db, batch_id)
    counts = pilot_counts(db, batch_id)
    funnel = funnel_counts(db, batch_id)
    dropoff = analyze_dropoff(funnel)
    leads = db.query(Lead).filter(Lead.pilot_batch_id == batch_id).order_by(Lead.id.desc()).all()
    invites = db.query(PilotInviteCode).filter_by(pilot_batch_id=batch_id).order_by(PilotInviteCode.id.desc()).all()
    feedback_count = db.query(CustomerFeedback).filter_by(pilot_batch_id=batch_id).count()
    issues = db.query(OperationIssue).filter(OperationIssue.related_lead_id.in_([x.id for x in leads] or [-1])).count()
    return templates.TemplateResponse(request=request, name="admin_pilot_batch_detail.html", context={
        "batch": item, "counts": counts, "funnel": funnel, "dropoff": dropoff, "leads": leads,
        "invites": invites, "feedback_count": feedback_count, "issues": issues,
        "base_url": settings.site_base_url.rstrip("/"), "current_user": user, "can_edit": user.role in WRITE_ROLES,
    })


@router.post("/admin/pilot-batches/{batch_id}/invite-codes/create")
def pilot_invite_create(batch_id: int, channel_name: str = Form(""), max_uses: int = Form(0), db: Session = Depends(get_db), user: User = Depends(require_roles(*WRITE_ROLES))):
    _batch(db, batch_id)
    create_invite_code(db, batch_id, channel_name.strip(), max_uses)
    db.commit()
    return RedirectResponse(f"/admin/pilot-batches/{batch_id}", 303)


@router.post("/admin/pilot-invite-codes/{code_id}/disable")
def pilot_invite_disable(code_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles(*WRITE_ROLES))):
    item = db.get(PilotInviteCode, code_id)
    if not item:
        raise HTTPException(404, "邀请码不存在")
    item.is_active = False
    db.commit()
    return RedirectResponse(f"/admin/pilot-batches/{item.pilot_batch_id}", 303)


@router.post("/admin/leads/{lead_id}/assign-pilot-batch")
def assign_pilot_batch(lead_id: int, pilot_batch_id: int = Form(...), pilot_note: str = Form(""), db: Session = Depends(get_db), user: User = Depends(require_roles(*WRITE_ROLES))):
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(404, "线索不存在")
    bind_lead_to_pilot(db, lead, pilot_batch_id, pilot_note, commit=True)
    return RedirectResponse(f"/admin/leads/{lead_id}", 303)


@router.post("/admin/pilot-batches/{batch_id}/add-leads")
def add_leads_to_pilot(batch_id: int, lead_ids: str = Form(...), db: Session = Depends(get_db), user: User = Depends(require_roles(*WRITE_ROLES))):
    _batch(db, batch_id)
    ids = [int(x) for x in lead_ids.replace("\n", ",").split(",") if x.strip().isdigit()]
    for lead in db.query(Lead).filter(Lead.id.in_(ids or [-1])).all():
        bind_lead_to_pilot(db, lead, batch_id, "batch_add", commit=False)
    db.commit()
    return RedirectResponse(f"/admin/pilot-batches/{batch_id}", 303)


@router.get("/admin/pilot-dashboard", response_class=HTMLResponse)
def pilot_dashboard(request: Request, batch_id: int = 0, db: Session = Depends(get_db), user: User = Depends(require_roles(*ADMIN_ROLES))):
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    show_test = request.query_params.get("show_test") == "1"
    active = db.query(PilotBatch).filter(PilotBatch.batch_status == "running").order_by(PilotBatch.id.desc()).all()
    counts_today = pilot_counts(db, batch_id or None, today, today + timedelta(days=1), show_test)
    funnel = funnel_counts(db, batch_id or None, show_test)
    dropoff = analyze_dropoff(funnel)
    high_issues = db.query(OperationIssue).filter(OperationIssue.severity.in_(["high", "critical"]), OperationIssue.status.in_(["open", "in_progress"])).order_by(OperationIssue.id.desc()).limit(10).all()
    track_event(db, "dropoff_analysis_generated", data={"batch_id": batch_id, "largest": dropoff["largest_dropoff_stage"]}, commit=False)
    track_event(db, "pilot_sop_viewed", data={"user_id": user.id}, commit=False)
    db.commit()
    return templates.TemplateResponse(request=request, name="admin_pilot_dashboard.html", context={
        "batches": db.query(PilotBatch).order_by(PilotBatch.id.desc()).all(), "active_batches": active,
        "selected_batch_id": batch_id, "counts": counts_today, "funnel": funnel, "dropoff": dropoff,
        "high_issues": high_issues, "current_user": user,
    })


@router.get("/client/feedback", response_class=HTMLResponse)
def client_feedback(request: Request, db: Session = Depends(get_db), customer: CustomerAccount = Depends(require_customer)):
    items = db.query(CustomerFeedback).filter_by(customer_id=customer.id).order_by(CustomerFeedback.id.desc()).all()
    return templates.TemplateResponse(request=request, name="client_feedback.html", context={"customer": customer, "items": items})


@router.post("/client/feedback/submit")
def client_feedback_submit(
    feedback_type: str = Form(...), rating: int = Form(0), title: str = Form(...),
    content: str = Form(""), page_url: str = Form(""),
    db: Session = Depends(get_db), customer: CustomerAccount = Depends(require_customer),
):
    lead = db.get(Lead, customer.lead_id)
    item = CustomerFeedback(customer_id=customer.id, lead_id=customer.lead_id, assessment_id=customer.assessment_id,
        pilot_batch_id=lead.pilot_batch_id if lead else None, feedback_type=feedback_type, rating=rating,
        title=title.strip(), content=content.strip(), page_url=page_url.strip())
    db.add(item); db.flush()
    if lead and rating >= 4:
        add_named_tag(db, lead, "高反馈价值")
    track_event(db, "customer_feedback_submitted", customer.assessment_id, customer.lead_id, {"feedback_id": item.id, "rating": rating}, commit=False)
    db.commit()
    return RedirectResponse("/client/feedback", 303)


@router.get("/admin/feedback", response_class=HTMLResponse)
def admin_feedback(request: Request, status: str = "", db: Session = Depends(get_db), user: User = Depends(require_roles(*ADMIN_ROLES))):
    q = db.query(CustomerFeedback)
    if status:
        q = q.filter(CustomerFeedback.status == status)
    return templates.TemplateResponse(request=request, name="admin_feedback.html", context={"items": q.order_by(CustomerFeedback.id.desc()).all(), "filters": {"status": status}, "current_user": user, "can_edit": user.role in WRITE_ROLES})


@router.get("/admin/feedback/{feedback_id}", response_class=HTMLResponse)
def admin_feedback_detail(request: Request, feedback_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles(*ADMIN_ROLES))):
    item = db.get(CustomerFeedback, feedback_id)
    if not item:
        raise HTTPException(404, "反馈不存在")
    return templates.TemplateResponse(request=request, name="admin_feedback_detail.html", context={"item": item, "lead": db.get(Lead, item.lead_id) if item.lead_id else None, "current_user": user, "can_edit": user.role in WRITE_ROLES})


@router.post("/admin/feedback/{feedback_id}/update")
def admin_feedback_update(feedback_id: int, status: str = Form(...), handled_note: str = Form(""), db: Session = Depends(get_db), user: User = Depends(require_roles(*WRITE_ROLES))):
    item = db.get(CustomerFeedback, feedback_id)
    if not item:
        raise HTTPException(404, "反馈不存在")
    item.status = status
    item.handled_by = user.id
    item.handled_note = handled_note.strip()
    db.commit()
    return RedirectResponse(f"/admin/feedback/{feedback_id}", 303)


@router.post("/admin/feedback/{feedback_id}/convert-issue")
def feedback_convert_issue(feedback_id: int, severity: str = Form("medium"), db: Session = Depends(get_db), user: User = Depends(require_roles(*WRITE_ROLES))):
    fb = db.get(CustomerFeedback, feedback_id)
    if not fb:
        raise HTTPException(404, "反馈不存在")
    issue = OperationIssue(issue_type="operation_issue", source="customer_feedback", severity=severity,
        title=f"客户反馈：{fb.title}", description=fb.content, related_lead_id=fb.lead_id,
        related_customer_id=fb.customer_id, page_url=fb.page_url, created_by=user.id)
    db.add(issue); db.flush()
    track_event(db, "feedback_converted_to_issue", fb.assessment_id, fb.lead_id, {"issue_id": issue.id, "feedback_id": fb.id}, commit=False)
    db.commit()
    return RedirectResponse(f"/admin/issues/{issue.id}", 303)


@router.get("/admin/issues", response_class=HTMLResponse)
def issues_page(request: Request, severity: str = "", status: str = "", db: Session = Depends(get_db), user: User = Depends(require_roles(*ADMIN_ROLES))):
    q = db.query(OperationIssue)
    if severity: q = q.filter(OperationIssue.severity == severity)
    if status: q = q.filter(OperationIssue.status == status)
    return templates.TemplateResponse(request=request, name="admin_issues.html", context={"items": q.order_by(OperationIssue.id.desc()).all(), "users": db.query(User).filter(User.is_active.is_(True)).all(), "filters": {"severity": severity, "status": status}, "current_user": user, "can_edit": user.role in WRITE_ROLES})


@router.post("/admin/issues/create")
def issue_create(issue_type: str = Form(...), severity: str = Form(...), title: str = Form(...), description: str = Form(""), related_lead_id: int = Form(0), assigned_to: int = Form(0), db: Session = Depends(get_db), user: User = Depends(require_roles(*WRITE_ROLES))):
    issue = OperationIssue(issue_type=issue_type, source="admin_created", severity=severity, title=title.strip(), description=description.strip(), related_lead_id=related_lead_id or None, assigned_to=assigned_to or None, created_by=user.id)
    db.add(issue); db.flush()
    track_event(db, "operation_issue_created", data={"issue_id": issue.id, "severity": severity}, commit=False)
    db.commit()
    return RedirectResponse("/admin/issues", 303)


@router.get("/admin/issues/{issue_id}", response_class=HTMLResponse)
def issue_detail(request: Request, issue_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles(*ADMIN_ROLES))):
    item = db.get(OperationIssue, issue_id)
    if not item: raise HTTPException(404, "问题不存在")
    return templates.TemplateResponse(request=request, name="admin_issue_detail.html", context={"item": item, "current_user": user, "can_edit": user.role in WRITE_ROLES})


@router.post("/admin/issues/{issue_id}/update")
def issue_update(issue_id: int, status: str = Form(...), severity: str = Form(...), resolution_note: str = Form(""), assigned_to: int = Form(0), db: Session = Depends(get_db), user: User = Depends(require_roles(*WRITE_ROLES))):
    item = db.get(OperationIssue, issue_id)
    if not item: raise HTTPException(404, "问题不存在")
    item.status = status; item.severity = severity; item.resolution_note = resolution_note.strip(); item.assigned_to = assigned_to or None
    if status in {"resolved", "closed"}:
        track_event(db, "operation_issue_resolved", data={"issue_id": item.id}, commit=False)
    db.commit()
    return RedirectResponse(f"/admin/issues/{issue_id}", 303)


@router.get("/admin/daily-reports", response_class=HTMLResponse)
def daily_reports(request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles(*ADMIN_ROLES))):
    return templates.TemplateResponse(request=request, name="admin_daily_reports.html", context={"items": db.query(OperationDailyReport).order_by(OperationDailyReport.id.desc()).all(), "batches": db.query(PilotBatch).all(), "current_user": user})


@router.post("/admin/daily-reports/generate")
def daily_report_generate(report_date: str = Form(""), pilot_batch_id: int = Form(0), db: Session = Depends(get_db), user: User = Depends(require_roles(*WRITE_ROLES))):
    item = generate_daily_report(db, datetime.fromisoformat(report_date) if report_date else datetime.now(), pilot_batch_id or None, user.id)
    db.commit()
    return RedirectResponse(f"/admin/daily-reports/{item.id}", 303)


@router.get("/admin/daily-reports/{report_id}", response_class=HTMLResponse)
def daily_report_detail(request: Request, report_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles(*ADMIN_ROLES))):
    item = db.get(OperationDailyReport, report_id)
    if not item: raise HTTPException(404, "日报不存在")
    return templates.TemplateResponse(request=request, name="admin_daily_report_detail.html", context={"item": item, "current_user": user})


@router.get("/admin/weekly-reports", response_class=HTMLResponse)
def weekly_reports(request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles(*ADMIN_ROLES))):
    return templates.TemplateResponse(request=request, name="admin_weekly_reports.html", context={"items": db.query(OperationWeeklyReport).order_by(OperationWeeklyReport.id.desc()).all(), "batches": db.query(PilotBatch).all(), "current_user": user})


@router.post("/admin/weekly-reports/generate")
def weekly_report_generate(week_start: str = Form(""), pilot_batch_id: int = Form(0), db: Session = Depends(get_db), user: User = Depends(require_roles(*WRITE_ROLES))):
    item = generate_weekly_report(db, datetime.fromisoformat(week_start) if week_start else datetime.now(), pilot_batch_id or None, user.id)
    db.commit()
    return RedirectResponse(f"/admin/weekly-reports/{item.id}", 303)


@router.get("/admin/weekly-reports/{report_id}", response_class=HTMLResponse)
def weekly_report_detail(request: Request, report_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles(*ADMIN_ROLES))):
    item = db.get(OperationWeeklyReport, report_id)
    if not item: raise HTTPException(404, "周报不存在")
    return templates.TemplateResponse(request=request, name="admin_weekly_report_detail.html", context={"item": item, "current_user": user})


@router.get("/admin/leads/{lead_id}/journey", response_class=HTMLResponse)
def customer_journey(request: Request, lead_id: int, event_type: str = "", db: Session = Depends(get_db), user: User = Depends(require_roles(*ADMIN_ROLES))):
    lead = db.get(Lead, lead_id)
    if not lead: raise HTTPException(404, "线索不存在")
    q = db.query(Event).filter((Event.lead_id == lead.id) | (Event.assessment_id == lead.assessment_id))
    if event_type: q = q.filter(Event.event_type == event_type)
    track_event(db, "customer_journey_viewed", lead.assessment_id, lead.id, {"user_id": user.id})
    return templates.TemplateResponse(request=request, name="admin_customer_journey.html", context={"lead": lead, "events": q.order_by(Event.created_at.desc()).all(), "orders": db.query(Order).filter_by(assessment_id=lead.assessment_id).all(), "feedback": db.query(CustomerFeedback).filter_by(lead_id=lead.id).all(), "documents": db.query(UploadedDocument).filter_by(lead_id=lead.id).all(), "filters": {"event_type": event_type}, "current_user": user})


@router.get("/admin/pilot-batches/{batch_id}/export.csv")
def pilot_export(batch_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "super_admin", "city_manager", "sales_manager"))):
    _batch(db, batch_id)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["企业名称", "联系人", "手机", "渠道", "当前阶段", "线索等级", "已购产品", "订单金额", "是否上传资料", "是否立项", "客户反馈评分", "最近动作时间", "负责人", "下一步动作"])
    for lead in db.query(Lead).filter_by(pilot_batch_id=batch_id).all():
        paid = db.query(Order).filter_by(assessment_id=lead.assessment_id, status="paid").order_by(Order.id.desc()).first()
        has_doc = db.query(UploadedDocument).filter_by(lead_id=lead.id).first() is not None
        has_project = db.query(FinancingProject).filter_by(lead_id=lead.id).first() is not None
        feedback = db.query(CustomerFeedback).filter_by(lead_id=lead.id).order_by(CustomerFeedback.id.desc()).first()
        sop = pilot_sop_recommendation(lead.pilot_stage, lead.lead_grade, paid.product_code if paid else "")
        writer.writerow([lead.company_name, lead.contact_name, lead.phone, lead.source_channel, lead.pilot_stage, lead.lead_grade, paid.product_code if paid else "", paid.amount if paid else 0, "是" if has_doc else "否", "是" if has_project else "否", feedback.rating if feedback else "", lead.updated_at, lead.owner_user_id or lead.assigned_sales_id or "", sop["next_action"]])
    track_event(db, "pilot_export_downloaded", data={"batch_id": batch_id}, commit=False); db.commit()
    return Response(("\ufeff" + out.getvalue()).encode("utf-8"), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="pilot-batch-{batch_id}.csv"'})
