"""End-to-end regression test for business-facing customer journey rendering."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
TEST_DB = ROOT / "phase_journey_display_test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
os.environ["AI_MODE"] = "mock"
if TEST_DB.exists():
    TEST_DB.unlink()
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from db.database import SessionLocal
from db.models import Event, Lead, Order
from main import app
from scripts.check_journey_display import find_journey_display_issues


PAYLOAD = {
    "company_name": "客户旅程验收企业", "contact_name": "李经理", "phone": "13800138000",
    "wechat_id": "journey_display", "city": "上海", "industry": "供应链服务",
    "years": "3", "employee_count": "22", "annual_revenue": "6000000", "net_profit": "280000",
    "monthly_cashflow": "120000", "debt_total": "2500000", "short_debt": "1900000",
    "receivable_days": "105", "funding_need": "1800000", "funding_purpose": "补充订单周转",
    "has_collateral": "false", "tax_status": "true", "credit_status": "true",
    "knows_cashflow": "true", "has_budget": "false", "leverage_attitude": "适中",
    "asset_efficiency": "中", "fund_usage_plan": "true",
}


def run() -> None:
    with TestClient(app) as client:
        assert client.post("/login", data={"username": "admin", "password": "admin123"}, follow_redirects=False).status_code == 303
        submitted = client.post("/assessment/submit", data=PAYLOAD, follow_redirects=False)
        assessment_id = int(submitted.headers["location"].rsplit("/", 1)[-1])
        assert client.post(f"/payment/mock-pay/{assessment_id}", follow_redirects=False).status_code == 303
        with SessionLocal() as db:
            lead = db.query(Lead).filter(Lead.assessment_id == assessment_id).one()
            lead_id = lead.id
            order = db.query(Order).filter(Order.assessment_id == assessment_id).first()
            db.add_all([
                Event(assessment_id=assessment_id, lead_id=lead.id, event_type="customer_journey_viewed", event_data_json=json.dumps({"user_id": 1}, ensure_ascii=False)),
                Event(assessment_id=assessment_id, lead_id=lead.id, event_type="payment_success", event_data_json=json.dumps({"order_id": order.id, "product_code": "299_report", "amount": 299.0, "channel": "mock", "operator": "mock"}, ensure_ascii=False)),
                Event(assessment_id=assessment_id, lead_id=lead.id, event_type="notification_job_created", event_data_json=json.dumps({"job_id": 47, "template_key": "upgrade_recommend_customer", "channel": "in_app"}, ensure_ascii=False)),
                Event(assessment_id=assessment_id, lead_id=lead.id, event_type="sales_next_action", event_data_json=json.dumps({"next_action": "升级699银行匹配报告", "operator": "admin"}, ensure_ascii=False)),
            ])
            db.commit()

        page = client.get(f"/admin/leads/{lead_id}/journey")
        assert page.status_code == 200
        assert not find_journey_display_issues(page.text)
        for expected in ["支付成功", "基础诊断报告", "模拟支付", "通知任务已创建", "升级推荐客户通知", "站内通知", "销售建议已生成", "系统管理员"]:
            assert expected in page.text
        assert not re.search(r"\d{2}:\d{2}:\d{2}\.\d+", page.text)

    print("JOURNEY_DISPLAY_TEST_OK")


if __name__ == "__main__":
    run()
