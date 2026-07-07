from typing import Any

from sqlalchemy.orm import Session

from db.models import BankProduct


def _amount_text(value: float) -> str:
    return f"{max(value, 0) / 10000:,.0f}万元"


def match_bank_products(db: Session, assessment: Any) -> dict:
    products = db.query(BankProduct).filter(BankProduct.is_active.is_(True)).all()
    matches = []
    for product in products:
        score = 55
        reasons = []
        risks = []
        if assessment.annual_revenue >= product.min_revenue:
            score += 12
            reasons.append("营业收入达到产品基础门槛")
        else:
            score -= 25
            risks.append("营业收入低于模拟准入门槛")
        if assessment.years >= product.min_years:
            score += 8
            reasons.append("经营年限满足要求")
        else:
            score -= 15
            risks.append("经营年限不足")
        if product.requires_tax_normal:
            score += 8 if assessment.tax_status else -25
            (reasons if assessment.tax_status else risks).append(
                "纳税状态正常" if assessment.tax_status else "纳税状态不满足要求"
            )
        if product.requires_credit_normal:
            score += 10 if assessment.credit_status else -35
            (reasons if assessment.credit_status else risks).append(
                "征信状态正常" if assessment.credit_status else "征信状态可能导致拒绝"
            )
        if product.requires_collateral:
            score += 15 if assessment.has_collateral else -35
            (reasons if assessment.has_collateral else risks).append(
                "具备可评估抵押物" if assessment.has_collateral else "缺少抵押物"
            )
        if product.product_type == "应收账款融资" and assessment.receivable_days >= 60:
            score += 12
            reasons.append("应收账款周期较长，存在保理或供应链融资场景")
        if assessment.industry and (
            product.suitable_industry in {"", "通用"}
            or assessment.industry in product.suitable_industry
        ):
            score += 5
        estimated = min(product.max_amount or assessment.funding_need, assessment.funding_need)
        matches.append({
            "product_id": product.id,
            "product_name": product.product_name,
            "bank_name": product.bank_name,
            "bank_type": product.bank_type,
            "product_type": product.product_type,
            "match_score": max(0, min(100, score)),
            "reason": "；".join(reasons) or "需进一步核验经营与财务资料",
            "estimated_amount": f"最高参考{_amount_text(estimated)}，实际以审批为准",
            "interest_rate_range": product.interest_rate_range,
            "loan_term": product.loan_term,
            "risk_notes": "；".join(risks) or product.risk_notes or "无明显硬性冲突",
        })
    matches.sort(key=lambda item: item["match_score"], reverse=True)
    top = matches[:5]
    return {
        "matched_products": top,
        "best_application_order": [
            f"第{index}顺位：{item['bank_type']}—{item['product_name']}（匹配度{item['match_score']}）"
            for index, item in enumerate(top[:3], 1)
        ],
    }
