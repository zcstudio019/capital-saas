from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable

from sqlalchemy.orm import Session

from db.models import Assessment, BankProduct, Order


BANK_MATCH_PRODUCTS = {"699_bank_match", "1999_structure_plan"}
DOCUMENT_CHECKLIST_PRODUCTS = {"1999_structure_plan"}
PAID_STATUSES = {"paid", "completed", "success"}


def _product_code(value: Any) -> str:
    if isinstance(value, str):
        return value
    return getattr(value, "product_code", "") or ""


def _product_codes(order_or_product: Any) -> set[str]:
    if order_or_product is None:
        return set()
    if isinstance(order_or_product, (list, tuple, set)):
        return {_product_code(item) for item in order_or_product if _product_code(item)}
    return {_product_code(order_or_product)} if _product_code(order_or_product) else set()


def get_paid_product_codes(db: Session, assessment_id: int) -> set[str]:
    orders = (
        db.query(Order)
        .filter(Order.assessment_id == assessment_id, Order.status.in_(PAID_STATUSES))
        .all()
    )
    return _product_codes(orders)


def can_view_full_bank_match(order_or_product: Any) -> bool:
    return bool(_product_codes(order_or_product) & BANK_MATCH_PRODUCTS)


def can_view_full_document_checklist(order_or_product: Any) -> bool:
    return bool(_product_codes(order_or_product) & DOCUMENT_CHECKLIST_PRODUCTS)


def can_view_full_bank_product_detail(order_or_product: Any) -> bool:
    return can_view_full_bank_match(order_or_product)


def _short_text(value: Any, default: str = "", limit: int = 72) -> str:
    text = str(value or default).strip()
    if not text:
        return default
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _detail_url(base_path: str, product_id: Any) -> str:
    if not product_id:
        return "#"
    return f"{base_path}/bank-products/{product_id}"


def _decorate_match(item: dict[str, Any], base_path: str) -> dict[str, Any]:
    decorated = dict(item)
    decorated["product_id"] = item.get("product_id") or item.get("id")
    decorated["detail_url"] = _detail_url(base_path, decorated.get("product_id"))
    decorated["preview_reason"] = _short_text(
        item.get("reason"),
        "该产品与当前企业融资需求存在基础匹配，可进入详情查看预览。",
        68,
    )
    decorated["access_hint"] = _short_text(
        item.get("access_hint") or item.get("risk_notes"),
        "需结合征信、纳税、流水和经营资料进一步核验准入。",
        58,
    )
    decorated["preview_note"] = _short_text(
        item.get("note") or item.get("risk_notes"),
        "完整准入规则、申请顺序和额度预测需解锁后查看。",
        58,
    )
    return decorated


def build_bank_match_preview(matches: dict[str, Any] | None, base_path: str = "") -> dict[str, Any]:
    matches = matches or {}
    products = [_decorate_match(item, base_path) for item in matches.get("matched_products", [])[:1]]
    return {
        "matched_products": products,
        "fallback_notice": matches.get("fallback_notice", ""),
        "preview_only": True,
        "upgrade_product": "699_bank_match",
        "upgrade_title": "当前为基础版预览",
        "upgrade_text": "升级699版本可查看完整产品匹配、申请顺序和额度预测。",
    }


def build_bank_match_full(matches: dict[str, Any] | None, base_path: str = "") -> dict[str, Any]:
    full = deepcopy(matches or {})
    full["matched_products"] = [
        _decorate_match(item, base_path) for item in full.get("matched_products", [])
    ]
    full["preview_only"] = False
    return full


def _category_name(group: Any) -> str:
    if isinstance(group, dict):
        return str(group.get("category") or group.get("name") or "").strip()
    return str(group or "").strip()


def _plain_category(category: str) -> str:
    fallback = {
        "enterprise": "企业基础资料",
        "finance": "财务资料",
        "bank": "银行流水",
        "operation": "经营证明",
        "tax": "纳税资料",
        "collateral": "抵押物资料",
    }
    return fallback.get(category, category)


def build_document_checklist_preview(
    checklist: dict[str, Any] | None,
    assessment: Assessment | None = None,
) -> dict[str, Any]:
    checklist = checklist or {}
    categories: list[str] = []
    for group in checklist.get("required_documents", []):
        name = _plain_category(_category_name(group))
        if name and name not in categories:
            categories.append(name)
    defaults = ["企业基础资料", "财务资料", "银行流水", "经营证明", "纳税资料"]
    for name in defaults:
        if name not in categories:
            categories.append(name)
    if assessment and assessment.has_collateral and "抵押物资料" not in categories:
        categories.append("抵押物资料")
    return {
        "required_documents": [{"category": name, "items": []} for name in categories],
        "missing_risk": [],
        "preparation_priority": [],
        "detail_level": "preview",
        "preview_only": True,
        "upgrade_product": "1999_structure_plan",
        "upgrade_title": "高级交付内容",
        "upgrade_text": "1999结构优化方案提供完整资料清单、优先级与30/90/180天执行计划。",
    }


