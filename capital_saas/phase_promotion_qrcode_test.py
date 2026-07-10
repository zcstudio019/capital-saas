import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi.testclient import TestClient

from core.config import BASE_DIR
from db.database import SessionLocal
from db.models import CustomerAccount, Event, FollowTask, InternalNotification, Lead, PromotionQRCode, Report, User
from main import app
from services.auth_service import hash_password


def _payload(company_name: str):
    return {
        "company_name": company_name, "contact_name": "二维码测试联系人", "phone": "13900000001",
        "wechat_id": "qr_test", "city": "上海", "industry": "制造业", "years": "5",
        "employee_count": "50", "annual_revenue": "10000000", "net_profit": "1000000",
        "monthly_cashflow": "500000", "debt_total": "1000000", "short_debt": "300000",
        "receivable_days": "45", "funding_need": "2000000", "funding_purpose": "经营周转",
        "has_collateral": "true", "tax_status": "true", "credit_status": "true",
        "knows_cashflow": "true", "has_budget": "true", "leverage_attitude": "适中",
        "asset_efficiency": "高", "fund_usage_plan": "true",
    }


def run():
    suffix = uuid4().hex[:10]
    sales_username = f"qr_sales_{suffix}"
    company_name = f"二维码归因测试企业-{suffix}"
    qrcode_id = None
    lead_id = None
    assessment_id = None
    sales_id = None
    image_file = None
    with TestClient(app) as client:
        try:
            with SessionLocal() as db:
                sales = User(username=sales_username, password_hash=hash_password("SalesPass123"), display_name="二维码测试销售", role="sales", is_active=True)
                db.add(sales)
                db.commit()
                sales_id = sales.id

            login = client.post("/login", data={"username": "admin", "password": "admin123", "next_url": "/admin/qrcodes"}, follow_redirects=False)
            assert login.status_code == 303
            created = client.post(
                "/admin/qrcodes",
                data={
                    "name": f"销售二维码-{suffix}", "landing_key": "rongzi", "channel": "qr",
                    "source": "sales_qr", "campaign": "二维码回归", "sales_id": str(sales_id),
                },
                follow_redirects=False,
            )
            assert created.status_code == 303

            with SessionLocal() as db:
                record = db.query(PromotionQRCode).filter(PromotionQRCode.name == f"销售二维码-{suffix}").one()
                qrcode_id = record.id
                assert record.full_url.startswith("https://capital.linhongtech.com/lp/rongzi?")
                assert f"sales_id={sales_id}" in record.full_url
                assert f"qr_id={record.id}" in record.full_url
                image_file = BASE_DIR / "static" / "uploads" / "qrcodes" / Path(record.qr_image_path).name
                assert image_file.is_file()

            page = client.get("/admin/qrcodes")
            assert page.status_code == 200
            assert f"销售二维码-{suffix}" in page.text
            preview = client.get(f"/admin/qrcodes/{qrcode_id}/image")
            assert preview.status_code == 200
            assert preview.headers["content-type"].startswith("image/png")
            assert preview.content.startswith(b"\x89PNG")

            landing = client.get(f"/lp/rongzi?channel=qr&source=sales_qr&campaign=%E4%BA%8C%E7%BB%B4%E7%A0%81%E5%9B%9E%E5%BD%92&sales_id={sales_id}&qr_id={qrcode_id}")
            assert landing.status_code == 200
            assert f"sales_id={sales_id}" in landing.text
            submitted = client.post("/assessment/submit", data=_payload(company_name), follow_redirects=False)
            assert submitted.status_code == 303
            assessment_id = int(submitted.headers["location"].rsplit("/", 1)[-1])

            with SessionLocal() as db:
                lead = db.query(Lead).filter(Lead.assessment_id == assessment_id).one()
                lead_id = lead.id
                assert lead.assigned_sales_id == sales_id
                assert lead.owner_user_id == sales_id
                assert lead.source_channel == "qr"
                assert lead.source_keyword == "sales_qr"
                assert lead.source_campaign == "二维码回归"
                assert db.query(Event).filter(Event.lead_id == lead.id, Event.event_type == "qr_lead_created").count() == 1
                assert db.query(InternalNotification).filter(InternalNotification.user_id == sales_id, InternalNotification.notification_type == "qr_lead").count() == 1

            client.get("/logout")
            sales_login = client.post("/login", data={"username": sales_username, "password": "SalesPass123", "next_url": "/admin/qrcodes"}, follow_redirects=False)
            assert sales_login.status_code == 303
            sales_page = client.get("/admin/qrcodes")
            assert sales_page.status_code == 200
            assert f"销售二维码-{suffix}" in sales_page.text
        finally:
            with SessionLocal() as db:
                if lead_id:
                    db.query(InternalNotification).filter(InternalNotification.related_type == "lead", InternalNotification.related_id == lead_id).delete(synchronize_session=False)
                    db.query(Event).filter(Event.lead_id == lead_id).delete(synchronize_session=False)
                    db.query(FollowTask).filter(FollowTask.lead_id == lead_id).delete(synchronize_session=False)
                    db.query(CustomerAccount).filter(CustomerAccount.lead_id == lead_id).delete(synchronize_session=False)
                    db.query(Lead).filter(Lead.id == lead_id).delete(synchronize_session=False)
                if assessment_id:
                    db.query(Report).filter(Report.assessment_id == assessment_id).delete(synchronize_session=False)
                    from db.models import Assessment
                    db.query(Assessment).filter(Assessment.id == assessment_id).delete(synchronize_session=False)
                if qrcode_id:
                    db.query(PromotionQRCode).filter(PromotionQRCode.id == qrcode_id).delete(synchronize_session=False)
                if sales_id:
                    db.query(User).filter(User.id == sales_id).delete(synchronize_session=False)
                db.commit()
            if image_file and image_file.exists():
                image_file.unlink()

    print("PROMOTION_QRCODE_TEST_OK")


if __name__ == "__main__":
    run()
