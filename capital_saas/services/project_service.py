import json
from datetime import datetime

from sqlalchemy.orm import Session

from core.project_sop_engine import project_sop_tasks
from db.models import (BankProduct, FinancingProject, FundingApplication, ProjectTask,
    ProjectTimelineEvent, RejectionReasonLibrary, User)
from services.event_service import track_event
from services.commission_service import create_commissions
from services.pilot_service import set_pilot_stage


STATUS_EVENT = {"submitted": "application_submitted", "supplement_required": "supplement_requested",
                "approved": "approved", "rejected": "rejected", "disbursed": "disbursed"}


def add_timeline(db: Session, project: FinancingProject, event_type: str, title: str,
                 user: User | None, content: str = "", application_id: int | None = None,
                 old_status: str = "", new_status: str = "") -> ProjectTimelineEvent:
    item = ProjectTimelineEvent(project_id=project.id, funding_application_id=application_id,
        event_type=event_type, event_title=title, event_content=content,
        old_status=old_status, new_status=new_status, operator_id=user.id if user else None)
    db.add(item)
    track_event(db, event_type if event_type.startswith("financing_") else f"project_{event_type}",
        project.assessment_id, project.lead_id,
        {"project_id": project.id, "application_id": application_id, "title": title,
         "old_status": old_status, "new_status": new_status}, commit=False)
    return item


def ensure_sop_tasks(db: Session, project: FinancingProject, status: str,
                     application_id: int | None = None) -> list[ProjectTask]:
    created = []
    for spec in project_sop_tasks(status):
        exists = db.query(ProjectTask).filter(ProjectTask.project_id == project.id,
            ProjectTask.task_title == spec["task_title"], ProjectTask.status == "pending").first()
        if exists: continue
        task = ProjectTask(project_id=project.id, funding_application_id=application_id,
            assigned_user_id=project.project_owner_id, status="pending", **spec)
        db.add(task); db.flush(); created.append(task)
        track_event(db, "project_task_created", project.assessment_id, project.lead_id,
            {"project_id": project.id, "task_id": task.id, "title": task.task_title}, commit=False)
    return created


def create_project(db: Session, lead, user: User, project_name: str, target_amount: float,
                   consulting_case_id: int | None = None, application_package_id: int | None = None,
                   priority: str = "high", expected_rate: float = 0,
                   expected_term: int = 12, expected_close_date=None) -> FinancingProject:
    project = FinancingProject(lead_id=lead.id, assessment_id=lead.assessment_id,
        consulting_case_id=consulting_case_id, application_package_id=application_package_id,
        project_name=project_name, project_status="preparing", target_amount=target_amount,
        expected_rate=expected_rate, expected_term=expected_term,
        funding_purpose=lead.assessment.funding_purpose, project_owner_id=user.id,
        priority=priority, expected_close_date=expected_close_date,
        org_id=lead.org_id, owner_org_id=lead.owner_org_id,
        owner_user_id=lead.owner_user_id or user.id,
        project_summary=f"{lead.company_name}融资交付项目，目标金额{target_amount / 10000:,.0f}万元。")
    db.add(project); db.flush()
    add_timeline(db, project, "project_created", "融资项目已立项", user,
                 project.project_summary, new_status="preparing")
    track_event(db, "financing_project_created", project.assessment_id, project.lead_id,
        {"project_id": project.id, "target_amount": target_amount}, commit=False)
    set_pilot_stage(db, lead, "project_created", commit=False)
    ensure_sop_tasks(db, project, "preparing")
    db.commit(); db.refresh(project); return project


def update_project_status(db: Session, project: FinancingProject, status: str, user: User,
                          summary: str = "") -> None:
    old = project.project_status; project.project_status = status; project.updated_at = datetime.now()
    if summary: project.project_summary = summary
    if status in {"rejected", "cancelled"}: project.success_result = "failed"
    if status == "disbursed": project.success_result = "success" if project.actual_disbursed_amount >= project.target_amount else "partial_success"
    if status in {"disbursed", "rejected", "cancelled", "archived"}: project.closed_at = datetime.now()
    add_timeline(db, project, "status_changed", f"项目状态更新为 {status}", user,
                 summary, old_status=old, new_status=status)
    track_event(db, "financing_project_status_changed", project.assessment_id, project.lead_id,
        {"project_id": project.id, "old_status": old, "new_status": status}, commit=False)
    ensure_sop_tasks(db, project, status)
    if status == "disbursed":
        create_commissions(db, "project_disbursed", project.actual_disbursed_amount,
            user_id=project.consultant_user_id or project.project_owner_id,
            org_id=project.owner_org_id or project.org_id, project_id=project.id,
            assessment_id=project.assessment_id, lead_id=project.lead_id)
    from services.customer_portal_service import notify_project_status
    notify_project_status(db, project)


