import sys
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi.testclient import TestClient

from db.database import SessionLocal
from db.models import Assessment, Lead, Report, User
from main import app
from services.auth_service import hash_password


def _create_assessment(db, company_name: str, created_at: datetime) -> Assessment:
    assessment = Assessment(
        company_name=company_name,
        contact_name="报告测试联系人",
        phone="13800000000",
        wechat_id="report_pagination",
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
        created_at=created_at,
    )
    db.add(assessment)
    db.flush()
    return assessment


def _seed_reports():
    suffix = uuid4().hex[:10]
    company_prefix = f"report-pagination-{suffix}"
    with SessionLocal() as db:
        sales = User(
            username=f"report_sales_{suffix}",
            password_hash=hash_password("SalesPass123"),
            display_name="报告分页销售",
            role="sales",
            is_active=True,
        )
        other_sales = User(
            username=f"report_other_{suffix}",
            password_hash=hash_password("OtherPass123"),
            display_name="其他报告销售",
            role="sales",
            is_active=True,
        )
        db.add_all([sales, other_sales])
        db.flush()

        report_ids = []
        lead_ids = []
        assessment_ids = []
        start = datetime(2030, 2, 1, 9, 0)
        for index in range(1, 13):
            is_sales_report = index <= 11
            created_at = start + timedelta(minutes=index)
            company_name = f"{company_prefix}-sales-{index:02d}" if is_sales_report else f"{company_prefix}-other-{index:02d}"
            assessment = _create_assessment(db, company_name, created_at)
            lead = Lead(
                assessment_id=assessment.id,
                company_name=company_name,
                contact_name="报告测试联系人",
                phone="13800000000",
                wechat_id="report_pagination",
                city="上海",
                lead_grade="B",
                lead_score=70,
                recommended_product="299_report",
                follow_status="待联系",
                conversion_status="未成交",
                assigned_sales_id=sales.id if is_sales_report else other_sales.id,
                created_at=created_at,
            )
            db.add(lead)
            db.flush()
            report = Report(
                assessment_id=assessment.id,
                free_summary_json="{}",
                full_report_json="{}",
                is_unlocked=True,
                review_status="approved",
                created_at=created_at,
            )
            db.add(report)
            db.flush()
            report_ids.append(report.id)
            lead_ids.append(lead.id)
            assessment_ids.append(assessment.id)
        db.commit()
        return sales.username, sales.id, other_sales.id, report_ids, lead_ids, assessment_ids, company_prefix


def _cleanup(seed_data):
    _, sales_id, other_sales_id, report_ids, lead_ids, assessment_ids, _ = seed_data
    with SessionLocal() as db:
        db.query(Report).filter(Report.id.in_(report_ids)).delete(synchronize_session=False)
        db.query(Lead).filter(Lead.id.in_(lead_ids)).delete(synchronize_session=False)
        db.query(Assessment).filter(Assessment.id.in_(assessment_ids)).delete(synchronize_session=False)
        db.query(User).filter(User.id.in_([sales_id, other_sales_id])).delete(synchronize_session=False)
        db.commit()


def run():
    seed_data = None
    with TestClient(app) as client:
        try:
            seed_data = _seed_reports()
            sales_username = seed_data[0]
            company_prefix = seed_data[-1]
            query = f"company_keyword={company_prefix}&generation_status=generated&review_status=approved&page_size=10"

            login = client.post(
                "/login",
                data={"username": "admin", "password": "admin123", "next_url": "/admin/reports"},
                follow_redirects=False,
            )
            assert login.status_code == 303

            page_one = client.get(f"/admin/reports?{query}&page=1")
            assert page_one.status_code == 200
            assert page_one.text.count('data-report-id="') == 10
            assert "当前第 1 页 / 共 2 页，共 12 份报告" in page_one.text
            assert "已生成" in page_one.text
            assert "已通过" in page_one.text
            assert ">generated<" not in page_one.text
            assert ">approved<" not in page_one.text

            page_two = client.get(f"/admin/reports?{query}&page=2")
            assert page_two.status_code == 200
            assert page_two.text.count('data-report-id="') == 2
            assert f"{company_prefix}-sales-02" in page_two.text
            assert "company_keyword=" in page_two.text
            assert "generation_status=generated" in page_two.text
            assert "review_status=approved" in page_two.text

            client.get("/logout")
            sales_login = client.post(
                "/login",
                data={"username": sales_username, "password": "SalesPass123", "next_url": "/admin/reports"},
                follow_redirects=False,
            )
            assert sales_login.status_code == 303
            sales_page = client.get(f"/admin/reports?{query}&page=1")
            assert sales_page.status_code == 200
            assert "当前第 1 页 / 共 2 页，共 11 份报告" in sales_page.text
            assert f"{company_prefix}-other-12" not in sales_page.text
        finally:
            if seed_data:
                _cleanup(seed_data)

    print("REPORTS_PAGINATION_TEST_OK")


if __name__ == "__main__":
    run()
