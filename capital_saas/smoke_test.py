"""无需启动服务器的端到端冒烟测试。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi.testclient import TestClient

from main import app


def run():
    payload = {
        "company_name": "上海示范智造有限公司",
        "contact_name": "张总",
        "phone": "13800138000",
        "wechat_id": "zhang_demo",
        "city": "上海",
        "industry": "智能制造",
        "years": "6",
        "employee_count": "48",
        "annual_revenue": "12000000",
        "net_profit": "1350000",
        "monthly_cashflow": "720000",
        "debt_total": "2800000",
        "short_debt": "900000",
        "receivable_days": "52",
        "funding_need": "2000000",
        "funding_purpose": "扩充产能与原材料采购",
        "has_collateral": "true",
        "tax_status": "true",
        "credit_status": "true",
        "knows_cashflow": "true",
        "has_budget": "true",
        "leverage_attitude": "适中",
        "asset_efficiency": "高",
        "fund_usage_plan": "true",
    }
    with TestClient(app) as client:
        login = client.post(
            "/login",
            data={"username": "admin", "password": "admin123", "next_url": "/admin"},
            follow_redirects=False,
        )
        assert login.status_code == 303
        checks = {
            "home": client.get("/").status_code,
            "form": client.get("/assessment").status_code,
            "products": client.get("/products").status_code,
            "admin_empty": client.get("/admin").status_code,
            "leads_empty": client.get("/admin/leads").status_code,
        }
        submit = client.post("/assessment/submit", data=payload, follow_redirects=False)
        checks["submit"] = submit.status_code
        assessment_id = int(submit.headers["location"].rsplit("/", 1)[-1])
        checks["free_result"] = client.get(f"/result/{assessment_id}").status_code
        checks["checkout"] = client.get(f"/checkout/{assessment_id}").status_code
        checks["checkout_699"] = client.get(
            f"/checkout/{assessment_id}?product=699_bank_match"
        ).status_code
        checks["locked_redirect"] = client.get(
            f"/report/{assessment_id}", follow_redirects=False
        ).status_code
        checks["payment"] = client.post(
            f"/payment/mock-pay/{assessment_id}", follow_redirects=False
        ).status_code
        full = client.get(f"/report/{assessment_id}")
        checks["full_report"] = full.status_code
        chapters = [
            "企业整体评分",
            "商业模式诊断",
            "财务健康体检",
            "SWOT综合研判",
            "融资策略",
            "资金投放策略",
            "贷后管理",
            "长期资本路径",
            "财商诊断",
            "行动建议",
        ]
        checks["ten_chapters"] = all(chapter in full.text for chapter in chapters)
        checks["upgrade_to_699"] = "升级银行匹配与额度预测报告 699元" in full.text
        lead_page = client.get("/admin/leads")
        checks["lead_fields"] = all(
            value in lead_page.text for value in ["张总", "13800138000", "zhang_demo", "上海"]
        )
        from db.database import SessionLocal
        from db.models import Lead
        with SessionLocal() as db:
            lead = db.query(Lead).filter(Lead.assessment_id == assessment_id).first()
            lead_id = lead.id
            checks["lead_score"] = lead.lead_score
            checks["lead_grade"] = lead.lead_grade
            checks["recommended_product"] = lead.recommended_product
        checks["lead_detail"] = client.get(f"/admin/leads/{lead_id}").status_code
        update = client.post(
            f"/admin/leads/{lead_id}/update",
            data={
                "follow_status": "跟进中",
                "conversion_status": "意向中",
                "next_follow_time": "2026-06-21T10:30",
                "last_follow_note": "客户希望先看银行匹配方案",
                "assigned_sales": "王顾问",
            },
            follow_redirects=False,
        )
        checks["lead_update"] = update.status_code
        detail_after_update = client.get(f"/admin/leads/{lead_id}")
        checks["lead_update_saved"] = all(
            value in detail_after_update.text
            for value in ["跟进中", "意向中", "王顾问", "客户希望先看银行匹配方案"]
        )
        pay_699 = client.post(
            f"/payment/mock-pay/{assessment_id}?product=699_bank_match",
            follow_redirects=False,
        )
        checks["payment_699"] = pay_699.status_code
        report_699 = client.get(f"/report/{assessment_id}")
        checks["upgrade_to_1999"] = "升级企业融资结构优化方案 1999元" in report_699.text
        checks["payment_1999"] = client.post(
            f"/payment/mock-pay/{assessment_id}?product=1999_structure_plan",
            follow_redirects=False,
        ).status_code
        report_1999 = client.get(f"/report/{assessment_id}")
        checks["consulting_cta"] = "预约1对1融资顾问服务" in report_1999.text
        paths = [
            "/admin",
            "/admin/leads",
            "/admin/reports",
            "/admin/orders",
            f"/api/assessment/{assessment_id}",
            f"/api/report/{assessment_id}",
            f"/api/order/{assessment_id}",
        ]
        for path in paths:
            checks[path] = client.get(path).status_code
        checks["score"] = client.get(f"/api/assessment/{assessment_id}").json()["score"]
        checks["unlocked"] = client.get(f"/api/report/{assessment_id}").json()[
            "is_unlocked"
        ]
        latest_order = client.get(f"/api/order/{assessment_id}").json()
        checks["latest_product_code"] = latest_order["product_code"]
        checks["latest_amount"] = latest_order["amount"]

        page_checks = [
            "home",
            "form",
            "products",
            "admin_empty",
            "leads_empty",
            "free_result",
            "checkout",
            "checkout_699",
            "full_report",
            "lead_detail",
            *paths,
        ]
        assert all(checks[key] == 200 for key in page_checks)
        assert checks["submit"] == 303
        assert checks["locked_redirect"] in {200, 303}
        assert checks["payment"] == 303
        assert checks["payment_699"] == 303
        assert checks["payment_1999"] == 303
        assert checks["lead_update"] == 303
        assert checks["ten_chapters"] is True
        assert checks["unlocked"] is True
        assert checks["lead_fields"] is True
        assert checks["lead_update_saved"] is True
        assert checks["upgrade_to_699"] is True
        assert checks["upgrade_to_1999"] is True
        assert checks["consulting_cta"] is True
        assert checks["latest_product_code"] == "1999_structure_plan"
        assert checks["latest_amount"] == 1999
        print(checks)
        print("END_TO_END_OK")


if __name__ == "__main__":
    run()