def create_funding_application(db: Session, project: FinancingProject, user: User,
    institution_name: str, institution_type: str, product_name: str, apply_amount: float,
    bank_product_id: int | None = None, expected_rate: float = 0, loan_term: int = 12,
    repayment_method: str = "interest_first") -> FundingApplication:
    bank = db.get(BankProduct, bank_product_id) if bank_product_id else None
    application = FundingApplication(project_id=project.id, lead_id=project.lead_id,
        bank_product_id=bank.id if bank else None,
        institution_name=institution_name or (bank.bank_name if bank else "待确认机构"),
        institution_type=institution_type, product_name=product_name or (bank.product_name if bank else "融资方案"),
        apply_amount=apply_amount, expected_rate=expected_rate, loan_term=loan_term,
        repayment_method=repayment_method, application_status="planned")
    application.org_id = project.owner_org_id or project.org_id
    db.add(application); db.flush()
    add_timeline(db, project, "application_created", f"新增资金方申请：{application.institution_name}",
                 user, application.product_name, application.id, new_status="planned")
    track_event(db, "funding_application_created", project.assessment_id, project.lead_id,
        {"project_id": project.id, "application_id": application.id}, commit=False)
    db.commit(); db.refresh(application); return application


def update_application_status(db: Session, application: FundingApplication, status: str,
                              user: User, supplement_note: str = "") -> None:
    project = db.get(FinancingProject, application.project_id); old = application.application_status
    application.application_status = status; application.updated_at = datetime.now()
    now = datetime.now()
    if status == "submitted": application.submitted_at = now
    elif status == "reviewing": application.reviewed_at = now
    elif status == "supplement_required": application.supplement_required = True; application.supplement_note = supplement_note
    elif status == "approved": application.approved_at = now
    elif status == "rejected": application.rejected_at = now
    elif status == "disbursed": application.disbursed_at = now
    event_type = STATUS_EVENT.get(status, "status_changed")
    add_timeline(db, project, event_type, f"{application.institution_name}状态更新为 {status}",
                 user, supplement_note, application.id, old, status)
    track_event(db, "funding_application_status_changed", project.assessment_id, project.lead_id,
        {"project_id": project.id, "application_id": application.id, "old_status": old, "new_status": status}, commit=False)
    if status in {"approved", "rejected", "disbursed"}:
        track_event(db, f"funding_application_{status}", project.assessment_id, project.lead_id,
            {"project_id": project.id, "application_id": application.id}, commit=False)
    if status == "supplement_required": ensure_sop_tasks(db, project, "supplement_required", application.id)
    from db.models import CustomerAccount
    from services.notification_service import safe_create_notification
    customer=db.query(CustomerAccount).filter(CustomerAccount.lead_id==project.lead_id).first()
    mapping={"supplement_required":"funding_application_supplement_required",
             "approved":"funding_application_approved_customer",
             "disbursed":"funding_application_disbursed_customer"}
    data={"company_name":customer.company_name if customer else "客户企业","project_name":project.project_name}
    if customer and status in mapping:safe_create_notification(db,mapping[status],data,
        recipient_customer_id=customer.id,related_type="funding_application",related_id=application.id)
    if status in {"supplement_required","approved","rejected","disbursed"}:
        key="funding_application_rejected_internal" if status=="rejected" else "project_status_changed_consultant"
        user_id=project.consultant_user_id or project.owner_user_id or project.project_owner_id
        if user_id:safe_create_notification(db,key,{**data,"status_label":status},recipient_user_id=user_id,
            related_type="funding_application",related_id=application.id)


def update_application_result(db: Session, application: FundingApplication, user: User,
    approved_amount: float, final_amount: float, approved_rate: float, loan_term: int,
    rejection_reason: str = "", reason_category: str = "其他", improvement: str = "") -> None:
    project = db.get(FinancingProject, application.project_id)
    application.approved_amount, application.final_amount = approved_amount, final_amount
    application.approved_rate, application.loan_term = approved_rate, loan_term
    application.rejection_reason = rejection_reason
    applications = db.query(FundingApplication).filter(FundingApplication.project_id == project.id).all()
    project.approved_amount = sum(x.approved_amount for x in applications)
    project.actual_disbursed_amount = sum(x.final_amount for x in applications if x.application_status == "disbursed")
    if approved_rate: project.final_rate = approved_rate
    if loan_term: project.final_term = loan_term
    if rejection_reason:
        db.add(RejectionReasonLibrary(reason_category=reason_category, reason_detail=rejection_reason,
            related_project_id=project.id, related_application_id=application.id,
            improvement_suggestion=improvement))
        track_event(db, "rejection_reason_added", project.assessment_id, project.lead_id,
            {"project_id": project.id, "application_id": application.id, "category": reason_category}, commit=False)
    add_timeline(db, project, "note_added", "更新资金方批复/放款结果", user,
                 json.dumps({"approved_amount": approved_amount, "final_amount": final_amount,
                             "approved_rate": approved_rate, "loan_term": loan_term}, ensure_ascii=False), application.id)
