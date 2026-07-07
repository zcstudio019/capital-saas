from sqlalchemy import distinct, func
from sqlalchemy.orm import Session

from db.models import Assessment, Lead, Order


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator * 100, 1) if denominator else 0.0


def build_funnel_analytics(db: Session) -> dict:
    assessments = db.query(Assessment).count()
    leads = db.query(Lead).count()
    paid_orders = db.query(Order).filter(Order.status == "paid").count()
    paid_assessments = (
        db.query(func.count(distinct(Order.assessment_id)))
        .filter(Order.status == "paid")
        .scalar()
        or 0
    )
    product_counts = {
        code: db.query(Order)
        .filter(Order.status == "paid", Order.product_code == code)
        .count()
        for code in ["299_report", "699_bank_match", "1999_structure_plan"]
    }
    total_revenue = (
        db.query(func.coalesce(func.sum(Order.amount), 0))
        .filter(Order.status == "paid")
        .scalar()
        or 0
    )
    grade_conversion = {}
    for grade in ["S", "A", "B", "C", "D"]:
        grade_leads = db.query(Lead).filter(Lead.lead_grade == grade).count()
        converted = (
            db.query(func.count(distinct(Lead.id)))
            .join(Order, Order.assessment_id == Lead.assessment_id)
            .filter(Lead.lead_grade == grade, Order.status == "paid")
            .scalar()
            or 0
        )
        grade_conversion[grade] = {
            "leads": grade_leads,
            "converted": converted,
            "rate": _rate(converted, grade_leads),
        }
    return {
        "assessments": assessments,
        "leads": leads,
        "paid_orders": paid_orders,
        "paid_assessments": paid_assessments,
        "product_counts": product_counts,
        "total_revenue": float(total_revenue),
        "assessment_to_paid_rate": _rate(paid_assessments, assessments),
        "lead_creation_rate": _rate(leads, assessments),
        "grade_conversion": grade_conversion,
        "product_conversion": {
            code: _rate(count, leads) for code, count in product_counts.items()
        },
    }
