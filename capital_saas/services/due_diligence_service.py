import json
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from core.assessment_autofill_engine import build_autofill_suggestions
from core.bank_product_matcher import match_bank_products
from core.document_completeness_engine import check_document_completeness
from db.models import DueDiligenceReport, FollowTask, Lead, UploadedDocument, User
from services.event_service import track_event
from services.tag_service import add_named_tag


TASK_MAP = {
    "营业执照": ("collect_documents", "补充营业执照", "请客户补充清晰、有效的营业执照或工商资料"),
    "银行流水": ("collect_documents", "补充近6-12个月银行流水", "收集主要经营账户近6-12个月完整流水"),
    "纳税/开票资料": ("collect_documents", "补充纳税/开票资料", "收集近一年纳税申报、完税及开票明细"),
    "抵押物权属证明": ("collect_documents", "补充抵押物权属证明", "收集产权证及权属人资料"),
}


def create_missing_document_tasks(db: Session, lead: Lead, completeness: dict) -> list[FollowTask]:
    created = []
    for missing in completeness["missing_required_documents"]:
        matched_key = next((key for key in TASK_MAP if key in missing), None)
        if not matched_key:
            continue
        task_type, title, content = TASK_MAP[matched_key]
        exists = db.query(FollowTask).filter(
            FollowTask.lead_id == lead.id, FollowTask.task_title == title,
            FollowTask.status == "pending",
        ).first()
        if not exists:
            task = FollowTask(
                lead_id=lead.id, assessment_id=lead.assessment_id,
                task_type=task_type, task_title=title, task_content=content,
                priority="high" if completeness["completeness_score"] < 50 else "medium",
                due_time=datetime.now() + timedelta(days=2), status="pending",
            )
            db.add(task)
            created.append(task)
    return created


def _parsed_financials(documents: list[UploadedDocument]) -> dict:
    result = {}
    for document in documents:
        try:
            data = json.loads(document.parsed_json or "{}")
        except json.JSONDecodeError:
            continue
        for key, value in data.get("financial_fields", {}).items():
            result.setdefault(key, {"value": value, "source_document": document.file_name})
    return result


def _apply_risk_tags(db: Session, lead: Lead, completeness: dict, autofill: dict) -> None:
    assessment = lead.assessment
    names = []
    if completeness["completeness_score"] < 70:
        names += ["资料不完整", "需人工尽调"]
    if autofill["conflicts"]:
        names.append("财务数据不一致")
    if assessment.monthly_cashflow <= max(assessment.annual_revenue / 36, 1):
        names.append("现金流弱")
    if assessment.short_debt / max(assessment.debt_total, 1) > 0.6:
        names.append("短债压力高")
    categories = " ".join(x.document_category for x in db.query(UploadedDocument).filter(
        UploadedDocument.lead_id == lead.id
    ).all())
    if "征信" not in categories:
        names.append("征信待核验")
    if "纳税" not in categories:
        names.append("纳税待核验")
    if assessment.has_collateral and "抵押" not in categories:
        names.append("抵押物待核验")
    if assessment.receivable_days > 75:
        names.append("应收账款风险")
    for name in names:
        add_named_tag(db, lead, name)


def generate_due_diligence(db: Session, lead: Lead, user: User) -> DueDiligenceReport:
    documents = db.query(UploadedDocument).filter(UploadedDocument.lead_id == lead.id).all()
    matches = match_bank_products(db, lead.assessment)
    completeness = check_document_completeness(
        lead, lead.assessment, documents, lead.recommended_product, matches
    )
    autofill = build_autofill_suggestions(lead.assessment, documents)
    financials = _parsed_financials(documents)
    risk_summary = {
        "document_risks": completeness["risk_notes"],
        "data_conflicts": autofill["conflicts"],
        "assessment_risks": [
            item for condition, item in [
                (lead.assessment.monthly_cashflow <= 0, "经营现金流不足"),
                (lead.assessment.receivable_days > 90, "应收账款周期偏长"),
                (lead.assessment.short_debt / max(lead.assessment.debt_total, 1) > 0.6, "短期债务占比偏高"),
                (not lead.assessment.credit_status, "征信状态异常或待核验"),
                (not lead.assessment.tax_status, "纳税状态异常或待核验"),
            ] if condition
        ],
        "missing_documents": completeness["missing_required_documents"],
    }
    item = db.query(DueDiligenceReport).filter(DueDiligenceReport.lead_id == lead.id).first()
    if not item:
        item = DueDiligenceReport(
            lead_id=lead.id, assessment_id=lead.assessment_id,
            report_id=lead.assessment.report.id if lead.assessment.report else None,
            created_by=user.id,
        )
        db.add(item)
    item.dd_status = "needs_more_documents" if completeness["completeness_score"] < 70 else "pending_review"
    item.completeness_score = completeness["completeness_score"]
    item.extracted_company_json = json.dumps({
        "company_name": lead.company_name, "industry": lead.assessment.industry,
        "years": lead.assessment.years, "contact_name": lead.contact_name,
        "city": lead.city,
    }, ensure_ascii=False)
    item.extracted_financial_json = json.dumps(financials, ensure_ascii=False)
    item.document_summary_json = json.dumps({
        "document_count": len(documents),
        "categories": sorted({x.document_category for x in documents}),
        "parsed_count": sum(x.parse_status == "parsed" for x in documents),
        "verified_count": sum(x.verify_status == "verified" for x in documents),
        "completeness": completeness,
    }, ensure_ascii=False)
    item.risk_summary_json = json.dumps(risk_summary, ensure_ascii=False)
    item.updated_at = datetime.now()
    if completeness["high_value_action_required"]:
        create_missing_document_tasks(db, lead, completeness)
    _apply_risk_tags(db, lead, completeness, autofill)
    track_event(db, "due_diligence_generated", lead.assessment_id, lead.id,
                {"completeness_score": completeness["completeness_score"], "status": item.dd_status}, commit=False)
    track_event(db, "autofill_suggested", lead.assessment_id, lead.id,
                {"fields": list(autofill["suggested_updates"])}, commit=False)
    db.commit()
    db.refresh(item)
    return item
