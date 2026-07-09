import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi.testclient import TestClient

from db.database import SessionLocal
from db.models import AdvisorBooking, ConsultingCase, Event, FollowTask, LeadFollowLog
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
        login = client.post(
            "/login",
            data={"username": "admin", "password": "admin123", "next_url": "/admin"},
            follow_redirects=False,
        )
        assert login.status_code == 303

        submit = client.post("/assessment/submit", data=payload, follow_redirects=False)
        assert submit.status_code == 303
        assessment_id = int(submit.headers["location"].rsplit("/", 1)[-1])

        pay = client.post(
            f"/payment/mock-pay/{assessment_id}?product=1999_structure_plan",
            follow_redirects=False,
        )
        assert pay.status_code == 303

        report_page = client.get(f"/report/{assessment_id}")
        assert report_page.status_code == 200
        assert "/advisor/book/" in report_page.text

        admin_home = client.get("/admin")
        assert admin_home.status_code == 200
        assert "/admin/advisor-bookings" in admin_home.text
        assert admin_home.text.find("/admin/consulting-cases") < admin_home.text.find("/admin/advisor-bookings")
        assert admin_home.text.find("/admin/advisor-bookings") < admin_home.text.find("/admin/orders")

        empty_list = client.get("/admin/advisor-bookings")
        assert empty_list.status_code == 200
        assert "暂无顾问预约记录" in empty_list.text

        booking_form = client.get("/advisor/book/1")
        assert booking_form.status_code == 200

        booked = client.post(
            "/advisor/book/1",
            data={
                "company_name": "预约测试企业",
                "contact_name": "王总",
                "phone": "13900001111",
                "wechat_id": "wang_test",
                "city": "上海",
                "service_type": "financing_structure_consulting",
                "urgency": "urgent",
                "consultation_focus": "希望沟通融资额度和银行申请顺序",
                "preferred_time": "明天下午3点",
                "note": "希望尽快联系",
            },
        )
        assert booked.status_code == 200
        assert "预约已提交" in booked.text

        admin_page = client.get("/admin/advisor-bookings")
        assert admin_page.status_code == 200
        assert "13900001111" in admin_page.text
        assert "上海" in admin_page.text
        assert "融资结构设计" in admin_page.text
        assert "标记已联系" in admin_page.text
        assert "标记已安排" in admin_page.text
        assert "标记已完成" in admin_page.text
        assert "financing_structure_consulting" not in admin_page.text

        detail_page = client.get("/admin/advisor-bookings/1")
        assert detail_page.status_code == 200
        assert "13900001111" in detail_page.text
        assert "上海" in detail_page.text
        assert "融资结构设计" in detail_page.text
        assert "一键复制联系话术" in detail_page.text
        assert "预约跟进" in detail_page.text

        contacted = client.post(
            "/admin/advisor-bookings/1/quick-status",
            data={"status": "contacted"},
            follow_redirects=False,
        )
        assert contacted.status_code == 303

        after_contact = client.get("/admin/advisor-bookings/1")
        assert after_contact.status_code == 200
        assert "已联系" in after_contact.text
        assert "确认顾问沟通时间" in after_contact.text

        scheduled = client.post(
            "/admin/advisor-bookings/1/follow-up",
            data={
                "booking_status": "scheduled",
                "owner_user_id": "0",
                "consultant_user_id": "0",
                "internal_note": "已约定明天下午电话沟通",
                "next_follow_time": "2026-07-10T15:00",
                "scheduled_time": "2026-07-10 15:00",
                "service_result": "",
            },
            follow_redirects=False,
        )
        assert scheduled.status_code == 303

        completed = client.post(
            "/admin/advisor-bookings/1/follow-up",
            data={
                "booking_status": "completed",
                "owner_user_id": "0",
                "consultant_user_id": "0",
                "internal_note": "客户希望继续做融资结构设计",
                "service_result": "已确认客户有进一步融资结构优化需求",
                "create_consulting_case": "true",
            },
            follow_redirects=False,
        )
        assert completed.status_code == 303

        final_detail = client.get("/admin/advisor-bookings/1")
        assert final_detail.status_code == 200
        assert "已完成" in final_detail.text
        assert "客户希望继续做融资结构设计" in final_detail.text

    with SessionLocal() as db:
        booking = db.query(AdvisorBooking).order_by(AdvisorBooking.id.desc()).first()
        assert booking is not None
        assert booking.city == "上海"
        assert booking.service_type == "financing_structure_consulting"
        assert booking.urgency == "urgent"
        assert booking.booking_status == "completed"
        assert booking.internal_note == "客户希望继续做融资结构设计"
        assert booking.follow_task_id is not None
        task = db.get(FollowTask, booking.follow_task_id)
        assert task is not None
        assert task.task_type == "advisor_booking"
        assert task.status == "pending"
        assert db.query(FollowTask).filter(FollowTask.task_title == "确认顾问沟通时间").count() >= 1
        assert db.query(FollowTask).filter(FollowTask.task_title == "按预约时间联系客户").count() >= 1
        assert db.query(LeadFollowLog).filter(LeadFollowLog.action_type == "advisor_booking").count() >= 3
        assert db.query(Event).filter(Event.event_type == "advisor_booking_followed").count() >= 3
        assert db.query(ConsultingCase).count() >= 1

    print("PHASE_ADVISOR_BOOKING_OK")


if __name__ == "__main__":
    run()
