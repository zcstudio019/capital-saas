import sys
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi.testclient import TestClient

from db.database import SessionLocal
from db.models import AdvisorBooking, Assessment, ConsultingCase, Lead, Order, User
from main import app
from services.auth_service import hash_password


def _assessment(db, company_name, created_at):
    item = Assessment(
        company_name=company_name, contact_name="运营测试联系人", phone="13800000000", wechat_id="ops_pagination",
        city="上海", industry="制造业", years=5, employee_count=30, annual_revenue=10_000_000,
        net_profit=1_000_000, monthly_cashflow=500_000, debt_total=1_000_000, short_debt=300_000,
        receivable_days=45, funding_need=2_000_000, funding_purpose="经营周转", has_collateral=True,
        tax_status=True, credit_status=True, knows_cashflow=True, has_budget=True,
        leverage_attitude="适中", asset_efficiency="高", fund_usage_plan=True, score=70, grade="B",
        risk_level="medium", funding_probability="good", created_at=created_at,
    )
    db.add(item)
    db.flush()
    return item


def _seed():
    suffix = uuid4().hex[:10]
    prefix = f"ops-pagination-{suffix}"
    with SessionLocal() as db:
        sales = User(username=f"ops_sales_{suffix}", password_hash=hash_password("SalesPass123"), display_name="运营分页销售", role="sales", is_active=True)
        other_sales = User(username=f"ops_other_{suffix}", password_hash=hash_password("OtherPass123"), display_name="其他运营销售", role="sales", is_active=True)
        consultant = User(username=f"ops_consultant_{suffix}", password_hash=hash_password("ConsultPass123"), display_name="运营分页顾问", role="consultant", is_active=True)
        db.add_all([sales, other_sales, consultant])
        db.flush()
        assessment_ids, lead_ids, order_ids, booking_ids, case_ids = [], [], [], [], []
        start = datetime(2030, 3, 1, 9, 0)
        for index in range(1, 13):
            owned_by_sales = index <= 11
            created_at = start + timedelta(minutes=index)
            company_name = f"{prefix}-sales-{index:02d}" if owned_by_sales else f"{prefix}-other-{index:02d}"
            assessment = _assessment(db, company_name, created_at)
            lead = Lead(
                assessment_id=assessment.id, company_name=company_name, contact_name="运营测试联系人",
                phone="13800000000", wechat_id="ops_pagination", city="上海", lead_grade="B", lead_score=70,
                recommended_product="299_report", follow_status="待联系", conversion_status="未成交",
                assigned_sales_id=sales.id if owned_by_sales else other_sales.id, owner_user_id=sales.id if owned_by_sales else other_sales.id,
                created_at=created_at,
            )
            db.add(lead)
            db.flush()
            order = Order(
                assessment_id=assessment.id, product_code="299_report", product_name="基础诊断报告（299元）",
                amount=299, status="paid", pay_channel="mock", owner_user_id=sales.id if owned_by_sales else other_sales.id,
                created_at=created_at,
            )
            booking = AdvisorBooking(
                assessment_id=assessment.id, lead_id=lead.id, company_name=company_name, contact_name="运营测试联系人",
                phone="13800000000", wechat_id="ops_pagination", city="上海", service_type="high_ticket_consulting",
                urgency="normal", consultation_focus="验证运营列表分页", booking_status="submitted",
                owner_user_id=sales.id if owned_by_sales else other_sales.id, consultant_user_id=consultant.id, created_at=created_at,
            )
            case = ConsultingCase(
                lead_id=lead.id, assessment_id=assessment.id, product_code="1999_structure_plan", case_status="pending",
                consultant_id=consultant.id, consultant_user_id=consultant.id, owner_user_id=sales.id if owned_by_sales else other_sales.id,
                case_summary="运营分页顾问案件", service_goal="验证案件分页", created_at=created_at,
            )
            db.add_all([order, booking, case])
            db.flush()
            assessment_ids.append(assessment.id); lead_ids.append(lead.id); order_ids.append(order.id); booking_ids.append(booking.id); case_ids.append(case.id)
        db.commit()
        return sales.username, sales.id, other_sales.id, consultant.id, assessment_ids, lead_ids, order_ids, booking_ids, case_ids, prefix


def _cleanup(seed):
    _, sales_id, other_sales_id, consultant_id, assessment_ids, lead_ids, order_ids, booking_ids, case_ids, _ = seed
    with SessionLocal() as db:
        db.query(ConsultingCase).filter(ConsultingCase.id.in_(case_ids)).delete(synchronize_session=False)
        db.query(AdvisorBooking).filter(AdvisorBooking.id.in_(booking_ids)).delete(synchronize_session=False)
        db.query(Order).filter(Order.id.in_(order_ids)).delete(synchronize_session=False)
        db.query(Lead).filter(Lead.id.in_(lead_ids)).delete(synchronize_session=False)
        db.query(Assessment).filter(Assessment.id.in_(assessment_ids)).delete(synchronize_session=False)
        db.query(User).filter(User.id.in_([sales_id, other_sales_id, consultant_id])).delete(synchronize_session=False)
        db.commit()


def run():
    seed = None
    with TestClient(app) as client:
        try:
            seed = _seed()
            sales_username, prefix = seed[0], seed[-1]
            login = client.post("/login", data={"username": "admin", "password": "admin123", "next_url": "/admin"}, follow_redirects=False)
            assert login.status_code == 303

            orders = client.get(f"/admin/orders?company_keyword={prefix}&status=paid&page_size=10&page=1")
            assert orders.status_code == 200
            assert orders.text.count('data-order-id="') == 10
            assert "共 12 笔订单" in orders.text
            assert "已支付" in orders.text
            order_page_two = client.get(f"/admin/orders?company_keyword={prefix}&status=paid&page_size=10&page=2")
            assert order_page_two.text.count('data-order-id="') == 2
            assert "company_keyword=" in order_page_two.text and "status=paid" in order_page_two.text

            bookings = client.get(f"/admin/advisor-bookings?city=%E4%B8%8A%E6%B5%B7&status=submitted&page_size=10&page=1")
            assert bookings.status_code == 200
            assert bookings.text.count('data-booking-id="') >= 10
            assert "每页10条" in bookings.text

            cases = client.get(f"/admin/consulting-cases?company_keyword={prefix}&case_status=pending&page_size=10&page=1")
            assert cases.status_code == 200
            assert cases.text.count('data-case-id="') == 10
            assert "待处理" in cases.text
            case_page_two = client.get(f"/admin/consulting-cases?company_keyword={prefix}&case_status=pending&page_size=10&page=2")
            assert case_page_two.text.count('data-case-id="') == 2
            assert "company_keyword=" in case_page_two.text and "case_status=pending" in case_page_two.text

            client.get("/logout")
            sales_login = client.post("/login", data={"username": sales_username, "password": "SalesPass123", "next_url": "/admin/advisor-bookings"}, follow_redirects=False)
            assert sales_login.status_code == 303
            sales_bookings = client.get("/admin/advisor-bookings?city=%E4%B8%8A%E6%B5%B7&status=submitted&page_size=10&page=1")
            assert sales_bookings.status_code == 200
            assert f"{prefix}-other-12" not in sales_bookings.text
        finally:
            if seed:
                _cleanup(seed)
    print("OPERATIONAL_PAGINATION_TEST_OK")


if __name__ == "__main__":
    run()
