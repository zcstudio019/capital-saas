import json
import secrets
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from core.dropoff_analysis_engine import analyze_dropoff
from db.models import (
    Assessment,
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
)
from services.event_service import track_event
from services.tag_service import add_named_tag
from utils.display_labels import is_demo_or_test_record


STAGE_ORDER = {
    "invited": 1, "assessed": 2, "paid": 3, "report_viewed": 4,
    "documents_uploaded": 5, "consulting_started": 6, "project_created": 7,
    "completed": 8, "dropped": 0,
}


def set_pilot_stage(db: Session, lead: Lead | None, stage: str, commit: bool = False) -> None:
    if not lead or not lead.pilot_batch_id:
        return
    if STAGE_ORDER.get(stage, 0) >= STAGE_ORDER.get(lead.pilot_stage or "invited", 0):
        lead.pilot_stage = stage
    if stage == "paid":
        add_named_tag(db, lead, "付费意向强")
    elif stage == "documents_uploaded":
        add_named_tag(db, lead, "卡在资料上传")
    elif stage == "project_created":
        add_named_tag(db, lead, "真实融资项目")
    if commit:
        db.commit()


def bind_lead_to_pilot(db: Session, lead: Lead, batch_id: int, note: str = "", commit: bool = False) -> None:
    batch = db.get(PilotBatch, batch_id)
    if not batch:
        return
    lead.pilot_batch_id = batch.id
    lead.pilot_stage = lead.pilot_stage or "assessed"
    lead.pilot_note = note or lead.pilot_note
    add_named_tag(db, lead, "试运营客户")
    track_event(db, "lead_assigned_to_pilot", lead.assessment_id, lead.id, {"batch_id": batch.id}, commit=False)
    if commit:
        db.commit()


def bind_by_invite_code(db: Session, lead: Lead, invite_code: str, commit: bool = False) -> None:
    code = db.query(PilotInviteCode).filter_by(invite_code=invite_code, is_active=True).first()
    if not code:
        return
    if code.max_uses and code.used_count >= code.max_uses:
        return
    bind_lead_to_pilot(db, lead, code.pilot_batch_id, f"invite:{code.invite_code}", commit=False)
    code.used_count += 1
    track_event(db, "pilot_invite_used", lead.assessment_id, lead.id, {"invite_code": code.invite_code, "batch_id": code.pilot_batch_id}, commit=False)
    if commit:
        db.commit()


def create_invite_code(db: Session, batch_id: int, channel_name: str, max_uses: int = 0):
    code = PilotInviteCode(
        pilot_batch_id=batch_id,
        invite_code=secrets.token_urlsafe(6).replace("-", "").replace("_", "")[:10].upper(),
        channel_name=channel_name,
        max_uses=max_uses,
    )
    db.add(code)
    db.flush()
    track_event(db, "pilot_invite_code_created", data={"batch_id": batch_id, "invite_code": code.invite_code}, commit=False)
    return code


def pilot_counts(db: Session, batch_id: int | None = None, start=None, end=None, include_test: bool = True) -> dict:
    lead_q = db.query(Lead)
    if batch_id:
        lead_q = lead_q.filter(Lead.pilot_batch_id == batch_id)
    leads = lead_q.all()
    if not include_test:
        leads = [x for x in leads if not is_demo_or_test_record((x.company_name, x.pilot_note))]
    lead_ids = [x.id for x in leads]
    assessment_ids = [x.assessment_id for x in leads]
    def between(q, col):
        if start: q = q.filter(col >= start)
        if end: q = q.filter(col < end)
        return q
    orders = between(db.query(Order).filter(Order.status == "paid"), Order.created_at)
    docs = between(db.query(UploadedDocument), UploadedDocument.created_at)
    projects = between(db.query(FinancingProject), FinancingProject.created_at)
    feedback = between(db.query(CustomerFeedback), CustomerFeedback.created_at)
    issues = between(db.query(OperationIssue), OperationIssue.created_at)
    if batch_id:
        orders = orders.filter(Order.assessment_id.in_(assessment_ids or [-1]))
        docs = docs.filter(UploadedDocument.lead_id.in_(lead_ids or [-1]))
        projects = projects.filter(FinancingProject.lead_id.in_(lead_ids or [-1]))
        feedback = feedback.filter(CustomerFeedback.pilot_batch_id == batch_id)
        issues = issues.filter(OperationIssue.related_lead_id.in_(lead_ids or [-1]))
    return {
        "customers": len(lead_ids),
        "assessments": len(assessment_ids),
        "paid_orders": orders.count(),
        "revenue": sum(x.amount for x in orders.all()),
        "document_uploads": docs.count(),
        "projects": projects.count(),
        "feedback": feedback.count(),
        "issues": issues.count(),
    }


