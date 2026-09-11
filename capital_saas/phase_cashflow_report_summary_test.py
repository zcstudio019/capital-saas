"""现金流报告前四章、真实额度依据及全端渲染专项测试。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEST_DB = ROOT / "phase_cashflow_report_summary_test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
os.environ["AI_MODE"] = "mock"
os.environ["PAYMENT_MODE"] = "mock"
os.environ["APP_ENV"] = "development"
if TEST_DB.exists():
    TEST_DB.unlink()
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from core.cashflow_report_summary import build_core_problems
from db.database import SessionLocal
from db.models import BankProduct, CashflowAssessment, CashflowReport, Report, ReportVersion
from main import app
from services.cashflow_service import create_diagnosis, report_content


PHONE = "13800138671"


def registration_payload():
    return {"phone": PHONE, "contact_name": "摘要验收客户", "password": "Customer123",
            "confirm_password": "Customer123", "company_name": "现金流摘要验收企业",
            "wechat_id": "", "city": "上海", "agree_legal": "1",
            "registration_method": "password", "next_url": "/client/dashboard"}


def capital_payload():
    return {"company_name": "现金流摘要验收企业", "contact_name": "摘要验收客户", "phone": PHONE,
            "industry": "制造业", "years": "8", "employee_count": "45", "annual_revenue": "12000000",
            "net_profit_margin": "9", "debt_total": "2800000", "short_debt": "1500000",
            "monthly_cashflow": "450000", "receivable_days": "80", "funding_need": "3000000",
            "funding_purposes": "补充流动资金", "collateral_types": "有设备",
            "has_collateral": "1", "tax_status": "1", "credit_status": "1",
            "enterprise_credit_status": "no_overdue", "legal_credit_status": "no_overdue",
            "credit_query_count_6m": "2"}


def cashflow_payload():
    return {"company_name": "现金流摘要验收企业", "phone": PHONE, "industry": "制造业",
            "business_scope": "产品生产制造", "company_type": "民营企业", "years": "8",
            "current_assets": "4200000", "current_liabilities": "3000000", "inventory": "1500000",
            "cash": "300000", "monthly_operating_expense": "200000", "revenue": "12000000",
            "net_profit": "1080000", "operating_cashflow": "600000", "cash_received_sales": "9000000",
            "capex": "500000", "total_assets": "9000000", "total_debt": "4200000",
            "interest_bearing_debt": "2800000", "short_interest_debt": "2300000",
            "interest_expense": "240000", "ebit": "1400000", "receivables_balance": "3200000",
            "dso": "105", "dso_yoy": "28", "dio": "80", "dio_yoy": "10", "dpo": "45",
            "credit_limit": "3000000", "credit_used": "2700000", "negative_operating_cf_months": "0",
            "compressible_expense": "180000", "capex_deferrable": "1",
            "forecast_in_1": "100000", "forecast_out_1": "650000"}


def run():
    with TestClient(app) as client:
        assert client.post("/client/register", data=registration_payload(), follow_redirects=False).status_code == 303
        assert client.post("/assessment/submit", data=capital_payload(), follow_redirects=False).status_code == 303
        with SessionLocal() as db:
            db.add(BankProduct(product_code="REAL-CF-001", bank_name="验收银行", bank_type="城商行",
                product_name="普惠经营贷", product_type="经营贷", city="全国", suitable_industry="制造业",
                min_revenue=1_000_000, min_years=2, min_amount=100_000, max_amount=5_000_000,
                interest_rate_range="以审批为准", loan_term="12-36个月", data_source="manual", is_active=True))
            db.commit()

        submitted = client.post("/cashflow-assessment/submit", data=cashflow_payload(), follow_redirects=False)
        assert submitted.status_code == 303
        assessment_id = int(submitted.headers["location"].rsplit("/", 1)[-1])
        with SessionLocal() as db:
            assessment = db.get(CashflowAssessment, assessment_id)
            source = db.query(CashflowReport).filter_by(assessment_id=assessment_id).one()
            content = report_content(source, db)
            summary = content["executive_summary"]
            problems = content["core_problems"]
            capacity = content["financing_capacity"]
            plan = content["improvement_plan"]
            assert summary["current_score"] != "待补充资料核验"
            assert summary["health_level"] in {"健康", "基本健康", "亚健康", "高风险", "严重风险"}
            assert problems and problems[0]["code"] == "forecast_gap"
            assert {item["code"] for item in problems} >= {"short_debt", "receivables"}
            assert capacity["status"] == "已测算" and capacity["basis"]
            assert capacity["matched_product_count"] == 1 and capacity["matched_products"] == ["普惠经营贷"]
            assert capacity["recommended_amount"].endswith("万元以内")
            assert all(plan[key] for key in ("immediate", "days_30", "days_90", "months_6"))
            assert any(item["solves_problem"] == "应收账款占用资金较多" for item in plan["days_30"])
            unified = db.query(Report).filter_by(cashflow_report_id=source.id).one()
            report_id = unified.id
            assert db.get(ReportVersion, unified.current_version_id).version_no == 1

            # 改变诊断数据，核心问题应随之改变，而不是固定模板。
            inventory_content = create_diagnosis(db, {
                "company_name": "库存问题企业", "current_assets": 3_000_000,
                "current_liabilities": 1_000_000, "cash": 800_000,
                "monthly_operating_expense": 200_000, "revenue": 6_000_000,
                "operating_cashflow": 500_000, "inventory": 2_000_000,
                "dio": 180, "dio_yoy": 45, "inventory_stagnant_ratio": .35,
            })[2]
            inventory_codes = {item["code"] for item in inventory_content["core_problems"]}
            assert "inventory" in inventory_codes and inventory_codes != {item["code"] for item in problems}

            partial_content = create_diagnosis(db, {"company_name": "资料不足企业"})[2]
            partial_capacity = partial_content["financing_capacity"]
            assert partial_capacity["status"] == "待补充资料后评估"
            assert partial_capacity["theoretical_range"] == "待补充资料后评估"
            assert {"银行流水", "企业征信", "纳税记录", "财务报表"} <= set(partial_capacity["missing_documents"])

        customer_page = client.get(f"/client/reports/{report_id}")
        customer_print = client.get(f"/client/reports/{report_id}/print")
        for response in (customer_page, customer_print):
            assert response.status_code == 200
            for number, title in (("01", "现状评分"), ("02", "核心问题"), ("03", "可融额度"),
                                  ("04", "改进建议"), ("05", "现金流健康指标"),
                                  ("09", "13周现金流预测"), ("13", "顾问建议")):
                assert number in response.text and title in response.text
            assert "普惠经营贷" in response.text and "P0 · 立即处理" in response.text
            assert "{'" not in response.text and '"executive_summary"' not in response.text
            for technical_key in ("cashflow_health_score", "cash_gap_week", "risk_level"):
                assert technical_key not in response.text
            for naked in (">DSO<", ">DIO<", ">DPO<", ">P0<"):
                assert naked not in response.text
        assert "打印 / 保存为PDF" in customer_print.text

        client.get("/client/logout")
        assert client.post("/login", data={"username": "admin", "password": "admin123",
                           "next_url": "/admin/reports"}, follow_redirects=False).status_code == 303
        for path in (f"/admin/reports/{report_id}", f"/admin/reports/{report_id}/preview",
                     f"/admin/reports/{report_id}/print"):
            response = client.get(path)
            assert response.status_code == 200 and "现状评分" in response.text and "改进建议" in response.text

        # 旧V1动态可看新版摘要；重新生成追加V2，不覆盖V1。
        assert client.post(f"/admin/reports/{report_id}/regenerate", follow_redirects=False).status_code == 303
        with SessionLocal() as db:
            unified = db.get(Report, report_id)
            versions = db.query(ReportVersion).filter_by(report_id=report_id).order_by(ReportVersion.version_no).all()
            assert [item.version_no for item in versions] == [1, 2]
            assert unified.current_version_id == versions[-1].id

    print("CASHFLOW_REPORT_SUMMARY_OK")


if __name__ == "__main__":
    run()
