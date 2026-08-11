"""客户手机登录、账号激活、历史报告与双会话隔离专项验收。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEST_DB = ROOT / "phase_client_login_mobile_test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
os.environ["AI_MODE"] = "mock"
os.environ["APP_ENV"] = "development"
if TEST_DB.exists():
    TEST_DB.unlink()
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from db.database import SessionLocal
from db.models import CustomerAccessToken, CustomerAccount, Report
from main import app


def assessment_payload(phone: str) -> dict[str, str]:
    return {
        "company_name": "移动端客户登录验收企业", "contact_name": "张经理", "phone": phone,
        "industry": "制造业", "years": "6", "annual_revenue": "12000000",
        "net_profit_margin": "8.5", "debt_total": "1600000", "short_debt": "500000",
        "funding_need": "2500000", "funding_purposes": "补充流动资金",
        "collateral_types": "有设备", "enterprise_credit_status": "no_overdue",
        "legal_credit_status": "no_overdue", "credit_query_count_6m": "3",
    }


def run() -> None:
    phone = "13800138666"
    with TestClient(app) as client:
        public_login = client.get("/client/login")
        assert public_login.status_code == 200
        for text in ["客户登录", "请输入手机号", "请输入密码", "记住我", "登录客户中心",
                     "忘记密码", "立即注册", "找回原账号", "返回首页"]:
            assert text in public_login.text
        assert 'name="viewport"' in public_login.text
        assert 'data-nav-toggle' in public_login.text and 'href="/client/login"' in public_login.text
        assert 'href="/admin/login">管理后台</a>' in public_login.text
        assert all(internal not in public_login.text for internal in ["客户账号管理", "产品管理", "推广二维码"])

        home = client.get("/")
        assert "客户登录" in home.text and 'href="/admin/login">管理后台</a>' in home.text

        submitted = client.post("/assessment/submit", data=assessment_payload(phone), follow_redirects=False)
        assert submitted.status_code == 303
        assessment_id = int(submitted.headers["location"].rsplit("/", 1)[-1])
        with SessionLocal() as db:
            account = db.query(CustomerAccount).filter_by(login_phone=phone).one()
            report = db.query(Report).filter_by(assessment_id=assessment_id).one()
            assert account.status == "pending_activation" and not account.password_hash
            assert report.customer_id == account.id
            account_id = account.id

        wrong = client.post("/client/login", data={
            "phone": phone, "password": "WrongPassword", "next_url": "/client/dashboard",
        })
        assert wrong.status_code == 400 and "手机号或密码不正确" in wrong.text

        activate_page = client.get(f"/client/activate?phone={phone}")
        assert activate_page.status_code == 200 and "历史账号找回" in activate_page.text
        requested = client.post("/client/activate", data={"phone": phone})
        assert requested.status_code == 200 and "找回申请已受理" in requested.text
        with SessionLocal() as db:
            token = db.query(CustomerAccessToken).filter_by(
                customer_id=account_id, token_type="account_activation", is_active=True,
            ).one()
            activation_token = token.token
        password_page = client.get(f"/client/activate/{activation_token}")
        assert password_page.status_code == 200 and "设置登录密码" in password_page.text
        activated = client.post(f"/client/activate/{activation_token}", data={
            "password": "MobileClient123", "confirm_password": "MobileClient123",
        }, follow_redirects=False)
        assert activated.status_code == 303 and activated.headers["location"] == "/client/reports"

        dashboard = client.get("/client/dashboard")
        assert dashboard.status_code == 200
        for text in ["我的报告", "我的订单", "待完成资料", "顾问预约", "融资项目", "未读通知"]:
            assert text in dashboard.text
        history = client.get("/client/reports")
        assert history.status_code == 200 and "移动端客户登录验收企业" in history.text

        customer_admin = client.get("/admin", follow_redirects=False)
        assert customer_admin.status_code == 303 and customer_admin.headers["location"].startswith("/admin/login")

        admin_login = client.post("/admin/login", data={
            "username": "admin", "password": "admin123", "next_url": "/admin",
        }, follow_redirects=False)
        assert admin_login.status_code == 303
        assert client.get("/admin").status_code == 200
        assert client.get("/client/dashboard").status_code == 200  # 后台登录不覆盖客户会话
        client.get("/logout")
        assert client.get("/client/dashboard").status_code == 200  # 后台退出也不覆盖客户会话

        client.get("/client/logout")
        logged_out = client.get("/client/dashboard", follow_redirects=False)
        assert logged_out.status_code == 303 and logged_out.headers["location"].startswith("/client/login")
        relogin = client.post("/client/login", data={
            "phone": phone, "password": "MobileClient123", "remember_me": "1",
            "next_url": "/client/reports",
        }, follow_redirects=False)
        assert relogin.status_code == 303 and relogin.headers["location"] == "/client/reports"
        assert "移动端客户登录验收企业" in client.get("/client/reports").text

        with SessionLocal() as db:
            account = db.get(CustomerAccount, account_id)
            assert account.status == "active" and account.password_hash and account.last_login_at

    css = (ROOT / "static/css/style.css").read_text(encoding="utf-8")
    js = (ROOT / "static/js/main.js").read_text(encoding="utf-8")
    assert "@media(max-width:767px)" in css and ".mobile-nav-toggle" in css
    assert "overflow-x:hidden" in css and "font-size:16px" in css
    assert "data-nav-toggle" in js and 'aria-expanded' in js and 'is-open' in js
    print("CLIENT_LOGIN_MOBILE_OK")


if __name__ == "__main__":
    run()
