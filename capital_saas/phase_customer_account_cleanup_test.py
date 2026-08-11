"""Customer account soft deletion, cleanup, recovery and retention checks."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEST_DB = ROOT / "phase_customer_account_cleanup_test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
os.environ["AI_MODE"] = "mock"
os.environ["APP_ENV"] = "development"
if TEST_DB.exists():
    TEST_DB.unlink()
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from db.database import SessionLocal
from db.models import AuditLog, CustomerAccount, Order, Report, User
from main import app
from services.auth_service import hash_password


def payload(phone: str, company: str) -> dict[str, str]:
    return {
        "company_name": company,
        "contact_name": "清理测试客户",
        "phone": phone,
        "industry": "制造业",
        "years": "6",
        "employee_count": "20",
        "annual_revenue": "12000000",
        "net_profit_margin": "8.5",
        "debt_total": "1600000",
        "short_debt": "500000",
        "funding_need": "2500000",
        "funding_purposes": "补充流动资金",
        "collateral_types": "有设备",
        "enterprise_credit_status": "no_overdue",
        "legal_credit_status": "no_overdue",
        "credit_query_count_6m": "3",
    }


def register_payload(phone: str) -> dict[str, str]:
    return {
        "phone": phone,
        "contact_name": "恢复注册客户",
        "password": "Cleanup123",
        "confirm_password": "Cleanup123",
        "company_name": "",
        "wechat_id": "",
        "city": "上海",
        "agree_legal": "1",
        "registration_method": "password",
        "next_url": "/client/dashboard",
    }


def admin_login(client: TestClient, username: str = "admin", password: str = "admin123") -> None:
    response = client.post(
        "/admin/login",
        data={"username": username, "password": password, "next_url": "/admin/customers"},
        follow_redirects=False,
    )
    assert response.status_code == 303


def run() -> None:
    business_phone = "13800138901"
    empty_phone = "13800138902"
    reuse_phone = "13800138903"
    with TestClient(app) as client:
        submitted = client.post(
            "/assessment/submit", data=payload(business_phone, "历史业务企业"),
            follow_redirects=False,
        )
        assert submitted.status_code == 303
        assessment_id = int(submitted.headers["location"].rsplit("/", 1)[-1])

        with SessionLocal() as db:
            admin = db.query(User).filter_by(username="admin").one()
            admin.role = "super_admin"
            sales = User(
                username="cleanup_sales",
                password_hash=hash_password("Sales12345"),
                display_name="清理权限销售",
                role="sales",
                is_active=True,
            )
            db.add(sales)
            business = db.query(CustomerAccount).filter_by(login_phone=business_phone).one()
            business.registration_source = "historical_data"
            business_id = business.id
            report = db.query(Report).filter_by(assessment_id=assessment_id).one()
            report_id = report.id
            db.add(Order(
                assessment_id=assessment_id,
                customer_id=business.id,
                product_code="980_capital_health_report",
                product_name="企业资本健康体检报告",
                amount=980,
                status="paid",
            ))
            empty = CustomerAccount(
                lead_id=None,
                assessment_id=None,
                company_name="",
                name="历史空账号",
                contact_name="历史空账号",
                phone=empty_phone,
                login_phone=empty_phone,
                password_hash="",
                registration_source="historical_data",
                status="pending_activation",
                is_active=True,
            )
            reuse = CustomerAccount(
                lead_id=None,
                assessment_id=None,
                company_name="曾删除账号",
                name="曾删除客户",
                contact_name="曾删除客户",
                phone=reuse_phone,
                login_phone=reuse_phone,
                password_hash=hash_password("OldPassword1"),
                registration_source="self_registration",
                status="active",
                is_active=True,
            )
            db.add_all([empty, reuse])
            db.commit()
            empty_id, reuse_id = empty.id, reuse.id

        admin_login(client)
        listing = client.get("/admin/customers")
        assert listing.status_code == 200
        assert "删除账号" in listing.text and "清理历史未激活账号" in listing.text

        confirm_page = client.get(f"/admin/customers/{business_id}/delete")
        assert confirm_page.status_code == 200
        assert "确认删除客户账号" in confirm_page.text and "DELETE" in confirm_page.text
        bad_delete = client.post(
            f"/admin/customers/{business_id}/delete",
            data={"confirmation": "WRONG", "delete_reason": "测试"},
        )
        assert bad_delete.status_code == 400
        deleted = client.post(
            f"/admin/customers/{business_id}/delete",
            data={"confirmation": "DELETE", "delete_reason": "清理历史登录身份"},
            follow_redirects=False,
        )
        assert deleted.status_code == 303
        with SessionLocal() as db:
            business = db.get(CustomerAccount, business_id)
            assert business.deleted_at and not business.is_active and business.status == "deleted"
            assert db.query(Report).filter_by(id=report_id, customer_id=business_id).count() == 1
            assert db.query(Order).filter_by(customer_id=business_id).count() == 1
            audit = db.query(AuditLog).filter_by(
                action="customer_account_deleted", target_id=business_id,
            ).one()
            audit_data = json.loads(audit.after_json)
            assert audit_data["reason"] == "清理历史登录身份"
            assert business_phone not in audit.after_json

        customer_login = client.post(
            "/client/login",
            data={"phone": business_phone, "password": "any-password", "next_url": "/client/dashboard"},
        )
        assert customer_login.status_code == 400
        assert client.get(f"/admin/reports/{report_id}/preview").status_code == 200

        restored = client.post(
            f"/admin/customers/{business_id}/restore",
            data={"restore_reason": "验收恢复"},
            follow_redirects=False,
        )
        assert restored.status_code == 303
        with SessionLocal() as db:
            business = db.get(CustomerAccount, business_id)
            assert business.deleted_at is None and business.is_active
            assert business.status == "pending_activation"

        cleanup = client.get("/admin/customers/cleanup")
        assert cleanup.status_code == 200
        assert "符合条件账号" in cleanup.text and business_phone in cleanup.text and empty_phone in cleanup.text
        cleaned = client.post(
            "/admin/customers/cleanup",
            data={
                "cleanup_scope": "all",
                "confirmation": "CONFIRM CLEANUP",
                "delete_reason": "专项测试批量清理",
            },
            follow_redirects=False,
        )
        assert cleaned.status_code == 303
        with SessionLocal() as db:
            assert db.get(CustomerAccount, business_id).deleted_at
            assert db.get(CustomerAccount, empty_id).deleted_at
            assert db.query(Report).filter_by(id=report_id, customer_id=business_id).count() == 1
            assert db.query(Order).filter_by(customer_id=business_id).count() == 1
            assert db.query(AuditLog).filter_by(action="customer_accounts_bulk_cleaned").count() == 1

        blocked_permanent = client.post(
            f"/admin/customers/{business_id}/permanent-delete",
            data={"confirmation": "PERMANENT DELETE", "delete_reason": "不应成功"},
        )
        assert blocked_permanent.status_code == 409
        permanent = client.post(
            f"/admin/customers/{empty_id}/permanent-delete",
            data={"confirmation": "PERMANENT DELETE", "delete_reason": "永久清理空账号"},
            follow_redirects=False,
        )
        assert permanent.status_code == 303
        with SessionLocal() as db:
            assert db.get(CustomerAccount, empty_id) is None
            assert db.query(AuditLog).filter_by(
                action="customer_account_permanently_deleted", target_id=empty_id,
            ).count() == 1

        # A deleted phone is restored in place, preserving the historical customer id.
        client.post(
            f"/admin/customers/{reuse_id}/delete",
            data={"confirmation": "DELETE", "delete_reason": "测试重新注册复用"},
            follow_redirects=False,
        )
        client.get("/logout")
        reregistered = client.post(
            "/client/register", data=register_payload(reuse_phone), follow_redirects=False,
        )
        assert reregistered.status_code == 303
        with SessionLocal() as db:
            reused = db.query(CustomerAccount).filter_by(login_phone=reuse_phone).one()
            assert reused.id == reuse_id and reused.deleted_at is None and reused.is_active

        client.get("/client/logout")
        admin_login(client, "cleanup_sales", "Sales12345")
        forbidden = client.post(
            f"/admin/customers/{reuse_id}/delete",
            data={"confirmation": "DELETE", "delete_reason": "越权尝试"},
        )
        assert forbidden.status_code == 403

    print("CUSTOMER_ACCOUNT_CLEANUP_OK")


if __name__ == "__main__":
    run()
