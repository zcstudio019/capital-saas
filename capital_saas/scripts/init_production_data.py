import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db.database import Base, SessionLocal, engine
from db.migrations import migrate_database
from services.auth_service import ensure_default_admin
from services.settings_service import ensure_default_settings
from services.ab_test_service import ensure_default_experiment
from services.script_template_service import ensure_default_scripts
from services.tag_service import ensure_default_tags
from services.bank_product_service import ensure_default_bank_products
from services.organization_service import ensure_default_organization
from services.notification_service import ensure_default_notification_templates
from services.legal_service import ensure_default_legal_documents

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
    db.commit()
print("生产基础数据初始化完成。迁移字段：", ", ".join(changed) if changed else "none")
