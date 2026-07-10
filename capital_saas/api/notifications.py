from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from core.access_scope import get_access_scope
from db.database import get_db
from db.models import (
    CustomerAccount,
    InternalNotification,
    Lead,
    NotificationJob,
    NotificationLog,
    NotificationTemplate,
    User,
)
from services.auth_service import require_roles
from services.customer_portal_service import require_customer
from services.event_service import track_event
from services.notification_service import (
    cancel_notification_job,
    create_notification_job,
    get_preference,
    get_user_notifications,
    mark_all_notifications_read,
    mark_notification_read,
    send_now,
    validate_template_content,
)

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))

READ = (
    "admin", "super_admin", "city_manager", "sales_manager", "sales",
    "consultant_manager", "consultant", "finance", "viewer",
)
ADMIN = ("admin", "super_admin")


def _job(db: Session, job_id: int) -> NotificationJob:
    item = db.get(NotificationJob, job_id)
    if not item:
        raise HTTPException(404, "通知任务不存在")
    return item


def _template(db: Session, template_id: int) -> NotificationTemplate:
    item = db.get(NotificationTemplate, template_id)
    if not item:
        raise HTTPException(404, "通知模板不存在")
    return item


def _validate(title: str, content: str) -> None:
    try:
        validate_template_content(title, content)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


def _notification_or_403(db: Session, notification_id: int, user: User) -> InternalNotification:
    item = db.get(InternalNotification, notification_id)
    if not item:
        raise HTTPException(404, "通知不存在")
    if item.user_id == user.id or user.role in {"admin", "super_admin"}:
        return item
    raise HTTPException(403, "无权查看该通知")


def _jobs_for_user(db: Session, user: User):
    scope = get_access_scope(db, user)
    query = db.query(NotificationJob)
    if scope.can_view_all or scope.role in {"finance", "viewer"}:
        return query
    if scope.role in {"sales", "consultant"}:
        customer_ids = [
            row[0] for row in db.query(CustomerAccount.id)
            .join(Lead, Lead.id == CustomerAccount.lead_id)
            .filter(or_(Lead.owner_user_id == user.id, Lead.assigned_sales_id == user.id))
            .all()
        ]
        return query.filter(or_(
            NotificationJob.recipient_user_id == user.id,
            NotificationJob.recipient_customer_id.in_(customer_ids or [-1]),
        ))
    customer_ids = [
        row[0] for row in db.query(CustomerAccount.id)
        .join(Lead, Lead.id == CustomerAccount.lead_id)
        .filter(Lead.owner_org_id.in_(scope.allowed_org_ids or [-1]))
        .all()
    ]
    return query.filter(or_(
        NotificationJob.recipient_user_id.in_(scope.allowed_user_ids or [-1]),
        NotificationJob.recipient_customer_id.in_(customer_ids or [-1]),
    ))


@router.get("/admin/notifications", response_class=HTMLResponse)
def internal_notifications(
    request: Request,
    unread: int = 0,
    status: str = "",
    view: str = "mine",
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*READ)),
):
    selected_status = "unread" if unread else status
    if selected_status not in {"", "unread", "read", "archived"}:
        selected_status = ""
    can_view_all = user.role in {"admin", "super_admin"}
    selected_view = "all" if view == "all" and can_view_all else "mine"
    if selected_view == "all":
        query = db.query(InternalNotification)
        if selected_status:
            query = query.filter(InternalNotification.status == selected_status)
        items = query.order_by(InternalNotification.created_at.desc()).all()
    else:
        items = get_user_notifications(db, user.id, selected_status or None)
    user_ids = {item.user_id for item in items}
    notification_users = {
        item.id: item for item in db.query(User).filter(User.id.in_(user_ids or {-1})).all()
    }
    return templates.TemplateResponse(
        request=request,
        name="admin_notifications.html",
        context={
            "items": items,
            "unread": unread,
            "status": selected_status,
            "view": selected_view,
            "can_view_all_notifications": can_view_all,
            "notification_users": notification_users,
            "current_user": user,
        },
    )


@router.get("/admin/notifications/{notification_id}/open")
def open_notification(
    notification_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*READ)),
):
    item = _notification_or_403(db, notification_id, user)
    if item.user_id == user.id:
        mark_notification_read(db, notification_id, user.id, commit=True)
    if item.action_url:
        return RedirectResponse(item.action_url, 303)
    return RedirectResponse(f"/admin/notifications/{item.id}", 303)


@router.get("/admin/notifications/{notification_id}", response_class=HTMLResponse)
def notification_detail(
    request: Request,
    notification_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*READ)),
):
    item = _notification_or_403(db, notification_id, user)
    owner = db.get(User, item.user_id)
    return templates.TemplateResponse(
        request=request,
        name="admin_notification_detail.html",
        context={"item": item, "owner": owner, "current_user": user},
    )


