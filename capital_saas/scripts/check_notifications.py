import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db.database import Base, SessionLocal, engine
from db.migrations import migrate_database
from db.models import InternalNotification, User
from services.auth_service import ensure_default_admin, hash_password
from services.notification_service import create_internal_notification, get_unread_count


def main() -> None:
    Base.metadata.create_all(bind=engine)
    migrate_database()
    with SessionLocal() as db:
        admin = ensure_default_admin(db)
        assert db.query(InternalNotification).limit(1).all() is not None
        create_internal_notification(
            db,
            admin.id,
            "通知中心检查",
            "管理员内部通知创建检查。",
            "system",
            related_type="system",
            related_id=0,
            action_url="/admin/notifications",
            commit=False,
        )
        sales = db.query(User).filter(User.username == "notification_check_sales").first()
        if not sales:
            sales = User(
                username="notification_check_sales",
                password_hash=hash_password("Passw0rd!"),
                display_name="通知检查销售",
                role="sales",
                is_active=True,
            )
            db.add(sales)
            db.flush()
        create_internal_notification(
            db,
            sales.id,
            "测试分配线索通知",
            "客户 测试企业 已分配给你，请尽快联系客户并记录跟进结果。",
            "lead_assigned",
            related_type="lead",
            related_id=0,
            action_url="/sales/leads",
            commit=False,
        )
        db.commit()
        assert get_unread_count(db, sales.id) >= 1
    print("NOTIFICATIONS_CHECK_OK")


if __name__ == "__main__":
    main()
