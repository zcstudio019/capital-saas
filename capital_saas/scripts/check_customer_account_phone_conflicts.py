"""Read-only customer phone identity diagnostic for production rollout."""
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db.database import SessionLocal
from db.models import CustomerAccount, Order, Report
from services.customer_phone_service import normalize_phone

with SessionLocal() as db:
    groups = defaultdict(list)
    for item in db.query(CustomerAccount).order_by(CustomerAccount.id).all():
        phone = normalize_phone(item.login_phone or item.phone)
        if phone:
            groups[phone].append(item)
    focus = "18487317529"
    for phone, accounts in groups.items():
        if len(accounts) == 1 and phone != focus:
            continue
        print(f"login_phone={phone} customer_account_count={len(accounts)}")
        for account in accounts:
            reports = db.query(Report).filter(Report.customer_id == account.id).count()
            orders = db.query(Order).filter(Order.customer_id == account.id).count()
            print("  ", {
                "id": account.id, "lead_id": account.lead_id, "assessment_id": account.assessment_id,
                "registration_source": account.registration_source, "deleted_at": str(account.deleted_at) if account.deleted_at else None,
                "password_hash_exists": bool(account.password_hash), "report_count": reports, "order_count": orders,
            })
print("CUSTOMER_ACCOUNT_PHONE_CONFLICT_CHECK_OK")
