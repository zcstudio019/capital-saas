import csv
import io
import json
import secrets
from datetime import date, datetime, time, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from core.funnel_analytics import build_funnel_analytics
from core.pricing_engine import products, recommended_product_labels
from core.config import settings
from db.database import get_db
from db.models import (
    AIGenerationLog, Assessment, CustomerAccount, CustomerTask, Event, FollowTask, Lead, LeadFollowLog, Order,
    Organization, PilotBatch, ProjectTask, Report, ReportVersion, Tag, User
)
from core.access_scope import effective_role, get_access_scope
from core.next_best_action_engine import calculate_next_best_action
from core.pilot_sop_engine import pilot_sop_recommendation
from core.data_masking import mask_phone,mask_wechat
from services.auth_service import require_roles, update_password, verify_password
from services.audit_service import write_audit_log
from services.crm_service import list_leads, list_orders, list_reports
from services.event_service import track_event
from services.follow_task_service import create_manual_task
from services.follow_log_service import add_follow_log
from services.script_template_service import matched_scripts
from services.payment_service import cancel_order, mark_order_paid, refund_order
from services.report_service import generate_full_report, parse_report
from services.settings_service import SETTING_DEFINITIONS, save_settings, settings_dict
from services.consulting_service import ensure_consulting_case
from utils.logger import logger
from utils.display_labels import is_demo_or_test_record


router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))
BACKEND_READ_ROLES = ("admin", "super_admin", "city_manager", "sales_manager", "sales", "consultant_manager", "consultant", "finance", "viewer", "partner")
SALES_WRITE_ROLES = ("admin", "super_admin", "city_manager", "sales_manager", "sales")
ORDER_LIST_ROLES = ("admin", "super_admin", "city_manager", "sales_manager", "finance", "viewer")

def _visible_leads(db, user, items):
    scope=get_access_scope(db,user)
    if scope.can_view_all:return items
    if scope.role=="partner":return [x for x in items if x.source_partner_id in scope.allowed_partner_ids]
    if scope.role=="sales":return [x for x in items if x.owner_user_id==user.id or x.assigned_sales_id==user.id]
    return [x for x in items if x.owner_org_id in scope.allowed_org_ids or x.org_id in scope.allowed_org_ids]


def _sales_owns_lead(user: User, lead: Lead | None) -> bool:
    return bool(lead and (lead.assigned_sales_id == user.id or (not lead.assigned_sales_id and lead.owner_user_id == user.id)))


def _assert_lead_access(db: Session, user: User, lead: Lead | None) -> None:
    if not lead:
        raise HTTPException(status_code=404, detail="线索不存在")
    scope = get_access_scope(db, user)
    if scope.can_view_all:
        return
    if scope.role == "sales" and _sales_owns_lead(user, lead):
        return
    if scope.role not in {"sales", "partner"} and (lead.owner_org_id in scope.allowed_org_ids or lead.org_id in scope.allowed_org_ids):
        return
    raise HTTPException(status_code=403, detail="无权访问该线索")