@router.post("/admin/notifications/{notification_id}/read")
def read_notification(
    notification_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*READ)),
):
    item = _notification_or_403(db, notification_id, user)
    if item.user_id == user.id:
        mark_notification_read(db, notification_id, user.id, commit=True)
    return RedirectResponse("/admin/notifications", 303)


@router.post("/admin/notifications/read-all")
def read_all(db: Session = Depends(get_db), user: User = Depends(require_roles(*READ))):
    mark_all_notifications_read(db, user.id)
    return RedirectResponse("/admin/notifications", 303)


@router.get("/admin/notification-templates", response_class=HTMLResponse)
def template_list(request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles(*READ))):
    return templates.TemplateResponse(
        request=request,
        name="admin_notification_templates.html",
        context={
            "items": db.query(NotificationTemplate).order_by(NotificationTemplate.id).all(),
            "current_user": user,
            "can_edit": user.role in {"admin", "super_admin"},
        },
    )


@router.post("/admin/notification-templates/create")
def template_create(
    template_key: str = Form(...),
    template_name: str = Form(...),
    audience_type: str = Form(...),
    channel: str = Form(...),
    category: str = Form("service"),
    title_template: str = Form(...),
    content_template: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*ADMIN)),
):
    _validate(title_template, content_template)
    if db.query(NotificationTemplate).filter_by(template_key=template_key.strip()).first():
        raise HTTPException(400, "模板标识已存在")
    item = NotificationTemplate(
        template_key=template_key.strip(),
        template_name=template_name.strip(),
        audience_type=audience_type,
        channel=channel,
        category=category,
        title_template=title_template.strip(),
        content_template=content_template.strip(),
    )
    db.add(item)
    db.flush()
    track_event(db, "notification_template_created", data={"template_id": item.id}, commit=False)
    db.commit()
    return RedirectResponse("/admin/notification-templates", 303)


@router.post("/admin/notification-templates/{template_id}/update")
def template_update(
    template_id: int,
    template_name: str = Form(...),
    audience_type: str = Form(...),
    channel: str = Form(...),
    category: str = Form("service"),
    title_template: str = Form(...),
    content_template: str = Form(...),
    is_active: bool = Form(False),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*ADMIN)),
):
    _validate(title_template, content_template)
    item = _template(db, template_id)
    item.template_name = template_name.strip()
    item.audience_type = audience_type
    item.channel = channel
    item.category = category
    item.title_template = title_template.strip()
    item.content_template = content_template.strip()
    item.is_active = is_active
    item.updated_at = datetime.now()
    track_event(db, "notification_template_updated", data={"template_id": item.id}, commit=False)
    db.commit()
    return RedirectResponse("/admin/notification-templates", 303)


@router.post("/admin/notification-templates/{template_id}/test")
def template_test(template_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles(*ADMIN))):
    item = _template(db, template_id)
    job = create_notification_job(
        db,
        item.template_key,
        {
            "company_name": "测试企业",
            "task_title": "测试任务",
            "project_name": "测试项目",
            "status_label": "测试状态",
            "missing_documents": "测试资料",
            "document_name": "测试文件",
        },
        recipient_user_id=user.id,
        channel="mock",
        related_type="template_test",
        related_id=item.id,
    )
    send_now(db, job)
    track_event(db, "notification_test_sent", data={"template_id": item.id, "job_id": job.id})
    return RedirectResponse("/admin/notification-jobs", 303)


@router.get("/admin/notification-jobs", response_class=HTMLResponse)
def job_list(
    request: Request,
    status: str = "",
    channel: str = "",
    template_key: str = "",
    date_from: str = "",
    date_to: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*READ)),
):
    query = _jobs_for_user(db, user)
    if status:
        query = query.filter(NotificationJob.send_status == status)
    if channel:
        query = query.filter(NotificationJob.channel == channel)
    if template_key:
        query = query.filter(NotificationJob.template_key == template_key)
    if date_from:
        query = query.filter(NotificationJob.created_at >= datetime.fromisoformat(date_from))
    if date_to:
        query = query.filter(NotificationJob.created_at < datetime.fromisoformat(date_to) + timedelta(days=1))
    return templates.TemplateResponse(
        request=request,
        name="admin_notification_jobs.html",
        context={
            "items": query.order_by(NotificationJob.created_at.desc()).all(),
            "current_user": user,
            "filters": {
                "status": status,
                "channel": channel,
                "template_key": template_key,
                "date_from": date_from,
                "date_to": date_to,
            },
            "templates_list": db.query(NotificationTemplate).all(),
            "can_edit": user.role in {"admin", "super_admin"},
        },
    )


