from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from core.access_scope import effective_role, get_access_scope
from core.capital_health_report import build_capital_health_report
from core.pricing_engine import PRODUCT_RANK
from db.models import ConsultingCase, Lead, Order, Report, ReportVersion, User
from services.report_access_service import build_report_access_context
from utils.report_display_mapper import build_customer_report_display
from utils.report_formatters import normalize_report_action_steps
from utils.report_render_formatter import format_report_for_render


ACCESS_RANK = {"free": 0, "capital_health_report": 1, "structure_plan": 2, "advisor_delivery": 3}


def _case_for_report(db: Session, report: Report) -> ConsultingCase | None:
    query = db.query(ConsultingCase)
    condition = ConsultingCase.report_id == report.id
    if report.assessment_id is not None:
        condition = condition | (ConsultingCase.assessment_id == report.assessment_id)
    return query.filter(condition).order_by(ConsultingCase.created_at.desc()).first()


def assert_admin_report_preview_access(db: Session, report: Report, user: User) -> str:
    """Return internal/customer preview mode after enforcing report data scope."""
    role = effective_role(user)
    lead = report.assessment.lead if report.assessment else (db.get(Lead, report.lead_id) if report.lead_id else None)
    case = _case_for_report(db, report)
    if role == "super_admin":
        return "internal"
    if role == "consultant":
        if case and (case.consultant_user_id == user.id or case.consultant_id == user.id):
            return "internal"
        raise HTTPException(status_code=403, detail="仅可查看分配给自己的顾问案件报告")
    if role == "consultant_manager":
        scope = get_access_scope(db, user)
        lead_allowed = bool(lead and (lead.owner_org_id in scope.allowed_org_ids or lead.org_id in scope.allowed_org_ids))
        case_allowed = bool(case and (case.owner_org_id in scope.allowed_org_ids or case.org_id in scope.allowed_org_ids))
        if lead_allowed or case_allowed:
            return "internal"
        raise HTTPException(status_code=403, detail="无权查看其他组织的报告")
    if role == "sales":
        if lead and (lead.assigned_sales_id == user.id or (not lead.assigned_sales_id and lead.owner_user_id == user.id)):
            return "customer"
        raise HTTPException(status_code=403, detail="无权查看未分配给自己的客户报告")
    raise HTTPException(status_code=403, detail="当前角色不能预览报告正文")


