"""现金流报告接入统一后台、客户中心和版本体系专项验收。"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEST_DB = ROOT / "phase_cashflow_report_admin_integration_test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
os.environ["AI_MODE"] = "mock"
os.environ["PAYMENT_MODE"] = "mock"
os.environ["APP_ENV"] = "development"
if TEST_DB.exists():
    TEST_DB.unlink()
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from db.database import SessionLocal
from db.models import (CashflowAssessment, CashflowReport, CustomerAccount, Report,
                       ReportVersion)
from main import app
from services.cashflow_service import (backfill_unified_cashflow_reports,
    create_failed_unified_cashflow_report, regenerate_unified_cashflow_report,
    sync_unified_cashflow_report)


PHONE = "13800138661"


def registration_payload():
    return {"phone": PHONE, "contact_name": "现金流客户", "password": "Customer123",
            "confirm_password": "Customer123", "company_name": "现金流验收企业",
            "wechat_id": "", "city": "上海", "agree_legal": "1",
            "registration_method": "password", "next_url": "/client/dashboard"}


def capital_payload():
    return {"company_name": "现金流验收企业", "contact_name": "现金流客户", "phone": PHONE,
            "industry": "制造业", "years": "6", "annual_revenue": "12000000",
            "net_profit_margin": "8.5", "debt_total": "1600000", "short_debt": "500000",
            "funding_need": "2500000", "funding_purposes": "补充流动资金",
            "collateral_types": "有设备", "enterprise_credit_status": "no_overdue",
            "legal_credit_status": "no_overdue", "credit_query_count_6m": "3"}


def cashflow_payload():
    return {"company_name": "现金流验收企业", "phone": "138-0013-8661", "industry": "制造业",
            "business_scope": "设备制造", "company_type": "民营企业",
            "current_assets": "1000000", "current_liabilities": "800000", "inventory": "200000",
            "cash": "300000", "monthly_operating_expense": "150000", "revenue": "5000000",
            "net_profit": "300000", "operating_cashflow": "250000", "cash_received_sales": "4600000",
            "capex": "100000", "total_assets": "6000000", "total_debt": "2800000",
            "interest_bearing_debt": "1500000", "short_interest_debt": "800000",
            "interest_expense": "100000", "ebit": "600000", "dso": "80", "dio": "70", "dpo": "45",
            "forecast_in_1": "100000", "forecast_out_1": "500000"}


def run():
    with TestClient(app) as client:
        response = client.post("/client/register", data=registration_payload(), follow_redirects=False)
        assert response.status_code == 303
        assert client.post("/assessment/submit", data=capital_payload(), follow_redirects=False).status_code == 303
        submitted = client.post("/cashflow-assessment/submit", data=cashflow_payload(), follow_redirects=False)
        assert submitted.status_code == 303

        with SessionLocal() as db:
            cash = db.query(CashflowAssessment).filter_by(company_name="现金流验收企业").one()
            source = db.query(CashflowReport).filter_by(assessment_id=cash.id).one()
            unified = db.query(Report).filter_by(cashflow_report_id=source.id).one()
            report_id = unified.id
            lead_id = cash.lead_id
            assert unified.report_type == "cashflow_health_report"
            assert unified.source_type == "cashflow_assessment" and unified.source_id == cash.id
            assert unified.customer_id == cash.customer_id and unified.lead_id == lead_id
            assert unified.current_version_id
            assert db.query(ReportVersion).filter_by(report_id=unified.id, version_no=1).count() == 1
            _, created = sync_unified_cashflow_report(db, cash, source, json.loads(source.content_json))
            assert not created and db.query(Report).filter_by(cashflow_report_id=source.id).count() == 1

        reports = client.get("/client/reports")
        assert reports.status_code == 200 and "企业现金流健康诊断报告" in reports.text
        detail = client.get(f"/client/reports/{report_id}")
        assert detail.status_code == 200 and "13周现金流预测" in detail.text
        assert client.get(f"/client/reports/{report_id}/print").status_code == 200
        assert client.get(f"/client/reports/{report_id}/versions").status_code == 200

        client.get("/client/logout")
        login = client.post("/login", data={"username": "admin", "password": "admin123",
                            "next_url": "/admin/reports"}, follow_redirects=False)
        assert login.status_code == 303
        listing = client.get("/admin/reports?report_type=cashflow_health_report")
        assert listing.status_code == 200 and "企业现金流健康诊断报告" in listing.text
        admin_detail = client.get(f"/admin/reports/{report_id}")
        assert admin_detail.status_code == 200 and "当前版本" in admin_detail.text and "V1" in admin_detail.text
        preview = client.get(f"/admin/reports/{report_id}/preview")
        assert preview.status_code == 200 and "13周现金流预测" in preview.text
        assert client.get(f"/admin/reports/{report_id}/print").status_code == 200
        assert client.get(f"/admin/reports/{report_id}/versions").status_code == 200
        if lead_id:
            lead_page = client.get(f"/admin/leads/{lead_id}")
            assert lead_page.status_code == 200 and "企业现金流健康诊断报告" in lead_page.text

        regenerated = client.post(f"/admin/reports/{report_id}/regenerate", follow_redirects=False)
        assert regenerated.status_code == 303
        with SessionLocal() as db:
            unified = db.get(Report, report_id)
            assert db.get(ReportVersion, unified.current_version_id).version_no == 2
            assert db.query(ReportVersion).filter_by(report_id=report_id).count() == 2

        # Existing standalone cashflow reports are adopted once; repeated backfills are stable.
        with SessionLocal() as db:
            account = db.query(CustomerAccount).filter_by(login_phone=PHONE).one()
            legacy_assessment = CashflowAssessment(customer_id=account.id, company_name="历史现金流企业",
                phone=PHONE, input_json="{}", risk_level="需关注")
            db.add(legacy_assessment); db.flush()
            legacy_source = CashflowReport(assessment_id=legacy_assessment.id, customer_id=account.id,
                content_json=json.dumps({"title": "企业现金流健康诊断报告", "overview": {}}, ensure_ascii=False))
            db.add(legacy_source); db.commit()
            legacy_source_id = legacy_source.id
            first = backfill_unified_cashflow_reports(db)
            count_after_first = db.query(Report).filter_by(cashflow_report_id=legacy_source_id).count()
            second = backfill_unified_cashflow_reports(db)
            assert first["created"] == 1 and count_after_first == 1
            assert second["created"] == 0 and second["reused"] >= 2
            assert db.query(Report).filter_by(cashflow_report_id=legacy_source_id).count() == 1

            failed_assessment = CashflowAssessment(customer_id=account.id, company_name="报告失败可见企业",
                phone=PHONE, input_json="{}", risk_level="待补充资料核验")
            db.add(failed_assessment); db.flush()
            failed = create_failed_unified_cashflow_report(db, failed_assessment, "模拟生成失败")
            assert failed.generation_status == "generation_failed" and failed.current_version_id is None

        failed_list = client.get("/admin/reports?generation_status=generation_failed")
        assert failed_list.status_code == 200 and "报告失败可见企业" in failed_list.text

    print("CASHFLOW_REPORT_ADMIN_INTEGRATION_OK")


if __name__ == "__main__":
    run()
