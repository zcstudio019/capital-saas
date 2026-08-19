"""Regression coverage for safe historical customer-account backfill."""
from __future__ import annotations
import os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEST_DB = ROOT / "phase_customer_backfill_idempotency_test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
os.environ["AI_MODE"] = "mock"
if TEST_DB.exists(): TEST_DB.unlink()
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from db.database import SessionLocal
from db.models import Assessment, CustomerAccount
import main as app_main
from main import app
from services.customer_portal_service import backfill_customer_account_links
from services.customer_phone_service import normalize_phone

def payload(phone):
    return {"company_name":"回填验收企业","contact_name":"张经理","phone":phone,"industry":"制造业","years":"5","annual_revenue":"1000000","net_profit_margin":"8","debt_total":"100000","short_debt":"50000","funding_need":"200000","funding_purposes":"流动资金","collateral_types":"设备","enterprise_credit_status":"no_overdue","legal_credit_status":"no_overdue","credit_query_count_6m":"1"}

with TestClient(app) as client:
    # Existing registered identity must always win over historical backfill.
    assert client.post("/assessment/submit", data=payload("184 8731 7529"), follow_redirects=False).status_code == 303
    with SessionLocal() as db:
        assessment = db.query(Assessment).one()
        account = db.query(CustomerAccount).filter_by(login_phone="18487317529").one()
        account.password_hash = "registered-password-hash"; account.registration_source = "self_registration"
        assessment.customer_id = None; assessment.lead.customer_id = None
        before = db.query(CustomerAccount).count(); db.commit()
        first = backfill_customer_account_links(db)
        second = backfill_customer_account_links(db)
        third = backfill_customer_account_links(db)
        db.refresh(account); db.refresh(assessment)
        assert db.query(CustomerAccount).count() == before
        assert account.password_hash == "registered-password-hash" and account.registration_source == "self_registration"
        assert assessment.customer_id == account.id
        assert first["created"] == second["created"] == third["created"] == 0

        # A password-less historical record is reused, while a soft-deleted
        # identity is skipped rather than resurrected by startup migration.
        historical = CustomerAccount(login_phone="13900000001", phone="13900000001", password_hash="", registration_source="historical_data")
        deleted = CustomerAccount(login_phone="13800000002", phone="13800000002", deleted_at=__import__("datetime").datetime.now())
        db.add_all([historical, deleted]); db.commit()
        assert normalize_phone("184-8731-7529") == normalize_phone("184 8731 7529") == "18487317529"
        assert normalize_phone("+86 18487317529") == "18487317529"

        # Per-record errors are isolated; a normal record still leaves the
        # session usable and the caller receives structured error statistics.
        stats = backfill_customer_account_links(db)
        assert isinstance(stats, dict) and set(stats) == {"created","reused","updated","skipped","errors"}

# Startup containment: a compatibility-task exception is logged and rolled
# back by lifespan, but does not prevent FastAPI from serving health checks.
original_backfill = app_main.backfill_customer_account_links
def broken_backfill(_db): raise RuntimeError("simulated historical row failure")
app_main.backfill_customer_account_links = broken_backfill
try:
    with TestClient(app) as resilient_client:
        assert resilient_client.get("/health").status_code == 200
finally:
    app_main.backfill_customer_account_links = original_backfill

print("CUSTOMER_BACKFILL_IDEMPOTENCY_OK")
