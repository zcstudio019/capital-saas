from sqlalchemy.orm import Session

from db.models import ChannelPartner, CommissionRecord, CommissionRule
from services.event_service import track_event


def create_commissions(db: Session, trigger_event: str, base_amount: float,
    user_id=None, org_id=None, partner_id=None, order_id=None, project_id=None,
    assessment_id=None, lead_id=None, product_code="") -> list[CommissionRecord]:
    rules = db.query(CommissionRule).filter(CommissionRule.trigger_event == trigger_event,
                                            CommissionRule.is_active.is_(True)).all()
    created = []
    for rule in rules:
        if rule.product_code and rule.product_code != product_code: continue
        exists = db.query(CommissionRecord).filter(CommissionRecord.related_order_id == order_id,
            CommissionRecord.related_project_id == project_id, CommissionRecord.trigger_event == trigger_event,
            CommissionRecord.user_id == user_id, CommissionRecord.partner_id == partner_id).first()
        if exists: continue
        amount = rule.commission_value if rule.commission_type == "fixed_amount" else base_amount * rule.commission_value / 100
        record = CommissionRecord(user_id=user_id, org_id=org_id, partner_id=partner_id,
            related_order_id=order_id, related_project_id=project_id, trigger_event=trigger_event,
            base_amount=base_amount, commission_amount=round(amount,2), settlement_status="pending")
        db.add(record); db.flush(); created.append(record)
        track_event(db,"commission_record_created",assessment_id,lead_id,
            {"record_id":record.id,"trigger_event":trigger_event,"amount":record.commission_amount},commit=False)
    partner = db.get(ChannelPartner, partner_id) if partner_id else None
    partner_matches = partner and (
        (trigger_event == "paid_order" and partner.settlement_mode == "per_paid_order") or
        (trigger_event == "project_disbursed" and partner.settlement_mode == "per_disbursed_amount")
    )
    if partner_matches and partner.commission_rate > 0:
        exists = db.query(CommissionRecord).filter(
            CommissionRecord.related_order_id == order_id,
            CommissionRecord.related_project_id == project_id,
            CommissionRecord.trigger_event == trigger_event,
            CommissionRecord.user_id.is_(None),
            CommissionRecord.partner_id == partner.id,
        ).first()
        if not exists:
            record = CommissionRecord(user_id=None, org_id=org_id, partner_id=partner.id,
                related_order_id=order_id, related_project_id=project_id, trigger_event=trigger_event,
                base_amount=base_amount, commission_amount=round(base_amount * partner.commission_rate / 100, 2),
                settlement_status="pending", settlement_note=f"渠道伙伴：{partner.partner_name}")
            db.add(record); db.flush(); created.append(record)
            track_event(db, "commission_record_created", assessment_id, lead_id,
                {"record_id": record.id, "trigger_event": trigger_event,
                 "partner_id": partner.id, "amount": record.commission_amount}, commit=False)
    return created
