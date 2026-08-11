"""客户报告历史、身份恢复与越权隔离专项验收。"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEST_DB = ROOT / "phase_customer_report_history_test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
os.environ["AI_MODE"] = "mock"
if TEST_DB.exists():
    TEST_DB.unlink()
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from db.database import SessionLocal
from db.models import CustomerAccessToken, CustomerAccount, NotificationJob, Report, ReportVersion
from main import app


def payload(company: str, phone: str, revenue: str = "12000000") -> dict[str, str]:
    return {
        "company_name": company, "contact_name": "张经理", "phone": phone,
        "industry": "制造业", "years": "6", "annual_revenue": revenue,
        "net_profit_margin": "8.5", "debt_total": "1800000",
        "short_debt": "600000", "funding_need": "3000000",
        "funding_purposes": "补充流动资金", "collateral_types": "有设备",
        "enterprise_credit_status": "no_overdue", "legal_credit_status": "no_overdue",
        "credit_query_count_6m": "3",
    }


def submit(client: TestClient, data: dict[str, str]) -> int:
    response = client.post("/assessment/submit", data=data, follow_redirects=False)
    assert response.status_code == 303
    return int(response.headers["location"].rsplit("/", 1)[-1])


def run() -> None:
    with TestClient(app) as client_a:
        first_id = submit(client_a, payload("上海历史报告一号有限公司", "13800138001"))
        first_result = client_a.get(f"/result/{first_id}")
        assert first_result.status_code == 200 and "企业资本健康摘要" in first_result.text
        setup = client_a.post("/client/setup-account", data={
            "name": "张经理", "password": "History123!", "confirm_password": "History123!",
        }, follow_redirects=False)
        assert setup.status_code == 303 and setup.headers["location"] == "/client/reports"
        reports_page = client_a.get("/client/reports")
        assert reports_page.status_code == 200 and "上海历史报告一号有限公司" in reports_page.text

        client_a.get("/client/logout")
        assert client_a.get(f"/result/{first_id}", follow_redirects=False).status_code == 303
        access_page = client_a.get("/my-reports")
        assert access_page.status_code == 200 and "找回我的报告" in access_page.text
        access_request = client_a.post("/my-reports/access", data={"phone": "13800138001"})
        assert access_request.status_code == 200 and "访问链接申请已受理" in access_request.text
        with SessionLocal() as db:
            customer = db.query(CustomerAccount).filter(CustomerAccount.login_phone == "13800138001").one()
            token = db.query(CustomerAccessToken).filter_by(customer_id=customer.id, is_active=True).one()
            first_report = db.query(Report).filter_by(assessment_id=first_id).one()
            assert first_report.customer_id == customer.id
            assert db.query(ReportVersion).filter_by(report_id=first_report.id, access_level="free").count() == 1
            assert db.query(NotificationJob).filter_by(
                recipient_customer_id=customer.id, template_key="free_report_ready_customer"
            ).count() == 1
            token_value = token.token
            report_id = first_report.id
        login = client_a.get(f"/client/login-token/{token_value}?next=/client/reports", follow_redirects=False)
        assert login.status_code == 303 and login.headers["location"] == "/client/reports"
        assert "上海历史报告一号有限公司" in client_a.get("/client/reports").text

        second_id = submit(client_a, payload("上海历史报告二号有限公司", "13800138001", "15000000"))
        history = client_a.get("/client/reports")
        assert all(name in history.text for name in ["上海历史报告一号有限公司", "上海历史报告二号有限公司"])
        with SessionLocal() as db:
            customer_count = db.query(CustomerAccount).filter(CustomerAccount.login_phone == "13800138001").count()
            owned_reports = db.query(Report).filter(Report.customer_id == customer.id).count()
            assert customer_count == 1 and owned_reports == 2

        paid = client_a.post(f"/payment/mock-pay/{first_id}?product=980_capital_health_report", follow_redirects=False)
        assert paid.status_code == 303
        paid_history = client_a.get("/client/reports")
        assert "企业资本健康体检报告" in paid_history.text and "完整体检报告" in paid_history.text
        with SessionLocal() as db:
            assert db.query(NotificationJob).filter_by(
                recipient_customer_id=customer.id, template_key="capital_health_report_unlocked_customer"
            ).count() == 1

        with TestClient(app) as client_b:
            other_id = submit(client_b, payload("上海隔离客户有限公司", "13800138002", "8000000"))
            with SessionLocal() as db:
                other_report_id = db.query(Report).filter_by(assessment_id=other_id).one().id
            forbidden = client_a.get(f"/client/reports/{other_report_id}")
            assert forbidden.status_code == 404
            assert "上海隔离客户有限公司" not in forbidden.text
            assert client_a.get(f"/api/report/{other_id}").status_code == 404

        client_a.get("/client/logout")
        with SessionLocal() as db:
            stale = db.query(CustomerAccessToken).filter_by(token=token_value).one()
            stale.expired_at = datetime.now() - timedelta(minutes=1)
            db.commit()
        expired = client_a.get(f"/client/login-token/{token_value}", follow_redirects=False)
        assert expired.status_code == 303 and expired.headers["location"].startswith("/client/login")
        client_a.post("/my-reports/access", data={"phone": "13800138001"})
        with SessionLocal() as db:
            fresh = db.query(CustomerAccessToken).filter_by(customer_id=customer.id, is_active=True).one()
            assert fresh.expired_at > datetime.now()
        assert client_a.get(f"/client/login-token/{fresh.token}", follow_redirects=False).status_code == 303
        assert client_a.get(f"/client/reports/{report_id}").status_code == 200

    print("CUSTOMER_REPORT_HISTORY_OK")


if __name__ == "__main__":
    run()
