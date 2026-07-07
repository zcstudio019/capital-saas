import csv
import io
import os
import zipfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from core.config import settings
from core.access_scope import get_access_scope
from core.growth_analytics import build_growth_analytics
from db.database import get_db, engine
from db.models import (
    Assessment, Event, FollowTask, Lead, LeadTag, Order, Report,
    SalesScriptTemplate, Tag, User,
)
from services.ab_test_service import ab_metrics
from services.auth_service import require_roles
from services.event_service import track_event
from services.script_template_service import matched_scripts
from utils.logger import logger


router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


@router.get("/admin/growth", response_class=HTMLResponse)
def growth_dashboard(
    request: Request, db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "super_admin", "city_manager", "sales_manager", "sales", "consultant_manager", "consultant", "finance", "viewer", "partner")),
):
    scope = get_access_scope(db, user)
    return templates.TemplateResponse(
        request=request, name="admin_growth.html",
        context={"growth": build_growth_analytics(db, None if scope.can_view_all else scope.allowed_org_ids, request.query_params.get("show_test") == "1"), "current_user": user},
    )


@router.get("/admin/ab-tests", response_class=HTMLResponse)
def ab_tests(
    request: Request, db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "viewer")),
):
    return templates.TemplateResponse(
        request=request, name="admin_ab_tests.html",
        context={"rows": ab_metrics(db), "current_user": user},
    )


@router.get("/admin/script-templates", response_class=HTMLResponse)
def script_templates(
    request: Request, db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "sales", "viewer")),
):
    return templates.TemplateResponse(
        request=request, name="admin_script_templates.html",
        context={
            "templates_list": db.query(SalesScriptTemplate).order_by(SalesScriptTemplate.id).all(),
            "current_user": user, "can_edit": user.role == "admin",
        },
    )


@router.post("/admin/script-templates/create")
def create_script(
    name: str = Form(...), scenario: str = Form(...), lead_grade: str = Form(""),
    product_code: str = Form(""), content: str = Form(...),
    db: Session = Depends(get_db), user: User = Depends(require_roles("admin")),
):
    db.add(SalesScriptTemplate(
        name=name.strip(), scenario=scenario.strip(), lead_grade=lead_grade,
        product_code=product_code, content=content.strip(), is_active=True
    ))
    db.commit()
    return RedirectResponse("/admin/script-templates", status_code=303)


@router.post("/admin/script-templates/{template_id}/update")
def update_script(
    template_id: int, name: str = Form(...), scenario: str = Form(...),
    lead_grade: str = Form(""), product_code: str = Form(""),
    content: str = Form(...), is_active: str = Form("false"),
    db: Session = Depends(get_db), user: User = Depends(require_roles("admin")),
):
    item = db.get(SalesScriptTemplate, template_id)
    if not item:
        raise HTTPException(404, "话术模板不存在")
    item.name, item.scenario, item.lead_grade = name.strip(), scenario.strip(), lead_grade
    item.product_code, item.content = product_code, content.strip()
    item.is_active = is_active == "true"
    item.updated_at = datetime.now()
    db.commit()
    return RedirectResponse("/admin/script-templates", status_code=303)


@router.post("/admin/leads/{lead_id}/tags/add")
def add_tag(
    lead_id: int, tag_id: int = Form(...), db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "sales")),
):
    lead, tag = db.get(Lead, lead_id), db.get(Tag, tag_id)
    if not lead or not tag:
        raise HTTPException(404, "线索或标签不存在")
    if not db.query(LeadTag).filter(LeadTag.lead_id == lead_id, LeadTag.tag_id == tag_id).first():
        db.add(LeadTag(lead_id=lead_id, tag_id=tag_id))
        track_event(db, "lead_tag_added", assessment_id=lead.assessment_id, lead_id=lead.id,
                    data={"tag": tag.name, "operator": user.username}, commit=False)
        db.commit()
    return RedirectResponse(f"/admin/leads/{lead_id}", status_code=303)


@router.post("/admin/leads/{lead_id}/tags/{tag_id}/remove")
def remove_tag(
    lead_id: int, tag_id: int, db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "sales")),
):
    link = db.query(LeadTag).filter(LeadTag.lead_id == lead_id, LeadTag.tag_id == tag_id).first()
    lead, tag = db.get(Lead, lead_id), db.get(Tag, tag_id)
    if link:
        db.delete(link)
        track_event(db, "lead_tag_removed", assessment_id=lead.assessment_id, lead_id=lead.id,
                    data={"tag": tag.name if tag else tag_id, "operator": user.username}, commit=False)
        db.commit()
    return RedirectResponse(f"/admin/leads/{lead_id}", status_code=303)


@router.post("/api/events/script-copied")
def script_copied(
    lead_id: int = Form(...), template_id: int = Form(0),
    db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "sales")),
):
    lead = db.get(Lead, lead_id)
    track_event(db, "script_copied", assessment_id=lead.assessment_id if lead else None,
                lead_id=lead_id, data={"template_id": template_id, "operator": user.username})
    return {"ok": True}


