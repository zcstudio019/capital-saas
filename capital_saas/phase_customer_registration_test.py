"""客户自主注册、历史账号找回和多企业报告归属专项验收。"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEST_DB = ROOT / "phase_customer_registration_test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
os.environ["AI_MODE"] = "mock"
os.environ["APP_ENV"] = "development"
if TEST_DB.exists():
    TEST_DB.unlink()
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from db.database import SessionLocal
from db.models import Assessment, AuditLog, CustomerAccount, Event, Report
from main import app
from services.auth_service import verify_password


def assessment_payload(phone: str, company: str) -> dict[str, str]:
    return {
        "company_name": company, "contact_name": "注册验收客户", "phone": phone,
        "industry": "制造业", "years": "6", "annual_revenue": "12000000",
        "net_profit_margin": "8.5", "debt_total": "1600000", "short_debt": "500000",
        "funding_need": "2500000", "funding_purposes": "补充流动资金",
        "collateral_types": "有设备", "enterprise_credit_status": "no_overdue",
        "legal_credit_status": "no_overdue", "credit_query_count_6m": "3",
    }


def registration_payload(phone: str, name: str = "注册验收客户") -> dict[str, str]:
    return {
        "phone": phone, "contact_name": name,
        "password": "Customer123", "confirm_password": "Customer123",
        "company_name": "", "wechat_id": "register_wechat", "city": "上海",
        "agree_legal": "1", "registration_method": "password",
        "next_url": "/client/dashboard",
    }


def run() -> None:
    phone = "13800138801"
    with TestClient(app) as client:
        login = client.get("/client/login")
        assert login.status_code == 200
        phone_input = re.search(r'id="client-login-phone"[^>]*value="([^"]*)"', login.text)
        assert phone_input and phone_input.group(1) == ""
        assert "还没有账号" in login.text and "立即注册" in login.text
        assert "已有历史报告但未设置密码" in login.text and "找回原账号" in login.text

        register_page = client.get("/client/register")
        assert register_page.status_code == 200
        for text in ["注册客户账号", "联系人姓名", "确认密码", "用户协议", "隐私政策", "注册并进入客户中心"]:
            assert text in register_page.text

        no_agreement = registration_payload(phone)
        no_agreement.pop("agree_legal")
        rejected = client.post("/client/register", data=no_agreement)
        assert rejected.status_code == 400 and "请先阅读并同意" in rejected.text

        registered = client.post("/client/register", data=registration_payload(phone), follow_redirects=False)
        assert registered.status_code == 303 and registered.headers["location"] == "/client/dashboard"
        dashboard = client.get("/client/dashboard")
        assert dashboard.status_code == 200
        assert "暂无报告" in dashboard.text and "开始免费测评" in dashboard.text

        with SessionLocal() as db:
            account = db.query(CustomerAccount).filter_by(login_phone=phone).one()
            customer_id = account.id
            assert account.lead_id is None and account.assessment_id is None
            assert account.status == "active" and account.is_active
            assert account.registration_source == "self_registration"
            assert account.registration_method == "password"
            assert account.activated_at and account.terms_accepted_at and account.privacy_accepted_at
            assert account.last_login_at and account.password_hash != "Customer123"
            assert verify_password("Customer123", account.password_hash)
            assert db.query(Event).filter_by(event_type="customer_registered").count() == 1
            assert db.query(AuditLog).filter_by(
                customer_id=account.id, action="customer_registered",
            ).count() == 1

        first = client.post(
            "/assessment/submit",
            data=assessment_payload("13999999999", "上海A公司"),
            follow_redirects=False,
        )
        second = client.post(
            "/assessment/submit",
            data=assessment_payload("13777777777", "苏州B公司"),
            follow_redirects=False,
        )
        assert first.status_code == 303 and second.status_code == 303
        with SessionLocal() as db:
            assessments = db.query(Assessment).filter(Assessment.customer_id == customer_id).all()
            assert {item.company_name for item in assessments} == {"上海A公司", "苏州B公司"}
            assert all(item.phone == phone for item in assessments)
            assert db.query(Report).filter(Report.customer_id == customer_id).count() == 2
            account = db.get(CustomerAccount, customer_id)
            assert account.lead_id and account.assessment_id

        reports = client.get("/client/reports")
        assert reports.status_code == 200 and "上海A公司" in reports.text and "苏州B公司" in reports.text
        customer_admin = client.get("/admin", follow_redirects=False)
        assert customer_admin.status_code == 303
        assert customer_admin.headers["location"].startswith("/admin/login")

        client.get("/client/logout")
        duplicate = client.post("/client/register", data=registration_payload(phone))
        assert duplicate.status_code == 409
        assert "该手机号已注册，请直接登录" in duplicate.text
        assert "去登录" in duplicate.text and "忘记密码" in duplicate.text

    history_phone = "13800138802"
    with TestClient(app) as assessment_client:
        submitted = assessment_client.post(
            "/assessment/submit",
            data=assessment_payload(history_phone, "历史报告企业"),
            follow_redirects=False,
        )
        assert submitted.status_code == 303
        with SessionLocal() as db:
            history_account = db.query(CustomerAccount).filter_by(login_phone=history_phone).one()
            history_customer_id = history_account.id
            assert not history_account.password_hash
            report_ids_before = [
                item.id for item in db.query(Report).filter_by(customer_id=history_customer_id).all()
            ]

        completed = assessment_client.post(
            "/client/register",
            data=registration_payload(history_phone, "历史客户"),
            follow_redirects=False,
        )
        assert completed.status_code == 303
        assert assessment_client.get("/client/reports").status_code == 200
        with SessionLocal() as db:
            account = db.get(CustomerAccount, history_customer_id)
            assert account.password_hash and account.status == "active"
            assert [item.id for item in db.query(Report).filter_by(
                customer_id=history_customer_id,
            ).all()] == report_ids_before

    recovery_phone = "13800138803"
    with TestClient(app) as source_client:
        assert source_client.post(
            "/assessment/submit",
            data=assessment_payload(recovery_phone, "待找回历史企业"),
            follow_redirects=False,
        ).status_code == 303
    with TestClient(app) as different_browser:
        recovery = different_browser.post("/client/register", data=registration_payload(recovery_phone))
        assert recovery.status_code == 409
        assert "检测到该手机号已有历史报告" in recovery.text
        assert f"/client/activate?phone={recovery_phone}" in recovery.text

    print("CUSTOMER_REGISTRATION_OK")


if __name__ == "__main__":
    run()
