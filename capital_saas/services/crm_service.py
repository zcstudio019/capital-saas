from sqlalchemy.orm import Session

from db.models import Lead, LeadTag, Order, Report


def list_leads(
    db: Session,
    lead_grade: str = "",
    follow_status: str = "",
    recommended_product: str = "",
    source_channel: str = "",
    tag_id: int = 0,
):
    query = db.query(Lead)
    if lead_grade:
        query = query.filter(Lead.lead_grade == lead_grade)
    if follow_status:
        query = query.filter(Lead.follow_status == follow_status)
    if recommended_product:
        query = query.filter(Lead.recommended_product == recommended_product)
    if source_channel:
        query = query.filter(Lead.source_channel == source_channel)
    if tag_id:
        query = query.join(LeadTag).filter(LeadTag.tag_id == tag_id)
    return query.order_by(Lead.created_at.desc()).all()


def list_reports(db: Session):
    return db.query(Report).order_by(Report.created_at.desc()).all()


def list_orders(db: Session):
    return db.query(Order).order_by(Order.created_at.desc()).all()
