"""Phase 3：报告、银行审批、任务、漏斗、事件和打印版验收。"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi.testclient import TestClient

from db.database import SessionLocal
from db.models import Event, FollowTask, Lead
from main import app


PAYLOAD = {
    "company_name": "上海成长供应链有限公司",
    "contact_name": "李总",
    "phone": "13900139000",
    "wechat_id": "li_growth",
    "city": "上海",
    "industry": "供应链服务",
    "years": "3",
    "employee_count": "22",
    "annual_revenue": "6000000",
    "net_profit": "280000",
    "monthly_cashflow": "120000",
    "debt_total": "2500000",
    "short_debt": "1900000",
    "receivable_days": "105",
    "funding_need": "1800000",
    "funding_purpose": "补充订单周转与置换高成本短期负债",
    "has_collateral": "false",
    "tax_status": "true",
    "credit_status": "true",
    "knows_cashflow": "true",
    "has_budget": "false",
    "leverage_attitude": "适中",
    "asset_efficiency": "中",
    "fund_usage_plan": "true",
}


def run():
    with TestClient(app) as client:
        login = client.post(
            "/login",
            data={"username": "admin", "password": "admin123", "next_url": "/admin"},
            follow_redirects=False,
        )
        assert login.status_code == 303
        submit = client.post("/assessment/submit", data=PAYLOAD, follow_redirects=False)
        assert submit.status_code == 303
        assessment_id = int(submit.headers["location"].rsplit("/", 1)[-1])

        with SessionLocal() as db:
            lead = db.query(Lead).filter(Lead.assessment_id == assessment_id).one()
            lead_id = lead.id
            auto_tasks = (
                db.query(FollowTask)
                .filter(FollowTask.lead_id == lead_id)
                .order_by(FollowTask.id)
                .all()
            )
            assert auto_tasks
            assert all(task.status == "pending" for task in auto_tasks)
            first_task_id = auto_tasks[0].id

        assert client.get("/admin/follow-tasks").status_code == 200
        filtered = client.get(f"/admin/follow-tasks?lead_grade={lead.lead_grade}&status=pending")
        assert filtered.status_code == 200
        assert PAYLOAD["company_name"] in filtered.text

        manual = client.post(
            f"/admin/leads/{lead_id}/tasks/create",
            data={
                "task_type": "call",
                "task_title": "确认银行申请窗口",
                "task_content": "确认客户近期是否已经提交其他银行。",
                "priority": "high",
                "due_time": "2026-06-22T09:30",
            },
            follow_redirects=False,
        )
        assert manual.status_code == 303
        detail = client.get(f"/admin/leads/{lead_id}")
        assert detail.status_code == 200
        assert "确认银行申请窗口" in detail.text
        with SessionLocal() as db:
            manual_task = (
                db.query(FollowTask)
                .filter(
                    FollowTask.lead_id == lead_id,
                    FollowTask.task_title == "确认银行申请窗口",
                )
                .one()
            )
            manual_task_id = manual_task.id

        done = client.post(
            f"/admin/follow-tasks/{first_task_id}/done",
            data={"next_url": f"/admin/leads/{lead_id}"},
            follow_redirects=False,
        )
        assert done.status_code == 303
        cancelled = client.post(
            f"/admin/follow-tasks/{manual_task_id}/cancel",
            data={"next_url": f"/admin/leads/{lead_id}"},
            follow_redirects=False,
        )
        assert cancelled.status_code == 303

        client.get(f"/result/{assessment_id}")
        client.get(
            f"/checkout/{assessment_id}?product=299_report&from_product=free&upgrade=1"
        )
        paid = client.post(
            f"/payment/mock-pay/{assessment_id}?product=299_report",
            follow_redirects=False,
        )
        assert paid.status_code == 303

        report_page = client.get(f"/report/{assessment_id}")
        assert report_page.status_code == 200
        for text in [
            "企业资本健康体检报告",
            "第一部分",
            "第二部分",
            "第三部分",
            "八维雷达评分概览",
            "分项检查报告",
            "风险预警与异常项汇总",
            "融资结构优化方案已生成",
        ]:
            assert text in report_page.text, text

        report_api = client.get(f"/api/report/{assessment_id}").json()["full_report"]
        assert report_api["schema_version"] == 3
        assert len(report_api["chapters"]) == 10
        assert 0.0 < report_api["bank_approval"]["approval_probability"] <= 1.0
        assert report_api["bank_approval"]["likely_rejection_reasons"]
        assert report_api["generated_by"]["provider"] == "mock"

        print_page = client.get(f"/report/{assessment_id}/print")
        assert print_page.status_code == 200
        assert "打印 / 保存为PDF" in print_page.text
        assert "企业资本健康体检报告" in print_page.text

        api_event = client.post(
            "/api/events/upgrade-click",
            data={
                "assessment_id": assessment_id,
                "product_code": "699_bank_match",
                "from_product": "299_report",
                "target_product": "699_bank_match",
            },
        )
        assert api_event.status_code == 200
        assert api_event.json()["ok"] is True

        dashboard = client.get("/admin")
        assert dashboard.status_code == 200
        for text in ["成交漏斗", "今日待跟进任务", "逾期任务", "高优先级任务"]:
            assert text in dashboard.text

        with SessionLocal() as db:
            event_types = {
                row.event_type
                for row in db.query(Event).filter(Event.assessment_id == assessment_id).all()
            }
            expected = {
                "assessment_submitted",
                "free_result_viewed",
                "checkout_viewed",
                "payment_success",
                "report_viewed",
                "upgrade_clicked",
                "task_done",
            }
            assert expected <= event_types
            completed = db.get(FollowTask, first_task_id)
            assert completed.status == "done"
            assert db.get(FollowTask, manual_task_id).status == "cancelled"
            print(
                json.dumps(
                    {
                        "assessment_id": assessment_id,
                        "lead_id": lead_id,
                        "auto_task_count": len(auto_tasks),
                        "events": sorted(event_types),
                        "bank_probability": report_api["bank_approval"]["approval_probability"],
                    },
                    ensure_ascii=False,
                )
            )
    print("PHASE3_END_TO_END_OK")


if __name__ == "__main__":
    run()
