"""测评提交完整链路检查。"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECK_DB = ROOT / "assessment_submit_chain_check.db"
os.environ["DATABASE_URL"] = f"sqlite:///{CHECK_DB.as_posix()}"
os.environ["AI_MODE"] = "mock"
if CHECK_DB.exists():
    CHECK_DB.unlink()
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from db.database import SessionLocal, engine
from db.models import Assessment, InternalNotification, Lead, Report
from main import app


def run() -> None:
    payload = {
        "company_name": "上海提交链路检查有限公司",
        "contact_name": "陈经理",
        "phone": "13700137000",
        "industry": "软件和信息技术服务业",
        "years": "4.5",
        "annual_revenue": "8000000",
        "net_profit_margin": "7.5",
        "monthly_cashflow": "",
        "debt_total": "1200000",
        "short_debt": "450000",
        "receivable_days": "",
        "funding_need": "1800000",
        "funding_purposes": ["研发投入"],
        "collateral_types": ["有知识产权"],
        "enterprise_credit_status": "no_overdue",
        "credit_query_count_6m": "2",
        "operating_flow_ratio": "",
        "public_private_ratio": "",
        "internal_transfer_ratio": "",
        "revenue_growth_rate": "-6.5",
    }
    try:
        with TestClient(app) as client:
            response = client.post(
                "/assessment/submit",
                data=payload,
                headers={"X-Assessment-Ajax": "1", "Accept": "application/json"},
            )
            assert response.status_code == 200, response.text
            result = response.json()
            assessment_id = result["assessment_id"]
            assert client.get(result["redirect_url"]).status_code == 200
            with SessionLocal() as db:
                assessment = db.get(Assessment, assessment_id)
                assert assessment is not None
                assert assessment.revenue_growth_rate == -6.5
                assert assessment.operating_flow_ratio is None
                lead = db.query(Lead).filter_by(assessment_id=assessment_id).one()
                report = db.query(Report).filter_by(assessment_id=assessment_id).one()
                summary = json.loads(report.free_summary_json)
                assert summary.get("score") == assessment.score
                assert db.query(InternalNotification).filter_by(
                    notification_type="new_lead",
                    related_type="lead",
                    related_id=lead.id,
                ).count() >= 1
        print("ASSESSMENT_SUBMIT_CHAIN_OK")
    finally:
        engine.dispose()
        if CHECK_DB.exists():
            CHECK_DB.unlink()


if __name__ == "__main__":
    run()
