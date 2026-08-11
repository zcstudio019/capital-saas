"""Customer header identity isolation and responsive navigation regression."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEST_DB = ROOT / "phase_client_navigation_test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
os.environ["AI_MODE"] = "mock"
os.environ["APP_ENV"] = "development"
if TEST_DB.exists():
    TEST_DB.unlink()
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from db.database import SessionLocal
from db.models import CustomerAccount, CustomerMessage
from main import app
from services.customer_auth_service import set_customer_password


PAYLOAD = {
    "company_name": "客户导航验收企业",
    "contact_name": "导航验收客户",
    "phone": "13800138921",
    "industry": "制造业",
    "years": "5",
    "employee_count": "18",
    "annual_revenue": "9000000",
    "net_profit_margin": "7.5",
    "debt_total": "1200000",
    "short_debt": "300000",
    "funding_need": "1800000",
    "funding_purposes": "补充流动资金",
    "collateral_types": "暂无抵押物",
    "enterprise_credit_status": "no_overdue",
    "legal_credit_status": "no_overdue",
    "credit_query_count_6m": "2",
}


def run() -> None:
    with TestClient(app) as client:
        submitted = client.post("/assessment/submit", data=PAYLOAD, follow_redirects=False)
        assert submitted.status_code == 303
        with SessionLocal() as db:
            customer = db.query(CustomerAccount).filter_by(login_phone=PAYLOAD["phone"]).one()
            set_customer_password(db, customer, "ClientNav123")
            customer.status = "active"
            db.add(CustomerMessage(
                customer_id=customer.id,
                lead_id=customer.lead_id,
                title="待查看通知",
                content="客户导航角标测试",
                status="unread",
            ))
            db.commit()

        logged_in = client.post(
            "/client/login",
            data={
                "phone": PAYLOAD["phone"],
                "password": "ClientNav123",
                "next_url": "/client/dashboard",
            },
            follow_redirects=False,
        )
        assert logged_in.status_code == 303
        dashboard = client.get("/client/dashboard")
        assert dashboard.status_code == 200
        html = dashboard.text
        assert html.count('class="client-site-header"') == 1
        assert html.count('class="client-desktop-nav"') == 1
        assert html.count('id="client-mobile-navigation"') == 1
        assert 'class="public-header"' not in html
        assert 'class="admin-site-header"' not in html
        for label in ["首页", "我的报告", "我的订单", "我的资料", "顾问预约", "通知", "账号设置", "退出登录"]:
            assert label in html
        for forbidden in ["融资项目", "管理后台", "员工入口"]:
            assert forbidden not in html
        assert 'class="notification-badge">1</span>' in html
        assert "您的报告、订单、资料和顾问服务记录都已归集在本账号中" in html

        css = client.get("/static/css/style.css").text
        assert ".client-site-header .client-desktop-nav" in css
        assert ".client-site-header .client-mobile-toggle" in css
        assert "@media (max-width: 768px)" in css
        assert "@media (min-width: 769px)" in css
        assert ".client-site-header .client-mobile-nav.is-open" in css

        # A simultaneous staff session must not add staff links to client pages.
        admin_login = client.post(
            "/admin/login",
            data={"username": "admin", "password": "admin123", "next_url": "/admin"},
            follow_redirects=False,
        )
        assert admin_login.status_code == 303
        client_again = client.get("/client/dashboard")
        assert "管理后台" not in client_again.text and "员工入口" not in client_again.text
        admin = client.get("/admin")
        assert admin.status_code == 200
        assert "admin-site-header" in admin.text
        assert 'href="/admin/reports"' in admin.text and 'href="/admin/customers"' in admin.text

    print("CLIENT_NAVIGATION_OK")


if __name__ == "__main__":
    run()