def _dashboard_context(db: Session, show_test: bool = False) -> dict:
    today_start = datetime.combine(date.today(), time.min)
    demo_assessment_ids = [] if show_test else [x.id for x in db.query(Assessment).all() if is_demo_or_test_record(x.company_name)]
    demo_lead_ids = [] if show_test else [x.id for x in db.query(Lead).all() if is_demo_or_test_record((x.company_name, x.pilot_note))]
    today_count = db.query(Assessment).filter(Assessment.created_at >= today_start).count()
    paid_orders = db.query(Order).filter(Order.status == "paid").count()
    total_revenue = (
        db.query(func.coalesce(func.sum(Order.amount), 0))
        .filter(Order.status == "paid")
        .scalar()
    )
    average_score = db.query(func.coalesce(func.avg(Assessment.score), 0)).scalar()
    grades = {grade: 0 for grade in ["S", "A", "B", "C", "D"]}
    grades.update(
        dict(db.query(Assessment.grade, func.count(Assessment.id)).group_by(Assessment.grade).all())
    )
    today_leads = db.query(Lead).filter(Lead.created_at >= today_start).count()
    lead_s = db.query(Lead).filter(Lead.lead_grade == "S").count()
    lead_a = db.query(Lead).filter(Lead.lead_grade == "A").count()
    pending_leads = db.query(Lead).filter(Lead.follow_status == "待联系").count()
    high_value_leads = db.query(Lead).filter(Lead.lead_grade.in_(["S", "A"])).count()
    product_counts = {
        code: db.query(Order)
        .filter(Order.status == "paid", Order.product_code == code)
        .count()
        for code in products
    }
    now = datetime.now()
    today_end = datetime.combine(date.today(), time.max)
    today_pending_tasks = db.query(FollowTask).filter(
        FollowTask.status == "pending", FollowTask.due_time <= today_end
    ).count()
    overdue_tasks = db.query(FollowTask).filter(
        FollowTask.status == "pending", FollowTask.due_time < now
    ).count()
    high_priority_tasks = db.query(FollowTask).filter(
        FollowTask.status == "pending", FollowTask.priority == "high"
    ).count()

    assessment_trend = []
    order_trend = []
    for offset in range(6, -1, -1):
        day = date.today() - timedelta(days=offset)
        start = datetime.combine(day, time.min)
        end = datetime.combine(day, time.max)
        assessment_trend.append({
            "date": day.strftime("%m-%d"),
            "count": db.query(Assessment).filter(
                Assessment.created_at >= start, Assessment.created_at <= end
            ).count(),
        })
        order_trend.append({
            "date": day.strftime("%m-%d"),
            "count": db.query(Order).filter(
                Order.status == "paid", Order.paid_at >= start, Order.paid_at <= end
            ).count(),
        })
    product_revenue = {
        code: float(
            db.query(func.coalesce(func.sum(Order.amount), 0))
            .filter(Order.status == "paid", Order.product_code == code, Order.assessment_id.notin_(demo_assessment_ids or [-1]))
            .scalar()
            or 0
        )
        for code in products
    }
    recent_tasks = db.query(FollowTask).filter(FollowTask.status == "pending")
    if demo_lead_ids:
        recent_tasks = recent_tasks.filter(FollowTask.lead_id.notin_(demo_lead_ids))
    recent_events = db.query(Event).order_by(Event.created_at.desc()).limit(50).all()
    if not show_test:
        recent_events = [event for event in recent_events if event.assessment_id not in demo_assessment_ids and event.lead_id not in demo_lead_ids and not is_demo_or_test_record(event.event_data_json)]
    return {
        "today_count": today_count,
        "paid_orders": paid_orders,
        "total_revenue": total_revenue,
        "average_score": average_score,
        "grades": grades,
        "today_leads": today_leads,
        "lead_s": lead_s,
        "lead_a": lead_a,
        "pending_leads": pending_leads,
        "high_value_leads": high_value_leads,
        "product_counts": product_counts,
        "today_pending_tasks": today_pending_tasks,
        "overdue_tasks": overdue_tasks,
        "high_priority_tasks": high_priority_tasks,
        "funnel": build_funnel_analytics(db),
        "assessment_trend": assessment_trend,
        "order_trend": order_trend,
        "product_revenue": product_revenue,
        "recent_tasks": recent_tasks.order_by(FollowTask.due_time.asc()).limit(8).all(),
        "recent_events": recent_events[:10],
        "upcoming_project_tasks": db.query(ProjectTask).filter(
            ProjectTask.status == "pending"
        ).order_by(ProjectTask.due_time.asc()).limit(8).all(),
    }


