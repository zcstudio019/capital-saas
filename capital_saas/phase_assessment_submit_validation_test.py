"""企业资本健康测评提交数值校验专项验收。"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
TEST_DB = ROOT / "phase_assessment_submit_validation_test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
os.environ["AI_MODE"] = "mock"
if TEST_DB.exists():
    TEST_DB.unlink()
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from db.database import SessionLocal
from db.models import Assessment, Event, InternalNotification, Lead, Report
from main import app


BASE_PAYLOAD = {
    "company_name": "上海测评提交校验有限公司",
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

OPTIONAL_NUMERIC_FIELDS = (
    "registered_capital",
    "employee_count",
    "monthly_cashflow",
    "receivable_days",
    "credit_card_usage_rate",
    "lender_count",
    "public_inflow_monthly",
    "public_outflow_monthly",
    "operating_flow_ratio",
    "public_private_ratio",
    "internal_transfer_ratio",
    "tax_paid_12m",
    "invoiced_revenue_12m",
    "revenue_growth_rate",
    "property_value",
    "factory_value",
    "land_value",
    "vehicle_value",
    "equipment_value",
    "financeable_receivables",
    "inventory_value",
    "external_investment_value",
)


def _ajax_headers() -> dict[str, str]:
    return {"X-Assessment-Ajax": "1", "Accept": "application/json"}


def run() -> None:
    with TestClient(app) as client:
        blank_payload = {**BASE_PAYLOAD, "company_name": "上海空值表单验证有限公司"}
        blank_payload.update({name: "" for name in OPTIONAL_NUMERIC_FIELDS})
        blank_response = client.post(
            "/assessment/submit", data=blank_payload, follow_redirects=False
        )
        assert blank_response.status_code == 303
        blank_id = int(blank_response.headers["location"].rsplit("/", 1)[-1])
        with SessionLocal() as db:
            blank = db.get(Assessment, blank_id)
            assert blank is not None
            assert blank.operating_flow_ratio is None
            assert blank.public_private_ratio is None
            assert blank.internal_transfer_ratio is None
            assert blank.revenue_growth_rate is None

        null_payload = {**BASE_PAYLOAD, "company_name": "上海空值接口验证有限公司"}
        null_payload.update({
            "operating_flow_ratio": None,
            "public_private_ratio": None,
            "internal_transfer_ratio": None,
            "revenue_growth_rate": None,
        })
        null_response = client.post(
            "/assessment/submit", json=null_payload, headers=_ajax_headers()
        )
        assert null_response.status_code == 200
        assert null_response.json()["ok"] is True

        valid_payload = {
            **BASE_PAYLOAD,
            "company_name": "上海合法比例验证有限公司",
            "operating_flow_ratio": "70",
            "public_private_ratio": "15.5",
            "internal_transfer_ratio": "8",
            "revenue_growth_rate": "-10",
        }
        valid_response = client.post(
            "/assessment/submit", data=valid_payload, headers=_ajax_headers()
        )
        assert valid_response.status_code == 200
        valid_id = valid_response.json()["assessment_id"]
        with SessionLocal() as db:
            item = db.get(Assessment, valid_id)
            assert item is not None
            assert item.operating_flow_ratio == 70
            assert item.public_private_ratio == 15.5
            assert item.internal_transfer_ratio == 8
            assert item.revenue_growth_rate == -10

        invalid_payload = {
            **BASE_PAYLOAD,
            "company_name": "上海非法比例验证有限公司",
            "operating_flow_ratio": "abc",
        }
        invalid_response = client.post(
            "/assessment/submit", data=invalid_payload, headers=_ajax_headers()
        )
        assert invalid_response.status_code == 422
        invalid_body = invalid_response.json()
        assert invalid_body["errors"]["operating_flow_ratio"] == "经营性流水占比请输入数字"
        serialized = json.dumps(invalid_body, ensure_ascii=False)
        assert "float_parsing" not in serialized
        assert "Input should be a valid number" not in serialized
        direct_invalid_response = client.post("/assessment/submit", data=invalid_payload)
        assert direct_invalid_response.status_code == 422
        assert "text/html" in direct_invalid_response.headers["content-type"]
        assert "部分数值填写格式不正确，请检查标红字段" in direct_invalid_response.text
        assert "data-assessment-server-state" in direct_invalid_response.text
        assert "company_name" in direct_invalid_response.text
        assert "float_parsing" not in direct_invalid_response.text

        chain_payload = {
            **BASE_PAYLOAD,
            "company_name": "上海完整链路验证有限公司",
            "phone": "13900139000",
        }
        chain_response = client.post(
            "/assessment/submit", data=chain_payload, headers=_ajax_headers()
        )
        assert chain_response.status_code == 200
        chain_data = chain_response.json()
        assessment_id = chain_data["assessment_id"]
        assert chain_data["redirect_url"] == f"/result/{assessment_id}"
        assert client.get(chain_data["redirect_url"]).status_code == 200
        with SessionLocal() as db:
            assessment = db.get(Assessment, assessment_id)
            assert assessment is not None and assessment.score is not None
            lead = db.query(Lead).filter_by(assessment_id=assessment_id).one()
            report = db.query(Report).filter_by(assessment_id=assessment_id).one()
            assert json.loads(report.free_summary_json)["score"] == assessment.score
            assert db.query(Event).filter_by(
                assessment_id=assessment_id, event_type="assessment_submitted"
            ).count() == 1
            assert db.query(InternalNotification).filter_by(
                notification_type="new_lead", related_type="lead", related_id=lead.id
            ).count() >= 1

    print("ASSESSMENT_SUBMIT_VALIDATION_OK")


if __name__ == "__main__":
    run()
