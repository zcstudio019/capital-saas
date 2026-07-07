import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TEST_DB = ROOT / "phase14_test.db"
if TEST_DB.exists():
    TEST_DB.unlink()

os.environ["APP_ENV"] = "development"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
os.environ["SECRET_KEY"] = "phase14-smoke-secret"
os.environ["RATE_LIMIT_ENABLED"] = "false"

from fastapi.testclient import TestClient  # noqa
from db.init_db import init_database  # noqa
from db.database import SessionLocal  # noqa
from db.models import CustomerAccount, CustomerFeedback, Lead, OperationIssue, PilotBatch, PilotInviteCode  # noqa
from main import app  # noqa

init_database()
client = TestClient(app)

assessment_payload = {
    "company_name": "Phase14试运营客户",
    "contact_name": "赵总",
    "phone": "13900001111",
    "wechat_id": "phase14wx",
    "city": "上海",
    "industry": "制造业",
    "years": 5,
    "employee_count": 30,
    "annual_revenue": 900,
    "net_profit": 90,
    "monthly_cashflow": 50,
    "debt_total": 150,
    "short_debt": 50,
    "receivable_days": 50,
    "funding_need": 300,
    "funding_purpose": "补充流动资金",
    "has_collateral": "true",
    "tax_status": "true",
    "credit_status": "true",
    "knows_cashflow": "true",
    "has_budget": "true",
    "leverage_attitude": "适中",
    "asset_efficiency": "中",
    "fund_usage_plan": "true",
}


with client:
    assert client.get("/").status_code == 200
    login = client.post("/login", data={"username": "admin", "password": "admin123"}, follow_redirects=False)
    assert login.status_code in (302, 303), login.text[:200]

    assert client.get("/admin/pilot-batches").status_code == 200
    r = client.post("/admin/pilot-batches/create", data={
        "batch_name": "Phase14首批客户验证",
        "start_date": "2026-06-27",
        "end_date": "2026-07-27",
        "target_customer_count": 50,
        "target_paid_count": 10,
        "target_revenue": 10000,
        "target_document_upload_count": 20,
        "target_project_count": 5,
        "owner_user_id": 0,
        "note": "phase14 smoke",
    }, follow_redirects=False)
    assert r.status_code in (302, 303)
    with SessionLocal() as db:
        batch = db.query(PilotBatch).filter_by(batch_name="Phase14首批客户验证").one()
        batch_id = batch.id

    detail = client.get(f"/admin/pilot-batches/{batch_id}")
    assert detail.status_code == 200
    r = client.post(f"/admin/pilot-batches/{batch_id}/invite-codes/create", data={"channel_name": "首批邀约", "max_uses": 10}, follow_redirects=False)
    assert r.status_code in (302, 303)
    with SessionLocal() as db:
        code = db.query(PilotInviteCode).filter_by(pilot_batch_id=batch_id).one()

    client.get(f"/lp/rongzi?pilot={code.invite_code}")
    r = client.post("/assessment/submit", data=assessment_payload, follow_redirects=False)
    assert r.status_code in (302, 303)
    aid = int(r.headers["location"].rstrip("/").split("/")[-1])
    with SessionLocal() as db:
        lead = db.query(Lead).filter_by(assessment_id=aid).one()
        assert lead.pilot_batch_id == batch_id
        assert lead.pilot_stage == "assessed"
        lead_id = lead.id
        customer = db.query(CustomerAccount).filter_by(lead_id=lead_id).one()
        customer_id = customer.id

    assert client.get("/admin/pilot-dashboard").status_code == 200
    assert client.get(f"/admin/leads/{lead_id}/journey").status_code == 200
    assert client.get(f"/admin/pilot-batches/{batch_id}/export.csv").status_code == 200

    token_resp = client.post(f"/admin/client-portals/{customer_id}/generate-token", follow_redirects=False)
    assert token_resp.status_code in (302, 303)
    with SessionLocal() as db:
        customer = db.get(CustomerAccount, customer_id)
        from db.models import CustomerAccessToken
        token = db.query(CustomerAccessToken).filter_by(customer_id=customer_id, is_active=True).order_by(CustomerAccessToken.id.desc()).first().token
    assert client.get(f"/client/login-token/{token}", follow_redirects=False).status_code in (302, 303)
    assert client.get("/client/feedback").status_code == 200
    r = client.post("/client/feedback/submit", data={
        "feedback_type": "report_quality",
        "rating": 5,
        "title": "报告很有帮助",
        "content": "希望补充更多银行路径。",
        "page_url": "/client/reports",
    }, follow_redirects=False)
    assert r.status_code in (302, 303)
    with SessionLocal() as db:
        fb = db.query(CustomerFeedback).filter_by(lead_id=lead_id).one()
        feedback_id = fb.id

    login = client.post("/login", data={"username": "admin", "password": "admin123"}, follow_redirects=False)
    assert login.status_code in (302, 303)
    assert client.get("/admin/feedback").status_code == 200
    assert client.get(f"/admin/feedback/{feedback_id}").status_code == 200
    r = client.post(f"/admin/feedback/{feedback_id}/convert-issue", data={"severity": "high"}, follow_redirects=False)
    assert r.status_code in (302, 303)
    with SessionLocal() as db:
        assert db.query(OperationIssue).filter_by(related_lead_id=lead_id).count() == 1

    assert client.get("/admin/issues").status_code == 200
    r = client.post("/admin/daily-reports/generate", data={"report_date": "2026-06-27", "pilot_batch_id": batch_id}, follow_redirects=False)
    assert r.status_code in (302, 303)
    assert client.get(r.headers["location"]).status_code == 200
    r = client.post("/admin/weekly-reports/generate", data={"week_start": "2026-06-27", "pilot_batch_id": batch_id}, follow_redirects=False)
    assert r.status_code in (302, 303)
    assert client.get(r.headers["location"]).status_code == 200

print({"assessment_id": aid, "lead_id": lead_id, "batch_id": batch_id, "feedback_id": feedback_id})
print("PHASE14_PILOT_OPERATIONS_OK")
