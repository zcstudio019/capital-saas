"""公共导航、客户导航、后台入口和双身份会话专项验收。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEST_DB = ROOT / "phase_navigation_identity_test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
os.environ["AI_MODE"] = "mock"
os.environ["APP_ENV"] = "development"
if TEST_DB.exists():
    TEST_DB.unlink()
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from db.database import SessionLocal
from db.models import CustomerAccount
from main import app
from services.customer_auth_service import set_customer_password


def assessment_payload(phone: str) -> dict[str, str]:
    return {
        "company_name": "导航身份验收企业",
        "contact_name": "测试客户",
        "phone": phone,
        "industry": "制造业",
        "years": "6",
        "annual_revenue": "12000000",
        "net_profit_margin": "8.5",
        "debt_total": "1600000",
        "short_debt": "500000",
        "funding_need": "2500000",
        "funding_purposes": "补充流动资金",
        "collateral_types": "有设备",
        "enterprise_credit_status": "no_overdue",
        "legal_credit_status": "no_overdue",
        "credit_query_count_6m": "3",
    }


def run() -> None:
    phone = "13800138777"
    with TestClient(app) as client:
        public = client.get("/")
        assert public.status_code == 200
        assert 'class="desktop-nav"' in public.text
        assert 'href="/client/login">客户登录</a>' in public.text
        assert 'href="/admin/login">管理后台</a>' in public.text
        assert 'class="mobile-menu-toggle"' in public.text
        assert 'id="mobile-public-navigation"' in public.text

        submitted = client.post(
            "/assessment/submit", data=assessment_payload(phone), follow_redirects=False,
        )
        assert submitted.status_code == 303
        with SessionLocal() as db:
            account = db.query(CustomerAccount).filter_by(login_phone=phone).one()
            set_customer_password(db, account, "Navigation123")
            db.commit()

        logged_in = client.post("/client/login", data={
            "phone": phone,
            "password": "Navigation123",
            "remember_me": "1",
            "next_url": "/client/dashboard",
        }, follow_redirects=False)
        assert logged_in.status_code == 303
        customer_public = client.get("/products")
        assert 'href="/client/reports">我的报告</a>' in customer_public.text
        assert 'href="/client/dashboard">客户中心</a>' in customer_public.text
        assert 'href="/client/login">客户登录</a>' not in customer_public.text

        customer_admin = client.get("/admin", follow_redirects=False)
        assert customer_admin.status_code == 303
        assert customer_admin.headers["location"].startswith("/admin/login")

        admin_login = client.post("/admin/login", data={
            "username": "admin",
            "password": "admin123",
            "next_url": "/admin",
        }, follow_redirects=False)
        assert admin_login.status_code == 303
        assert client.get("/admin").status_code == 200
        dual_identity_public = client.get("/products")
        assert 'href="/admin">管理后台</a>' in dual_identity_public.text
        assert 'href="/client/reports">我的报告</a>' in dual_identity_public.text
        assert client.get("/client/dashboard").status_code == 200

        client.get("/logout")
        assert client.get("/client/dashboard").status_code == 200
        admin_after_logout = client.get("/admin", follow_redirects=False)
        assert admin_after_logout.status_code == 303

    css = (ROOT / "static/css/style.css").read_text(encoding="utf-8")
    js = (ROOT / "static/js/main.js").read_text(encoding="utf-8")
    public_header = (ROOT / "templates/components/public_header.html").read_text(encoding="utf-8")
    client_header = (ROOT / "templates/client_base.html").read_text(encoding="utf-8")

    assert "@media(max-width:768px)" in css
    assert "@media(min-width:769px)" in css
    assert ".public-header .desktop-nav" in css and "display:none!important" in css
    assert ".public-header .mobile-menu-toggle" in css and "display:inline-flex!important" in css
    assert ".mobile-nav.is-open" in css
    assert all(label in public_header for label in ["免费测评", "产品服务", "客户登录", "管理后台"])
    assert all(label in client_header for label in ["我的报告", "客户中心", "管理后台"])
    assert 'class="desktop-nav"' in public_header
    assert 'class="mobile-nav"' in public_header
    assert "nav-open" in js and "header.contains(event.target)" in js
    assert 'event.key === "Escape"' in js and "window.innerWidth > 768" in js
    print("NAVIGATION_IDENTITY_OK")


if __name__ == "__main__":
    run()
