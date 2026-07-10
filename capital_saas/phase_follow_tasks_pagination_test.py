import sys
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi.testclient import TestClient

from db.database import SessionLocal
from db.models import Assessment, FollowTask, Lead, User
from main import app
from services.auth_service import hash_password


TEST_PREFIX = "follow-task-pagination"


def _create_assessment(db, company_name: str, created_at: datetime) -> Assessment:
    assessment = Assessment(
        company_name=company_name,
        contact_name="任务测试联系人",
        phone="13800000000",
        wechat_id="task_pagination",
        city="上海",
        industry="制造业",
        years=5,
        employee_count=30,
        annual_revenue=10_000_000,
        net_profit=1_000_000,
        monthly_cashflow=500_000,
        debt_total=1_000_000,
        short_debt=300_000,
        receivable_days=45,
        funding_need=2_000_000,
        funding_purpose="经营周转",
        has_collateral=True,
        tax_status=True,
        credit_status=True,
        knows_cashflow=True,
        has_budget=True,
        leverage_attitude="适中",
        asset_efficiency="高",
        fund_usage_plan=True,
        score=70,
        grade="B",
        risk_level="medium",
        funding_probability="good",
        created_at=created_at,
    )
    db.add(assessment)
    db.flush()
    return assessment


def _seed_tasks():
    suffix = uuid4().hex[:10]
    test_grade = f"task_test_{suffix}"
    with SessionLocal() as db:
        sales = User(
            username=f"task_sales_{suffix}",
            password_hash=hash_password("SalesPass123"),
            display_name="任务分页销售",
            role="sales",
            is_active=True,
        )
        other_sales = User(
            username=f"task_other_{suffix}",
            password_hash=hash_password("OtherPass123"),
            display_name="其他任务销售",
            role="sales",
            is_active=True,
        )
        db.add_all([sales, other_sales])
        db.flush()

        task_ids = []
        lead_ids = []
        assessment_ids = []
        start = datetime(2030, 1, 1, 9, 0)
        for index in range(1, 13):
            is_sales_task = index <= 11
            created_at = start + timedelta(minutes=index)
            company_name = f"{TEST_PREFIX}-sales-{index:02d}" if is_sales_task else f"{TEST_PREFIX}-other-{index:02d}"
            assessment = _create_assessment(db, company_name, created_at)
            lead = Lead(
                assessment_id=assessment.id,
                company_name=company_name,
                contact_name="任务测试联系人",
                phone="13800000000",
                wechat_id="task_pagination",
                city="上海",
                lead_grade=test_grade,
                lead_score=70,
                recommended_product="299_report",
                follow_status="待联系",
                conversion_status="未成交",
                assigned_sales_id=sales.id if is_sales_task else other_sales.id,
                created_at=created_at,
            )
            db.add(lead)
            db.flush()
            task = FollowTask(
                lead_id=lead.id,
                assessment_id=assessment.id,
                task_type="manual_followup",
                task_title=f"任务分页跟进-{index:02d}",
                task_content="用于验证任务表格分页、换行与权限范围。",
                priority="high" if index % 2 else "medium",
                due_time=created_at,
                status="pending",
                created_at=created_at,
            )
            db.add(task)
            db.flush()
            task_ids.append(task.id)
            lead_ids.append(lead.id)
            assessment_ids.append(assessment.id)
        db.commit()
        return sales.username, sales.id, other_sales.id, task_ids, lead_ids, assessment_ids, test_grade


def _cleanup(seed_data):
    _, sales_id, other_sales_id, task_ids, lead_ids, assessment_ids, _ = seed_data
    with SessionLocal() as db:
        db.query(FollowTask).filter(FollowTask.id.in_(task_ids)).delete(synchronize_session=False)
        db.query(Lead).filter(Lead.id.in_(lead_ids)).delete(synchronize_session=False)
        db.query(Assessment).filter(Assessment.id.in_(assessment_ids)).delete(synchronize_session=False)
        db.query(User).filter(User.id.in_([sales_id, other_sales_id])).delete(synchronize_session=False)
        db.commit()


def run():
    seed_data = None
    with TestClient(app) as client:
        try:
            seed_data = _seed_tasks()
            sales_username = seed_data[0]
            test_grade = seed_data[-1]

            login = client.post(
                "/login",
                data={"username": "admin", "password": "admin123", "next_url": "/admin/follow-tasks"},
                follow_redirects=False,
            )
            assert login.status_code == 303

            page_one = client.get(
                f"/admin/follow-tasks?status=pending&lead_grade={test_grade}&page_size=10&page=1"
            )
            assert page_one.status_code == 200
            assert page_one.text.count('data-task-id="') == 10
            assert "当前第 1 页 / 共 2 页，共 12 条任务" in page_one.text
            assert 'class="follow-tasks-table"' in page_one.text
            assert "wide-table" not in page_one.text
            for column_name in ["客户信息", "线索等级", "任务内容", "优先级", "时间状态", "操作"]:
                assert column_name in page_one.text
            assert "follow-task-actions" in page_one.text

            page_two = client.get(
                f"/admin/follow-tasks?status=pending&lead_grade={test_grade}&page_size=10&page=2"
            )
            assert page_two.status_code == 200
            assert page_two.text.count('data-task-id="') == 2
            assert "任务分页跟进-11" in page_two.text
            assert "status=pending" in page_two.text
            assert f"lead_grade={test_grade}" in page_two.text
            assert "page=1" in page_two.text

            client.get("/logout")
            sales_login = client.post(
                "/login",
                data={"username": sales_username, "password": "SalesPass123", "next_url": "/sales/follow-tasks"},
                follow_redirects=False,
            )
            assert sales_login.status_code == 303
            sales_redirect = client.get(
                f"/sales/follow-tasks?status=pending&lead_grade={test_grade}&page_size=10&page=1",
                follow_redirects=False,
            )
            assert sales_redirect.status_code == 303
            assert sales_redirect.headers["location"] == (
                f"/admin/follow-tasks?status=pending&lead_grade={test_grade}&page_size=10&page=1"
            )
            sales_page = client.get(sales_redirect.headers["location"])
            assert sales_page.status_code == 200
            assert "当前第 1 页 / 共 2 页，共 11 条任务" in sales_page.text
            assert f"{TEST_PREFIX}-other-12" not in sales_page.text
        finally:
            if seed_data:
                _cleanup(seed_data)

    print("FOLLOW_TASKS_PAGINATION_TEST_OK")


if __name__ == "__main__":
    run()
