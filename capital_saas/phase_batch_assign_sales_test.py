import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi.testclient import TestClient

from db.database import SessionLocal
from db.models import AuditLog, Event, Lead, LeadFollowLog, User
from main import app


def _assessment_payload(company_name: str, phone: str):
    return {
        "company_name": company_name,
        "contact_name": "张三",
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
        login = client.post(
            "/login",
            data={"username": "admin", "password": "admin123", "next_url": "/admin/leads"},
            follow_redirects=False,
        )
        assert login.status_code == 303

        created_user = client.post(
            "/admin/users/create",
            data={
                "username": "batch_sales",
                "password": "SalesPass123",
                "display_name": "批量销售",
                "phone": "13800009001",
                "role": "sales",
                "is_active": "true",
            },
            follow_redirects=False,
        )
        assert created_user.status_code == 303

        first = client.post("/assessment/submit", data=_assessment_payload("批量分配一号企业", "13990000001"), follow_redirects=False)
        second = client.post("/assessment/submit", data=_assessment_payload("批量分配二号企业", "13990000002"), follow_redirects=False)
        third = client.post("/assessment/submit", data=_assessment_payload("未分配企业", "13990000003"), follow_redirects=False)
        assert first.status_code == 303
        assert second.status_code == 303
        assert third.status_code == 303

        leads_page = client.get("/admin/leads")
        assert leads_page.status_code == 200
        assert "分配线索" in leads_page.text
        assert 'name="lead_ids"' in leads_page.text
        assert 'id="select-all-leads"' in leads_page.text

        with SessionLocal() as db:
            sales = db.query(User).filter_by(username="batch_sales").one()
            lead_ids = [
                db.query(Lead).filter_by(company_name="批量分配一号企业").one().id,
                db.query(Lead).filter_by(company_name="批量分配二号企业").one().id,
            ]

        assigned = client.post(
            "/admin/leads/batch-assign-sales",
            data={"lead_ids": [str(lead_ids[0]), str(lead_ids[1])], "sales_user_id": str(sales.id)},
            follow_redirects=False,
        )
        assert assigned.status_code == 303
        assert "assign_success=2" in assigned.headers["location"]

        filtered = client.get(f"/admin/leads?sales_user_id={sales.id}")
        assert filtered.status_code == 200
        assert "批量分配一号企业" in filtered.text
        assert "批量分配二号企业" in filtered.text
        assert "未分配企业" not in filtered.text

        client.get("/logout")
        sales_login = client.post(
            "/login",
            data={"username": "batch_sales", "password": "SalesPass123", "next_url": "/sales/workbench"},
            follow_redirects=False,
        )
        assert sales_login.status_code == 303
        my_leads = client.get("/sales/leads", follow_redirects=True)
        assert my_leads.status_code == 200
        assert "批量分配一号企业" in my_leads.text
        assert "批量分配二号企业" in my_leads.text
        assert "未分配企业" not in my_leads.text
        assert "分配线索" not in my_leads.text

        workbench = client.get("/sales/workbench")
        assert workbench.status_code == 200
        assert "批量分配一号企业" in workbench.text
        assert "批量分配二号企业" in workbench.text

    with SessionLocal() as db:
        sales = db.query(User).filter_by(username="batch_sales").one()
        assigned_leads = db.query(Lead).filter(Lead.company_name.in_(["批量分配一号企业", "批量分配二号企业"])).all()
        assert len(assigned_leads) == 2
        for lead in assigned_leads:
            assert lead.assigned_sales_id == sales.id
            assert lead.owner_user_id == sales.id
        assert db.query(LeadFollowLog).filter(LeadFollowLog.action_type == "assign_sales").count() >= 2
        assert db.query(Event).filter(Event.event_type == "lead_sales_assigned").count() >= 2
        assert db.query(AuditLog).filter(AuditLog.action == "lead_sales_assigned").count() >= 2

    print("PHASE_BATCH_ASSIGN_SALES_OK")


if __name__ == "__main__":
    run()