@router.post("/admin/notification-jobs/{job_id}/send-now")
def job_send(job_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles(*ADMIN))):
    send_now(db, _job(db, job_id))
    return RedirectResponse("/admin/notification-jobs", 303)


@router.post("/admin/notification-jobs/{job_id}/retry")
def job_retry(job_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles(*ADMIN))):
    job = _job(db, job_id)
    job.send_status = "queued"
    job.scheduled_at = datetime.now()
    track_event(db, "notification_retried", data={"job_id": job.id}, commit=False)
    db.commit()
    send_now(db, job)
    return RedirectResponse("/admin/notification-jobs", 303)


@router.post("/admin/notification-jobs/{job_id}/cancel")
def job_cancel(job_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles(*ADMIN))):
    cancel_notification_job(db, _job(db, job_id))
    return RedirectResponse("/admin/notification-jobs", 303)


@router.get("/admin/notification-dashboard", response_class=HTMLResponse)
def notification_dashboard(request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles(*READ))):
    query = _jobs_for_user(db, user)
    today = datetime.combine(datetime.now().date(), datetime.min.time())
    items = query.filter(NotificationJob.created_at >= today).all()
    channels = db.query(NotificationJob.channel, func.count(NotificationJob.id)).group_by(NotificationJob.channel).all()
    template_stats = (
        db.query(NotificationJob.template_key, func.count(NotificationJob.id))
        .group_by(NotificationJob.template_key)
        .order_by(func.count(NotificationJob.id).desc())
        .limit(15)
        .all()
    )
    delivery_count = (
        db.query(func.count())
        .select_from(NotificationLog)
        .filter(NotificationLog.status == "success", NotificationLog.created_at >= today)
        .scalar()
    )
    return templates.TemplateResponse(
        request=request,
        name="admin_notification_dashboard.html",
        context={
            "current_user": user,
            "today": len(items),
            "success": sum(item.send_status == "success" for item in items),
            "failed": sum(item.send_status == "failed" for item in items),
            "queued": sum(item.send_status == "queued" for item in items),
            "channels": channels,
            "template_stats": template_stats,
            "recent_failed": query.filter(NotificationJob.send_status == "failed").order_by(NotificationJob.failed_at.desc()).limit(10).all(),
            "recent_success": query.filter(NotificationJob.send_status == "success").order_by(NotificationJob.sent_at.desc()).limit(10).all(),
            "delivery_count": delivery_count,
        },
    )


@router.get("/admin/my-notification-preferences", response_class=HTMLResponse)
def user_preferences(request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles(*READ))):
    return templates.TemplateResponse(
        request=request,
        name="admin_notification_preferences.html",
        context={"preference": get_preference(db, user_id=user.id), "current_user": user},
    )


@router.post("/admin/my-notification-preferences/update")
def user_preferences_update(
    receive_in_app: bool = Form(False),
    receive_email: bool = Form(False),
    receive_wecom: bool = Form(False),
    quiet_hours_start: str = Form("22:00"),
    quiet_hours_end: str = Form("08:00"),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*READ)),
):
    preference = get_preference(db, user_id=user.id)
    preference.receive_in_app = receive_in_app
    preference.receive_email = receive_email
    preference.receive_wecom = receive_wecom
    preference.quiet_hours_start = quiet_hours_start
    preference.quiet_hours_end = quiet_hours_end
    track_event(db, "user_notification_preference_updated", data={"user_id": user.id}, commit=False)
    db.commit()
    return RedirectResponse("/admin/my-notification-preferences", 303)


@router.get("/client/preferences", response_class=HTMLResponse)
def client_preferences(request: Request, db: Session = Depends(get_db), customer=Depends(require_customer)):
    return templates.TemplateResponse(
        request=request,
        name="client_preferences.html",
        context={"customer": customer, "preference": get_preference(db, customer_id=customer.id)},
    )


@router.post("/client/preferences/update")
def client_preferences_update(
    receive_in_app: bool = Form(False),
    receive_email: bool = Form(False),
    receive_sms: bool = Form(False),
    quiet_hours_start: str = Form("22:00"),
    quiet_hours_end: str = Form("08:00"),
    is_unsubscribed: bool = Form(False),
    db: Session = Depends(get_db),
    customer=Depends(require_customer),
):
    preference = get_preference(db, customer_id=customer.id)
    preference.receive_in_app = receive_in_app
    preference.receive_email = receive_email
    preference.receive_sms = receive_sms
    preference.quiet_hours_start = quiet_hours_start
    preference.quiet_hours_end = quiet_hours_end
    preference.is_unsubscribed = is_unsubscribed
    track_event(db, "customer_notification_preference_updated", customer.assessment_id, customer.lead_id, {"customer_id": customer.id}, commit=False)
    db.commit()
    return RedirectResponse("/client/preferences", 303)