@router.get("/admin", response_class=HTMLResponse)
def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*BACKEND_READ_ROLES)),
):
    role=effective_role(user)
    if role=="partner":
        scope=get_access_scope(db,user)
        if scope.allowed_partner_ids:return RedirectResponse(f"/admin/channel-partners/{scope.allowed_partner_ids[0]}",303)
    if role=="city_manager":return RedirectResponse('/admin/city-dashboard',303)
    if role in {"sales_manager","sales"}:return RedirectResponse('/sales/workbench',303)
    if role in {"consultant_manager","consultant"}:return RedirectResponse('/admin/delivery',303)
    return templates.TemplateResponse(
        request=request,
        name="admin_dashboard.html",
        context={**_dashboard_context(db, request.query_params.get("show_test") == "1"), "current_user": user},
    )


@router.get("/admin/leads", response_class=HTMLResponse)
def leads(
    request: Request,
    lead_grade: str = "",
    follow_status: str = "",
    recommended_product: str = "",
    source_channel: str = "",
    tag_id: int = 0,
    sales_user_id: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*BACKEND_READ_ROLES)),
):
    lead_items=_visible_leads(db,user,list_leads(db, lead_grade, follow_status, recommended_product, source_channel, tag_id))
    if sales_user_id and effective_role(user)!="sales":
        lead_items=[lead for lead in lead_items if lead.assigned_sales_id==sales_user_id or (not lead.assigned_sales_id and lead.owner_user_id==sales_user_id)]
    role=effective_role(user);contacts={}
    for item in lead_items:
        full=role=="super_admin" or (role=="sales" and _sales_owns_lead(user,item))
        contacts[item.id]={"phone":item.phone if full else mask_phone(item.phone),"wechat":item.wechat_id if full else mask_wechat(item.wechat_id)}
    return templates.TemplateResponse(
        request=request,
        name="admin_leads.html",
        context={
            "leads": lead_items,
            "contacts": contacts,
            "filters": {
                "lead_grade": lead_grade,
                "follow_status": follow_status,
                "recommended_product": recommended_product,
                "source_channel": source_channel,
                "tag_id": tag_id,
                "sales_user_id": sales_user_id,
            },
            "products": products,
            "product_labels": recommended_product_labels,
            "current_user": user,
            "tags": db.query(Tag).order_by(Tag.name).all(),
            "channels": [
                row[0] for row in db.query(Lead.source_channel).distinct().all() if row[0]
            ],
            "sales_users": db.query(User).filter(User.role == "sales", User.is_active.is_(True)).order_by(User.id).all(),
            "next_actions": {
                lead.id: calculate_next_best_action(
                    lead,
                    db.query(Order).filter(Order.assessment_id == lead.assessment_id).all(),
                    db.query(FollowTask).filter(FollowTask.lead_id == lead.id).all(),
                )
                for lead in lead_items
            },
        },
    )


