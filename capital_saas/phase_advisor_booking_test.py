import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi.testclient import TestClient

from db.database import SessionLocal
from db.models import AdvisorBooking, FollowTask
from main import app


def run():
    payload = {
        "company_name": "预约测试企业",
        "contact_name": "王总",
        "phone": "13900001111",
        "wechat_id": "wang_test",
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
    with TestClient(app) as client:
        login = client.post("/login", data={"username": "admin", "password": "admin123", "next_url": "/admin"}, follow_redirects=False)
        assert login.status_code == 303
        submit = client.post("/assessment/submit", data=payload, follow_redirects=False)
        assert submit.status_code == 303
        assessment_id = int(submit.headers["location"].rsplit("/", 1)[-1])
        pay = client.post(f"/payment/mock-pay/{assessment_id}?product=1999_structure_plan", follow_redirects=False)
        assert pay.status_code == 303
        report_page = client.get(f"/report/{assessment_id}")
        assert report_page.status_code == 200
        assert "/advisor/book/" in report_page.text
        booking_form = client.get("/advisor/book/1")
        assert booking_form.status_code == 200
        booked = client.post(
            "/advisor/book/1",
            data={
                "company_name": "预约测试企业",
                "contact_name": "王总",
                "phone": "13900001111",
                "wechat_id": "wang_test",
                "consultation_focus": "希望沟通融资额度和银行申请顺序",
                "preferred_time": "明天下午3点",
                "note": "希望尽快联系",
            },
        )
        assert booked.status_code == 200
        assert "预约已提交" in booked.text
        admin_page = client.get("/admin/advisor-bookings")
        assert admin_page.status_code == 200
        assert "预约测试企业" in admin_page.text
    with SessionLocal() as db:
        booking = db.query(AdvisorBooking).order_by(AdvisorBooking.id.desc()).first()
        assert booking is not None
        assert booking.follow_task_id is not None
        task = db.get(FollowTask, booking.follow_task_id)
        assert task is not None
        assert task.task_type == "advisor_booking"
        assert task.status == "pending"
    print("PHASE_ADVISOR_BOOKING_OK")


if __name__ == "__main__":
    run()
