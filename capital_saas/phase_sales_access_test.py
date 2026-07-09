import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi.testclient import TestClient

from db.database import SessionLocal
from db.models import AuditLog, Event, Lead, LeadFollowLog, User
from services.auth_service import verify_password
from main import app


def _assessment_payload(company_name: str, phone: str):
    return {
        "company_name": company_name,
        "contact_name": "张总",
        "phone": phone,
        "wechat_id": phone,
        "city": "上海",
        "industry": "制造业",
        "years": "5",
        "employee_count": "50",
        "annual_revenue": "10000000",
        "net_profit": "1000000",
        "monthly_cashflow": "500000",
        "debt_total": "1000000",
        "short_debt": "300000",
        "receivable_days": "45",
        "funding_need": "2000000",
        "funding_purpose": "经营周转",
        "has_collateral": "true",
        "tax_status": "true",
        "credit_status": "true",
        "knows_cashflow": "true",
        "has_budget": "true",
        "leverage_attitude": "适中",
        "asset_efficiency": "高",
        "fund_usage_plan": "true",
    }


def run():
    with TestClient(app) as client:
        with SessionLocal() as db:
            admin = db.query(User).filter_by(username="admin").first()
            assert admin is not None
            admin.role = "sales"
            admin.is_active = False
            db.commit()

        login = client.post("/login", data={"username": "admin", "password": "admin123", "next_url": "/admin"}, follow_redirects=False)
        assert login.status_code == 303
        assert login.headers["location"] == "/admin"
        with SessionLocal() as db:
            admin = db.query(User).filter_by(username="admin").first()
            assert admin.role in {"admin", "super_admin"}
            assert admin.is_active is True

        client.get("/logout")
        admin_login_ignores_sales_next = client.post(
            "/login",
            data={"username": "admin", "password": "admin123", "next_url": "/sales/workbench"},
            follow_redirects=False,
        )
        assert admin_login_ignores_sales_next.status_code == 303
        assert admin_login_ignores_sales_next.headers["location"] == "/admin"
        admin_dashboard = client.get("/admin", follow_redirects=False)
        assert admin_dashboard.status_code == 200
        assert "/admin/users" in admin_dashboard.text

        users_page = client.get("/admin/users")
        assert users_page.status_code == 200
        assert "后台账号管理" in users_page.text

        created_user = client.post(
            "/admin/users/create",
            data={
                "username": "sales01",
                "password": "SalesPass123",
                "display_name": "销售一号",
                "phone": "13800000001",
                "role": "sales",
                "is_active": "true",
            },
            follow_redirects=False,
        )
        assert created_user.status_code == 303

        first = client.post("/assessment/submit", data=_assessment_payload("分配给销售一号企业", "13900000001"), follow_redirects=False)
        second = client.post("/assessment/submit", data=_assessment_payload("未分配企业", "13900000002"), follow_redirects=False)
        assert first.status_code == 303
        assert second.status_code == 303

        assigned = client.post("/admin/leads/1/assign-sales", data={"sales_user_id": "2"}, follow_redirects=False)
        assert assigned.status_code == 303

        client.get("/logout")
        sales_login = client.post("/login", data={"username": "sales01", "password": "SalesPass123", "next_url": "/admin"}, follow_redirects=False)
        assert sales_login.status_code == 303
        assert sales_login.headers["location"] == "/sales/workbench"

        admin_as_sales = client.get("/admin", follow_redirects=False)
        assert admin_as_sales.status_code == 303
        assert admin_as_sales.headers["location"] == "/sales/workbench"

        denied_users = client.get("/admin/users")
        assert denied_users.status_code == 403

        my_leads = client.get("/sales/leads", follow_redirects=True)
        assert my_leads.status_code == 200
        assert "分配给销售一号企业" in my_leads.text
        assert "未分配企业" not in my_leads.text
        assert "分配</button>" not in my_leads.text

        own_detail = client.get("/sales/leads/1", follow_redirects=True)
        assert own_detail.status_code == 200
        assert "分配给销售一号企业" in own_detail.text

        other_detail = client.get("/sales/leads/2", follow_redirects=True)
        assert other_detail.status_code == 403

        updated = client.post(
            "/admin/leads/1/update",
            data={
                "follow_status": "已联系",
                "conversion_status": "意向中",
                "next_follow_time": "",
                "last_follow_note": "销售已电话联系客户",
                "assigned_sales": "",
                "assigned_sales_id": "0",
            },
            follow_redirects=False,
        )
        assert updated.status_code == 303

        client.get("/logout")
        disabled_login_before = client.post("/login", data={"username": "admin", "password": "admin123"}, follow_redirects=False)
        assert disabled_login_before.status_code == 303
        disabled = client.post("/admin/users/2/disable", follow_redirects=False)
        assert disabled.status_code == 303
        client.get("/logout")
        disabled_login = client.post("/login", data={"username": "sales01", "password": "SalesPass123", "next_url": "/admin"}, follow_redirects=False)
        assert disabled_login.status_code == 403
        assert "账号已停用" in disabled_login.text

    with SessionLocal() as db:
        sales = db.query(User).filter_by(username="sales01").first()
        assert sales is not None
        assert verify_password("SalesPass123", sales.password_hash)
        assert sales.display_name == "销售一号"
        lead = db.get(Lead, 1)
        assert lead.assigned_sales_id == sales.id
        assert lead.owner_user_id == sales.id
        assert db.query(LeadFollowLog).filter(LeadFollowLog.action_type == "assign_sales").count() >= 1
        assert db.query(Event).filter(Event.event_type == "lead_sales_assigned").count() >= 1
        assert db.query(AuditLog).filter(AuditLog.action == "lead_sales_assigned").count() >= 1
        assert db.query(LeadFollowLog).filter(LeadFollowLog.action_type == "note_added").count() >= 1

    print("PHASE_SALES_ACCESS_OK")


if __name__ == "__main__":
    run()
