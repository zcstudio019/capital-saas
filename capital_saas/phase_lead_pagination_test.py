import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi.testclient import TestClient

from db.database import SessionLocal
from db.models import Assessment, Lead, User
from main import app
from services.auth_service import hash_password


TEST_SOURCE = "lead_pagination_test"


def _create_assessment(db, company_name: str, created_at: datetime) -> Assessment:
    assessment = Assessment(
        company_name=company_name,
        contact_name="分页测试联系人",
        phone="13800000000",
        wechat_id="pagination_test",
        city="上海",
        industry="制造业",
        years=5,
        employee_count=30,
        annual_revenue=10_000_000,
        net_profit=1_000_000,
        monthly_cashflow=500_000,
        debt_total=1_000_000,
        short_debt=300_000,
        receivable_days=45,
        funding_need=2_000_000,
        funding_purpose="经营周转",
        has_collateral=True,
        tax_status=True,
        credit_status=True,
        knows_cashflow=True,
        has_budget=True,
        leverage_attitude="适中",
        asset_efficiency="高",
        fund_usage_plan=True,
        score=70,
        grade="B",
        risk_level="medium",
        funding_probability="good",
        source_channel=TEST_SOURCE,
        created_at=created_at,
    )
    db.add(assessment)
    db.flush()
    return assessment


def _seed_leads():
    with SessionLocal() as db:
        sales = User(
            username="lead_pagination_sales",
            password_hash=hash_password("SalesPass123"),
            display_name="分页销售",
            role="sales",
            is_active=True,
        )
        other_sales = User(
            username="lead_pagination_other",
            password_hash=hash_password("OtherPass123"),
            display_name="其他销售",
            role="sales",
            is_active=True,
        )
        db.add_all([sales, other_sales])
        db.flush()

        lead_ids = []
        assessment_ids = []
        start = datetime(2026, 1, 1, 9, 0)
        for index in range(1, 27):
            is_sales_lead = index <= 23
            company_name = (
                f"pagination-sales-{index:02d}"
                if is_sales_lead
                else f"pagination-other-{index:02d}"
            )
            created_at = start + timedelta(minutes=index)
            assessment = _create_assessment(db, company_name, created_at)
            lead = Lead(
                assessment_id=assessment.id,
                company_name=company_name,
                contact_name="分页测试联系人",
                phone="13800000000",
                wechat_id="pagination_test",
                city="上海",
                lead_grade="B",
                lead_score=70,
                recommended_product="299_report",
                follow_status="待联系",
                conversion_status="未成交",
                assigned_sales_id=sales.id if is_sales_lead else other_sales.id,
                source_channel=TEST_SOURCE,
                created_at=created_at,
            )
            db.add(lead)
            db.flush()
            lead_ids.append(lead.id)
            assessment_ids.append(assessment.id)
        db.commit()
        return sales.id, other_sales.id, lead_ids, assessment_ids


def _cleanup(seed_data):
    sales_id, other_sales_id, lead_ids, assessment_ids = seed_data
    with SessionLocal() as db:
        db.query(Lead).filter(Lead.id.in_(lead_ids)).delete(synchronize_session=False)
        db.query(Assessment).filter(Assessment.id.in_(assessment_ids)).delete(synchronize_session=False)
        db.query(User).filter(User.id.in_([sales_id, other_sales_id])).delete(synchronize_session=False)
        db.commit()


def run():
    seed_data = None
    with TestClient(app) as client:
        try:
            seed_data = _seed_leads()
            sales_id = seed_data[0]

            login = client.post(
                "/login",
                data={"username": "admin", "password": "admin123", "next_url": "/admin/leads"},
                follow_redirects=False,
            )
            assert login.status_code == 303

            page_one = client.get(f"/admin/leads?source_channel={TEST_SOURCE}&page_size=10&page=1")
            assert page_one.status_code == 200
            assert page_one.text.count('data-company-name="') == 10
            assert "当前第 1 页 / 共 3 页，共 26 条线索" in page_one.text
            assert "pagination-other-26" in page_one.text
            assert "pagination-sales-16" not in page_one.text
            assert 'class="leads-table has-selection"' in page_one.text
            assert "wide-table" not in page_one.text
            assert "lead-assign-form" in page_one.text
            for column_name in ["客户信息", "评分等级", "负责销售", "推荐产品", "跟进状态", "下一步动作", "操作"]:
                assert column_name in page_one.text

            filtered_page = client.get(
                f"/admin/leads?source_channel={TEST_SOURCE}&sales_user_id={sales_id}&page_size=10&page=2"
            )
            assert filtered_page.status_code == 200
            assert filtered_page.text.count('data-company-name="') == 10
            assert "当前第 2 页 / 共 3 页，共 23 条线索" in filtered_page.text
            assert "pagination-sales-13" in filtered_page.text
            assert "pagination-sales-14" not in filtered_page.text
            expected_next_url = (
                f'/admin/leads?page_size=10&amp;source_channel={TEST_SOURCE}'
                f'&amp;sales_user_id={sales_id}&amp;page=3'
            )
            assert expected_next_url in filtered_page.text

            page_size_twenty = client.get(f"/admin/leads?source_channel={TEST_SOURCE}&page_size=20&page=1")
            assert page_size_twenty.status_code == 200
            assert page_size_twenty.text.count('data-company-name="') == 20
            assert "每页20条" in page_size_twenty.text

            last_page = client.get(f"/admin/leads?source_channel={TEST_SOURCE}&page_size=10&page=999")
            assert last_page.status_code == 200
            assert "当前第 3 页 / 共 3 页，共 26 条线索" in last_page.text

            client.get("/logout")
            sales_login = client.post(
                "/login",
                data={"username": "lead_pagination_sales", "password": "SalesPass123", "next_url": "/sales/leads"},
                follow_redirects=False,
            )
            assert sales_login.status_code == 303

            sales_redirect = client.get(
                f"/sales/leads?source_channel={TEST_SOURCE}&page_size=10&page=2",
                follow_redirects=False,
            )
            assert sales_redirect.status_code == 303
            assert sales_redirect.headers["location"] == (
                f"/admin/leads?source_channel={TEST_SOURCE}&page_size=10&page=2"
            )
            sales_page = client.get(sales_redirect.headers["location"])
            assert sales_page.status_code == 200
            assert "当前第 2 页 / 共 3 页，共 23 条线索" in sales_page.text
            assert "pagination-sales-13" in sales_page.text
            assert "pagination-other-26" not in sales_page.text
            assert "lead-assign-form" not in sales_page.text
        finally:
            if seed_data:
                _cleanup(seed_data)

    print("LEAD_PAGINATION_TEST_OK")


if __name__ == "__main__":
    run()