@router.get("/admin/backup", response_class=HTMLResponse)
def backup_page(request: Request, user: User = Depends(require_roles("admin"))):
    return templates.TemplateResponse(
        request=request, name="admin_backup.html",
        context={"current_user": user, "app_env": settings.app_env},
    )


@router.get("/admin/backup/database")
def backup_database(
    db: Session = Depends(get_db), user: User = Depends(require_roles("admin")),
):
    if engine.dialect.name != "sqlite":
        raise HTTPException(400, "当前数据库不是SQLite")
    path = Path(engine.url.database).resolve()
    if not path.exists():
        raise HTTPException(404, "数据库文件不存在")
    track_event(db, "backup_downloaded", data={"type": "database", "operator": user.username})
    return FileResponse(path, filename=f"capital_saas_{date_stamp()}.db")


def date_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _csv_bytes(headers, rows) -> bytes:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    writer.writerows(rows)
    return ("\ufeff" + output.getvalue()).encode("utf-8")


@router.get("/admin/backup/business-zip")
def backup_business_zip(
    db: Session = Depends(get_db), user: User = Depends(require_roles("admin")),
):
    files = {
        "leads.csv": _csv_bytes(
            ["id", "company", "contact", "phone", "grade", "source", "status"],
            [[x.id, x.company_name, x.contact_name, x.phone, x.lead_grade, x.source_channel, x.conversion_status] for x in db.query(Lead).all()]
        ),
        "orders.csv": _csv_bytes(
            ["id", "assessment_id", "product", "amount", "status", "source"],
            [[x.id, x.assessment_id, x.product_code, x.amount, x.status, x.source_channel] for x in db.query(Order).all()]
        ),
        "reports.csv": _csv_bytes(
            ["id", "assessment_id", "unlocked", "created_at"],
            [[x.id, x.assessment_id, x.is_unlocked, x.created_at] for x in db.query(Report).all()]
        ),
        "follow_tasks.csv": _csv_bytes(
            ["id", "lead_id", "type", "title", "status", "due_time"],
            [[x.id, x.lead_id, x.task_type, x.task_title, x.status, x.due_time] for x in db.query(FollowTask).all()]
        ),
        "events.csv": _csv_bytes(
            ["id", "assessment_id", "lead_id", "type", "source", "created_at"],
            [[x.id, x.assessment_id, x.lead_id, x.event_type, x.source_channel, x.created_at] for x in db.query(Event).all()]
        ),
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for filename, content in files.items():
            archive.writestr(filename, content)
        archive.writestr("README.txt", "业务备份不包含users表、密码哈希或任何环境变量密钥。")
    track_event(db, "backup_downloaded", data={"type": "business_zip", "operator": user.username})
    return Response(
        content=buffer.getvalue(), media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="capital_saas_business_{date_stamp()}.zip"'}
    )


@router.post("/admin/dev/clear-test-data")
def clear_test_data(
    db: Session = Depends(get_db), user: User = Depends(require_roles("admin")),
):
    if settings.app_env != "development":
        raise HTTPException(403, "生产环境禁止清理测试数据")
    test_markers = ["示范", "成长供应链", "生产验证", "Phase5", "测试"]
    leads = db.query(Lead).all()
    assessment_ids = [
        x.assessment_id for x in leads
        if any(marker in (x.company_name or "") for marker in test_markers)
    ]
    if assessment_ids:
        db.query(Event).filter(Event.assessment_id.in_(assessment_ids)).delete(synchronize_session=False)
        db.query(FollowTask).filter(FollowTask.assessment_id.in_(assessment_ids)).delete(synchronize_session=False)
        db.query(LeadTag).filter(LeadTag.lead_id.in_(
            db.query(Lead.id).filter(Lead.assessment_id.in_(assessment_ids))
        )).delete(synchronize_session=False)
        from db.models import ABAssignment, LeadFollowLog
        db.query(ABAssignment).filter(ABAssignment.assessment_id.in_(assessment_ids)).delete(synchronize_session=False)
        db.query(LeadFollowLog).filter(LeadFollowLog.lead_id.in_(
            db.query(Lead.id).filter(Lead.assessment_id.in_(assessment_ids))
        )).delete(synchronize_session=False)
        db.query(Order).filter(Order.assessment_id.in_(assessment_ids)).delete(synchronize_session=False)
        db.query(Report).filter(Report.assessment_id.in_(assessment_ids)).delete(synchronize_session=False)
        db.query(Lead).filter(Lead.assessment_id.in_(assessment_ids)).delete(synchronize_session=False)
        db.query(Assessment).filter(Assessment.id.in_(assessment_ids)).delete(synchronize_session=False)
        db.commit()
    logger.info("清理测试数据 operator=%s count=%s", user.username, len(assessment_ids))
    return RedirectResponse("/admin/backup", status_code=303)
