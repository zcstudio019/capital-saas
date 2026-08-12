"""注册资本字段从测评表单到报告与后台展示的专项验收。"""

from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
TEST_DB = ROOT / "phase_registered_capital_test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
os.environ["AI_MODE"] = "mock"
if TEST_DB.exists():
    TEST_DB.unlink()
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from sqlalchemy import inspect

from core.capital_health_report import build_capital_health_report
from core.scoring_engine import calculate_score
from db.database import SessionLocal, engine
from db.migrations import SQLITE_COLUMNS
from db.models import Assessment
from main import app


BASE_PAYLOAD = {
    "company_name": "上海注册资本验收有限公司",
    "contact_name": "张经理",
    "phone": "13800138000",
    "industry": "制造业",
    "years": "5",
    "annual_revenue": "12000000",
    "net_profit_margin": "8.5",
    "debt_total": "1800000",
    "short_debt": "600000",
    "funding_need": "3000000",
    "funding_purposes": ["补充流动资金"],
    "collateral_types": ["有设备"],
    "enterprise_credit_status": "no_overdue",
    "legal_credit_status": "no_overdue",
    "credit_query_count_6m": "3",
}


def _business_dimension(report: dict) -> dict:
    return next(item for item in report["dimensions"] if item["dimension_name"] == "企业基本面")


def _registered_capital_item(report: dict) -> dict:
    dimension = _business_dimension(report)
    return next(item for item in dimension["items"] if item["check_item"] == "注册资本")


def run() -> None:
    with TestClient(app) as client:
        page = client.get("/assessment")
        assert page.status_code == 200
        company_at = page.text.index('name="company_name"')
        capital_at = page.text.index('name="registered_capital"')
        industry_at = page.text.index('name="industry"')
        assert company_at < capital_at < industry_at
        assert "注册资本（元）" in page.text
        assert "请输入营业执照登记的注册资本" in page.text
        assert "请按营业执照登记金额填写，单位为人民币元。" in page.text

        blank = client.post(
            "/assessment/submit",
            data={**BASE_PAYLOAD, "registered_capital": ""},
            follow_redirects=False,
        )
        assert blank.status_code == 303
        blank_id = int(blank.headers["location"].rsplit("/", 1)[-1])

        provided = client.post(
            "/assessment/submit",
            data={
                **BASE_PAYLOAD,
                "company_name": "上海注册资本展示有限公司",
                "phone": "13900139000",
                "registered_capital": "5000000",
            },
            follow_redirects=False,
        )
        assert provided.status_code == 303
        provided_id = int(provided.headers["location"].rsplit("/", 1)[-1])

        with SessionLocal() as db:
            blank_item = db.get(Assessment, blank_id)
            provided_item = db.get(Assessment, provided_id)
            assert blank_item is not None and blank_item.registered_capital is None
            assert provided_item is not None and provided_item.registered_capital == 5_000_000

            blank_report = build_capital_health_report(db, blank_item, include_extended=False)
            blank_capital = _registered_capital_item(blank_report)
            assert blank_capital["check_result"] == "待补充资料核验"
            assert blank_capital["score"] is None

            full_report = build_capital_health_report(db, provided_item, include_extended=False)
            capital = _registered_capital_item(full_report)
            assert capital["check_result"] == "500万元"
            assert capital["score"] is None
            assert "不直接参与融资评分" in capital["scoring_basis"]

        score_input = {
            "years": 5,
            "annual_revenue": 12_000_000,
            "net_profit_margin": 8.5,
            "monthly_cashflow": 600_000,
            "debt_total": 1_800_000,
            "short_debt": 600_000,
            "receivable_days": 45,
            "funding_need": 3_000_000,
            "tax_status": True,
            "credit_status": True,
            "knows_cashflow": True,
            "has_budget": True,
            "has_collateral": True,
            "fund_usage_plan": True,
        }
        baseline_score = calculate_score(score_input)
        capital_score = calculate_score({**score_input, "registered_capital": 50_000_000})
        assert capital_score.total == baseline_score.total
        assert capital_score.dimensions == baseline_score.dimensions

        admin_login = client.post(
            "/login",
            data={"username": "admin", "password": "admin123", "next_url": "/admin"},
            follow_redirects=False,
        )
        assert admin_login.status_code == 303
        with SessionLocal() as db:
            provided_item = db.get(Assessment, provided_id)
            lead_id = provided_item.lead.id
        lead_page = client.get(f"/admin/leads/{lead_id}")
        assert lead_page.status_code == 200
        assert "注册资本" in lead_page.text and "500万元" in lead_page.text

    assert "registered_capital" in {
        column["name"] for column in inspect(engine).get_columns("assessments")
    }
    assert SQLITE_COLUMNS["assessments"]["registered_capital"] == "FLOAT"
    print("REGISTERED_CAPITAL_OK")


if __name__ == "__main__":
    run()
