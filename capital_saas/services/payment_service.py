import secrets
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from core.pricing_engine import get_product
from db.models import Assessment, CommissionRecord, CustomerAccount, Order
from services.event_service import track_event
from services.attribution_service import ATTRIBUTION_FIELDS
from utils.logger import logger
from services.tag_service import add_named_tag
from services.consulting_service import ensure_consulting_case
from services.commission_service import create_commissions
from services.settings_service import get_setting
from services.notification_service import notify_payment_success
from services.pilot_service import set_pilot_stage


VALID_PAYMENT_MODES = {"mock", "wechat_pay", "alipay", "manual_transfer"}
VALID_ORDER_STATUSES = {"pending", "paid", "failed", "cancelled", "refunded"}


def create_order(
    db: Session,
    assessment: Assessment,
    product_code: str = "980_capital_health_report",
    pay_channel: str = "mock",
    buyer_contact: str = "",
) -> Order:
    product_code, product = get_product(product_code, db, assessment.id)
    channel = pay_channel if pay_channel in VALID_PAYMENT_MODES else "mock"
    if channel == "mock":
        existing = (
            db.query(Order)
            .filter(
                Order.assessment_id == assessment.id,
                Order.product_code == product_code,
                Order.status == "paid",
            )
            .order_by(Order.id.desc())
            .first()
        )
        if existing:
            return existing
    customer = (db.query(CustomerAccount).filter(CustomerAccount.lead_id == assessment.lead.id).first()
                if assessment.lead else None)
    order = Order(
        assessment_id=assessment.id,
        product_code=product_code,
        product_name=product["name"],
        amount=product["price"],
        status="pending",
        pay_channel=channel,
        transaction_id="",
        buyer_contact=buyer_contact or assessment.phone,
        org_id=assessment.lead.org_id if assessment.lead else None,
        owner_org_id=assessment.lead.owner_org_id if assessment.lead else None,
        owner_user_id=assessment.lead.owner_user_id if assessment.lead else None,
        source_partner_id=assessment.lead.source_partner_id if assessment.lead else None,
        customer_id=customer.id if customer else None,
        **{key: getattr(assessment, key, "") for key in ATTRIBUTION_FIELDS},
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    if customer:
        from services.notification_service import safe_create_notification
        minutes=int(get_setting(db,"payment_pending_remind_minutes","30"))
        safe_create_notification(db,"payment_pending_customer",{"company_name":customer.company_name},
            recipient_customer_id=customer.id,scheduled_at=datetime.now()+timedelta(minutes=minutes),
            related_type="order",related_id=order.id)
        db.commit()
    logger.info(
        "创建订单 order_id=%s assessment_id=%s product=%s channel=%s amount=%s",
        order.id,
        assessment.id,
        product_code,
        channel,
        order.amount,
    )
    return order


def mark_order_paid(
    db: Session,
    order: Order,
    transaction_id: str = "",
    operator: str = "system",
) -> Order:
    if order.status == "paid":
        notify_payment_success(db, order, commit=True)
        return order
    if order.status == "refunded":
        raise ValueError("已退款订单不能重新标记为支付")
    order.status = "paid"
    order.paid_at = datetime.now()
    order.refund_at = None
    order.transaction_id = transaction_id or order.transaction_id or f"LOCAL-{secrets.token_hex(6)}"
    from db.models import NotificationJob
    db.query(NotificationJob).filter(NotificationJob.related_type=="order",
        NotificationJob.related_id==order.id,NotificationJob.template_key=="payment_pending_customer",
        NotificationJob.send_status=="queued").update({"send_status":"cancelled"},synchronize_session=False)
    assessment = order.assessment
    if assessment.lead:
        assessment.lead.conversion_status = "已成交"
        assessment.lead.follow_status = "已付款"
        set_pilot_stage(db, assessment.lead, "paid", commit=False)
        add_named_tag(db, assessment.lead, "已成交")
        if order.product_code in {"299_report", "699_bank_match", "980_capital_health_report"}:
            add_named_tag(db, assessment.lead, "需复购")
    ensure_consulting_case(db, assessment, order.product_code)
    create_commissions(db, "paid_order", order.amount,
        user_id=assessment.lead.owner_user_id if assessment.lead else None,
        org_id=assessment.lead.owner_org_id if assessment.lead else None,
        partner_id=assessment.lead.source_partner_id if assessment.lead else None,
        order_id=order.id, assessment_id=assessment.id,
        lead_id=assessment.lead.id if assessment.lead else None, product_code=order.product_code)
    if order.customer_id and order.product_code in {"299_report","699_bank_match","980_capital_health_report"}:
        from services.notification_service import safe_create_notification
        hours=int(get_setting(db,"upgrade_remind_hours","24"))
        safe_create_notification(db,"upgrade_recommend_customer",{"company_name":assessment.company_name},
            recipient_customer_id=order.customer_id,scheduled_at=datetime.now()+timedelta(hours=hours),
            related_type="order_upgrade",related_id=order.id)
    db.flush()
    track_event(
        db,
        "payment_success",
        assessment_id=assessment.id,
        lead_id=assessment.lead.id if assessment.lead else None,
        data={
            "order_id": order.id,
            "product_code": order.product_code,
            "amount": order.amount,
            "channel": order.pay_channel,
            "operator": operator,
        },
        attribution={key: getattr(assessment, key, "") for key in ATTRIBUTION_FIELDS},
        commit=False,
    )
    notify_payment_success(db, order, commit=False)
    db.commit()
    db.refresh(order)
    logger.info("订单已支付 order_id=%s operator=%s", order.id, operator)
    return order


def mock_pay(db: Session, assessment: Assessment, product_code: str = "980_capital_health_report") -> Order:
    order = create_order(db, assessment, product_code, "mock", assessment.phone)
    return mark_order_paid(db, order, operator="mock")


def refund_order(db: Session, order: Order, operator: str) -> Order:
    if order.status != "paid":
        raise ValueError("只有已支付订单可以退款")
    order.status = "refunded"
    order.refund_at = datetime.now()
    cancelled = (
        db.query(CommissionRecord)
        .filter(CommissionRecord.related_order_id == order.id)
        .update({
            "settlement_status": "cancelled",
            "settlement_note": f"订单#{order.id}已退款，提成记录已取消。",
            "updated_at": datetime.now(),
        }, synchronize_session=False)
    )
    assessment = order.assessment
    track_event(
        db,
        "order_refunded",
        assessment_id=assessment.id if assessment else None,
        lead_id=assessment.lead.id if assessment and assessment.lead else None,
        data={
            "order_id": order.id,
            "product_code": order.product_code,
            "amount": order.amount,
            "operator": operator,
            "cancelled_commissions": cancelled,
        },
        attribution={key: getattr(assessment, key, "") for key in ATTRIBUTION_FIELDS} if assessment else {},
        commit=False,
    )
    db.commit()
    logger.info("订单退款 order_id=%s operator=%s", order.id, operator)
    return order


def cancel_order(db: Session, order: Order, operator: str) -> Order:
    if order.status not in {"pending", "failed", "paid"}:
        raise ValueError("只有待支付、失败或已支付订单可以取消")
    order.status = "cancelled"
    if order.paid_at:
        db.query(CommissionRecord).filter(CommissionRecord.related_order_id == order.id).update({
            "settlement_status": "cancelled",
            "settlement_note": f"订单#{order.id}已取消，提成记录已取消。",
            "updated_at": datetime.now(),
        }, synchronize_session=False)
    db.commit()
    logger.info("订单取消 order_id=%s operator=%s", order.id, operator)
    return order


def has_paid_order(db: Session, assessment_id: int) -> bool:
    return (
        db.query(Order)
        .filter(Order.assessment_id == assessment_id, Order.status == "paid")
        .first()
        is not None
    )