def build_document_checklist_full(checklist: dict[str, Any] | None) -> dict[str, Any]:
    full = deepcopy(checklist or {})
    full["preview_only"] = False
    return full


def build_report_access_context(
    db: Session,
    assessment: Assessment,
    report: dict[str, Any],
    base_path: str | None = None,
) -> dict[str, Any]:
    paid_product_codes = get_paid_product_codes(db, assessment.id)
    bank_unlocked = can_view_full_bank_match(paid_product_codes)
    checklist_unlocked = can_view_full_document_checklist(paid_product_codes)
    base_path = base_path or f"/report/{assessment.id}"
    matches = report.get("bank_product_matches") or {}
    checklist = report.get("document_checklist") or {}
    return {
        "paid_product_codes": paid_product_codes,
        "bank_match_unlocked": bank_unlocked,
        "bank_match_preview": build_bank_match_preview(matches, base_path),
        "bank_match_full": build_bank_match_full(matches, base_path),
        "document_checklist_unlocked": checklist_unlocked,
        "document_checklist_preview": build_document_checklist_preview(checklist, assessment),
        "document_checklist_full": build_document_checklist_full(checklist),
        "product_detail_unlocked": can_view_full_bank_product_detail(paid_product_codes),
    }


def find_report_matched_product(report: dict[str, Any], product_id: int) -> dict[str, Any] | None:
    for item in (report.get("bank_product_matches") or {}).get("matched_products", []):
        try:
            if int(item.get("product_id") or item.get("id") or 0) == int(product_id):
                return dict(item)
        except (TypeError, ValueError):
            continue
    return None


def build_bank_product_detail_context(
    db: Session,
    assessment: Assessment,
    report: dict[str, Any],
    product_id: int,
) -> dict[str, Any] | None:
    product = db.get(BankProduct, product_id)
    matched = find_report_matched_product(report, product_id)
    if not product and not matched:
        return None
    paid_product_codes = get_paid_product_codes(db, assessment.id)
    unlocked = can_view_full_bank_product_detail(paid_product_codes)
    product_data = {
        "id": product_id,
        "product_code": getattr(product, "product_code", "") if product else matched.get("product_code", ""),
        "bank_name": getattr(product, "bank_name", "") if product else matched.get("bank_name", ""),
        "bank_type": getattr(product, "bank_type", "") if product else matched.get("bank_type", ""),
        "product_name": getattr(product, "product_name", "") if product else matched.get("product_name", ""),
        "product_type": getattr(product, "product_type", "") if product else matched.get("product_type", ""),
        "guarantee_method": getattr(product, "guarantee_method", "") if product else "",
        "amount_description": getattr(product, "amount_description", "") if product else "",
        "max_amount": getattr(product, "max_amount", "") if product else "",
        "min_amount": getattr(product, "min_amount", "") if product else "",
        "interest_rate_range": getattr(product, "interest_rate_range", "") if product else matched.get("interest_rate_range", ""),
        "loan_term": getattr(product, "loan_term", "") if product else matched.get("loan_term", ""),
        "repayment_methods": getattr(product, "repayment_methods", "") if product else "",
        "application_requirements": getattr(product, "application_requirements", "") if product else "",
        "access_conditions_json": getattr(product, "access_conditions_json", "") if product else "",
        "prohibited_conditions_json": getattr(product, "prohibited_conditions_json", "") if product else "",
        "suitable_scenarios": getattr(product, "suitable_scenarios", "") if product else "",
        "target_customer_type": getattr(product, "target_customer_type", "") if product else "",
        "required_documents": getattr(product, "required_documents", "") if product else "",
        "required_documents_json": getattr(product, "required_documents_json", "") if product else "",
        "risk_notes": getattr(product, "risk_notes", "") if product else matched.get("risk_notes", ""),
        "update_note": getattr(product, "update_note", "") if product else "",
        "match_score": matched.get("match_score", "") if matched else "",
        "reason": matched.get("reason", "") if matched else "",
        "estimated_amount": matched.get("estimated_amount", "") if matched else "",
    }
    if not product_data["amount_description"]:
        product_data["amount_description"] = matched.get("estimated_amount", "") if matched else ""
    return {
        "product": product_data,
        "matched_product": matched,
        "product_detail_unlocked": unlocked,
        "upgrade_product": "699_bank_match",
    }
