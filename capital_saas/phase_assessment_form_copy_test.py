"""免费测评字段文案与净利润百分比口径验收。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEST_DB = ROOT / "phase_assessment_form_copy_test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
os.environ["AI_MODE"] = "mock"
if TEST_DB.exists():
    TEST_DB.unlink()
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from db.database import SessionLocal
from db.models import Assessment
from main import app
from core.capital_health_report import build_capital_health_report
from core.financial_metrics import net_profit_margin_percent


BASE_PAYLOAD = {
    "company_name": "上海字段口径验证有限公司",
    "contact_name": "王经理",
    "phone": "13800138000",
    "wechat_id": "assessment_copy_test",
    "city": "上海",
    "industry": "企业服务",
    "years": "5",
    "employee_count": "30",
    "annual_revenue": "1000000",
    "net_profit_margin": "12",
    "monthly_cashflow": "100000",
    "debt_total": "200000",
    "short_debt": "80000",
    "receivable_days": "45",
    "funding_need": "200000",
    "funding_purpose": "经营周转",
    "funding_purposes": "补充流动资金",
    "collateral_types": "有设备",
    "enterprise_credit_status": "no_overdue",
    "legal_credit_status": "no_overdue",
    "credit_query_count_6m": "3",
    "credit_card_usage_rate": "40",
    "tax_credit_grade": "B",
    "tax_arrears_status": "none",
    "has_collateral": "false",
    "tax_status": "true",
    "credit_status": "true",
    "knows_cashflow": "true",
    "has_budget": "true",
    "leverage_attitude": "适中",
    "asset_efficiency": "中",
    "fund_usage_plan": "true",
}


def run() -> None:
    assert net_profit_margin_percent(120000, 1000000, None) == 12
    assert net_profit_margin_percent(999999, 1000000, 8.5) == 8.5
    with TestClient(app) as client:
        form = client.get("/assessment")
        assert form.status_code == 200
        assert 'placeholder="例如：8.5，亏损可填写负数"' in form.text
        assert "近12个月净利润率" in form.text
        assert "一年内到期的短期负债" in form.text
        assert "短期负债是指未来12个月内需要偿还的负债" in form.text
        assert "近6个月月均经营性现金流入" in form.text
        assert "企业近24个月是否有贷款逾期" in form.text
        assert "近6个月月均对公账户经营性流入" in form.text
        assert "近12个月实际纳税总额" in form.text
        assert "企业名下房产估值" in form.text
        assert "元，可为负数" not in form.text

        submitted = client.post("/assessment/submit", data=BASE_PAYLOAD, follow_redirects=False)
        assert submitted.status_code == 303
        assessment_id = int(submitted.headers["location"].rsplit("/", 1)[-1])
        assert client.get(f"/result/{assessment_id}").status_code == 200
        with SessionLocal() as db:
            assessment = db.get(Assessment, assessment_id)
            assert assessment is not None
            assert assessment.net_profit == 120000
            assert assessment.net_profit_margin == 12
            assert assessment.funding_purpose == "补充流动资金"
            assert assessment.collateral_types == "有设备"
            assert assessment.enterprise_credit_status == "no_overdue"
            report = build_capital_health_report(db, assessment, include_extended=False)
            profit_item = next(
                item for dimension in report["dimensions"]
                for item in dimension["items"]
                if item["check_item"] == "近12个月净利润率"
            )
            short_debt_item = next(
                item for dimension in report["dimensions"]
                for item in dimension["items"]
                if item["check_item"] == "一年内到期负债"
            )
            assert profit_item["check_result"] == "12.0%"
            assert "万元" in short_debt_item["check_result"]

        legacy_payload = {
            **BASE_PAYLOAD,
            "company_name": "上海历史金额兼容验证有限公司",
            "phone": "13900139000",
            "wechat_id": "legacy_profit_amount",
            "net_profit": "120000",
        }
        legacy_payload.pop("net_profit_margin", None)
        legacy = client.post("/assessment/submit", data=legacy_payload, follow_redirects=False)
        legacy_id = int(legacy.headers["location"].rsplit("/", 1)[-1])
        with SessionLocal() as db:
            assessment = db.get(Assessment, legacy_id)
            assert assessment is not None
            assert assessment.net_profit == 120000
            assert assessment.net_profit_margin == 12

    print("ASSESSMENT_FORM_COPY_OK")


if __name__ == "__main__":
    run()
