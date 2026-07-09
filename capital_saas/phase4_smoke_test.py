"""Phase 4：登录权限、人工转账、报告授权、公开链接、配置和导出验收。"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from db.database import SessionLocal
from db.models import Lead, Order, Report, SystemSetting, User
from main import app
from services.auth_service import hash_password, verify_password


PAYLOAD = {
    "company_name": "上海生产验证企业有限公司",
    "contact_name": "周总",
    "phone": "13700137000",
    "wechat_id": "zhou_prod",
    "city": "上海",
    "industry": "企业服务",
    "years": "5",
    "employee_count": "35",
    "annual_revenue": "9000000",
    "net_profit": "850000",
    "monthly_cashflow": "420000",
    "debt_total": "1800000",
    "short_debt": "700000",
    "receivable_days": "58",
    "funding_need": "1500000",
    "funding_purpose": "补充经营周转",
    "has_collateral": "true",
    "tax_status": "true",
    "credit_status": "true",
    "knows_cashflow": "true",
    "has_budget": "true",
    "leverage_attitude": "适中",
    "asset_efficiency": "高",
    "fund_usage_plan": "true",
}


def login(client: TestClient, username: str, password: str):
    return client.post(
        "/login",
        data={"username": username, "password": password, "next_url": "/admin"},
        follow_redirects=False,
    )


def run():
    with TestClient(app) as client:
        unauth = client.get("/admin", follow_redirects=False)
        assert unauth.status_code == 303
        assert unauth.headers["location"].startswith("/login")

        assert login(client, "admin", "admin123").status_code == 303
        assert client.get("/admin").status_code == 200
        assert client.get("/admin/settings").status_code == 200

        with SessionLocal() as db:
            admin = db.query(User).filter(User.username == "admin").one()
            assert admin.password_hash != "admin123"
            assert verify_password("admin123", admin.password_hash)
            if not db.query(User).filter(User.username == "sales_demo").first():
                db.add(User(username="sales_demo", password_hash=hash_password("sales-pass-123"), role="sales"))
            if not db.query(User).filter(User.username == "viewer_demo").first():
                db.add(User(username="viewer_demo", password_hash=hash_password("viewer-pass-123"), role="viewer"))
            db.commit()
        saved_settings = client.post(
            "/admin/settings",
            data={
                "site_name": "生产验证融资系统",
                "company_name": "沪上银测试",
                "contact_phone": "400-000-0000",
                "contact_wechat": "hushangyin",
                "report_price_299": "333",
                "report_price_699": "699",
                "report_price_1999": "1999",
                "ai_mode": "mock",
                "openai_model": "gpt-4.1-mini",
                "payment_mode": "manual_transfer",
                "enable_registration": "false",
            },
            follow_redirects=False,
        )
        assert saved_settings.status_code == 303
        with SessionLocal() as db:
            assert db.query(SystemSetting).filter(
                SystemSetting.key == "payment_mode",
                SystemSetting.value == "manual_transfer",
            ).first()

        submit = client.post("/assessment/submit", data=PAYLOAD, follow_redirects=False)
        assert submit.status_code == 303
        assessment_id = int(submit.headers["location"].rsplit("/", 1)[-1])
        with SessionLocal() as db:
            lead = db.query(Lead).filter(Lead.assessment_id == assessment_id).one()
            lead_id = lead.id
            sales_demo = db.query(User).filter(User.username == "sales_demo").one()
            lead.assigned_sales_id = sales_demo.id
            lead.owner_user_id = sales_demo.id
            db.commit()

        checkout = client.get(f"/checkout/{assessment_id}?product=299_report")
        assert checkout.status_code == 200
        assert "333" in checkout.text
        order_redirect = client.post(
            f"/payment/mock-pay/{assessment_id}?product=299_report",
            follow_redirects=False,
        )
        assert order_redirect.status_code == 303
        with SessionLocal() as db:
            order = db.query(Order).filter(Order.assessment_id == assessment_id).order_by(Order.id.desc()).first()
            order_id = order.id
            assert order.status == "pending"
            assert order.pay_channel == "manual_transfer"
            assert order.amount == 333

        client.get("/logout")
        locked = client.get(f"/report/{assessment_id}", follow_redirects=False)
        assert locked.status_code == 303
        locked_api = client.get(f"/api/report/{assessment_id}").json()
        assert locked_api["is_unlocked"] is False
        assert locked_api["full_report"] is None

        assert login(client, "admin", "admin123").status_code == 303
        mark_paid = client.post(
            f"/admin/orders/{order_id}/mark-paid",
            data={"transaction_id": "MANUAL-TEST-001"},
            follow_redirects=False,
        )
        assert mark_paid.status_code == 303
        with SessionLocal() as db:
            paid_order = db.get(Order, order_id)
            report = db.query(Report).filter(Report.assessment_id == assessment_id).one()
            report_id = report.id
            assert paid_order.status == "paid"
            assert paid_order.transaction_id == "MANUAL-TEST-001"
            assert report.full_report_json

        token_result = client.post(
            f"/admin/reports/{report_id}/generate-token", follow_redirects=False
        )
        assert token_result.status_code == 303
        with SessionLocal() as db:
            report = db.get(Report, report_id)
            public_token = report.public_token
            assert public_token and report.token_expired_at

        for url in [
            "/admin/export/leads.csv",
            "/admin/export/orders.csv",
            "/admin/export/follow-tasks.csv",
        ]:
            response = client.get(url)
            assert response.status_code == 200
            assert response.content.startswith(b"\xef\xbb\xbf")

        client.get("/logout")
        assert client.get(f"/report/{assessment_id}").status_code == 200
        assert client.get(f"/report/{assessment_id}/print").status_code == 200
        assert client.get(f"/public/report/{public_token}").status_code == 200
        unlocked_api = client.get(f"/api/report/{assessment_id}").json()
        assert unlocked_api["is_unlocked"] is True
        assert unlocked_api["full_report"]["schema_version"] == 3

        assert login(client, "sales_demo", "sales-pass-123").status_code == 303
        assert client.get("/admin/leads").status_code == 200
        assert client.get("/admin/follow-tasks").status_code == 200
        assert client.get("/admin/reports").status_code == 200
        assert client.get("/admin/orders").status_code == 403
        assert client.get("/admin/settings").status_code == 403
        sales_update = client.post(
            f"/admin/leads/{lead_id}/update",
            data={
                "follow_status": "跟进中",
                "conversion_status": "意向中",
                "next_follow_time": "",
                "last_follow_note": "销售角色更新",
                "assigned_sales": "销售演示",
            },
            follow_redirects=False,
        )
        assert sales_update.status_code == 303

        client.get("/logout")
        assert login(client, "viewer_demo", "viewer-pass-123").status_code == 303
        assert client.get("/admin").status_code == 200
        assert client.get("/admin/orders").status_code == 200
        viewer_update = client.post(
            f"/admin/leads/{lead_id}/update",
            data={
                "follow_status": "已联系",
                "conversion_status": "意向中",
                "next_follow_time": "",
                "last_follow_note": "不应保存",
                "assigned_sales": "viewer",
            },
            follow_redirects=False,
        )
        assert viewer_update.status_code == 403
        assert client.get("/admin/export/leads.csv").status_code == 403

        client.get("/logout")
        assert client.post("/payment/webhook/wechat", content=b"test-wechat").status_code == 200
        assert client.post("/payment/webhook/alipay", content=b"test-alipay").status_code == 200
        assert client.get("/not-found-page").status_code == 404

        assert login(client, "admin", "admin123").status_code == 303
        second_order_redirect = client.post(
            f"/payment/mock-pay/{assessment_id}?product=699_bank_match",
            follow_redirects=False,
        )
        assert second_order_redirect.status_code == 303
        with SessionLocal() as db:
            second_order = db.query(Order).filter(
                Order.assessment_id == assessment_id,
                Order.product_code == "699_bank_match",
            ).order_by(Order.id.desc()).first()
            second_order_id = second_order.id
            assert second_order.status == "pending"
        assert client.post(
            f"/admin/orders/{second_order_id}/cancel", follow_redirects=False
        ).status_code == 303
        assert client.post(
            f"/admin/orders/{order_id}/refund", follow_redirects=False
        ).status_code == 303
        with SessionLocal() as db:
            assert db.get(Order, second_order_id).status == "cancelled"
            assert db.get(Order, order_id).status == "refunded"
        client.get("/logout")
        assert client.get(f"/report/{assessment_id}", follow_redirects=False).status_code == 303
        assert client.get(f"/public/report/{public_token}").status_code == 403

        for relative in [
            "Dockerfile",
            "docker-compose.yml",
            ".dockerignore",
            "gunicorn_conf.py",
            "deploy/capital-saas.conf.example",
            "deploy/capital-saas-backend.service.example",
        ]:
            assert (ROOT / relative).exists()
        print({
            "assessment_id": assessment_id,
            "order_id": order_id,
            "report_id": report_id,
            "public_token_created": bool(public_token),
            "roles_checked": ["admin", "sales", "viewer"],
        })
    print("PHASE4_PRODUCTION_READY_OK")


if __name__ == "__main__":
    run()
