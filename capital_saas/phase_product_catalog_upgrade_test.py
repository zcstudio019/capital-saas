"""公开产品目录、隐藏产品定向链接与统一升级抵扣验收。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEST_DB = ROOT / "phase_product_catalog_upgrade_test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
os.environ["AI_MODE"] = "mock"
os.environ["PAYMENT_MODE"] = "mock"
if TEST_DB.exists():
    TEST_DB.unlink()
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from db.database import SessionLocal
from db.models import Assessment, Order, User
from main import app
from services.auth_service import hash_password
from services.payment_service import refund_order
from services.settings_service import save_settings
from services.upgrade_pricing_service import calculate_upgrade_amount


PAYLOAD = {
    "company_name": "上海产品体系验证有限公司",
    "contact_name": "陈经理",
    "phone": "13800138000",
    "wechat_id": "product_catalog_test",
    "city": "上海",
    "industry": "企业服务",
    "years": "5",
    "employee_count": "30",
    "annual_revenue": "8000000",
    "net_profit": "600000",
    "monthly_cashflow": "500000",
    "debt_total": "2000000",
    "short_debt": "1000000",
    "receivable_days": "60",
    "funding_need": "1500000",
    "funding_purpose": "经营周转",
    "has_collateral": "false",
    "tax_status": "true",
    "credit_status": "true",
    "knows_cashflow": "true",
    "has_budget": "true",
    "leverage_attitude": "适中",
    "asset_efficiency": "中",
    "fund_usage_plan": "true",
}


def submit(client: TestClient, suffix: str = "") -> int:
    payload = {
        **PAYLOAD,
        "company_name": f"上海产品体系验证{suffix}有限公司",
        "phone": f"1380013{8000 + len(suffix):04d}",
        "wechat_id": f"product_catalog_{suffix or 'main'}",
    }
    response = client.post("/assessment/submit", data=payload, follow_redirects=False)
    assert response.status_code == 303
    return int(response.headers["location"].rsplit("/", 1)[-1])


def login(client: TestClient, username: str, password: str) -> None:
    response = client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    assert response.status_code == 303


def run() -> None:
    with TestClient(app) as client, TestClient(app) as backend:
        catalog = client.get("/products")
        assert catalog.status_code == 200
        public_names = [
            "免费测评",
            "企业资本健康体检报告",
            "融资结构优化方案",
            "1对1融资顾问服务",
        ]
        positions = [catalog.text.index(name) for name in public_names]
        assert positions == sorted(positions)
        assert "企业资本健康简版报告" not in catalog.text
        assert "银行产品专项匹配报告" not in catalog.text

        assessment_id = submit(client, "主")
        assert client.post(
            f"/payment/mock-pay/{assessment_id}?product=299_report",
            follow_redirects=False,
        ).status_code == 303
        with SessionLocal() as db:
            assert calculate_upgrade_amount(None, "980_capital_health_report", db, assessment_id) == 681
            assert calculate_upgrade_amount(None, "1999_structure_plan", db, assessment_id) == 1700
        checkout_980 = client.get(f"/checkout/{assessment_id}?product=980_capital_health_report")
        assert "¥681" in checkout_980.text
        assert client.get(f"/report/{assessment_id}").status_code == 200

        assert client.post(
            f"/payment/mock-pay/{assessment_id}?product=699_bank_match",
            follow_redirects=False,
        ).status_code == 303
        with SessionLocal() as db:
            assert calculate_upgrade_amount(None, "1999_structure_plan", db, assessment_id) == 1300
        assert "¥1300" in client.get(f"/checkout/{assessment_id}?product=1999_structure_plan").text

        second_id = submit(client, "退款")
        assert client.post(
            f"/payment/mock-pay/{second_id}?product=980_capital_health_report",
            follow_redirects=False,
        ).status_code == 303
        with SessionLocal() as db:
            assert calculate_upgrade_amount(None, "1999_structure_plan", db, second_id) == 1019
            order = db.query(Order).filter(
                Order.assessment_id == second_id,
                Order.product_code == "980_capital_health_report",
            ).one()
            refund_order(db, order, "test")
            assert calculate_upgrade_amount(None, "1999_structure_plan", db, second_id) == 1999

        login(backend, "admin", "admin123")
        management = backend.get("/admin/products")
        assert management.status_code == 200
        for text in ("是否公开", "是否启用", "产品类型", "可抵扣目标产品", "抵扣金额规则"):
            assert text in management.text
        generated = backend.post(
            f"/admin/products/699_bank_match/purchase-link",
            data={"assessment_id": assessment_id},
            follow_redirects=False,
        )
        assert generated.status_code == 303 and "product%3D699_bank_match" in generated.headers["location"]

        toggled = backend.post(
            "/admin/products/299_report/save",
            data={"is_public": "true", "is_active": "true", "product_type": "hidden_offer"},
            follow_redirects=False,
        )
        assert toggled.status_code == 303
        assert "企业资本健康简版报告" in client.get("/products").text
        with SessionLocal() as db:
            save_settings(db, {"product_299_report_is_public": "false"})

            assessment = db.get(Assessment, assessment_id)
            sales = User(
                username="catalog_sales",
                password_hash=hash_password("Sales123!"),
                role="sales",
                is_active=True,
                force_password_change=False,
            )
            db.add(sales)
            db.flush()
            assessment.lead.assigned_sales_id = sales.id
            db.commit()

        with TestClient(app) as sales_client:
            login(sales_client, "catalog_sales", "Sales123!")
            sales_link = sales_client.post(
                "/admin/products/299_report/purchase-link",
                data={"assessment_id": assessment_id},
                follow_redirects=False,
            )
            assert sales_link.status_code == 303 and "product%3D299_report" in sales_link.headers["location"]

    print("PRODUCT_CATALOG_UPGRADE_OK")


if __name__ == "__main__":
    run()
