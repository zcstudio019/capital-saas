"""Regression test for report rendering without raw dict or JSON output."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
TEST_DB = ROOT / "phase_report_delivery_quality_test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
os.environ["AI_MODE"] = "mock"
if TEST_DB.exists():
    TEST_DB.unlink()
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from db.database import SessionLocal
from db.models import Report
from main import app
from utils.report_render_formatter import (
    contains_raw_structure_text,
    format_action_plan,
    validate_report_for_delivery,
)


PAYLOAD = {
    "company_name": "交付质量验收企业",
    "contact_name": "王经理",
    "phone": "13900139000",
    "wechat_id": "delivery_quality_check",
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

RAW_ACTION_PLAN = [
    {
        "period": "30_days",
        "owner": "企业负责人牵头，财务负责人配合",
        "actions": ["统一资料口径", "准备13周现金流预测"],
        "outcome": "形成统一资料包和现金流预测报告。",
    },
    {
        "period": "90_days",
        "owner": "财务负责人主责，企业负责人确认融资策略",
        "actions": ["完成银行预匹配", "提交核心额度申请"],
        "outcome": "至少一家银行进入审批流程。",
    },
]


def run() -> None:
    formatted = format_action_plan(RAW_ACTION_PLAN)
    assert formatted[0]["period"] == "未来30天行动计划"
    assert formatted[0]["actions"] == ["统一资料口径", "准备13周现金流预测"]

    with TestClient(app) as client:
        login = client.post(
            "/login",
            data={"username": "admin", "password": "admin123", "next_url": "/admin"},
            follow_redirects=False,
        )
        assert login.status_code == 303
        submitted = client.post("/assessment/submit", data=PAYLOAD, follow_redirects=False)
        assessment_id = int(submitted.headers["location"].rsplit("/", 1)[-1])
        assert client.post(
            f"/payment/mock-pay/{assessment_id}?product=1999_structure_plan",
            follow_redirects=False,
        ).status_code == 303
        assert client.get(f"/report/{assessment_id}").status_code == 200

        with SessionLocal() as db:
            report = db.query(Report).filter(Report.assessment_id == assessment_id).one()
            payload = json.loads(report.full_report_json)
            payload["risk_level"] = "medium"
            payload["chapters"][9]["next_steps"] = json.dumps(RAW_ACTION_PLAN, ensure_ascii=False)
            report.full_report_json = json.dumps(payload, ensure_ascii=False)
            db.commit()

        report_page = client.get(f"/report/{assessment_id}")
        print_page = client.get(f"/report/{assessment_id}/print")
        assert report_page.status_code == 200
        assert print_page.status_code == 200
        for text in (report_page.text, print_page.text):
            assert not contains_raw_structure_text(text)
            assert validate_report_for_delivery(text)["valid"]
            for forbidden in ("{'period'", "owner", "actions", "outcome", "medium", "_days"):
                assert forbidden not in text.lower()
            for expected in ("未来30天行动计划", "负责人", "核心动作", "交付结果", "中等风险"):
                assert expected in text

    print("REPORT_DELIVERY_QUALITY_TEST_OK")


if __name__ == "__main__":
    run()
