"""企业资本健康体检报告分层解锁与交付质量验收。"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
TEST_DB = ROOT / "phase_capital_health_report_test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
os.environ["AI_MODE"] = "mock"
os.environ["PAYMENT_MODE"] = "mock"
if TEST_DB.exists():
    TEST_DB.unlink()
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from db.database import SessionLocal
from db.models import BankProduct, Order, Report
from main import app


PAYLOAD = {
    "company_name": "资本健康报告验收企业",
    "contact_name": "陈总",
    "phone": "13800138000",
    "wechat_id": "capital_health_test",
    "city": "上海",
    "industry": "企业服务",
    "years": "6",
    "employee_count": "42",
    "annual_revenue": "12000000",
    "net_profit": "960000",
    "monthly_cashflow": "700000",
    "debt_total": "3200000",
    "short_debt": "1800000",
    "receivable_days": "75",
    "funding_need": "2400000",
    "funding_purpose": "订单周转与高成本负债置换",
    "has_collateral": "true",
    "tax_status": "true",
    "credit_status": "true",
    "knows_cashflow": "true",
    "has_budget": "true",
    "leverage_attitude": "适中",
    "asset_efficiency": "中",
    "fund_usage_plan": "true",
}

FORBIDDEN = [
    r"\{\s*['\"]", r"\[\s*\{", r"\bmedium\b", r"\bhigh\b", r"\blow\b",
    r"\bproduct_code\b", r"\bmatch_score\b", r"\bowner\b", r"\bactions\b",
    r"\boutcome\b", r"\bNone\b", r"\bnull\b", r"\bundefined\b",
    r"填写说明", r"内部使用说明", r"定价策略", r"转化路径",
]


def _visible_text(html: str) -> str:
    html = re.sub(r"<(style|script)\b[^>]*>.*?</\1>", " ", html, flags=re.I | re.S)
    return re.sub(r"<[^>]+>", " ", html)


def _assert_customer_safe(html: str) -> None:
    text = _visible_text(html)
    for pattern in FORBIDDEN:
        assert not re.search(pattern, text, re.I), pattern


def run() -> None:
    with TestClient(app) as client:
        submitted = client.post("/assessment/submit", data=PAYLOAD, follow_redirects=False)
        assert submitted.status_code == 303
        assessment_id = int(submitted.headers["location"].rsplit("/", 1)[-1])

        with SessionLocal() as db:
            db.add(
                BankProduct(
                    product_code="MANUAL-CREDIT-001",
                    bank_name="示例商业银行",
                    bank_type="商业银行",
                    product_name="优质经营贷",
                    product_type="经营信用贷",
                    city="上海",
                    suitable_industry="企业服务",
                    min_revenue=3_000_000,
                    min_years=2,
                    max_amount=3_000_000,
                    min_amount=500_000,
                    interest_rate_range="年化3.5%—5.5%",
                    loan_term="12—36个月",
                    risk_notes="需保持征信、纳税与经营流水连续稳定。",
                    data_source="manual",
                    is_active=True,
                )
            )
            db.commit()

        free = client.get(f"/result/{assessment_id}")
        assert free.status_code == 200
        assert "企业资本健康度" in free.text
        assert "前三个核心风险" in free.text
        assert "初步优化建议" in free.text
        assert "完整企业资本健康体检报告已生成" in free.text
        assert "第二部分" not in free.text
        assert "优化处方" not in free.text
        _assert_customer_safe(free.text)

        paid_980 = client.post(
            f"/payment/mock-pay/{assessment_id}?product=980_capital_health_report",
            follow_redirects=False,
        )
        assert paid_980.status_code == 303
        report_980 = client.get(f"/report/{assessment_id}")
        assert report_980.status_code == 200
        for expected in ("企业资本健康体检报告", "第一部分", "第二部分", "第三部分", "八维雷达评分概览", "融资结构优化方案已生成"):
            assert expected in report_980.text
        assert "第四部分" not in report_980.text
        assert "资料准备清单" in report_980.text  # 锁定卡片说明权益，不泄露明细。
        _assert_customer_safe(report_980.text)

        paid_1999 = client.post(
            f"/payment/mock-pay/{assessment_id}?product=1999_structure_plan",
            follow_redirects=False,
        )
        assert paid_1999.status_code == 303
        full = client.get(f"/report/{assessment_id}")
        printable = client.get(f"/report/{assessment_id}/print")
        for page in (full, printable):
            assert page.status_code == 200
            for expected in (
                "第四部分", "第五部分", "第六部分", "第七部分",
                "征信修复方案", "优质经营贷", "资料准备清单",
                "未来30天行动计划", "未来90天行动计划",
                "未来180天行动计划", "6个月融资落地节奏",
                "预约融资顾问",
            ):
                assert expected in page.text
            _assert_customer_safe(page.text)

        with SessionLocal() as db:
            codes = {
                order.product_code
                for order in db.query(Order).filter(Order.assessment_id == assessment_id, Order.status == "paid")
            }
            assert {"980_capital_health_report", "1999_structure_plan"} <= codes
            assert db.query(Report).filter(Report.assessment_id == assessment_id).one().full_report_json

            # 历史产品兼容：299解锁主体，699解锁银行匹配，1999解锁完整方案。
            report = db.query(Report).filter(Report.assessment_id == assessment_id).one()
            report.assessment.orders.extend([
                Order(product_code="299_report", product_name="历史基础诊断报告", amount=299, status="paid"),
                Order(product_code="699_bank_match", product_name="银行匹配报告", amount=699, status="paid"),
            ])
            db.commit()

    print("CAPITAL_HEALTH_REPORT_TEST_OK")


if __name__ == "__main__":
    run()
