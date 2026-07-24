"""Phase 6：AI流水线、质量门禁、版本审核、产品匹配、顾问案件与上传验收。"""

import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from db.database import SessionLocal
from db.models import (
    AIGenerationLog, BankProduct, ConsultingCase, Lead, Report,
    ReportVersion, UploadedDocument,
)
from main import app


PAYLOAD = {
    "company_name": "Phase6智能顾问测试企业有限公司",
    "contact_name": "顾问测试",
    "phone": "13500135000",
    "wechat_id": "phase6_advisor",
    "city": "上海",
    "industry": "制造业",
    "years": "6",
    "employee_count": "65",
    "annual_revenue": "18000000",
    "net_profit": "1450000",
    "monthly_cashflow": "480000",
    "debt_total": "6500000",
    "short_debt": "4200000",
    "receivable_days": "95",
    "funding_need": "5000000",
    "funding_purpose": "订单周转、设备投入与高成本短债置换",
    "has_collateral": "true",
    "tax_status": "true",
    "credit_status": "true",
    "knows_cashflow": "true",
    "has_budget": "false",
    "leverage_attitude": "适中",
    "asset_efficiency": "中",
    "fund_usage_plan": "true",
}


def login(client):
    response = client.post(
        "/login",
        data={"username": "admin", "password": "admin123", "next_url": "/admin"},
        follow_redirects=False,
    )
    assert response.status_code == 303


def run():
    with TestClient(app) as client:
        submit = client.post("/assessment/submit", data=PAYLOAD, follow_redirects=False)
        assert submit.status_code == 303
        assessment_id = int(submit.headers["location"].rsplit("/", 1)[-1])
        paid = client.post(
            f"/payment/mock-pay/{assessment_id}?product=1999_structure_plan",
            follow_redirects=False,
        )
        assert paid.status_code == 303

        report_page = client.get(f"/report/{assessment_id}")
        assert report_page.status_code == 200
        for text in ["银行产品组合建议", "资料准备清单", "免责声明", "优化处方"]:
            assert text in report_page.text
        print_page = client.get(f"/report/{assessment_id}/print")
        assert print_page.status_code == 200
        assert "不构成任何形式的融资承诺" in print_page.text

        with SessionLocal() as db:
            report = db.query(Report).filter(Report.assessment_id == assessment_id).one()
            report_id = report.id
            lead = db.query(Lead).filter(Lead.assessment_id == assessment_id).one()
            lead_id = lead.id
            payload = json.loads(report.full_report_json)
            assert payload["pipeline_version"] == 6
            assert payload["product_code"] == "1999_structure_plan"
            assert len(payload["chapters"]) == 10
            assert payload["quality"]["quality_score"] >= 70
            assert payload["document_checklist"]["detail_level"] == "full"
            assert payload["bank_product_matches"]["matched_products"]
            for section in payload["chapters"]:
                assert {
                    "section_title", "conclusion", "key_findings", "bank_view",
                    "boss_action", "next_steps", "risk_warning", "upsell_hint",
                } <= set(section)
            assert db.query(ReportVersion).filter(ReportVersion.report_id == report.id).count() == 1
            assert db.query(AIGenerationLog).filter(AIGenerationLog.report_id == report.id).count() == 10
            assert db.query(ConsultingCase).filter(
                ConsultingCase.assessment_id == assessment_id
            ).count() == 1
            assert db.query(BankProduct).count() >= 6
            assert report.review_status == "approved"

        login(client)
        for url in [
            f"/admin/reports/{report_id}",
            f"/admin/reports/{report_id}/versions",
            "/admin/bank-products",
            "/admin/consulting-cases",
            f"/admin/leads/{lead_id}/documents",
        ]:
            assert client.get(url).status_code == 200

        regenerate = client.post(
            f"/admin/reports/{report_id}/regenerate", follow_redirects=False
        )
        assert regenerate.status_code == 303
        with SessionLocal() as db:
            versions = db.query(ReportVersion).filter(
                ReportVersion.report_id == report_id
            ).order_by(ReportVersion.version_no).all()
            assert len(versions) == 2
            old_version_id = versions[0].id

        switched = client.post(
            f"/admin/reports/{report_id}/versions/{old_version_id}/set-current",
            follow_redirects=False,
        )
        assert switched.status_code == 303
        assert client.post(
            f"/admin/reports/{report_id}/approve",
            data={"review_note": "Phase6审核通过"},
            follow_redirects=False,
        ).status_code == 303
        assert client.post(
            f"/admin/reports/{report_id}/generate-token",
            follow_redirects=False,
        ).status_code == 303

        with SessionLocal() as db:
            report = db.get(Report, report_id)
            token = report.public_token
            assert token and report.review_status == "approved"
        public_page = client.get(f"/public/report/{token}")
        assert public_page.status_code == 200
        assert "不构成任何形式的融资承诺" in public_page.text

        created = client.post(
            "/admin/bank-products/save",
            data={
                "product_id": "0", "bank_name": "模拟测试银行", "bank_type": "城商行",
                "product_name": "Phase6测试经营贷", "product_type": "经营贷",
                "suitable_industry": "制造业", "min_revenue": "1000000",
                "min_years": "2", "requires_tax_normal": "true",
                "requires_credit_normal": "true", "max_amount": "3000000",
                "interest_rate_range": "以审批为准", "loan_term": "12-36个月",
                "application_requirements": "经营真实", "risk_notes": "仅模拟规则",
            },
            follow_redirects=False,
        )
        assert created.status_code == 303
        with SessionLocal() as db:
            bank_product = db.query(BankProduct).filter(
                BankProduct.product_name == "Phase6测试经营贷"
            ).one()
            bank_product_id = bank_product.id
        assert client.get(f"/admin/bank-products/{bank_product_id}/edit").status_code == 200
        assert client.post(
            f"/admin/bank-products/{bank_product_id}/toggle",
            follow_redirects=False,
        ).status_code == 303

        upload = client.post(
            f"/admin/leads/{lead_id}/documents",
            data={"document_category": "财务资料"},
            files={"upload": ("phase6-finance.pdf", io.BytesIO(b"%PDF-1.4 phase6"), "application/pdf")},
            follow_redirects=False,
        )
        assert upload.status_code == 303
        with SessionLocal() as db:
            document = db.query(UploadedDocument).filter(
                UploadedDocument.lead_id == lead_id
            ).one()
            document_id = document.id
        assert client.post(
            f"/admin/leads/{lead_id}/documents/{document_id}/delete",
            follow_redirects=False,
        ).status_code == 303

        print({
            "assessment_id": assessment_id,
            "report_id": report_id,
            "lead_id": lead_id,
            "quality_score": payload["quality"]["quality_score"],
            "versions": 2,
            "ai_logs": 20,
        })
    print("PHASE6_AI_ADVISOR_OK")


if __name__ == "__main__":
    run()