@router.get("/admin/leads/{lead_id}", response_class=HTMLResponse)
def lead_detail(
    request: Request,
    lead_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*BACKEND_READ_ROLES)),
):
    lead = db.get(Lead, lead_id)
    _assert_lead_access(db,user,lead)
    if not lead:
        raise HTTPException(status_code=404, detail="线索不存在")
    if lead not in _visible_leads(db,user,[lead]): raise HTTPException(status_code=403,detail="无权查看该线索")
    try:
        sales_script = json.loads(lead.sales_script or "{}")
    except json.JSONDecodeError:
        sales_script = {}
    orders = db.query(Order).filter(Order.assessment_id == lead.assessment_id).all()
    tasks = db.query(FollowTask).filter(FollowTask.lead_id == lead.id).order_by(FollowTask.due_time).all()
    next_action = calculate_next_best_action(lead, orders, tasks)
    track_event(
        db, "next_best_action_viewed", assessment_id=lead.assessment_id, lead_id=lead.id,
        data={"next_action": next_action["next_action"], "operator": user.username}
    )
    return templates.TemplateResponse(
        request=request,
        name="admin_lead_detail.html",
        context={
            "lead": lead,
            "assessment": lead.assessment,
            "sales_script": sales_script,
            "products": products,
            "product_labels": recommended_product_labels,
            "tasks": tasks,
            "current_user": user,
            "can_edit": user.role in SALES_WRITE_ROLES,
            "next_action": next_action,
            "matched_scripts": matched_scripts(db, lead),
            "all_tags": db.query(Tag).order_by(Tag.name).all(),
            "lead_tags": [link.tag for link in lead.tag_links],
            "follow_logs": db.query(LeadFollowLog).filter(
                LeadFollowLog.lead_id == lead.id
            ).order_by(LeadFollowLog.created_at.desc()).all(),
            "sales_users": db.query(User).filter(User.role == "sales", User.is_active.is_(True)).all(),
            "organizations": db.query(Organization).filter(Organization.status=="active").all(),
            "customer_account": db.query(CustomerAccount).filter(CustomerAccount.lead_id==lead.id).first(),
            "customer_tasks": db.query(CustomerTask).filter(CustomerTask.lead_id==lead.id).order_by(CustomerTask.created_at.desc()).all(),
            "pilot_batches": db.query(PilotBatch).filter(PilotBatch.batch_status.in_(["planning","running","paused"])).order_by(PilotBatch.id.desc()).all(),
            "pilot_sop": pilot_sop_recommendation(lead.pilot_stage, lead.lead_grade, orders[-1].product_code if orders else ""),
        },
    )


@router.post("/admin/leads/{lead_id}/update")
def update_lead(
    lead_id: int,
    follow_status: str = Form(...),
    conversion_status: str = Form(...),
    next_follow_time: str = Form(""),
    last_follow_note: str = Form(""),
    assigned_sales: str = Form(""),
    assigned_sales_id: int = Form(0),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*SALES_WRITE_ROLES)),
):
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="线索不存在")
    _assert_lead_access(db,user,lead)
    if effective_role(user)=="sales":
        assigned_sales_id = lead.assigned_sales_id or lead.owner_user_id or 0
    old_follow, old_conversion, old_sales_id = lead.follow_status, lead.conversion_status, lead.assigned_sales_id
    lead.follow_status = follow_status.strip()
    lead.conversion_status = conversion_status.strip()
    lead.next_follow_time = datetime.fromisoformat(next_follow_time) if next_follow_time else None
    lead.last_follow_note = last_follow_note.strip()
    lead.assigned_sales = assigned_sales.strip()
    lead.assigned_sales_id = assigned_sales_id or None
    if lead.assigned_sales_id:
        lead.owner_user_id = lead.assigned_sales_id
    lead.updated_at = datetime.now()
    track_event(
        db, "lead_updated", assessment_id=lead.assessment_id, lead_id=lead.id,
        data={"operator": user.username, "follow_status": lead.follow_status}, commit=False
    )
    if old_follow != lead.follow_status:
        add_follow_log(db, lead.id, user, "follow_status_changed", "修改跟进状态", old_follow, lead.follow_status)
    if old_conversion != lead.conversion_status:
        add_follow_log(db, lead.id, user, "conversion_status_changed", "修改成交状态", old_conversion, lead.conversion_status)
    if last_follow_note.strip():
        add_follow_log(db, lead.id, user, "note_added", last_follow_note.strip())
    if old_sales_id != lead.assigned_sales_id:
        add_follow_log(db, lead.id, user, "sales_assigned", f"分配销售ID：{lead.assigned_sales_id or '未分配'}")
    if lead.conversion_status == "高客单意向":
        ensure_consulting_case(db, lead.assessment, "1999_structure_plan")
    db.commit()
    logger.info("线索更新 lead_id=%s operator=%s", lead.id, user.username)
    return RedirectResponse(url=f"/admin/leads/{lead_id}", status_code=303)


