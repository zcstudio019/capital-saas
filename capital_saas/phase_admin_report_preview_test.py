"""后台报告正文预览、版本兼容与权限隔离专项测试。"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEST_DB = ROOT / "phase_admin_report_preview_test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
os.environ["AI_MODE"] = "mock"
os.environ["PAYMENT_MODE"] = "mock"
if TEST_DB.exists():
    TEST_DB.unlink()
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from core.capital_health_report import build_capital_health_report
from db.database import SessionLocal
from db.models import Report, ReportVersion, User
from main import app
from services.auth_service import hash_password


PAYLOAD = {
    "company_name": "后台报告预览验收企业",
    "contact_name": "张经理",
    "phone": "13800138991",
    "industry": "制造业",
    "years": "6",
    "employee_count": "36",
    "annual_revenue": "12000000",
    "net_profit_margin": "8.5",
    "debt_total": "2200000",
    "short_debt": "900000",
    "funding_need": "2600000",
    "funding_purposes": "补充流动资金",
    "collateral_types": "有设备",
    "enterprise_credit_status": "no_overdue",
    "legal_credit_status": "no_overdue",
    "credit_query_count_6m": "3",
}


def login(client: TestClient, username: str, password: str) -> None:
    response = client.post(
        "/login",
        data={"username": username, "password": password, "next_url": "/admin/reports"},
        follow_redirects=False,
    )
    assert response.status_code == 303


def run() -> None:
    with TestClient(app) as client:
        submitted = client.post("/assessment/submit", data=PAYLOAD, follow_redirects=False)
        assert submitted.status_code == 303
        assessment_id = int(submitted.headers["location"].rsplit("/", 1)[-1])
        with SessionLocal() as db:
            report = db.query(Report).filter_by(assessment_id=assessment_id).one()
            report_id = report.id
            # 模拟历史报告：正文存在，但版本表和 current_version_id 均缺失。
            db.query(ReportVersion).filter_by(report_id=report.id).delete()
            report.current_version_id = None
            db.commit()

        login(client, "admin", "admin123")
        detail = client.get(f"/admin/reports/{report_id}")
        assert detail.status_code == 200
        assert "查看免费报告" in detail.text and "V1" in detail.text
        free_preview = client.get(f"/admin/reports/{report_id}/preview")
        assert free_preview.status_code == 200
        assert "企业资本健康摘要" in free_preview.text
        assert free_preview.text.count("free-dimension-card") >= 8
        assert client.get(f"/admin/reports/{report_id}/print").status_code == 200
        with SessionLocal() as db:
            report = db.get(Report, report_id)
            assert report.current_version_id
            assert db.query(ReportVersion).filter_by(report_id=report_id, version_no=1).count() == 1

        paid_980 = client.post(
            f"/payment/mock-pay/{assessment_id}?product=980_capital_health_report",
            follow_redirects=False,
        )
        assert paid_980.status_code == 303
        preview_980 = client.get(f"/admin/reports/{report_id}/preview")
        assert preview_980.status_code == 200
        assert "分项检查报告" in preview_980.text and "八维资本健康评分" in preview_980.text
        assert "融资方案深度升级" in preview_980.text

        # 客户未购买1999时，后台仍可查看已生成的1999候选草稿。
        with SessionLocal() as db:
            report = db.get(Report, report_id)
            snapshot = build_capital_health_report(db, report.assessment, admin_override=True, include_extended=True)
            snapshot["access_level"] = "structure_plan"
            payload = {"capital_health_snapshot": snapshot, "report_meta": {"access_level": "structure_plan"}}
            candidate = ReportVersion(
                report_id=report.id,
                assessment_id=report.assessment_id,
                version_no=max(item.version_no for item in db.query(ReportVersion).filter_by(report_id=report.id)) + 1,
                product_code="1999_structure_plan",
                access_level="structure_plan",
                generator_mode="mock",
                quality_score=90,
                report_json=json.dumps(payload, ensure_ascii=False),
                created_by="test-candidate",
            )
            db.add(candidate)
            db.commit()
            candidate_id = candidate.id
        candidate_preview = client.get(f"/admin/reports/{report_id}/preview?version_id={candidate_id}")
        assert candidate_preview.status_code == 200
        assert "优化处方" in candidate_preview.text and "融资落地行动计划" in candidate_preview.text
        customer_view = client.get(f"/report/{assessment_id}")
        assert customer_view.status_code == 200 and "融资方案深度升级" in customer_view.text

        paid_1999 = client.post(
            f"/payment/mock-pay/{assessment_id}?product=1999_structure_plan",
            follow_redirects=False,
        )
        assert paid_1999.status_code == 303
        with SessionLocal() as db:
            assert db.get(Report, report_id).review_status == "pending_review"
        pending_preview = client.get(f"/admin/reports/{report_id}/preview")
        review_page = client.get(f"/admin/reports/{report_id}/review")
        assert pending_preview.status_code == 200 and "优化处方" in pending_preview.text
        assert review_page.status_code == 200 and "完整报告预览" in review_page.text
        approved = client.post(
            f"/admin/reports/{report_id}/approve",
            data={"review_note": "额度、产品和行动方案已复核。"},
            follow_redirects=False,
        )
        assert approved.status_code == 303
        with SessionLocal() as db:
            assert db.get(Report, report_id).review_status == "approved"

        versions = client.get(f"/admin/reports/{report_id}/versions")
        assert versions.status_code == 200 and "查看版本" in versions.text
        assert client.get(f"/admin/reports/{report_id}/versions/{candidate_id}").status_code == 200

        client.get("/logout")
        with SessionLocal() as db:
            db.add(User(
                username="preview_sales",
                password_hash=hash_password("sales123"),
                display_name="非归属销售",
                role="sales",
                is_active=True,
            ))
            db.commit()
        login(client, "preview_sales", "sales123")
        assert client.get(f"/admin/reports/{report_id}/preview").status_code == 403

    print("ADMIN_REPORT_PREVIEW_OK")


if __name__ == "__main__":
    run()
