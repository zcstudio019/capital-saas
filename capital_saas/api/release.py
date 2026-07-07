import json
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from core.config import BASE_DIR, settings
from db.database import get_db
from db.models import Assessment, Event, Lead, LegalDocument, NotificationJob, OperationIssue, Order, SetupProgress, User, WorkerRun
from services.auth_service import require_roles
from services.event_service import track_event
from services.release_service import flatten_preflight, get_git_commit, preflight_groups, read_version, setup_status
from services.backup_service import list_backups
from utils.display_labels import is_demo_or_test_record

router = APIRouter()
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
ADMIN = ("admin", "super_admin")


@router.get("/admin/setup-wizard", response_class=HTMLResponse)
def setup_wizard(request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles(*ADMIN))):
    track_event(db, "setup_wizard_viewed", data={"user_id": user.id})
    return templates.TemplateResponse(
        request=request,
        name="admin_setup_wizard.html",
        context={"steps": setup_status(db), "current_user": user},
    )


@router.post("/admin/setup-wizard/mark-step")
def setup_mark_step(step_key: str = Form(...), status: str = Form("completed"), db: Session = Depends(get_db), user: User = Depends(require_roles(*ADMIN))):
    item = db.query(SetupProgress).filter_by(step_key=step_key).first()
    if not item:
        item = SetupProgress(step_key=step_key)
        db.add(item)
    item.status = status
    item.completed_by = user.id if status == "completed" else None
    item.completed_at = datetime.now() if status == "completed" else None
    item.updated_at = datetime.now()
    track_event(db, "setup_step_completed", data={"step_key": step_key, "status": status, "user_id": user.id}, commit=False)
    db.commit()
    return Response(status_code=303, headers={"Location": "/admin/setup-wizard"})


@router.get("/admin/launch-dashboard", response_class=HTMLResponse)
def launch_dashboard(request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles(*ADMIN))):
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    show_test = request.query_params.get("show_test") == "1"
    demo_assessment_ids = [] if show_test else [x.id for x in db.query(Assessment).all() if is_demo_or_test_record(x.company_name)]
    demo_lead_ids = [] if show_test else [x.id for x in db.query(Lead).all() if is_demo_or_test_record((x.company_name, x.pilot_note))]
    paid_orders = db.query(Order).filter(Order.status == "paid", Order.created_at >= today, Order.assessment_id.notin_(demo_assessment_ids or [-1]))
    metrics = {
        "assessment_views": db.query(Event).filter(Event.event_type.in_(["landing_page_viewed", "assessment_page_viewed"]), Event.created_at >= today).count(),
        "assessments": db.query(Assessment).filter(Assessment.created_at >= today, Assessment.id.notin_(demo_assessment_ids or [-1])).count(),
        "leads": db.query(Lead).filter(Lead.created_at >= today, Lead.id.notin_(demo_lead_ids or [-1])).count(),
        "orders": paid_orders.count(),
        "revenue": sum(x.amount for x in paid_orders.all()),
        "client_logins": db.query(Event).filter(Event.event_type == "customer_logged_in", Event.created_at >= today).count(),
        "uploads": db.query(Event).filter(Event.event_type.in_(["document_uploaded", "client_document_uploaded"]), Event.created_at >= today).count(),
        "notifications": db.query(Event).filter(Event.event_type == "notification_sent", Event.created_at >= today).count(),
        "errors": db.query(Event).filter(Event.event_type.in_(["unhandled_exception", "notification_failed"]), Event.created_at >= today).count(),
        "rate_limits": db.query(Event).filter(Event.event_type == "rate_limit_blocked", Event.created_at >= today).count(),
    }
    workers = {name: db.query(WorkerRun).filter_by(worker_name=name).order_by(WorkerRun.id.desc()).first() for name in ["notification_worker", "reminder_scan", "daily_backup"]}
    recent_events = db.query(Event).order_by(Event.created_at.desc()).limit(50).all()
    error_events = db.query(Event).filter(Event.event_type.in_(["unhandled_exception", "notification_failed", "rate_limit_blocked"])).order_by(Event.created_at.desc()).limit(50).all()
    if not show_test:
        recent_events = [x for x in recent_events if x.assessment_id not in demo_assessment_ids and x.lead_id not in demo_lead_ids and not is_demo_or_test_record(x.event_data_json)]
        error_events = [x for x in error_events if x.assessment_id not in demo_assessment_ids and x.lead_id not in demo_lead_ids and not is_demo_or_test_record(x.event_data_json)]
    track_event(db, "launch_dashboard_viewed", data={"user_id": user.id})
    return templates.TemplateResponse(
        request=request,
        name="admin_launch_dashboard.html",
        context={
            "metrics": metrics,
            "events": recent_events[:10],
            "errors": error_events[:10],
            "workers": workers,
            "backups": list_backups()[:3],
            "high_issues": db.query(OperationIssue).filter(OperationIssue.severity.in_(["high","critical"]), OperationIssue.status.in_(["open","in_progress"])).order_by(OperationIssue.id.desc()).limit(10).all(),
            "current_user": user,
        },
    )