@router.post("/admin/leads/{lead_id}/assign-sales")
def assign_sales_to_lead(
    request: Request,
    lead_id: int,
    sales_user_id: int = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "super_admin", "sales_manager")),
):
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="线索不存在")
    sales_user = db.get(User, sales_user_id)
    if not sales_user or sales_user.role != "sales" or not sales_user.is_active:
        raise HTTPException(status_code=400, detail="请选择启用中的销售账号")
    old_sales_id = lead.assigned_sales_id or lead.owner_user_id
    lead.assigned_sales_id = sales_user.id
    lead.owner_user_id = sales_user.id
    lead.assigned_sales = sales_user.display_name or sales_user.username
    lead.updated_at = datetime.now()
    content = f"管理员将线索分配给销售{sales_user.display_name or sales_user.username}"
    add_follow_log(db, lead.id, user, "assign_sales", content, str(old_sales_id or ""), str(sales_user.id))
    track_event(db, "lead_sales_assigned", lead.assessment_id, lead.id, {"sales_user_id": sales_user.id, "operator": user.username}, commit=False)
    write_audit_log(db, "lead_sales_assigned", "lead", lead.id, user_id=user.id, before={"assigned_sales_id": old_sales_id}, after={"assigned_sales_id": sales_user.id}, request=request, risk_level="medium", commit=False)
    db.commit()
    return RedirectResponse(url="/admin/leads", status_code=303)


@router.post("/admin/leads/{lead_id}/tasks/create")
def create_lead_task(
    lead_id: int,
    task_type: str = Form(...),
    task_title: str = Form(...),
    task_content: str = Form(""),
    priority: str = Form(...),
    due_time: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*SALES_WRITE_ROLES)),
):
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="线索不存在")
    _assert_lead_access(db,user,lead)
    create_manual_task(
        db, lead, task_type, task_title.strip(), task_content.strip(),
        priority, datetime.fromisoformat(due_time)
    )
    logger.info("创建跟进任务 lead_id=%s operator=%s", lead.id, user.username)
    return RedirectResponse(url=f"/admin/leads/{lead_id}", status_code=303)


@router.get("/admin/follow-tasks", response_class=HTMLResponse)
def follow_tasks(
    request: Request,
    status: str = "",
    priority: str = "",
    lead_grade: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*BACKEND_READ_ROLES)),
):
    query = db.query(FollowTask).join(Lead)
    scope=get_access_scope(db,user)
    if not scope.can_view_all:
        if scope.role=="partner": query=query.filter(Lead.source_partner_id.in_(scope.allowed_partner_ids or [-1]))
        elif scope.role=="sales": query=query.filter(or_(Lead.owner_user_id==user.id,Lead.assigned_sales_id==user.id))
        else: query=query.filter(or_(Lead.owner_org_id.in_(scope.allowed_org_ids or [-1]),Lead.org_id.in_(scope.allowed_org_ids or [-1])))
    if status:
        query = query.filter(FollowTask.status == status)
    if priority:
        query = query.filter(FollowTask.priority == priority)
    if lead_grade:
        query = query.filter(Lead.lead_grade == lead_grade)
    return templates.TemplateResponse(
        request=request,
        name="admin_follow_tasks.html",
        context={
            "tasks": query.order_by(FollowTask.due_time.asc()).all(),
            "filters": {"status": status, "priority": priority, "lead_grade": lead_grade},
            "now": datetime.now(),
            "current_user": user,
            "can_edit": user.role in SALES_WRITE_ROLES,
        },
    )