def _json_dict(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _paid_product_code(db: Session, report: Report) -> str:
    codes = [
        item.product_code or "free_assessment"
        for item in db.query(Order).filter(Order.assessment_id == report.assessment_id, Order.status == "paid")
    ]
    return max(codes, key=lambda code: PRODUCT_RANK.get(code, 0), default="free_assessment")


def access_level_for_product(product_code: str) -> str:
    if product_code in {"one_on_one_consulting", "high_ticket_consulting"}:
        return "advisor_delivery"
    if PRODUCT_RANK.get(product_code, 0) >= PRODUCT_RANK.get("1999_structure_plan", 0):
        return "structure_plan"
    if product_code == "980_capital_health_report":
        return "capital_health_report"
    return "free"


def infer_version_access_level(db: Session, report: Report, version: ReportVersion | None, payload: dict[str, Any]) -> str:
    if report.report_type == "cashflow_health_report":
        return "cashflow_health_report"
    product_code = version.product_code if version else ""
    product_level = access_level_for_product(product_code)
    meta_level = str((payload.get("report_meta") or {}).get("access_level") or "")
    snapshot_level = str((payload.get("capital_health_snapshot") or {}).get("access_level") or "")
    stored_level = str(version.access_level or "") if version else ""
    levels = [product_level, meta_level, snapshot_level, stored_level]
    if version is None:
        levels.append(access_level_for_product(_paid_product_code(db, report)))
    return max(levels, key=lambda item: ACCESS_RANK.get(item, 0), default="free")


def report_has_generated_content(report: Report) -> bool:
    return bool((report.full_report_json or "").strip() or (report.free_summary_json or "").strip() or (report.html_content or "").strip())


def ensure_report_version_compat(db: Session, report: Report) -> ReportVersion | None:
    """Repair V- for legacy reports without deleting or rewriting their source content."""
    versions = db.query(ReportVersion).filter(ReportVersion.report_id == report.id).order_by(ReportVersion.version_no.desc()).all()
    current = db.get(ReportVersion, report.current_version_id) if report.current_version_id else None
    if current and current.report_id == report.id:
        return current
    if versions:
        report.current_version_id = versions[0].id
        db.commit()
        return versions[0]
    if not report_has_generated_content(report):
        return None

    payload = _json_dict(report.full_report_json)
    if report.report_type == "cashflow_health_report":
        version = ReportVersion(
            report_id=report.id,
            assessment_id=None,
            version_no=1,
            product_code="cashflow_health_report",
            access_level="cashflow_health_report",
            generator_mode="legacy_migration",
            quality_score=int(report.score or 0),
            report_json=json.dumps(payload, ensure_ascii=False),
            html_content=report.html_content or "",
            created_by="legacy-migration",
            created_at=report.created_at,
        )
        db.add(version)
        db.flush()
        report.current_version_id = version.id
        db.commit()
        db.refresh(version)
        return version
    product_code = _paid_product_code(db, report)
    access_level = access_level_for_product(product_code)
    if not payload.get("capital_health_snapshot"):
        snapshot = build_capital_health_report(
            db,
            report.assessment,
            admin_override=True,
            include_extended=ACCESS_RANK[access_level] >= ACCESS_RANK["structure_plan"],
        )
        snapshot["access_level"] = access_level
        payload["capital_health_snapshot"] = snapshot
    payload.setdefault("report_meta", {
        "access_level": access_level,
        "created_at": report.created_at.isoformat(),
        "created_by": "legacy-migration",
        "review_status": report.review_status,
        "change_summary": "历史报告内容兼容迁移",
    })
    version = ReportVersion(
        report_id=report.id,
        assessment_id=report.assessment_id,
        version_no=1,
        product_code=product_code,
        access_level=access_level,
        generator_mode="legacy_migration",
        quality_score=int(((payload.get("quality") or {}).get("quality_score") or 0)),
        report_json=json.dumps(payload, ensure_ascii=False),
        html_content=report.html_content or "",
        created_by="legacy-migration",
        created_at=report.created_at,
    )
    db.add(version)
    db.flush()
    report.current_version_id = version.id
    db.commit()
    db.refresh(version)
    return version


def report_generation_status(report: Report) -> str:
    if report.generation_status:
        return report.generation_status
    if not report_has_generated_content(report):
        return "draft"
    if report.review_status == "quality_failed":
        return "generation_failed"
    return "generated"


def _customer_visible_level(db: Session, report: Report) -> str:
    level = access_level_for_product(_paid_product_code(db, report))
    if ACCESS_RANK[level] >= ACCESS_RANK["structure_plan"] and report.review_status != "approved":
        paid_codes = {
            item.product_code for item in db.query(Order).filter(
                Order.assessment_id == report.assessment_id, Order.status == "paid"
            )
        }
        return "capital_health_report" if "980_capital_health_report" in paid_codes else "free"
    return level


def build_admin_report_preview_context(
    db: Session,
    report: Report,
    user: User,
    version_id: int | None = None,
) -> dict[str, Any]:
    preview_mode = assert_admin_report_preview_access(db, report, user)
    current = ensure_report_version_compat(db, report)
    version = current
    if version_id:
        version = db.query(ReportVersion).filter(
            ReportVersion.id == version_id, ReportVersion.report_id == report.id
        ).first()
        if not version:
            raise HTTPException(status_code=404, detail="报告版本不存在")
    payload = _json_dict(version.report_json if version else report.full_report_json)
    level = infer_version_access_level(db, report, version, payload)
    if preview_mode == "customer":
        allowed_level = _customer_visible_level(db, report)
        if ACCESS_RANK[level] > ACCESS_RANK[allowed_level]:
            level = allowed_level

    health_report = deepcopy(payload.get("capital_health_snapshot") or {})
    if not health_report:
        health_report = build_capital_health_report(
            db,
            report.assessment,
            admin_override=True,
            include_extended=ACCESS_RANK[level] >= ACCESS_RANK["structure_plan"],
        )
    health_report["access_level"] = level
    health_report["entitlements"] = {
        "access_level": level,
        "body_unlocked": ACCESS_RANK[level] >= ACCESS_RANK["capital_health_report"],
        "structure_unlocked": ACCESS_RANK[level] >= ACCESS_RANK["structure_plan"],
        "bank_match_unlocked": ACCESS_RANK[level] >= ACCESS_RANK["structure_plan"],
        "legacy_report_unlocked": False,
        "paid_products": [],
    }
    safe_report = format_report_for_render(build_customer_report_display(format_report_for_render(payload))) or {}
    normalize_report_action_steps(safe_report)
    access_context = build_report_access_context(
        db, report.assessment, safe_report, base_path=f"/admin/reports/{report.id}/preview"
    )
    internal_full = preview_mode == "internal" and ACCESS_RANK[level] >= ACCESS_RANK["structure_plan"]
    access_context.update({
        "bank_match_unlocked": internal_full,
        "document_checklist_unlocked": internal_full,
        "execution_plan_unlocked": internal_full,
        "product_detail_unlocked": internal_full,
    })
    return {
        "report_item": report,
        "assessment": report.assessment,
        "lead": report.assessment.lead,
        "customer": None,
        "report": safe_report,
        "health_report": health_report,
        "current_version": current,
        "preview_version": version,
        "access_level": level,
        "preview_mode": preview_mode,
        "backend_view": True,
        "admin_preview": True,
        "print_mode": False,
        **access_context,
    }
