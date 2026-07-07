from db.database import Base, engine
from db import models  # noqa: F401
from db.migrations import migrate_database
from db.database import SessionLocal
from services.auth_service import ensure_default_admin
from services.settings_service import ensure_default_settings
from services.ab_test_service import ensure_default_experiment
from services.script_template_service import ensure_default_scripts
from services.tag_service import ensure_default_tags
from services.bank_product_service import ensure_default_bank_products
from services.organization_service import ensure_default_organization
from services.notification_service import ensure_default_notification_templates
from services.legal_service import ensure_default_legal_documents


def init_database():
    Base.metadata.create_all(bind=engine)
    changed = migrate_database()
    with SessionLocal() as db:
        admin = ensure_default_admin(db)
        ensure_default_settings(db)
        ensure_default_experiment(db)
        ensure_default_scripts(db)
        ensure_default_tags(db)
        ensure_default_bank_products(db)
        ensure_default_organization(db, admin)
        ensure_default_notification_templates(db)
        ensure_default_legal_documents(db)
    suffix = f" 已补充字段：{', '.join(changed)}" if changed else ""
    print(f"数据库初始化完成。{suffix}")


if __name__ == "__main__":
    init_database()
