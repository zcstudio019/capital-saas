import csv
import hashlib
import io
import json
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_
from sqlalchemy.orm import Session

from core.access_scope import get_access_scope
from core.assessment_autofill_engine import build_autofill_suggestions
from core.bank_product_matcher import match_bank_products
from core.config import BASE_DIR, settings
from core.document_completeness_engine import check_document_completeness
from core.document_request_script_engine import generate_document_request_script
from core.scoring_engine import calculate_score
from db.database import get_db
from db.models import (BankProduct, ConsultingCase, DocumentParseTask, DueDiligenceReport,
    FinancingApplicationPackage, Lead, UploadedDocument, User)
from services.auth_service import require_roles
from services.document_parse_service import classify_document, run_parse_task
from services.due_diligence_service import generate_due_diligence
from services.event_service import track_event
from services.follow_log_service import add_follow_log
from services.notification_service import notify_document_uploaded
from services.settings_service import get_setting

router = APIRouter()
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
UPLOAD_ROOT = BASE_DIR / "data" / "uploads"
ALLOWED = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".png", ".jpg", ".jpeg"}
CATEGORIES = [
    "营业执照/工商资料", "财务报表", "银行流水", "纳税资料", "征信资料",
    "经营合同", "应收账款资料", "抵押物资料", "法人/股东资料", "其他资料",
]
AUTOFILL_FIELDS = {"annual_revenue", "net_profit", "monthly_cashflow", "debt_total", "short_debt",
    "receivable_days", "tax_status", "credit_status", "has_collateral", "funding_purpose"}


def _lead(db, lead_id):
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(404, "线索不存在")
    return lead


def _document(db, document_id):
    document = db.get(UploadedDocument, document_id)
    if not document:
        raise HTTPException(404, "资料不存在")
    return document


def _analysis(db, lead):
    documents = db.query(UploadedDocument).filter(UploadedDocument.lead_id == lead.id,UploadedDocument.deleted_at.is_(None)).order_by(UploadedDocument.created_at.desc()).all()
    matches = match_bank_products(db, lead.assessment)
    completeness = check_document_completeness(lead, lead.assessment, documents, lead.recommended_product, matches)
    return documents, completeness, generate_document_request_script(
        lead.company_name, lead.contact_name, completeness["missing_required_documents"])


def _assert_document_center_access(db: Session, lead: Lead, user: User, *, write: bool = False) -> bool:
    if write and user.role == "viewer":
        raise HTTPException(403, "只读账号不能上传资料")
    if user.role == "viewer":
        return False
    scope = get_access_scope(db, user)
    if scope.can_view_all:
        can_upload = user.role in {"admin", "super_admin"}
        if write and not can_upload:
            raise HTTPException(403, "无权上传该客户资料")
        return can_upload
    if scope.role == "sales":
        if lead.assigned_sales_id == user.id or lead.owner_user_id == user.id:
            return True
        raise HTTPException(403, "无权访问该客户资料")
    if scope.role == "consultant":
        case = db.query(ConsultingCase).filter(
            ConsultingCase.lead_id == lead.id,
            or_(ConsultingCase.consultant_user_id == user.id, ConsultingCase.consultant_id == user.id),
        ).first()
        if case:
            return True
        raise HTTPException(403, "无权访问该客户资料")
    if lead.owner_org_id in scope.allowed_org_ids or lead.org_id in scope.allowed_org_ids:
        can_upload = user.role in {"admin", "super_admin"}
        if write and not can_upload:
            raise HTTPException(403, "无权上传该客户资料")
        return can_upload
    raise HTTPException(403, "无权访问该客户资料")


@router.get("/admin/leads/{lead_id}/document-center", response_class=HTMLResponse)
def document_center(request: Request, lead_id: int, duplicate: int = 0,
    uploaded: int = 0, db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "super_admin", "sales_manager", "sales", "consultant_manager", "consultant", "viewer"))):
    lead = _lead(db, lead_id)
    can_upload = _assert_document_center_access(db, lead, user)
    documents, completeness, script = _analysis(db, lead)
    groups = {category: [d for d in documents if d.document_category == category] for category in CATEGORIES}
    return templates.TemplateResponse(request=request, name="admin_document_center.html", context={
        "lead": lead, "documents": documents, "groups": groups, "completeness": completeness,
        "request_script": script, "categories": CATEGORIES, "duplicate_count": duplicate,
        "uploaded_count": uploaded,
        "max_mb": int(get_setting(db, "upload_max_mb", str(settings.upload_max_mb))),
        "parse_tasks": db.query(DocumentParseTask).filter(DocumentParseTask.lead_id == lead.id).order_by(DocumentParseTask.created_at.desc()).limit(50).all(),
        "current_user": user, "can_upload": can_upload, "can_delete": user.role in {"admin", "super_admin"}})


