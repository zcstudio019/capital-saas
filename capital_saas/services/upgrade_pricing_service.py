"""统一计算产品升级应付金额，历史订单只作权益凭证，不做重复抵扣。"""

from __future__ import annotations

from sqlalchemy import or_
from sqlalchemy.orm import Session

from core.pricing_engine import PRODUCT_DEDUCTION_RULES, products
from db.models import Order
from services.settings_service import get_setting


PRICE_SETTING_KEYS = {
    "free_assessment": None,
    "299_report": "report_price_299",
    "980_capital_health_report": "capital_health_report_price",
    "699_bank_match": "report_price_699",
    "1999_structure_plan": "capital_structure_plan_price",
    "one_on_one_consulting": "one_on_one_consulting_price",
}


def _eligible_orders(
    db: Session,
    customer_id: int | None,
    assessment_id: int | None,
    target_product_code: str,
) -> list[Order]:
    source_codes = [
        code
        for code, targets in PRODUCT_DEDUCTION_RULES.items()
        if target_product_code in targets
    ]
    if not source_codes or (not customer_id and not assessment_id):
        return []
    identity_filters = []
    if customer_id:
        identity_filters.append(Order.customer_id == customer_id)
    if assessment_id:
        identity_filters.append(Order.assessment_id == assessment_id)
    return (
        db.query(Order)
        .filter(
            Order.status == "paid",
            Order.refund_at.is_(None),
            Order.product_code.in_(source_codes),
            or_(*identity_filters),
        )
        .all()
    )


def get_upgrade_quote(
    customer_id: int | None,
    target_product_code: str,
    db: Session,
    *,
    assessment_id: int | None = None,
    allow_deduction: bool = True,
    target_price: float | None = None,
) -> dict:
    if target_price is None:
        default_price = float(products.get(target_product_code, {}).get("price", 0))
        price_key = PRICE_SETTING_KEYS.get(target_product_code)
        try:
            original_price = float(get_setting(db, price_key, str(default_price))) if price_key else default_price
        except ValueError:
            original_price = default_price
    else:
        original_price = float(target_price)
    best_order = None
    best_deduction = 0.0
    if allow_deduction:
        for order in _eligible_orders(db, customer_id, assessment_id, target_product_code):
            deduction = min(float(order.amount or 0), original_price)
            if deduction > best_deduction:
                best_order = order
                best_deduction = deduction
    return {
        "original_price": original_price,
        "deduction": best_deduction,
        "price": max(0.0, original_price - best_deduction),
        "upgrade_from_product": best_order.product_code if best_order else "",
        "deduction_order_id": best_order.id if best_order else None,
        "upgrade_mode": "highest_paid_order" if best_order else "no_deduction",
    }


def calculate_upgrade_amount(
    customer_id: int | None,
    target_product_code: str,
    db: Session,
    assessment_id: int | None = None,
) -> float:
    """返回客户升级目标产品的应付金额。"""
    return float(
        get_upgrade_quote(
            customer_id,
            target_product_code,
            db,
            assessment_id=assessment_id,
        )["price"]
    )
