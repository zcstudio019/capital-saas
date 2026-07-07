import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.config import BASE_DIR
from db.database import SessionLocal
from db.models import BankProduct, CommissionRule, LegalDocument, NotificationTemplate, Organization, SalesScriptTemplate, SystemSetting, Tag

MODELS = {m.__tablename__: m for m in [SystemSetting, LegalDocument, NotificationTemplate, SalesScriptTemplate, BankProduct, Tag, Organization, CommissionRule]}
UNIQUE_KEYS = {
    "system_settings": "key",
    "legal_documents": "document_key",
    "notification_templates": "template_key",
    "sales_script_templates": "name",
    "bank_products": "product_name",
    "tags": "name",
    "organizations": "org_name",
    "commission_rules": "rule_name",
}

path = Path(__file__).resolve().parent.parent / "data" / "seed_export.json"
data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
created = updated = 0
with SessionLocal() as db:
    for table, rows in data.items():
        model = MODELS.get(table)
        if not model:
            continue
        key = UNIQUE_KEYS.get(table)
        for row in rows:
            item = db.query(model).filter(getattr(model, key) == row[key]).first() if key and row.get(key) is not None else None
            if item:
                for k, v in row.items():
                    if hasattr(item, k):
                        setattr(item, k, v)
                updated += 1
            else:
                db.add(model(**row))
                created += 1
    db.commit()
print(f"种子数据导入完成：created={created}, updated={updated}")