def funnel_counts(db: Session, batch_id: int | None = None, include_test: bool = True) -> dict:
    lead_q = db.query(Lead)
    if batch_id:
        lead_q = lead_q.filter(Lead.pilot_batch_id == batch_id)
    leads = lead_q.all()
    if not include_test:
        leads = [x for x in leads if not is_demo_or_test_record((x.company_name, x.pilot_note))]
    lead_ids = [x.id for x in leads]
    assessment_ids = [x.assessment_id for x in leads]
    event_q = db.query(Event)
    if assessment_ids:
        event_q = event_q.filter(Event.assessment_id.in_(assessment_ids))
    elif batch_id:
        event_q = event_q.filter(Event.id == -1)
    mapping = {
        "landing_view": ["landing_page_viewed"],
        "assessment_submitted": ["assessment_submitted"],
        "free_result_viewed": ["free_result_viewed"],
        "checkout_viewed": ["checkout_viewed"],
        "payment_success": ["payment_success"],
        "report_viewed": ["report_viewed", "client_report_viewed"],
        "document_uploaded": ["document_uploaded", "client_document_uploaded"],
        "consulting_case_created": ["consulting_case_created"],
        "financing_project_created": ["financing_project_created"],
    }
    counts = {}
    for key, events in mapping.items():
        counts[key] = event_q.filter(Event.event_type.in_(events)).count()
    return counts


def generate_daily_report(db: Session, date: datetime, batch_id: int | None, user_id: int | None):
    start = date.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    counts = pilot_counts(db, batch_id, start, end)
    visits = db.query(Event).filter(Event.event_type == "landing_page_viewed", Event.created_at >= start, Event.created_at < end).count()
    item = OperationDailyReport(
        report_date=start, pilot_batch_id=batch_id, visits_count=visits,
        assessments_count=counts["assessments"], leads_count=counts["customers"],
        paid_orders_count=counts["paid_orders"], revenue=counts["revenue"],
        document_upload_count=counts["document_uploads"], project_created_count=counts["projects"],
        feedback_count=counts["feedback"], issue_count=counts["issues"],
        key_findings=f"今日新增测评{counts['assessments']}，付费{counts['paid_orders']}，收入{counts['revenue']:.0f}元。",
        risks="关注未支付、未上传资料和高优先级问题。",
        next_actions="销售跟进支付卡点，顾问推进资料上传和尽调。",
        created_by=user_id,
    )
    db.add(item); db.flush()
    track_event(db, "daily_report_generated", data={"report_id": item.id, "batch_id": batch_id}, commit=False)
    return item


def generate_weekly_report(db: Session, week_start: datetime, batch_id: int | None, user_id: int | None):
    start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=7)
    counts = pilot_counts(db, batch_id, start, end)
    funnel = funnel_counts(db, batch_id)
    dropoff = analyze_dropoff(funnel)
    item = OperationWeeklyReport(
        week_start=start, week_end=end, pilot_batch_id=batch_id,
        total_visits=funnel.get("landing_view", 0), total_assessments=counts["assessments"],
        total_paid_orders=counts["paid_orders"], total_revenue=counts["revenue"],
        conversion_summary_json=json.dumps({"funnel": funnel, "dropoff": dropoff}, ensure_ascii=False),
        channel_summary_json=json.dumps({}, ensure_ascii=False),
        product_summary_json=json.dumps({}, ensure_ascii=False),
        feedback_summary_json=json.dumps({"feedback_count": counts["feedback"]}, ensure_ascii=False),
        issue_summary_json=json.dumps({"issue_count": counts["issues"]}, ensure_ascii=False),
        key_lessons=f"最大掉点：{dropoff['largest_dropoff_stage']}，掉点率{dropoff['dropoff_rate']}。",
        next_week_plan="围绕最大掉点优化话术、页面和交付动作。",
        created_by=user_id,
    )
    db.add(item); db.flush()
    track_event(db, "weekly_report_generated", data={"report_id": item.id, "batch_id": batch_id}, commit=False)
    return item
