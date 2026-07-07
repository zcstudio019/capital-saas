"""Phase 5：渠道、落地页、A/B、工作台、时间线、话术、标签、增长和备份验收。"""

import io
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from db.database import SessionLocal
from db.models import (
    ABAssignment, Event, Lead, LeadFollowLog, LeadTag, Order,
    SalesScriptTemplate, Tag, User,
)
from main import app
from services.auth_service import hash_password


PAYLOAD = {
    "company_name": "Phase5渠道测试企业有限公司", "contact_name": "增长总",
    "phone": "13600136000", "wechat_id": "growth_test", "city": "上海",
    "industry": "企业服务", "years": "4", "employee_count": "28",
    "annual_revenue": "7000000", "net_profit": "560000",
    "monthly_cashflow": "240000", "debt_total": "2200000",
    "short_debt": "1400000", "receivable_days": "92",
    "funding_need": "2500000", "funding_purpose": "订单周转和债务置换",
    "has_collateral": "true", "tax_status": "true", "credit_status": "true",
    "knows_cashflow": "true", "has_budget": "false",
    "leverage_attitude": "适中", "asset_efficiency": "中",
    "fund_usage_plan": "true",
}


def login(client, username="admin", password="admin123"):
    return client.post(
        "/login", data={"username": username, "password": password, "next_url": "/admin"},
        follow_redirects=False,
    )


