"""融资结构优化方案人工审核闭环验收。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEST_DB = ROOT / "phase_report_review_workflow_test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
os.environ["AI_MODE"] = "mock"
os.environ["PAYMENT_MODE"] = "mock"
if TEST_DB.exists():
    TEST_DB.unlink()
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from db.database import SessionLocal
from db.models import AuditLog, ConsultingCase, Event, InternalNotification, NotificationJob, Report, User
from main import app
from services.auth_service import hash_password
from services.settings_service import save_settings

PAYLOAD = {
    "company_name": "上海启明供应链有限公司",
    "contact_name": "周先生",
    "phone": "13800138000",
    "wechat_id": "review_workflow",
    "city": "上海",
    "industry": "供应链服务",
    "years": "5",
    "employee_count": "35",
    "annual_revenue": "9000000",
    "net_profit": "720000",
    "monthly_cashflow": "560000",
    "debt_total": "2600000",
    "short_debt": "1500000",
    "receivable_days": "70",
    "funding_need": "2000000",
    "funding_purpose": "经营周转",
    "has_collateral": "false",
    "tax_status": "true",
    "credit_status": "true",
    "knows_cashflow": "true",
    "has_budget": "true",
    "leverage_attitude": "适中",
    "asset_efficiency": "中",
    "fund_usage_plan": "true",
}


def login(client: TestClient, username: str, password: str) -> None:
    response = client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    assert response.status_code == 303


def run() -> None:
    with TestClient(app) as customer, TestClient(app) as backend:
        submitted = customer.post("/assessment/submit", data=PAYLOAD, follow_redirects=False)
        assert submitted.status_code == 303
        assessment_id = int(submitted.headers["location"].rsplit("/", 1)[-1])

        assert customer.post(
            f"/payment/mock-pay/{assessment_id}?product=980_capital_health_report",
            follow_redirects=False,
        ).status_code == 303
        assert customer.get(f"/report/{assessment_id}").status_code == 200

        assert customer.post(
            f"/payment/mock-pay/{assessment_id}?product=1999_structure_plan",
            follow_redirects=False,
        ).status_code == 303
        pending = customer.get(f"/report/{assessment_id}")
        assert pending.status_code == 202
        assert "方案正在由融资顾问复核" in pending.text
        assert "提交审核时间" in pending.text

        login(backend, "admin", "admin123")
        pending_list = backend.get("/admin/reports?review_status=pending_review")
        assert pending_list.status_code == 200
        assert "报告管理（1）" in pending_list.text
        assert "立即审核" in pending_list.text

        with SessionLocal() as db:
            report = db.query(Report).filter(Report.assessment_id == assessment_id).one()
            report_id = report.id

        review = backend.get(f"/admin/reports/{report_id}/review")
        assert review.status_code == 200
        for expected in ("完整报告预览", "银行产品", "融资额度测算", "行动计划", "资料清单", "质量检查", "审核通过", "驳回修改"):
            assert expected in review.text
        with SessionLocal() as db:
            assert db.get(Report, report_id).review_status == "reviewing"

        saved = backend.post(
            f"/admin/reports/{report_id}/review-note",
            data={"review_note": "额度口径需补充流水依据。"},
            follow_redirects=False,
        )
        assert saved.status_code == 303

        rejected = backend.post(
            f"/admin/reports/{report_id}/reject",
            data={"review_note": "请补充流水依据后重新生成。"},
            follow_redirects=False,
        )
        assert rejected.status_code == 303
        with SessionLocal() as db:
            assert db.get(Report, report_id).review_status == "rejected"
            assert db.query(AuditLog).filter(AuditLog.action == "report_rejected").count() == 1
        assert customer.get(f"/report/{assessment_id}").status_code == 202

        regenerated = backend.post(f"/admin/reports/{report_id}/regenerate", follow_redirects=False)
        assert regenerated.status_code == 303
        with SessionLocal() as db:
            assert db.get(Report, report_id).review_status == "pending_review"
        backend.get(f"/admin/reports/{report_id}/review")
        approved = backend.post(
            f"/admin/reports/{report_id}/approve",
            data={"review_note": "产品、额度口径和行动计划已完成复核。"},
            follow_redirects=False,
        )
        assert approved.status_code == 303
        assert customer.get(f"/report/{assessment_id}").status_code == 200

        with SessionLocal() as db:
            report = db.get(Report, report_id)
            assert report.review_status == "approved"
            assert report.reviewed_by is not None and report.reviewed_at is not None
            assert db.query(NotificationJob).filter(
                NotificationJob.template_key == "structure_plan_approved_customer",
                NotificationJob.related_id == report_id,
            ).count() == 1
            assert db.query(InternalNotification).filter(
                InternalNotification.related_type == "report",
                InternalNotification.related_id == report_id,
            ).count() >= 1
            assert db.query(Event).filter(Event.event_type == "report_review_approved").count() == 1
            assert db.query(AuditLog).filter(AuditLog.action == "report_approved").count() == 1

            assigned = User(username="review_consultant", password_hash=hash_password("Consult123!"), role="consultant", is_active=True, force_password_change=False)
            other = User(username="other_consultant", password_hash=hash_password("Consult123!"), role="consultant", is_active=True, force_password_change=False)
            sales = User(username="review_sales", password_hash=hash_password("Sales123!"), role="sales", is_active=True, force_password_change=False)
            db.add_all([assigned, other, sales])
            db.flush()
            case = db.query(ConsultingCase).filter(ConsultingCase.report_id == report_id).first()
            assert case is not None
            case.consultant_user_id = assigned.id
            case.consultant_id = assigned.id
            report.review_status = "pending_review"
            db.commit()

        with TestClient(app) as assigned_client:
            login(assigned_client, "review_consultant", "Consult123!")
            assigned_list = assigned_client.get("/admin/reports?review_status=pending_review")
            assert assigned_list.status_code == 200 and "立即审核" in assigned_list.text
            assert assigned_client.get(f"/admin/reports/{report_id}/review").status_code == 200
        with TestClient(app) as other_client:
            login(other_client, "other_consultant", "Consult123!")
            assert other_client.get(f"/admin/reports/{report_id}/review").status_code == 403
        with TestClient(app) as sales_client:
            login(sales_client, "review_sales", "Sales123!")
            assert sales_client.get(f"/admin/reports/{report_id}/review").status_code == 403

        # 配置关闭 1999 人工审核后，应在生成成功时自动通过并立即交付。
        with SessionLocal() as db:
            save_settings(db, {"1999_plan_review_required": "false"})
        auto_payload = {
            **PAYLOAD,
            "company_name": "上海自动交付验证有限公司",
            "phone": "13900139000",
            "wechat_id": "auto_review_policy",
        }
        auto_submit = customer.post("/assessment/submit", data=auto_payload, follow_redirects=False)
        auto_assessment_id = int(auto_submit.headers["location"].rsplit("/", 1)[-1])
        assert customer.post(
            f"/payment/mock-pay/{auto_assessment_id}?product=1999_structure_plan",
            follow_redirects=False,
        ).status_code == 303
        assert customer.get(f"/report/{auto_assessment_id}").status_code == 200
        with SessionLocal() as db:
            auto_report = db.query(Report).filter(Report.assessment_id == auto_assessment_id).one()
            assert auto_report.review_status == "approved"
            save_settings(db, {"1999_plan_review_required": "true"})

    print("REPORT_REVIEW_WORKFLOW_OK")


if __name__ == "__main__":
    run()
