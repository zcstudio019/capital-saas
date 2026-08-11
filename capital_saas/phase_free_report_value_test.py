"""免费企业资本健康摘要的价值与付费边界专项验收。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEST_DB = ROOT / "phase_free_report_value_test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
os.environ["AI_MODE"] = "mock"
if TEST_DB.exists():
    TEST_DB.unlink()
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from main import app

DIMENSIONS = ["企业基本面", "征信状况", "流水质量", "负债情况", "司法风险", "税务合规", "资产状况", "融资能力"]


def run() -> None:
    data = {
        "company_name": "上海免费报告价值有限公司", "contact_name": "李总", "phone": "13800138011",
        "industry": "批发零售", "years": "4.5", "annual_revenue": "9000000",
        "net_profit_margin": "6.8", "monthly_cashflow": "450000", "debt_total": "3200000",
        "short_debt": "2400000", "receivable_days": "75", "funding_need": "1800000",
        "funding_purposes": "采购原材料", "collateral_types": "暂无抵押物",
        "enterprise_credit_status": "no_overdue", "legal_credit_status": "no_overdue",
        "credit_query_count_6m": "8", "operating_flow_ratio": "55",
        "public_private_ratio": "32", "internal_transfer_ratio": "18", "revenue_growth_rate": "-8",
    }
    with TestClient(app) as client:
        response = client.post("/assessment/submit", data=data, follow_redirects=False)
        assert response.status_code == 303
        assessment_id = int(response.headers["location"].rsplit("/", 1)[-1])
        page = client.get(f"/result/{assessment_id}")
        assert page.status_code == 200
        required = [
            "企业资本健康摘要", "综合评分", "综合评级", "风险等级", "八维评分完整展示",
            "3个主要优势", "3个核心风险", "3条基础建议", "融资路径初判",
            "完整企业资本健康体检报告", "融资结构优化方案", "我的报告",
        ] + DIMENSIONS
        assert all(text in page.text for text in required)
        assert page.text.count('class="free-dimension-card"') == 8
        assert page.text.count("<li>") >= 11
        forbidden = [
            "dimension-check-table", "bank-product-card", "action-stage-card",
            "report-remediation", "查看产品详情", "未来30天行动计划正文",
        ]
        assert not any(text in page.text for text in forbidden)
        assert "真实银行产品匹配" in page.text  # 仅权益目录可以出现
        assert "本层仅展示权益目录" in page.text
        assert "待补充资料后评估" in page.text or "初步融资空间参考" in page.text

    print("FREE_REPORT_VALUE_OK")


if __name__ == "__main__":
    run()
