import json
import hashlib
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
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
    AIGenerationLog, BankProduct, ConsultingCase, CustomerTask, DocumentParseTask, Lead, Report,
    ReportVersion, UploadedDocument, User,
)
from services.auth_service import require_roles
from services.event_service import track_event
from services.report_service import generate_full_report
from services.settings_service import get_setting
from services.document_parse_service import run_parse_task
from utils.logger import logger


router = APIRouter()
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
UPLOAD_DIR = BASE_DIR / "data" / "uploads"
ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".png", ".jpg", ".jpeg"}


def _report_or_404(db: Session, report_id: int) -> Report:
    report = db.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")
    return report


@router.get("/admin/reports/{report_id}/versions", response_class=HTMLResponse)
def report_versions(
    request: Request,
    report_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "sales", "viewer")),
):
    report = _report_or_404(db, report_id)
    versions = db.query(ReportVersion).filter(
        ReportVersion.report_id == report.id
    ).order_by(ReportVersion.version_no.desc()).all()
    return templates.TemplateResponse(
        request=request, name="admin_report_versions.html",
        context={"report_item": report, "versions": versions, "current_user": user},
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
    return templates.TemplateResponse(
        request=request, name="admin_report_version_detail.html",
        context={
            "report_item": report, "version": version,
            "report": json.loads(version.report_json), "current_user": user,
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
    from services.audit_service import write_audit_log
    write_audit_log(db,"report_rejected","report",report.id,user_id=user.id,after={"review_status":"rejected","note":report.review_note},request=request,risk_level="high")
    db.commit()
    logger.info("驳回报告 report_id=%s operator=%s", report.id, user.username)
    return RedirectResponse(url=f"/admin/reports/{report.id}", status_code=303)


@router.get("/admin/bank-products", response_class=HTMLResponse)
def bank_products_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "sales", "viewer")),
):
    return templates.TemplateResponse(
        request=request, name="admin_bank_products.html",
        context={
            "bank_products": db.query(BankProduct).order_by(BankProduct.id).all(),
            "current_user": user, "edit_item": None,
        },
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


@router.get("/admin/consulting-cases", response_class=HTMLResponse)
def consulting_cases(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "super_admin", "city_manager", "consultant_manager", "consultant", "sales_manager", "sales", "viewer")),
):
    scope = get_access_scope(db, user)
    query = db.query(ConsultingCase)
    if not scope.can_view_all:
        query = query.filter(ConsultingCase.owner_org_id.in_(scope.allowed_org_ids or [-1]))
        if scope.role == "consultant":
            query = query.filter(ConsultingCase.consultant_user_id == user.id)
    cases = query.order_by(ConsultingCase.updated_at.desc()).all()
    return templates.TemplateResponse(
        request=request, name="admin_consulting_cases.html",
        context={"cases": cases, "current_user": user},
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