def _update_task_status(db: Session, task_id: int, status: str, user: User) -> FollowTask:
    task = db.get(FollowTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    _assert_lead_access(db,user,db.get(Lead, task.lead_id))
    old_status = task.status
    task.status = status
    task.updated_at = datetime.now()
    if status == "done":
        track_event(
            db, "task_done", assessment_id=task.assessment_id, lead_id=task.lead_id,
            data={"task_id": task.id, "operator": user.username}, commit=False
        )
    add_follow_log(
        db, task.lead_id, user,
        "task_done" if status == "done" else "task_cancelled",
        f"{task.task_title}（任务#{task.id}）", old_status, status
    )
    db.commit()
    return task


@router.post("/admin/follow-tasks/{task_id}/done")
def done_task(
    task_id: int,
    next_url: str = Form("/admin/follow-tasks"),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*SALES_WRITE_ROLES)),
):
    _update_task_status(db, task_id, "done", user)
    return RedirectResponse(url=next_url, status_code=303)


@router.post("/admin/follow-tasks/{task_id}/cancel")
def cancel_task(
    task_id: int,
    next_url: str = Form("/admin/follow-tasks"),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*SALES_WRITE_ROLES)),
):
    _update_task_status(db, task_id, "cancelled", user)
    return RedirectResponse(url=next_url, status_code=303)


@router.get("/admin/reports", response_class=HTMLResponse)
def reports(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*BACKEND_READ_ROLES)),
):
    reports = list_reports(db)
    if effective_role(user) == "sales":
        allowed_assessment_ids = [lead.assessment_id for lead in db.query(Lead).filter(or_(Lead.assigned_sales_id == user.id, Lead.owner_user_id == user.id)).all()]
        reports = [report for report in reports if report.assessment_id in allowed_assessment_ids]
    return templates.TemplateResponse(
        request=request,
        name="admin_reports.html",
        context={"reports": reports, "current_user": user},
    )


@router.get("/admin/reports/{report_id}", response_class=HTMLResponse)
def report_detail(
    request: Request,
    report_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*BACKEND_READ_ROLES)),
):
    report = db.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")
    if report.assessment and report.assessment.lead:
        _assert_lead_access(db,user,report.assessment.lead)
    paid_orders = db.query(Order).filter(
        Order.assessment_id == report.assessment_id, Order.status == "paid"
    ).all()
    full = None
    if paid_orders or user.role == "admin":
        generate_full_report(db, report.assessment)
        _, full = parse_report(report)
    return templates.TemplateResponse(
        request=request,
        name="admin_report_detail.html",
        context={
            "report_item": report,
            "assessment": report.assessment,
            "lead": report.assessment.lead,
            "paid_orders": paid_orders,
            "report": full,
            "current_user": user,
            "site_base_url": settings.site_base_url.rstrip("/"),
            "versions": db.query(ReportVersion).filter(
                ReportVersion.report_id == report.id
            ).order_by(ReportVersion.version_no.desc()).all(),
            "ai_logs": db.query(AIGenerationLog).filter(
                AIGenerationLog.report_id == report.id
            ).order_by(AIGenerationLog.created_at.desc()).limit(50).all(),
        },
    )


@router.post("/admin/reports/{report_id}/generate-token")
def generate_report_token(
    report_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
):
    report = db.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")
    paid = db.query(Order).filter(
        Order.assessment_id == report.assessment_id, Order.status == "paid"
    ).first()
    if not paid:
        raise HTTPException(status_code=400, detail="未支付报告不能生成公开链接")
    if report.review_status != "approved":
        raise HTTPException(status_code=400, detail="报告审核通过后才能生成公开链接")
    report.public_token = secrets.token_urlsafe(32)
    report.token_expired_at = datetime.now() + timedelta(days=7)
    db.commit()
    logger.info("生成公开报告链接 report_id=%s operator=%s", report.id, user.username)
    return RedirectResponse(url=f"/admin/reports/{report_id}", status_code=303)


