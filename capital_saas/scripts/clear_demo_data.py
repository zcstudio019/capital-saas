import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.config import settings
from db.database import SessionLocal
from db.models import Assessment, CustomerAccount, Event, FinancingProject, Lead, NotificationJob, Organization, RejectionReasonLibrary, Report, SuccessCase, User
from services.event_service import track_event

if settings.app_env == "production":
    print("production 环境禁止清理 demo 数据。")
    sys.exit(1)

with SessionLocal() as db:
    demo_assessments = [x.id for x in db.query(Assessment).filter(Assessment.company_name.like("[DEMO]%")).all()]
    demo_leads = [x.id for x in db.query(Lead).filter(Lead.company_name.like("[DEMO]%")).all()]
    demo_projects = [x.id for x in db.query(FinancingProject).filter(FinancingProject.project_name.like("[DEMO]%")).all()]
    for model, condition in [
        (SuccessCase, SuccessCase.project_id.in_(demo_projects or [-1])),
        (RejectionReasonLibrary, RejectionReasonLibrary.reason_detail.like("[DEMO]%")),
        (NotificationJob, NotificationJob.title.like("[DEMO]%")),
        (FinancingProject, FinancingProject.id.in_(demo_projects or [-1])),
        (CustomerAccount, CustomerAccount.lead_id.in_(demo_leads or [-1])),
        (Report, Report.assessment_id.in_(demo_assessments or [-1])),
        (Lead, Lead.id.in_(demo_leads or [-1])),
        (Assessment, Assessment.id.in_(demo_assessments or [-1])),
        (User, User.username.like("demo_%")),
        (Organization, Organization.org_name.like("[DEMO]%")),
    ]:
        db.query(model).filter(condition).delete(synchronize_session=False)
    track_event(db, "demo_data_cleared", data={"source": "script"}, commit=False)
    db.commit()
print("demo 数据清理完成。")