@router.post("/admin/leads/{lead_id}/document-center/upload")
@router.post("/admin/leads/{lead_id}/documents/upload")
async def upload_documents(request:Request,lead_id: int, document_category: str = Form("其他资料"), note: str = Form(""),
    uploads: list[UploadFile] = File(...), db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "super_admin", "sales_manager", "sales", "consultant_manager", "consultant"))):
    lead = _lead(db, lead_id)
    _assert_document_center_access(db, lead, user, write=True)
    max_bytes = int(get_setting(db, "upload_max_mb", str(settings.upload_max_mb))) * 1024 * 1024
    prepared = []
    from utils.file_security import enforce_lead_total,validate_upload_metadata
    from services.audit_service import write_audit_log
    for upload in uploads:
        try:name,suffix=validate_upload_metadata(upload)
        except HTTPException as exc:track_event(db,'file_security_rejected',lead.assessment_id,lead.id,{'reason':str(exc.detail)});raise
        content = await upload.read(max_bytes + 1)
        if not content:
            raise HTTPException(400, f"文件 {name} 为空")
        if len(content) > max_bytes:
            raise HTTPException(400, f"文件 {name} 超过上传限制")
        enforce_lead_total(db,lead.id,len(content),int(get_setting(db,"max_lead_upload_mb",str(settings.max_lead_upload_mb))))
        prepared.append((name, suffix, content, hashlib.sha256(content).hexdigest()))
    lead_dir = UPLOAD_ROOT / str(lead.id)
    lead_dir.mkdir(parents=True, exist_ok=True)
    created, duplicates = [], 0
    for name, suffix, content, digest in prepared:
        duplicate = db.query(UploadedDocument).filter(UploadedDocument.lead_id == lead.id,
            UploadedDocument.file_hash == digest).first()
        duplicates += int(bool(duplicate))
        path = lead_dir / f"{uuid.uuid4().hex}{suffix}"
        path.write_bytes(content)
        item = UploadedDocument(lead_id=lead.id, assessment_id=lead.assessment_id, file_name=name,
            file_path=str(path.relative_to(BASE_DIR)), file_type=suffix.lstrip("."),
            document_category=classify_document(name, document_category), uploaded_by=user.id,
            file_size=len(content), file_hash=digest, note=note.strip())
        db.add(item); db.flush(); created.append(item)
        track_event(db, "document_uploaded", lead.assessment_id, lead.id,
            {"document_id": item.id, "file_name": name, "duplicate": bool(duplicate)}, commit=False)
        write_audit_log(db,"document_uploaded","uploaded_document",item.id,user_id=user.id,
            after={"file_name":name,"size":len(content)},request=request,risk_level="medium")
        notify_document_uploaded(db, lead, item, commit=False)
    db.commit()
    for item in created:
        run_parse_task(db, item)
    return RedirectResponse(f"/admin/leads/{lead.id}/document-center?duplicate={duplicates}&uploaded={len(created)}", 303)