@router.get("/admin/orders", response_class=HTMLResponse)
def orders(
    request: Request,
    source_channel: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*ORDER_LIST_ROLES)),
):
    query = db.query(Order)
    scope=get_access_scope(db,user)
    if not scope.can_view_all:
        if scope.role=="partner":query=query.filter(Order.source_partner_id.in_(scope.allowed_partner_ids or [-1]))
        elif scope.role=="sales":query=query.filter(Order.owner_user_id==user.id)
        else:query=query.filter(or_(Order.owner_org_id.in_(scope.allowed_org_ids or [-1]),Order.org_id.in_(scope.allowed_org_ids or [-1])))
    if source_channel:
        query = query.filter(Order.source_channel == source_channel)
    return templates.TemplateResponse(
        request=request,
        name="admin_orders.html",
        context={
            "orders": query.order_by(Order.created_at.desc()).all(),
            "current_user": user,
            "source_channel": source_channel,
            "channels": [row[0] for row in db.query(Order.source_channel).distinct().all() if row[0]],
        },
    )


@router.get("/admin/orders/{order_id}", response_class=HTMLResponse)
def order_detail(
    request: Request,
    order_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*BACKEND_READ_ROLES)),
):
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    scope = get_access_scope(db, user)
    if not scope.can_view_all:
        if scope.role == "partner" and order.source_partner_id not in scope.allowed_partner_ids:
            raise HTTPException(status_code=403, detail="无权查看该订单")
        if scope.role == "sales" and order.owner_user_id != user.id:
            raise HTTPException(status_code=403, detail="无权查看该订单")
        if scope.role not in {"partner", "sales"} and order.owner_org_id not in scope.allowed_org_ids:
            raise HTTPException(status_code=403, detail="无权查看该订单")
    return templates.TemplateResponse(
        request=request,
        name="admin_order_detail.html",
        context={"order": order, "current_user": user},
    )


