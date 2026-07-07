import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.config import BASE_DIR
from db.database import SessionLocal
from db.models import BankProduct, CommissionRule, LegalDocument, NotificationTemplate, Organization, SalesScriptTemplate, SystemSetting, Tag

MODELS = [SystemSetting, LegalDocument, NotificationTemplate, SalesScriptTemplate, BankProduct, Tag, Organization, CommissionRule]


def row_dict(obj):
    skip = {"id", "created_at", "updated_at"}
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns if c.name not in skip}


out = BASE_DIR / "data" / "seed_export.json"
with SessionLocal() as db:
    data = {model.__tablename__: [row_dict(x) for x in db.query(model).all()] for model in MODELS}
out.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
print(f"基础数据已导出：{out}")