@router.get("/admin/release-notes", response_class=HTMLResponse)
def release_notes(request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles(*ADMIN))):
    changelog = BASE_DIR / "CHANGELOG.md"
    track_event(db, "release_notes_viewed", data={"user_id": user.id})
    return templates.TemplateResponse(
        request=request,
        name="admin_release_notes.html",
        context={
            "version": read_version(),
            "changelog": changelog.read_text(encoding="utf-8") if changelog.exists() else "暂无变更日志",
            "started_at": getattr(request.app.state, "started_at", None),
            "route_count": len(request.app.routes),
            "git_commit": get_git_commit(),
            "current_user": user,
        },
    )


@router.get("/admin/production-checklist", response_class=HTMLResponse)
def phase13_production_checklist(request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles(*ADMIN))):
    groups = preflight_groups(db)
    track_event(db, "production_checklist_viewed", data={"user_id": user.id})
    return templates.TemplateResponse(
        request=request,
        name="admin_production_checklist.html",
        context={"groups": groups, "checks": flatten_preflight(groups), "current_user": user},
    )


@router.get("/robots.txt")
def robots(request: Request, db: Session = Depends(get_db)):
    track_event(db, "robots_viewed", data={})
    return PlainTextResponse("User-agent: *\nAllow: /\nDisallow: /admin\nDisallow: /client\nSitemap: " + settings.site_base_url.rstrip("/") + "/sitemap.xml\n")


@router.get("/sitemap.xml")
def sitemap(request: Request, db: Session = Depends(get_db)):
    track_event(db, "sitemap_viewed", data={})
    urls = ["", "/lp/rongzi", "/lp/cashflow", "/lp/bank", "/lp/boss", "/legal/privacy", "/legal/terms", "/legal/disclaimer", "/legal/data-authorization"]
    base = settings.site_base_url.rstrip("/")
    body = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for url in urls:
        body.append(f"<url><loc>{base}{url}</loc></url>")
    body.append("</urlset>")
    return Response("\n".join(body), media_type="application/xml")


LEGAL_KEYS = {
    "privacy": "privacy_policy",
    "terms": "user_agreement",
    "disclaimer": "financing_service_disclaimer",
    "data-authorization": "data_authorization",
}


@router.get("/legal/{page_key}", response_class=HTMLResponse)
def public_legal_page(request: Request, page_key: str, db: Session = Depends(get_db)):
    doc_key = LEGAL_KEYS.get(page_key)
    if not doc_key:
        raise HTTPException(404, "法律页面不存在")
    doc = db.query(LegalDocument).filter_by(document_key=doc_key, is_active=True).order_by(LegalDocument.id.desc()).first()
    if not doc:
        raise HTTPException(404, "法律文档尚未配置")
    track_event(db, "public_legal_page_viewed", data={"page_key": page_key})
    return templates.TemplateResponse(request=request, name="public_legal.html", context={"doc": doc, "page_key": page_key})
