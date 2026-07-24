"""商业级资本健康报告视觉交付与权限分层验收。"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEST_DB = ROOT / "phase_report_visual_delivery_test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
os.environ["AI_MODE"] = "mock"
os.environ["PAYMENT_MODE"] = "mock"
if TEST_DB.exists():
    TEST_DB.unlink()
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from db.database import SessionLocal
from db.models import BankProduct, Report
from main import app

PAYLOAD = {
    "company_name": "上海远航企业管理有限公司",
    "contact_name": "陈先生",
    "phone": "13800138000",
    "wechat_id": "visual_delivery",
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


def visible_text(html: str) -> str:
    html = re.sub(r"<(style|script)\b[^>]*>.*?</\1>", " ", html, flags=re.I | re.S)
    return re.sub(r"<[^>]+>", " ", html)


def assert_delivery_safe(html: str) -> None:
    text = visible_text(html)
    forbidden = [
        r"\{\s*['\"]", r"\[\s*\{", r"\bproduct_code\b", r"\bmatch_score\b",
        r"\bNone\b", r"\bnull\b", r"\bundefined\b", "填写说明", "内部使用说明",
        "定价策略", "转化路径", "模拟银行", "测试企业",
    ]
    for pattern in forbidden:
        assert not re.search(pattern, text, re.I), pattern


def run() -> None:
    with TestClient(app) as client:
        submitted = client.post("/assessment/submit", data=PAYLOAD, follow_redirects=False)
        assert submitted.status_code == 303
        assessment_id = int(submitted.headers["location"].rsplit("/", 1)[-1])
        with SessionLocal() as db:
            db.add(BankProduct(
                product_code="HSY-MANUAL-001",
                bank_name="浦发银行",
                bank_type="股份制商业银行",
                product_name="经营周转贷",
                product_type="经营信用贷",
                city="上海",
                suitable_industry="企业服务",
                min_revenue=3_000_000,
                min_years=2,
                min_amount=500_000,
                max_amount=3_000_000,
                interest_rate_range="年化3.5%—5.5%",
                loan_term="12—36个月",
                data_source="manual",
                is_active=True,
            ))
            db.commit()

        free = client.get(f"/result/{assessment_id}")
        assert free.status_code == 200
        assert "score-ring" in free.text and "核心发现" in free.text
        assert "检查项目" not in free.text
        assert "完整企业资本健康体检报告已生成" in free.text
        assert_delivery_safe(free.text)

        assert client.post(
            f"/payment/mock-pay/{assessment_id}?product=980_capital_health_report",
            follow_redirects=False,
        ).status_code == 303
        report_980 = client.get(f"/report/{assessment_id}")
        assert report_980.status_code == 200
        for expected in ("report-cover", "报告目录", "八维资本健康评分", "分项检查报告", "风险预警与异常项汇总"):
            assert expected in report_980.text
        assert "诊断已经明确，下一步需要把问题转化为执行方案" in report_980.text
        assert "真实银行产品匹配</h3>" not in report_980.text
        assert "capital_health_report.css" in report_980.text
        assert_delivery_safe(report_980.text)

        assert client.post(
            f"/payment/mock-pay/{assessment_id}?product=1999_structure_plan",
            follow_redirects=False,
        ).status_code == 303
        pending = client.get(f"/report/{assessment_id}")
        assert pending.status_code == 202
        assert "融资顾问复核" in pending.text
        with SessionLocal() as db:
            report = db.query(Report).filter(Report.assessment_id == assessment_id).one()
            report.review_status = "approved"
            db.commit()

        full = client.get(f"/report/{assessment_id}")
        printable = client.get(f"/report/{assessment_id}/print")
        for page in (full, printable):
            assert page.status_code == 200
            for expected in ("优化处方", "真实银行产品匹配", "经营周转贷", "融资资料准备清单", "6个月融资落地节奏", "预约1对1融资顾问服务"):
                assert expected in page.text
            assert "action-timeline" in page.text
            assert "capital_health_report.css" in page.text
            assert_delivery_safe(page.text)
        css = (ROOT / "static/css/capital_health_report.css").read_text(encoding="utf-8")
        assert "@media print" in css and "@page" in css
    print("REPORT_VISUAL_DELIVERY_OK")


if __name__ == "__main__":
    run()