@router.post("/admin/documents/{document_id}/parse")
def parse_document_route(document_id: int, db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin", "sales"))):
    document = _document(db, document_id); run_parse_task(db, document)
    return RedirectResponse(f"/admin/leads/{document.lead_id}/document-center", 303)


@router.post("/admin/documents/{document_id}/reparse")
def reparse_document_route(document_id: int, db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin", "sales"))):
    document = _document(db, document_id); run_parse_task(db, document, True)
    return RedirectResponse(f"/admin/leads/{document.lead_id}/document-center", 303)


@router.post("/admin/documents/{document_id}/verify")
def verify_document(document_id: int, verify_status: str = Form(...), db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin"))):
    if verify_status not in {"verified", "rejected"}:
        raise HTTPException(400, "无效核验状态")
    document = _document(db, document_id)
    document.verify_status, document.parse_status = verify_status, verify_status
    document.verified_by, document.verified_at = user.id, datetime.now()
    if verify_status == "verified":
        track_event(db, "document_verified", document.assessment_id, document.lead_id,
            {"document_id": document.id}, commit=False)
    db.commit()
    return RedirectResponse(f"/admin/leads/{document.lead_id}/document-center", 303)


@router.post("/admin/documents/{document_id}/delete")
def delete_document(request:Request,document_id: int,delete_reason:str=Form("后台资料删除"), db: Session = Depends(get_db), user: User = Depends(require_roles("admin"))):
    document = _document(db, document_id); lead_id = document.lead_id
    document.deleted_at=datetime.now();document.deleted_by=user.id;document.delete_reason=delete_reason.strip()
    from services.audit_service import write_audit_log
    write_audit_log(db,"data_soft_deleted","uploaded_document",document.id,user_id=user.id,after={"reason":document.delete_reason},request=request,risk_level="critical");track_event(db,"data_soft_deleted",document.assessment_id,document.lead_id,{"document_id":document.id},commit=False);db.commit()
    return RedirectResponse(f"/admin/leads/{lead_id}/document-center", 303)


@router.get("/admin/leads/{lead_id}/due-diligence", response_class=HTMLResponse)
def due_diligence_page(request: Request, lead_id: int, db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "sales", "viewer"))):
    lead = _lead(db, lead_id)
    dd = db.query(DueDiligenceReport).filter(DueDiligenceReport.lead_id == lead.id).first()
    parsed = {} if not dd else {"company": json.loads(dd.extracted_company_json),
        "financial": json.loads(dd.extracted_financial_json), "documents": json.loads(dd.document_summary_json),
        "risks": json.loads(dd.risk_summary_json)}
    return templates.TemplateResponse(request=request, name="admin_due_diligence.html", context={
        "lead": lead, "dd": dd, "parsed": parsed, "current_user": user, "can_edit": user.role in {"admin", "sales"}})


@router.post("/admin/leads/{lead_id}/due-diligence/generate")
def generate_dd(lead_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "sales"))):
    lead = _lead(db, lead_id); generate_due_diligence(db, lead, user)
    return RedirectResponse(f"/admin/leads/{lead.id}/due-diligence", 303)


@router.post("/admin/leads/{lead_id}/due-diligence/update-note")
def update_dd(lead_id: int, advisor_notes: str = Form(""), dd_status: str = Form("pending_review"),
    db: Session = Depends(get_db), _: User = Depends(require_roles("admin", "sales"))):
    dd = db.query(DueDiligenceReport).filter(DueDiligenceReport.lead_id == lead_id).first()
    if not dd: raise HTTPException(404, "请先生成尽调底稿")
    dd.advisor_notes, dd.dd_status, dd.updated_at = advisor_notes.strip(), dd_status, datetime.now()
    db.commit(); return RedirectResponse(f"/admin/leads/{lead_id}/due-diligence", 303)


@router.get("/admin/leads/{lead_id}/autofill-review", response_class=HTMLResponse)
def autofill_review(request: Request, lead_id: int, db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "sales", "viewer"))):
    lead = _lead(db, lead_id); documents = db.query(UploadedDocument).filter(UploadedDocument.lead_id == lead.id).all()
    suggestions = build_autofill_suggestions(lead.assessment, documents)
    track_event(db, "autofill_suggested", lead.assessment_id, lead.id, {"fields": list(suggestions["suggested_updates"])})
    return templates.TemplateResponse(request=request, name="admin_autofill_review.html", context={
        "lead": lead, "suggestions": suggestions, "current_user": user, "can_apply": user.role == "admin"})


@router.post("/admin/leads/{lead_id}/autofill/apply")
def apply_autofill(lead_id: int, fields: list[str] = Form(...), db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin"))):
    lead = _lead(db, lead_id); documents = db.query(UploadedDocument).filter(UploadedDocument.lead_id == lead.id).all()
    suggestions = build_autofill_suggestions(lead.assessment, documents)["suggested_updates"]; applied = {}
    for field in fields:
        if field not in AUTOFILL_FIELDS or field not in suggestions: continue
        old, value = getattr(lead.assessment, field), suggestions[field]["new_value"]
        if field == "receivable_days": value = int(value)
        elif field in {"annual_revenue", "net_profit", "monthly_cashflow", "debt_total", "short_debt"}: value = float(value)
        elif field in {"tax_status", "credit_status", "has_collateral"}: value = bool(value)
        setattr(lead.assessment, field, value); applied[field] = {"old": old, "new": value}
    score = calculate_score({c.name: getattr(lead.assessment, c.name) for c in lead.assessment.__table__.columns})
    lead.assessment.score, lead.assessment.grade = score.total, score.grade
    lead.assessment.risk_level, lead.assessment.funding_probability = score.risk_level, score.funding_probability
    track_event(db, "autofill_applied", lead.assessment_id, lead.id, {"applied": applied}, commit=False)
    add_follow_log(db, lead.id, user, "autofill_applied", json.dumps(applied, ensure_ascii=False)); db.commit()
    return RedirectResponse(f"/admin/leads/{lead.id}/autofill-review", 303)


@router.get("/admin/leads/{lead_id}/application-package", response_class=HTMLResponse)
def package_page(request: Request, lead_id: int, db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "sales", "viewer"))):
    lead = _lead(db, lead_id); documents, completeness, _ = _analysis(db, lead)
    packages = db.query(FinancingApplicationPackage).filter(FinancingApplicationPackage.lead_id == lead.id).order_by(FinancingApplicationPackage.created_at.desc()).all()
    return templates.TemplateResponse(request=request, name="admin_application_package.html", context={
        "lead": lead, "documents": documents, "completeness": completeness, "packages": packages,
        "bank_products": db.query(BankProduct).filter(BankProduct.is_active.is_(True)).all(),
        "current_user": user, "can_edit": user.role in {"admin", "sales"}})


