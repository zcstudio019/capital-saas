import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.config import settings
from db.database import Base, SessionLocal, engine
from db.models import (
    Assessment,
    CustomerAccount,
    FinancingProject,
    Lead,
    NotificationJob,
    Organization,
    RejectionReasonLibrary,
    Report,
    SuccessCase,
    User,
)
from services.auth_service import hash_password
from services.event_service import track_event

if settings.app_env == "production":
    print("production 环境禁止生成 demo 数据。")
    sys.exit(1)

Base.metadata.create_all(bind=engine)

with SessionLocal() as db:
    orgs = []
    for name, city in [("[DEMO]上海分公司", "上海"), ("[DEMO]苏州分公司", "苏州"), ("[DEMO]杭州分公司", "杭州")]:
        item = db.query(Organization).filter_by(org_name=name).first()
        if not item:
            item = Organization(org_name=name, org_type="branch", city=city, province="华东", status="active")
            db.add(item)
            db.flush()
        orgs.append(item)

    users = []
    for i in range(3):
        username = f"demo_sales_{i+1}"
        user = db.query(User).filter_by(username=username).first()
        if not user:
            user = User(username=username, password_hash=hash_password("DemoPass123!"), role="sales", is_active=True, org_id=orgs[i % len(orgs)].id)
            db.add(user)
            db.flush()
        users.append(user)
    for i in range(2):
        username = f"demo_consultant_{i+1}"
        user = db.query(User).filter_by(username=username).first()
        if not user:
            user = User(username=username, password_hash=hash_password("DemoPass123!"), role="consultant", is_active=True, org_id=orgs[i % len(orgs)].id)
            db.add(user)
            db.flush()
        users.append(user)

    projects = []
    for i in range(5):
        company = f"[DEMO]华东成长企业{i+1}"
        exists = db.query(Assessment).filter_by(company_name=company).first()
        if exists:
            continue
        assessment = Assessment(
            company_name=company, contact_name=f"王总{i+1}", phone=f"1380000{i+1:04d}",
            wechat_id=f"demo_wx_{i+1}", city=orgs[i % len(orgs)].city, industry="制造业",
            years=3+i, employee_count=20+i*8, annual_revenue=500+i*200, net_profit=50+i*20,
            monthly_cashflow=30+i*10, debt_total=120+i*40, short_debt=40+i*10,
            receivable_days=45+i*5, funding_need=100+i*80, funding_purpose="补充流动资金",
            has_collateral=i % 2 == 0, tax_status=True, credit_status=True,
            knows_cashflow=True, has_budget=i % 2 == 0, leverage_attitude="适中",
            asset_efficiency="中", fund_usage_plan=True, score=70+i*4, grade="A" if i > 2 else "B",
            risk_level="medium", funding_probability="medium", source_channel="demo",
        )
        db.add(assessment); db.flush()
        lead = Lead(
            assessment_id=assessment.id, company_name=company, contact_name=assessment.contact_name,
            phone=assessment.phone, wechat_id=assessment.wechat_id, city=assessment.city,
            lead_grade="A" if i > 2 else "B", lead_score=72+i*3, conversion_status="未成交",
            recommended_product="1999_structure_plan" if i > 2 else "699_bank_match",
            follow_status="待联系", org_id=orgs[i % len(orgs)].id, owner_org_id=orgs[i % len(orgs)].id,
            owner_user_id=users[i % 3].id, source_channel="demo",
        )
        db.add(lead); db.flush()
        report = Report(
            assessment_id=assessment.id,
            free_summary_json=json.dumps({"summary": "demo"}),
            full_report_json=json.dumps({"sections": []}),
            html_content="<h1>DEMO 报告</h1>",
            is_unlocked=i < 3,
            review_status="approved",
        )
        db.add(report); db.flush()
        if i < 2:
            db.add(CustomerAccount(lead_id=lead.id, assessment_id=assessment.id, company_name=company, contact_name=lead.contact_name, phone=lead.phone, login_phone=lead.phone))
        if i < 2:
            project = FinancingProject(
                lead_id=lead.id, assessment_id=assessment.id, project_name=f"[DEMO]融资项目{i+1}",
                project_status="bank_review" if i == 0 else "disbursed", target_amount=assessment.funding_need,
                approved_amount=80+i*100, actual_disbursed_amount=0 if i == 0 else 120,
                funding_purpose=assessment.funding_purpose, owner_user_id=users[i].id, owner_org_id=orgs[i].id,
                project_summary="demo 项目",
            )
            db.add(project); db.flush(); projects.append(project)

    if projects:
        db.add(SuccessCase(project_id=projects[-1].id, industry="制造业", company_scale="小微企业", funding_amount=120, product_type="经营贷", institution_type="bank", approval_days=12, rate_range="4%-6%", case_title="[DEMO]制造业经营贷成功案例", case_summary="匿名demo案例", key_success_factors="资料完整、流水稳定"))
        db.add(RejectionReasonLibrary(reason_category="资料不完整", reason_detail="[DEMO]银行流水缺失", related_project_id=projects[0].id, improvement_suggestion="补充近12个月流水"))
    for i in range(2):
        db.add(NotificationJob(template_key="demo", audience_type="admin", channel="mock", recipient_type="user", recipient_user_id=users[i].id, title="[DEMO]通知任务", content="demo notification", payload_json="{}"))

    track_event(db, "demo_data_created", data={"source": "script"}, commit=False)
    db.commit()

print("demo 数据生成完成：3组织、5用户、5线索、3报告、2客户门户、2项目等。")
