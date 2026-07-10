"""End-to-end customer-report language regression check."""

from __future__ import annotations

import os
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
TEST_DB = ROOT / "phase_report_chinese_check_test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
os.environ["AI_MODE"] = "mock"
if TEST_DB.exists():
    TEST_DB.unlink()
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from main import app
from scripts.check_report_english import assert_report_chinese_only
from utils.report_display_mapper import display_value


PAYLOAD = {
    "company_name": "报告中文化验收企业",
    "contact_name": "张经理",
    "phone": "13800138000",
    "wechat_id": "report_language_check",
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
    "funding_purpose": "补充订单周转与置换短期负债",
    "has_collateral": "false",
    "tax_status": "true",
    "credit_status": "true",
    "knows_cashflow": "true",
    "has_budget": "false",
    "leverage_attitude": "适中",
    "asset_efficiency": "中",
    "fund_usage_plan": "true",
}


def run() -> None:
    with TestClient(app) as client:
        login = client.post(
            "/login",
            data={"username": "admin", "password": "admin123", "next_url": "/admin"},
            follow_redirects=False,
        )
        assert login.status_code == 303
        submitted = client.post("/assessment/submit", data=PAYLOAD, follow_redirects=False)
        assert submitted.status_code == 303
        assessment_id = int(submitted.headers["location"].rsplit("/", 1)[-1])
        paid = client.post(
            f"/payment/mock-pay/{assessment_id}?product=1999_structure_plan",
            follow_redirects=False,
        )
        assert paid.status_code == 303

        report_page = client.get(f"/report/{assessment_id}")
        print_page = client.get(f"/report/{assessment_id}/print")
        report_api = client.get(f"/api/report/{assessment_id}").json()["full_report"]
        assert report_page.status_code == 200
        assert print_page.status_code == 200
        assert_report_chinese_only(report_page.text)
        assert_report_chinese_only(print_page.text)
        assert_report_chinese_only(json.dumps(report_api, ensure_ascii=False))
        assert "中等风险" in report_page.text
        assert "一般" in report_page.text
        assert "良好" in report_page.text
        assert "risk_level" not in report_api
        assert "funding_probability" not in report_api
        assert report_api["company_grade_display"] == "良好"
        assert report_api["bank_approval"]["approval_probability_display"].endswith("%")

    assert display_value("risk_level", "medium") == "中等风险"
    assert display_value("finance_feasibility", "excellent") == "优秀"
    assert display_value("company_grade", "B") == "良好"
    assert display_value("status", "pending") == "待评估"
    assert display_value("priority", "high") == "高优先级"
    assert display_value("trend", "stable") == "稳定"
    assert display_value("confidence", "low") == "低置信度"

    print("REPORT_LANGUAGE_CHECK_OK")


if __name__ == "__main__":
    run()
