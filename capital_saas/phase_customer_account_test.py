"""正式客户账号、长期登录、跨测评归集和权限隔离专项验收。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEST_DB = ROOT / "phase_customer_account_test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
os.environ["AI_MODE"] = "mock"
os.environ["PAYMENT_MODE"] = "mock"
if TEST_DB.exists():
    TEST_DB.unlink()
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from db.database import SessionLocal
from db.models import AdvisorBooking, CustomerAccessToken, CustomerAccount, Order, Report, User
from main import app
from services.customer_portal_service import backfill_customer_account_links, generate_login_token
from services.project_service import create_project


def payload(company: str, phone: str) -> dict[str, str]:
    return {
        "company_name": company, "contact_name": "张经理", "phone": phone,
        "industry": "制造业", "years": "5", "annual_revenue": "10000000",
        "net_profit_margin": "8", "debt_total": "1500000", "short_debt": "500000",
        "funding_need": "2000000", "funding_purposes": "补充流动资金",
        "collateral_types": "有设备", "enterprise_credit_status": "no_overdue",
        "legal_credit_status": "no_overdue", "credit_query_count_6m": "2",
    }


def submit(client: TestClient, company: str, phone: str) -> int:
    response = client.post("/assessment/submit", data=payload(company, phone), follow_redirects=False)
    assert response.status_code == 303
    return int(response.headers["location"].rsplit("/", 1)[-1])


def login(client: TestClient, phone: str, password: str = "Customer123") -> None:
    response = client.post("/client/login", data={
        "phone": phone, "password": password, "remember_me": "1", "next_url": "/client/dashboard",
    }, follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/client/dashboard"
    cookie = response.headers.get("set-cookie", "")
    assert "capital_customer_remember=" in cookie and "HttpOnly" in cookie and "SameSite=lax" in cookie


def run() -> None:
    phone_a = "13800138881"
    with TestClient(app) as client_a:
        first_assessment = submit(client_a, "客户账号验收企业一期", phone_a)
        result = client_a.get(f"/result/{first_assessment}")
        assert result.status_code == 200 and "激活我的账号" in result.text
        setup = client_a.get("/client/setup-account")
        assert setup.status_code == 200 and phone_a in setup.text
        created = client_a.post("/client/setup-account", data={
            "name": "张经理", "password": "Customer123", "confirm_password": "Customer123",
        }, follow_redirects=False)
        assert created.status_code == 303 and created.headers["location"] == "/client/reports"
        reports = client_a.get("/client/reports")
        assert reports.status_code == 200 and "客户账号验收企业一期" in reports.text

        client_a.get("/client/logout")
        logged_out = client_a.get("/client/dashboard", follow_redirects=False)
        assert logged_out.status_code == 303 and logged_out.headers.get("location", "").startswith("/client/login"), (
            logged_out.status_code, dict(logged_out.headers), logged_out.text,
        )
        wrong = client_a.post("/client/login", data={"phone": phone_a, "password": "wrong-password"})
        assert wrong.status_code == 400 and "手机号或密码不正确" in wrong.text
        login(client_a, phone_a)

        second_assessment = submit(client_a, "客户账号验收企业二期", phone_a)
        history = client_a.get("/client/reports")
        assert history.status_code == 200
        assert "客户账号验收企业一期" in history.text and "客户账号验收企业二期" in history.text
        with SessionLocal() as db:
            customers = db.query(CustomerAccount).filter(CustomerAccount.login_phone == phone_a).all()
            assert len(customers) == 1
            customer_a = customers[0]
            reports_a = db.query(Report).filter(Report.customer_id == customer_a.id).all()
            assert len(reports_a) == 2
            first_report = next(item for item in reports_a if item.assessment_id == first_assessment)
            second_report = next(item for item in reports_a if item.assessment_id == second_assessment)
            customer_a_id, first_report_id, second_report_id = customer_a.id, first_report.id, second_report.id

        paid = client_a.post(
            f"/payment/mock-pay/{first_assessment}?product=980_capital_health_report",
            follow_redirects=False,
        )
        assert paid.status_code == 303
        with SessionLocal() as db:
            order = db.query(Order).filter_by(assessment_id=first_assessment, status="paid").one()
            assert order.customer_id == customer_a_id

        booked = client_a.post(f"/advisor/book/{first_report_id}", data={
            "company_name": "客户账号验收企业一期", "contact_name": "张经理", "phone": phone_a,
            "service_type": "one_on_one_consulting", "consultation_focus": "融资结构优化",
            "preferred_time": "工作日下午",
        })
        assert booked.status_code == 200
        with SessionLocal() as db:
            booking = db.query(AdvisorBooking).filter_by(report_id=first_report_id).one()
            assert booking.customer_id == customer_a_id
            lead = db.get(Report, first_report_id).assessment.lead
            admin = db.query(User).filter_by(username="admin").one()
            project = create_project(db, lead, admin, "客户融资项目", 2_000_000)
            assert project.customer_id == customer_a_id

        dashboard = client_a.get("/client/dashboard")
        assert dashboard.status_code == 200 and all(text in dashboard.text for text in ["我的报告", "我的订单", "顾问预约", "融资项目", "未读通知"])
        assert client_a.get("/client/advisor-bookings").status_code == 200
        assert client_a.get("/client/account").status_code == 200

        with TestClient(app) as client_b:
            phone_b = "13800138882"
            assessment_b = submit(client_b, "隔离客户企业", phone_b)
            client_b.post("/client/setup-account", data={
                "name": "李经理", "password": "Customer456", "confirm_password": "Customer456",
            })
            with SessionLocal() as db:
                report_b = db.query(Report).filter_by(assessment_id=assessment_b).one()
                report_b_id = report_b.id
            assert client_a.get(f"/client/reports/{report_b_id}").status_code == 404

        # 模拟旧数据丢失 customer_id，再按手机号回填。
        with SessionLocal() as db:
            report = db.get(Report, second_report_id)
            report.customer_id = None
            report.assessment.customer_id = None
            report.assessment.lead.customer_id = None
            db.commit()
            customer = db.get(CustomerAccount, customer_a_id)
            backfill_customer_account_links(db, customer)
            db.refresh(report)
            assert report.customer_id == customer_a_id
            assert report.assessment.customer_id == customer_a_id
            assert report.assessment.lead.customer_id == customer_a_id

        client_a.get("/client/logout")
        with SessionLocal() as db:
            token = generate_login_token(db, db.get(CustomerAccount, customer_a_id), days=7)
            token_value = token.token
        token_login = client_a.get(f"/client/login-token/{token_value}?next=/client/reports", follow_redirects=False)
        assert token_login.status_code == 303 and token_login.headers["location"] == "/client/reports"
        assert "客户账号验收企业一期" in client_a.get("/client/reports").text
        assert client_a.get("/client/dashboard").status_code == 200

        client_a.get("/client/logout")
        login(client_a, phone_a)
        assert "客户账号验收企业二期" in client_a.get("/client/reports").text

        client_a.get("/client/logout")
        known = client_a.post("/client/forgot-password", data={"phone": phone_a})
        unknown = client_a.post("/client/forgot-password", data={"phone": "13999999999"})
        assert known.status_code == unknown.status_code == 200
        assert "如果该手机号已注册" in known.text and "如果该手机号已注册" in unknown.text
        with SessionLocal() as db:
            reset = db.query(CustomerAccessToken).filter_by(
                customer_id=customer_a_id, token_type="password_reset", is_active=True,
            ).one()
            reset_token = reset.token
        changed = client_a.post(f"/client/reset-password/{reset_token}", data={
            "password": "NewCustomer123", "confirm_password": "NewCustomer123",
        }, follow_redirects=False)
        assert changed.status_code == 303
        client_a.get("/client/logout")
        login(client_a, phone_a, "NewCustomer123")

        admin_login = client_a.post("/login", data={
            "username": "admin", "password": "admin123", "next_url": "/admin/customers",
        }, follow_redirects=False)
        assert admin_login.status_code == 303
        admin_customers = client_a.get("/admin/customers")
        assert admin_customers.status_code == 200 and "客户账号" in admin_customers.text

    print("CUSTOMER_ACCOUNT_SYSTEM_OK")


if __name__ == "__main__":
    run()