def run():
    with TestClient(app) as client:
        for page in ["rongzi", "cashflow", "bank", "boss"]:
            response = client.get(
                f"/lp/{page}?utm_source=douyin&utm_medium=cpc"
                f"&utm_campaign=rongzi_test&channel=douyin&campaign=phase5"
            )
            assert response.status_code == 200
            assert "/assessment" in response.text

        client.get(
            "/lp/rongzi?utm_source=douyin&utm_medium=cpc&utm_campaign=rongzi_test"
            "&utm_content=video_a&utm_term=融资贷款&channel=douyin&campaign=phase5"
        )
        submit = client.post("/assessment/submit", data=PAYLOAD, follow_redirects=False)
        assert submit.status_code == 303
        assessment_id = int(submit.headers["location"].rsplit("/", 1)[-1])
        result = client.get(f"/result/{assessment_id}")
        assert result.status_code == 200
        assert "variant_" not in result.text or ("风险提示型" in result.text or "机会收益型" in result.text)

        with SessionLocal() as db:
            lead = db.query(Lead).filter(Lead.assessment_id == assessment_id).one()
            lead_id = lead.id
            assert lead.source_channel == "douyin"
            assert lead.utm_source == "douyin"
            assert lead.utm_medium == "cpc"
            assert lead.utm_campaign == "rongzi_test"
            assert lead.source_landing_page == "/lp/rongzi"
            assert db.query(ABAssignment).filter(
                ABAssignment.assessment_id == assessment_id
            ).count() == 1
            tag_names = {link.tag.name for link in lead.tag_links}
            assert {"高融资需求", "有抵押物", "征信正常", "纳税正常"} <= tag_names

        assert login(client).status_code == 303
        for url in ["/admin/ab-tests", "/admin/growth?show_test=1", "/admin/script-templates", "/admin/backup"]:
            assert client.get(url).status_code == 200
        growth = client.get("/admin/growth?show_test=1")
        assert "douyin" in growth.text and "/lp/rongzi" in growth.text
        ab_page = client.get("/admin/ab-tests")
        assert "free_result_conversion" in ab_page.text

        with SessionLocal() as db:
            sales = db.query(User).filter(User.username == "phase5_sales").first()
            if not sales:
                sales = User(
                    username="phase5_sales",
                    password_hash=hash_password("phase5-sales-pass"),
                    role="sales",
                )
                db.add(sales)
                db.commit()
                db.refresh(sales)
            sales_id = sales.id

        update = client.post(
            f"/admin/leads/{lead_id}/update",
            data={
                "follow_status": "已联系", "conversion_status": "意向中",
                "next_follow_time": "", "last_follow_note": "客户已添加微信",
                "assigned_sales": "增长销售", "assigned_sales_id": str(sales_id),
            },
            follow_redirects=False,
        )
        assert update.status_code == 303
        detail = client.get(f"/admin/leads/{lead_id}")
        for text in ["下一步最佳动作", "跟进时间线", "客户已添加微信", "匹配话术库"]:
            assert text in detail.text
        with SessionLocal() as db:
            assert db.query(LeadFollowLog).filter(LeadFollowLog.lead_id == lead_id).count() >= 3

        client.get("/logout")
        assert login(client, "phase5_sales", "phase5-sales-pass").status_code == 303
        workbench = client.get("/sales/workbench?show_test=1")
        assert workbench.status_code == 200
        assert PAYLOAD["company_name"] in workbench.text
        copied = client.post(
            "/api/events/script-copied",
            data={"lead_id": lead_id, "template_id": "1"},
        )
        assert copied.status_code == 200

        client.get("/logout")
        assert login(client).status_code == 303
        with SessionLocal() as db:
            optional_tag = db.query(Tag).filter(Tag.name == "需复购").one()
            tag_id = optional_tag.id
        assert client.post(
            f"/admin/leads/{lead_id}/tags/add", data={"tag_id": tag_id},
            follow_redirects=False,
        ).status_code == 303
        filtered = client.get(f"/admin/leads?tag_id={tag_id}")
        assert PAYLOAD["company_name"] in filtered.text
        assert client.post(
            f"/admin/leads/{lead_id}/tags/{tag_id}/remove",
            follow_redirects=False,
        ).status_code == 303

        new_script = client.post(
            "/admin/script-templates/create",
            data={
                "name": "Phase5测试话术", "scenario": "phase5_test",
                "lead_grade": lead.lead_grade, "product_code": lead.recommended_product,
                "content": "这是用于Phase5测试的一键复制话术。",
            },
            follow_redirects=False,
        )
        assert new_script.status_code == 303
        scripts = client.get("/admin/script-templates")
        assert "Phase5测试话术" in scripts.text

        paid = client.post(
            f"/payment/mock-pay/{assessment_id}?product=299_report",
            follow_redirects=False,
        )
        assert paid.status_code == 303
        with SessionLocal() as db:
            order = db.query(Order).filter(Order.assessment_id == assessment_id).first()
            assert order.source_channel == "douyin"
            assert order.utm_campaign == "rongzi_test"
            event_types = {
                x.event_type for x in db.query(Event).filter(
                    Event.assessment_id == assessment_id
                ).all()
            }
            assert {"ab_assigned", "script_copied", "lead_tag_added", "lead_tag_removed"} <= event_types

        db_backup = client.get("/admin/backup/database")
        assert db_backup.status_code == 200
        business_zip = client.get("/admin/backup/business-zip")
        assert business_zip.status_code == 200
        archive = zipfile.ZipFile(io.BytesIO(business_zip.content))
        assert {"leads.csv", "orders.csv", "reports.csv", "follow_tasks.csv", "events.csv"} <= set(archive.namelist())
        assert "users.csv" not in archive.namelist()

        clear = client.post("/admin/dev/clear-test-data", follow_redirects=False)
        assert clear.status_code == 303
        with SessionLocal() as db:
            assert not db.query(Lead).filter(Lead.id == lead_id).first()
            assert db.query(Event).filter(Event.event_type == "backup_downloaded").count() >= 1

        print({
            "assessment_id": assessment_id,
            "lead_id": lead_id,
            "source_channel": "douyin",
            "landing_page": "/lp/rongzi",
            "sales_user_id": sales_id,
        })
    print("PHASE5_GROWTH_OPERATIONS_OK")


if __name__ == "__main__":
    run()