@router.post("/admin/orders/{order_id}/mark-paid")
def admin_mark_paid(
    request: Request,
    order_id: int,
    transaction_id: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
):
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    try:
        mark_order_paid(db, order, transaction_id, operator=user.username)
        generate_full_report(db, order.assessment)
        if order.assessment.lead:
            add_follow_log(
                db, order.assessment.lead.id, user, "order_marked_paid",
                f"订单#{order.id} {order.product_name} 已手动确认支付", commit=True
            )
        from services.audit_service import write_audit_log
        write_audit_log(db,"order_marked_paid","order",order.id,user_id=user.id,after={"status":"paid"},request=request,risk_level="critical",commit=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(url=f"/admin/orders/{order_id}", status_code=303)


@router.post("/admin/orders/{order_id}/refund")
def admin_refund(
    request: Request,
    order_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
):
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    try:
        refund_order(db, order, user.username)
        from services.audit_service import write_audit_log
        write_audit_log(db,"order_refunded","order",order.id,user_id=user.id,after={"status":"refunded"},request=request,risk_level="critical",commit=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(url=f"/admin/orders/{order_id}", status_code=303)


@router.post("/admin/orders/{order_id}/cancel")
def admin_cancel(
    request: Request,
    order_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
):
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    try:
        cancel_order(db, order, user.username)
        from services.audit_service import write_audit_log
        write_audit_log(db,"order_cancelled","order",order.id,user_id=user.id,after={"status":"cancelled"},request=request,risk_level="high",commit=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(url=f"/admin/orders/{order_id}", status_code=303)


@router.get("/admin/settings", response_class=HTMLResponse)
def settings_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
):
    return templates.TemplateResponse(
        request=request,
        name="admin_settings.html",
        context={
            "settings": settings_dict(db),
            "definitions": SETTING_DEFINITIONS,
            "current_user": user,
        },
    )


@router.post("/admin/settings")
def update_settings(
    request: Request,
    site_name: str = Form(...),
    company_name: str = Form(...),
    contact_phone: str = Form(""),
    contact_wechat: str = Form(""),
    report_price_299: str = Form(...),
    report_price_699: str = Form(...),
    report_price_1999: str = Form(...),
    ai_mode: str = Form(...),
    openai_model: str = Form(...),
    payment_mode: str = Form(...),
    enable_registration: str = Form("false"),
    report_review_required: str = Form("false"),
    upload_max_mb: str = Form("20"),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
):
    save_settings(db, {
        "site_name": site_name, "company_name": company_name,
        "contact_phone": contact_phone, "contact_wechat": contact_wechat,
        "report_price_299": report_price_299, "report_price_699": report_price_699,
        "report_price_1999": report_price_1999, "ai_mode": ai_mode,
        "openai_model": openai_model, "payment_mode": payment_mode,
        "enable_registration": enable_registration,
        "report_review_required": report_review_required,
        "upload_max_mb": upload_max_mb,
    })
    from services.audit_service import write_audit_log
    write_audit_log(db,"system_settings_updated","system_settings",None,user_id=user.id,request=request,risk_level="high",commit=True)
    logger.info("系统配置更新 operator=%s", user.username)
    return RedirectResponse(url="/admin/settings", status_code=303)


@router.post("/admin/settings/password")
def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
):
    if not verify_password(current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="当前密码错误")
    if len(new_password) < 10:
        raise HTTPException(status_code=400, detail="新密码至少10位")
    update_password(db, user, new_password)
    request.session["session_version"]=user.session_version
    from services.audit_service import write_audit_log
    write_audit_log(db,"password_changed","user",user.id,user_id=user.id,request=request,risk_level="high",commit=True)
    logger.info("管理员修改密码 user_id=%s", user.id)
    return RedirectResponse(url="/admin/settings", status_code=303)


def _csv_response(filename: str, headers: list[str], rows: list[list]) -> Response:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    writer.writerows(rows)
    content = "\ufeff" + output.getvalue()
    return Response(
        content=content.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/admin/export/leads.csv")
def export_leads(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin")),
):
    rows = db.query(Lead).order_by(Lead.id).all()
    return _csv_response("leads.csv", [
        "ID", "企业", "联系人", "手机号", "微信", "城市", "企业评分",
        "企业等级", "线索评分", "线索等级", "推荐产品", "跟进状态", "成交状态",
        "渠道", "活动", "落地页", "UTM来源", "UTM媒介", "UTM活动", "创建时间"
    ], [[
        x.id, x.company_name, x.contact_name, x.phone, x.wechat_id, x.city,
        x.assessment.score, x.assessment.grade, x.lead_score, x.lead_grade,
        x.recommended_product, x.follow_status, x.conversion_status,
        x.source_channel, x.source_campaign, x.source_landing_page,
        x.utm_source, x.utm_medium, x.utm_campaign, x.created_at
    ] for x in rows])


@router.get("/admin/export/orders.csv")
def export_orders(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin")),
):
    rows = db.query(Order).order_by(Order.id).all()
    return _csv_response("orders.csv", [
        "ID", "企业", "产品编码", "产品", "金额", "状态", "支付渠道",
        "交易号", "买家联系方式", "渠道", "活动", "落地页",
        "UTM来源", "UTM媒介", "UTM活动", "支付时间", "退款时间", "创建时间"
    ], [[
        x.id, x.assessment.company_name, x.product_code, x.product_name, x.amount,
        x.status, x.pay_channel, x.transaction_id, x.buyer_contact,
        x.source_channel, x.source_campaign, x.source_landing_page,
        x.utm_source, x.utm_medium, x.utm_campaign,
        x.paid_at, x.refund_at, x.created_at
    ] for x in rows])


@router.get("/admin/export/follow-tasks.csv")
def export_tasks(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin")),
):
    rows = db.query(FollowTask).order_by(FollowTask.id).all()
    return _csv_response("follow-tasks.csv", [
        "ID", "企业", "联系人", "线索等级", "任务类型", "任务标题",
        "优先级", "到期时间", "状态", "创建时间"
    ], [[
        x.id, x.lead.company_name, x.lead.contact_name, x.lead.lead_grade,
        x.task_type, x.task_title, x.priority, x.due_time, x.status, x.created_at
    ] for x in rows])
