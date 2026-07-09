import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi.testclient import TestClient

from db.database import SessionLocal
from db.models import Lead, LeadFollowLog, User
from main import app


def _assessment_payload(company_name: str, phone: str):
    return {
        "company_name": company_name,
        "contact_name": "李四",
        "phone": phone,
        "wechat_id": "wx_" + phone[-4:],
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
        login = client.post("/login", data={"username": "admin", "password": "admin123", "next_url": "/admin/leads"}, follow_redirects=False)
        assert login.status_code == 303
        created_user = client.post(
            "/admin/users/create",
            data={"username": "detail_sales", "password": "SalesPass123", "display_name": "详情销售", "phone": "13800009991", "role": "sales", "is_active": "true"},
            follow_redirects=False,
        )
        assert created_user.status_code == 303
        submit = client.post("/assessment/submit", data=_assessment_payload("详情页跟进企业", "13991000001"), follow_redirects=False)
        assert submit.status_code == 303
        with SessionLocal() as db:
            lead = db.query(Lead).filter_by(company_name="详情页跟进企业").one()
            sales = db.query(User).filter_by(username="detail_sales").one()
            lead_id = lead.id
            sales_id = sales.id

        page = client.get(f"/admin/leads/{lead_id}")
        assert page.status_code == 200
        for text in ["销售跟进详情页", "企业名称", "复制电话", "添加跟进", "历史跟进记录", "试运营跟进建议"]:
            assert text in page.text, text
        assert "分配销售" in page.text

        assigned = client.post(f"/admin/leads/{lead_id}/assign-sales", data={"sales_user_id": str(sales_id)}, follow_redirects=False)
        assert assigned.status_code == 303

        client.get("/logout")
        sales_login = client.post("/login", data={"username": "detail_sales", "password": "SalesPass123", "next_url": "/sales/workbench"}, follow_redirects=False)
        assert sales_login.status_code == 303
        sales_page = client.get(f"/sales/leads/{lead_id}", follow_redirects=True)
        assert sales_page.status_code == 200
        assert 'id="assign-sales"' not in sales_page.text
        assert f'action="/admin/leads/{lead_id}/assign-sales"' not in sales_page.text
        assert "添加跟进记录" in sales_page.text

        status_update = client.post(f"/admin/leads/{lead_id}/follow-status", data={"follow_status": "已加微信"}, follow_redirects=False)
        assert status_update.status_code == 303
        follow = client.post(
            f"/admin/leads/{lead_id}/follow-records/create",
            data={"follow_method": "微信", "follow_result": "已加微信", "follow_note": "客户已通过微信，约明天看报告。", "next_follow_time": "2026-07-10T10:30"},
            follow_redirects=False,
        )
        assert follow.status_code == 303
        history = client.get(f"/sales/leads/{lead_id}", follow_redirects=True)
        assert "客户已通过微信" in history.text
        assert "2026-07-10 10:30" in history.text

    with SessionLocal() as db:
        lead = db.get(Lead, lead_id)
        assert lead.follow_status == "已加微信"
        assert db.query(LeadFollowLog).filter(LeadFollowLog.lead_id == lead_id, LeadFollowLog.action_type == "manual_followup").count() == 1

    print("PHASE_LEAD_DETAIL_FOLLOW_OK")


if __name__ == "__main__":
    run()