@router.post("/admin/leads/{lead_id}/application-package/create")
def create_package(lead_id: int, package_name: str = Form(...), target_product_code: str = Form("699_bank_match"),
    target_bank_product_id: int = Form(0), document_ids: list[int] = Form(default=[]), advisor_note: str = Form(""),
    db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "sales"))):
    lead = _lead(db, lead_id)
    selected = db.query(UploadedDocument).filter(UploadedDocument.lead_id == lead.id,
        UploadedDocument.id.in_(document_ids or [-1])).all()
    bank = db.get(BankProduct, target_bank_product_id) if target_bank_product_id else None
    completeness = check_document_completeness(lead, lead.assessment, selected, target_product_code,
        {"matched_products": [{"product_type": bank.product_type}] if bank else []})
    item = FinancingApplicationPackage(lead_id=lead.id, assessment_id=lead.assessment_id,
        package_name=package_name.strip(), package_status="ready" if not completeness["missing_required_documents"] else "draft",
        target_product_code=target_product_code, target_bank_product_id=bank.id if bank else None,
        document_ids_json=json.dumps([d.id for d in selected]), checklist_json=json.dumps(completeness, ensure_ascii=False),
        missing_json=json.dumps(completeness["missing_required_documents"], ensure_ascii=False),
        advisor_note=advisor_note.strip(), created_by=user.id)
    db.add(item); db.flush(); track_event(db, "application_package_created", lead.assessment_id, lead.id,
        {"package_id": item.id, "document_count": len(selected)}, commit=False); db.commit()
    return RedirectResponse(f"/admin/leads/{lead.id}/application-package", 303)


@router.post("/admin/application-packages/{package_id}/update-status")
def update_package(package_id: int, package_status: str = Form(...), db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin", "sales"))):
    if package_status not in {"draft", "ready", "submitted", "returned", "archived"}: raise HTTPException(400, "无效状态")
    item = db.get(FinancingApplicationPackage, package_id)
    if not item: raise HTTPException(404, "材料包不存在")
    item.package_status, item.updated_at = package_status, datetime.now(); db.commit()
    return RedirectResponse(f"/admin/leads/{item.lead_id}/application-package", 303)


@router.get("/admin/application-packages/{package_id}/checklist.csv")
def package_csv(package_id: int, db: Session = Depends(get_db), _: User = Depends(require_roles("admin", "sales"))):
    item = db.get(FinancingApplicationPackage, package_id)
    if not item: raise HTTPException(404, "材料包不存在")
    ids, missing = json.loads(item.document_ids_json or "[]"), json.loads(item.missing_json or "[]")
    docs = db.query(UploadedDocument).filter(UploadedDocument.id.in_(ids or [-1])).all()
    output = io.StringIO(); writer = csv.writer(output); writer.writerow(["材料包", "状态", "资料状态", "资料名称", "分类", "核验状态"])
    for d in docs: writer.writerow([item.package_name, item.package_status, "已提供", d.file_name, d.document_category, d.verify_status])
    for name in missing: writer.writerow([item.package_name, item.package_status, "缺失", name, "", ""])
    return Response(content=("\ufeff" + output.getvalue()).encode("utf-8"), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="application-package-{item.id}.csv"'})


@router.post("/api/events/document-request-script-copied")
def script_copied(lead_id: int = Form(...), db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "sales"))):
    lead = _lead(db, lead_id); track_event(db, "document_request_script_copied", lead.assessment_id, lead.id, {"operator": user.username})
    return {"ok": True}
