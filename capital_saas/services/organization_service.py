from sqlalchemy import text
from sqlalchemy.orm import Session

from db.models import (CommissionRule, Organization, User)


DEFAULT_RULES = [
    ("299销售固定奖励", "sales", "299_report", "paid_order", "fixed_amount", 30),
    ("699销售提成", "sales", "699_bank_match", "paid_order", "percentage", 5),
    ("1999销售提成", "sales", "1999_structure_plan", "paid_order", "percentage", 8),
    ("顾问放款预留", "consultant", "", "project_disbursed", "percentage", 0.1),
]


def ensure_default_organization(db: Session, admin_user: User | None = None) -> Organization:
    hq = db.query(Organization).filter(Organization.org_type == "headquarters").first()
    if not hq:
        hq = Organization(org_name="沪上银总部", org_type="headquarters", city="上海",
                          province="上海", status="active")
        db.add(hq); db.flush()
    if admin_user:
        admin_user.org_id = hq.id; hq.manager_user_id = admin_user.id
    for model_name in ["users", "leads", "orders", "consulting_cases", "financing_projects", "funding_applications"]:
        try:
            columns = {row[1] for row in db.execute(text(f"PRAGMA table_info({model_name})")).all()}
            if "org_id" in columns: db.execute(text(f"UPDATE {model_name} SET org_id=:hq WHERE org_id IS NULL"), {"hq":hq.id})
            if "owner_org_id" in columns: db.execute(text(f"UPDATE {model_name} SET owner_org_id=:hq WHERE owner_org_id IS NULL"), {"hq":hq.id})
        except Exception:
            pass
    if not db.query(CommissionRule).count():
        for name, role, product, trigger, ctype, value in DEFAULT_RULES:
            db.add(CommissionRule(rule_name=name, role_type=role, product_code=product,
                trigger_event=trigger, commission_type=ctype, commission_value=value))
    db.commit(); db.refresh(hq); return hq
