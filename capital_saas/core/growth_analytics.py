from datetime import date, datetime, time, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from db.models import ABAssignment, Assessment, Lead, Order
from services.ab_test_service import ab_metrics
from utils.display_labels import is_demo_or_test_record


def _rate(a: int, b: int) -> float:
    return round(a / b * 100, 1) if b else 0.0


def build_growth_analytics(db: Session, allowed_org_ids: list[int] | None = None, include_test: bool = True) -> dict:
    assessment_ids = None
    if allowed_org_ids is not None:
        assessment_ids = [row[0] for row in db.query(Lead.assessment_id).filter(
            Lead.owner_org_id.in_(allowed_org_ids or [-1])
        ).all()]
    if not include_test:
        real_ids = [row.id for row in db.query(Assessment).all() if not is_demo_or_test_record(row.company_name)]
        assessment_ids = real_ids if assessment_ids is None else [item for item in assessment_ids if item in set(real_ids)]

    def scoped(query, model):
        if assessment_ids is None:
            return query
        column = model.id if model.__tablename__ == "assessments" else model.assessment_id
        return query.filter(column.in_(assessment_ids or [-1]))

    channels = []
    names = {row[0] or "direct" for row in scoped(
        db.query(Assessment.source_channel), Assessment
    ).distinct().all()}
    for name in sorted(names):
        assessment_filter = (
            Assessment.source_channel == name if name != "direct"
            else ((Assessment.source_channel == "") | (Assessment.source_channel.is_(None)))
        )
        lead_filter = (
            Lead.source_channel == name if name != "direct"
            else ((Lead.source_channel == "") | (Lead.source_channel.is_(None)))
        )
        order_filter = (
            Order.source_channel == name if name != "direct"
            else ((Order.source_channel == "") | (Order.source_channel.is_(None)))
        )
        assessment_count = scoped(db.query(Assessment), Assessment).filter(assessment_filter).count()
        lead_count = scoped(db.query(Lead), Lead).filter(lead_filter).count()
        orders = scoped(db.query(Order), Order).filter(order_filter, Order.status == "paid").all()
        revenue = sum(x.amount for x in orders)
        channels.append({
            "name": name, "assessments": assessment_count, "leads": lead_count,
            "orders": len(orders), "revenue": revenue,
            "conversion_rate": _rate(len({x.assessment_id for x in orders}), assessment_count),
            "average_order_value": round(revenue / len(orders), 2) if orders else 0,
        })
    landing_pages = []
    for path in ["/lp/rongzi", "/lp/cashflow", "/lp/bank", "/lp/boss"]:
        assessments = scoped(db.query(Assessment), Assessment).filter(Assessment.source_landing_page == path).count()
        leads = scoped(db.query(Lead), Lead).filter(Lead.source_landing_page == path).count()
        orders = scoped(db.query(Order), Order).filter(
            Order.source_landing_page == path, Order.status == "paid"
        ).all()
        landing_pages.append({
            "path": path, "assessments": assessments, "leads": leads,
            "orders": len(orders), "revenue": sum(x.amount for x in orders),
            "conversion_rate": _rate(len({x.assessment_id for x in orders}), assessments),
        })
    products = []
    for code in ["299_report", "699_bank_match", "1999_structure_plan"]:
        orders = scoped(db.query(Order), Order).filter(Order.product_code == code, Order.status == "paid").all()
        products.append({"code": code, "orders": len(orders), "revenue": sum(x.amount for x in orders)})
    grades = []
    for grade in ["S", "A", "B", "C", "D"]:
        leads = scoped(db.query(Lead), Lead).filter(Lead.lead_grade == grade).all()
        ids = [x.assessment_id for x in leads]
        paid = db.query(Order).filter(Order.status == "paid", Order.assessment_id.in_(ids or [-1])).all()
        grades.append({
            "grade": grade, "leads": len(leads),
            "paid": len({x.assessment_id for x in paid}),
            "conversion_rate": _rate(len({x.assessment_id for x in paid}), len(leads)),
            "revenue": sum(x.amount for x in paid),
        })
    trend = []
    for offset in range(6, -1, -1):
        day = date.today() - timedelta(days=offset)
        start, end = datetime.combine(day, time.min), datetime.combine(day, time.max)
        trend.append({
            "date": day.strftime("%m-%d"),
            "assessments": scoped(db.query(Assessment), Assessment).filter(
                Assessment.created_at >= start, Assessment.created_at <= end
            ).count(),
            "orders": scoped(db.query(Order), Order).filter(
                Order.status == "paid", Order.paid_at >= start, Order.paid_at <= end
            ).count(),
        })
    return {
        "channels": channels, "landing_pages": landing_pages, "products": products,
        "grades": grades, "ab_tests": ab_metrics(db) if assessment_ids is None else [], "trend": trend,
    }
