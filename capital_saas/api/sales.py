import json
from datetime import date, datetime, time
from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from core.next_best_action_engine import calculate_next_best_action
from core.access_scope import get_access_scope
from db.database import get_db
from db.models import AdvisorBooking, FollowTask, Lead, Order, User
from services.auth_service import require_roles
from services.event_service import track_event
from services.script_template_service import matched_scripts
from utils.display_labels import is_demo_or_test_record


router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


@router.get("/sales/workbench", response_class=HTMLResponse)
def workbench(
    request: Request, db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "super_admin", "city_manager", "sales_manager", "sales")),
):
    show_test = request.query_params.get("show_test") == "1"
    lead_query = db.query(Lead)
    task_query = db.query(FollowTask).join(Lead)
    scope=get_access_scope(db,user)
    if not scope.can_view_all:
        if scope.role=="sales":
            lead_query=lead_query.filter((Lead.owner_user_id==user.id)|(Lead.assigned_sales_id==user.id));task_query=task_query.filter((Lead.owner_user_id==user.id)|(Lead.assigned_sales_id==user.id))
        else:
            lead_query=lead_query.filter(Lead.owner_org_id.in_(scope.allowed_org_ids or [-1]));task_query=task_query.filter(Lead.owner_org_id.in_(scope.allowed_org_ids or [-1]))
    leads = lead_query.order_by(Lead.updated_at.desc()).all()
    if not show_test:
        leads = [lead for lead in leads if not is_demo_or_test_record((lead.company_name, lead.pilot_note))]
    today_end = datetime.combine(date.today(), time.max)
    now = datetime.now()
    pending_tasks = task_query.filter(
        FollowTask.status == "pending", FollowTask.due_time <= today_end
    ).order_by(FollowTask.due_time).all()
    overdue_tasks = task_query.filter(
        FollowTask.status == "pending", FollowTask.due_time < now
    ).order_by(FollowTask.due_time).all()
    if not show_test:
        pending_tasks = [task for task in pending_tasks if not is_demo_or_test_record((task.lead.company_name, task.task_title, task.task_content))]
        overdue_tasks = [task for task in overdue_tasks if not is_demo_or_test_record((task.lead.company_name, task.task_title, task.task_content))]
    paid_query=db.query(Order).filter(Order.status=="paid")
    if not scope.can_view_all:
        if scope.role=="sales":
            assessment_ids=[lead.assessment_id for lead in leads]
            paid_query=paid_query.filter(Order.assessment_id.in_(assessment_ids or [-1]))
        else:
            paid_query=paid_query.filter(Order.owner_org_id.in_(scope.allowed_org_ids or [-1]))
    paid_orders=paid_query.order_by(Order.paid_at.desc()).limit(10).all()
    if not show_test:
        paid_orders = [order for order in paid_orders if not is_demo_or_test_record(order.assessment.company_name)]
    cards = []
    for lead in leads:
        orders = db.query(Order).filter(Order.assessment_id == lead.assessment_id).all()
        tasks = db.query(FollowTask).filter(FollowTask.lead_id == lead.id).all()
        cards.append({
            "lead": lead,
            "nba": calculate_next_best_action(lead, orders, tasks),
            "scripts": matched_scripts(db, lead)[:3],
        })
    track_event(db, "sales_workbench_viewed", data={"operator": user.username, "role": user.role})
    booking_query = db.query(AdvisorBooking)
    if not scope.can_view_all:
        if scope.role == "sales":
            lead_ids = [lead.id for lead in leads]
            booking_query = booking_query.filter(AdvisorBooking.lead_id.in_(lead_ids or [-1]))
        else:
            lead_ids = [lead.id for lead in leads]
            booking_query = booking_query.filter(AdvisorBooking.lead_id.in_(lead_ids or [-1]))
    advisor_bookings = booking_query.order_by(AdvisorBooking.created_at.desc()).limit(10).all()
    return templates.TemplateResponse(
        request=request, name="sales_workbench.html",
        context={
            "current_user": user, "lead_cards": cards,
            "pending_tasks": pending_tasks, "overdue_tasks": overdue_tasks,
            "high_value": [x for x in cards if x["lead"].lead_grade in {"S", "A"}],
            "paid_orders": paid_orders,
            "advisor_bookings": advisor_bookings,
            "contacted_leads": [lead for lead in leads if lead.follow_status in {"已联系", "跟进中", "已付款"}],
            "won_leads": [lead for lead in leads if lead.conversion_status in {"已成交", "已付款"}],
        },
    )


@router.get("/sales/leads", response_class=HTMLResponse)
def sales_leads(
    request: Request,
    user: User = Depends(require_roles("admin", "super_admin", "city_manager", "sales_manager", "sales")),
):
    query = urlencode(list(request.query_params.multi_items()))
    target = "/admin/leads" + (f"?{query}" if query else "")
    return RedirectResponse(url=target, status_code=303)


@router.get("/sales/leads/{lead_id}", response_class=HTMLResponse)
def sales_lead_detail(lead_id: int):
    return RedirectResponse(url=f"/admin/leads/{lead_id}", status_code=303)
