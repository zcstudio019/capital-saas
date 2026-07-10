import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db.database import Base, SessionLocal, engine
from db.migrations import migrate_database
from db.models import InternalNotification, User
from services.assessment_service import create_assessment
from services.auth_service import ensure_default_admin, hash_password
from services.payment_service import create_order, mark_order_paid
from services.notification_service import notify_payment_success


PAYLOAD = {
    "company_name": "支付通知检查企业",
    "contact_name": "张三",
    "phone": "13800138000",
    "wechat_id": "pay_notice_demo",
    "city": "上海",
    "industry": "智能制造",
    "years": 6,
    "employee_count": 48,
    "annual_revenue": 12000000,
    "net_profit": 1350000,
    "monthly_cashflow": 720000,
    "debt_total": 2800000,
    "short_debt": 900000,
    "receivable_days": 52,
    "funding_need": 2000000,
    "funding_purpose": "补充经营周转资金",
    "has_collateral": True,
    "tax_status": True,
    "credit_status": True,
    "knows_cashflow": True,
    "has_budget": True,
    "leverage_attitude": "适中",
    "asset_efficiency": "高",
    "fund_usage_plan": True,
}


def main() -> None:
    Base.metadata.create_all(bind=engine)
    migrate_database()
    with SessionLocal() as db:
        admin = ensure_default_admin(db)
        sales = db.query(User).filter(User.username == "payment_notice_sales").first()
        if not sales:
            sales = User(
                username="payment_notice_sales",
                password_hash=hash_password("Passw0rd!"),
                display_name="支付通知销售",
                role="sales",
                is_active=True,
            )
            db.add(sales)
            db.flush()
        assessment = create_assessment(db, PAYLOAD)
        lead = assessment.lead
        lead.assigned_sales_id = sales.id
        lead.owner_user_id = sales.id
        db.commit()
        order = create_order(db, assessment, "299_report", "mock", assessment.phone)
        mark_order_paid(db, order, operator="payment_notification_check")
        before = db.query(InternalNotification).filter(
            InternalNotification.notification_type == "payment_success",
            InternalNotification.related_type == "order",
            InternalNotification.related_id == order.id,
        ).count()
        notify_payment_success(db, order, commit=True)
        after = db.query(InternalNotification).filter(
            InternalNotification.notification_type == "payment_success",
            InternalNotification.related_type == "order",
            InternalNotification.related_id == order.id,
        ).count()
        assert before == after
        assert db.query(InternalNotification).filter(
            InternalNotification.user_id == admin.id,
            InternalNotification.notification_type == "payment_success",
            InternalNotification.related_type == "order",
            InternalNotification.related_id == order.id,
            InternalNotification.status == "unread",
        ).first()
        assert db.query(InternalNotification).filter(
            InternalNotification.user_id == sales.id,
            InternalNotification.notification_type == "payment_success",
            InternalNotification.related_type == "order",
            InternalNotification.related_id == order.id,
        ).first()
    print("PAYMENT_NOTIFICATION_CHECK_OK")


if __name__ == "__main__":
    main()
