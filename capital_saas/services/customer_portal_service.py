import secrets
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from core.document_completeness_engine import check_document_completeness
from db.database import get_db
from db.models import (AdvisorBooking, Assessment, ConsultingCase, CustomerAccessToken, CustomerAccount,
    CustomerMessage, CustomerTask, FinancingProject, Lead, Order, Report, UploadedDocument)
from services.event_service import track_event
from services.customer_phone_service import normalize_phone
from utils.logger import logger


def normalize_customer_phone(value: str | None) -> str:
    """Return a stable phone identity without changing the submitted lead value."""
    return normalize_phone(value) or ""


def ensure_customer_account(db: Session, lead: Lead, commit: bool = True) -> CustomerAccount:
    customer = db.query(CustomerAccount).filter(CustomerAccount.lead_id == lead.id).first()
    normalized_phone = normalize_customer_phone(lead.phone)
    if not customer and normalized_phone:
        # Disabled/locked accounts still own their historical data.  Reuse the
        # identity instead of creating a duplicate account that could collide
        # with the unique phone index or bypass an administrator's decision.
        candidates = db.query(CustomerAccount).order_by(CustomerAccount.created_at.asc()).all()
        customer = next(
            (item for item in candidates if normalize_customer_phone(item.login_phone or item.phone) == normalized_phone),
            None,
        )
    if not customer:
        customer = CustomerAccount(lead_id=lead.id, assessment_id=lead.assessment_id,
            company_name=lead.company_name, name=lead.contact_name, contact_name=lead.contact_name, phone=lead.phone,
            wechat_id=lead.wechat_id, login_phone=normalized_phone or lead.phone,
            status="pending_activation", is_active=True,
            registration_method="password", registration_source="free_assessment_auto")
        db.add(customer); db.flush()
        track_event(db, "customer_portal_created", lead.assessment_id, lead.id,
                    {"customer_id": customer.id}, commit=False)
    else:
        if customer.lead_id is None:
            customer.lead_id = lead.id
        if customer.assessment_id is None:
            customer.assessment_id = lead.assessment_id
        if not customer.company_name:
            customer.company_name = lead.company_name
        if not customer.login_phone and normalized_phone:
            customer.login_phone = normalized_phone
        if not customer.password_hash and customer.status == "active":
            customer.status = "pending_activation"
        if lead.wechat_id and not customer.wechat_id:
            customer.wechat_id = lead.wechat_id
        track_event(db, "assessment_linked_to_customer", lead.assessment_id, lead.id,
                    {"customer_id": customer.id}, commit=False)
    bind_customer_records(db, customer, lead)
    if commit: db.commit(); db.refresh(customer)
    return customer


def bind_customer_records(db: Session, customer: CustomerAccount, lead: Lead) -> None:
    """Bind one assessment's business objects while preserving legacy lead fields."""
    lead.customer_id = customer.id
    if lead.assessment:
        lead.assessment.customer_id = customer.id
    db.query(Report).filter(Report.assessment_id == lead.assessment_id).update(
        {"customer_id": customer.id}, synchronize_session=False)
    db.query(Order).filter(Order.assessment_id == lead.assessment_id).update(
        {"customer_id": customer.id}, synchronize_session=False)
    db.query(UploadedDocument).filter(
        (UploadedDocument.assessment_id == lead.assessment_id) | (UploadedDocument.lead_id == lead.id)
    ).update({"customer_id": customer.id}, synchronize_session=False)
    db.query(AdvisorBooking).filter(
        (AdvisorBooking.assessment_id == lead.assessment_id) | (AdvisorBooking.lead_id == lead.id)
    ).update({"customer_id": customer.id}, synchronize_session=False)
    db.query(FinancingProject).filter(
        (FinancingProject.assessment_id == lead.assessment_id) | (FinancingProject.lead_id == lead.id)
    ).update({"customer_id": customer.id}, synchronize_session=False)


def backfill_customer_account_links(db: Session, customer: CustomerAccount | None = None) -> dict[str, int]:
    """Idempotently attach historical records to an existing account identity.

    This function never deletes or revives accounts.  In particular, a soft
    deleted account is deliberately skipped so a startup migration cannot
    undo an administrator's decision.
    """
    stats = {"created": 0, "reused": 0, "updated": 0, "skipped": 0, "errors": 0}
    customers = [customer] if customer else db.query(CustomerAccount).order_by(CustomerAccount.id).all()
    assessments = db.query(Assessment).all() if customer is None else [
        item for item in db.query(Assessment).all()
        if normalize_customer_phone(item.phone) == normalize_customer_phone(customer.login_phone or customer.phone)
    ]

    def fill_blank(account: CustomerAccount, lead: Lead, assessment: Assessment) -> bool:
        changed = False
        for field, value in {
            "lead_id": lead.id, "assessment_id": assessment.id, "company_name": lead.company_name,
            "name": lead.contact_name, "contact_name": lead.contact_name, "phone": lead.phone,
            "wechat_id": lead.wechat_id, "city": lead.city,
        }.items():
            if getattr(account, field) in (None, "") and value not in (None, ""):
                setattr(account, field, value); changed = True
        normalized = normalize_customer_phone(account.login_phone or account.phone)
        if not account.login_phone and normalized:
            account.login_phone = normalized; changed = True
        return changed

    # Canonical map is only a lookup cache. A database query is still made
    # immediately before INSERT; this protects concurrent startup workers.
    by_phone = {
        normalize_customer_phone(item.login_phone or item.phone): item for item in customers
        if not item.deleted_at and normalize_customer_phone(item.login_phone or item.phone)
    }
    for assessment in assessments:
        lead = assessment.lead
        normalized = normalize_customer_phone(assessment.phone)
        if not lead or not normalized:
            stats["skipped"] += 1
            continue
        try:
            with db.begin_nested():
                exact = db.query(CustomerAccount).filter(CustomerAccount.login_phone == normalized).first()
                account = exact or by_phone.get(normalized)
                if account is None:
                    # A historical format (for example +86 or dashes) can be
                    # unique in SQL yet represent the same customer identity.
                    account = next((item for item in db.query(CustomerAccount).order_by(CustomerAccount.id).all()
                                    if normalize_customer_phone(item.login_phone or item.phone) == normalized), None)
                if account is None:
                    account = next((item for item in customers if item.lead_id == lead.id or item.assessment_id == assessment.id), None)
                if account and account.deleted_at:
                    stats["skipped"] += 1
                    continue
                if account is None:
                    account = CustomerAccount(lead_id=lead.id, assessment_id=assessment.id,
                        company_name=lead.company_name or "", name=lead.contact_name or "",
                        contact_name=lead.contact_name or "", phone=lead.phone or "",
                        wechat_id=lead.wechat_id or "", login_phone=normalized,
                        status="pending_activation", is_active=True,
                        registration_method="password", registration_source="historical_data")
                    db.add(account); db.flush()
                    customers.append(account); by_phone[normalized] = account; stats["created"] += 1
                else:
                    stats["reused"] += 1
                    if fill_blank(account, lead, assessment): stats["updated"] += 1
                bind_customer_records(db, account, lead)
                db.flush()
        except Exception:
            # Savepoint rollback isolates malformed historical records while
            # leaving earlier successful attachments available for commit.
            stats["errors"] += 1
            logger.exception("客户历史账号回填单条失败 assessment_id=%s phone=%s", assessment.id, normalized)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return stats


def bind_report_to_customer(db: Session, report: Report, customer: CustomerAccount) -> Report:
    if report.customer_id != customer.id:
        report.customer_id = customer.id
    return report


def customer_owns_report(db: Session, customer: CustomerAccount, report: Report) -> bool:
    """Authorize by direct ownership, with one-time legacy adoption by verified identity."""
    if report.customer_id == customer.id:
        return True
    assessment = report.assessment or db.get(Assessment, report.assessment_id)
    if not assessment:
        return False
    same_phone = bool(
        normalize_customer_phone(customer.login_phone or customer.phone)
        and normalize_customer_phone(customer.login_phone or customer.phone)
        == normalize_customer_phone(assessment.phone)
    )
    same_wechat = bool(customer.wechat_id and assessment.wechat_id and customer.wechat_id == assessment.wechat_id)
    if same_phone or same_wechat:
        report.customer_id = customer.id
        db.flush()
        return True
    return False


def reports_for_customer(db: Session, customer: CustomerAccount) -> list[Report]:
    """Return every historical report and adopt compatible legacy rows."""
    direct = db.query(Report).filter(Report.customer_id == customer.id).all()
    reports = {item.id: item for item in direct}
    identity_phone = normalize_customer_phone(customer.login_phone or customer.phone)
    legacy = db.query(Report).join(Assessment, Report.assessment_id == Assessment.id).all()
    changed = False
    for report in legacy:
        assessment = report.assessment
        phone_match = bool(identity_phone and identity_phone == normalize_customer_phone(assessment.phone))
        wechat_match = bool(customer.wechat_id and assessment.wechat_id == customer.wechat_id)
        if phone_match or wechat_match:
            report.customer_id = customer.id
            reports[report.id] = report
            changed = True
    if changed:
        db.commit()
    return sorted(reports.values(), key=lambda item: (item.created_at, item.id), reverse=True)


def generate_login_token(db: Session, customer: CustomerAccount,
                         token_type: str = "portal_login", days: int = 7) -> CustomerAccessToken:
    db.query(CustomerAccessToken).filter(CustomerAccessToken.customer_id == customer.id,
        CustomerAccessToken.token_type == token_type, CustomerAccessToken.is_active.is_(True)).update(
            {"is_active": False}, synchronize_session=False)
    item = CustomerAccessToken(customer_id=customer.id, lead_id=customer.lead_id,
        token=secrets.token_urlsafe(40), token_type=token_type,
        expired_at=datetime.now() + timedelta(days=days), is_active=True)
    db.add(item); db.flush()
    track_event(db, "customer_login_token_generated", customer.assessment_id, customer.lead_id,
                {"customer_id": customer.id, "token_type": token_type}, commit=False)
    db.commit(); db.refresh(item); return item


def customer_from_session(request: Request, db: Session) -> CustomerAccount | None:
    customer_id = request.session.get("customer_id")
    customer = db.get(CustomerAccount, int(customer_id)) if customer_id else None
    if customer and not customer.deleted_at and customer.is_active:
        if customer.status == "active":
            request.state.customer_unread_count = db.query(CustomerMessage).filter(
                CustomerMessage.customer_id == customer.id,
                CustomerMessage.status == "unread",
            ).count()
            return customer
        if customer.status == "pending_activation" and request.session.get("token_login_notice"):
            request.state.customer_unread_count = db.query(CustomerMessage).filter(
                CustomerMessage.customer_id == customer.id,
                CustomerMessage.status == "unread",
            ).count()
            return customer
    from services.customer_auth_service import customer_from_remember_cookie
    customer = customer_from_remember_cookie(request, db)
    if customer:
        request.state.customer_unread_count = db.query(CustomerMessage).filter(
            CustomerMessage.customer_id == customer.id,
            CustomerMessage.status == "unread",
        ).count()
    return customer


def require_customer(request: Request, db: Session = Depends(get_db)) -> CustomerAccount:
    customer = customer_from_session(request, db)
    if not customer:
        raise HTTPException(401, "请先登录客户账号")
    return customer


def portal_completeness(db: Session, customer: CustomerAccount) -> dict:
    lead = db.get(Lead, customer.lead_id) if customer.lead_id else None
    if not lead:
        return {
            "completeness_score": 0,
            "level": "pending",
            "missing_required_documents": [],
            "missing_optional_documents": [],
            "available_documents": [],
        }
    docs = db.query(UploadedDocument).filter(UploadedDocument.lead_id == lead.id).all()
    return check_document_completeness(lead, lead.assessment, docs, lead.recommended_product, {})


def ensure_document_tasks(db: Session, customer: CustomerAccount) -> list[CustomerTask]:
    if not customer.lead_id or not customer.assessment_id:
        return []
    result = portal_completeness(db, customer); created=[]
    for missing in result["missing_required_documents"]:
        title=f"补充资料：{missing}"
        exists=db.query(CustomerTask).filter(CustomerTask.customer_id==customer.id,
            CustomerTask.task_title==title,CustomerTask.status=="pending").first()
        if not exists:
            task=CustomerTask(customer_id=customer.id,lead_id=customer.lead_id,
                assessment_id=customer.assessment_id,task_type="upload_document",task_title=title,
                task_content=f"请上传{missing}，顾问将在收到后进行核验。",priority="high",
                due_time=datetime.now()+timedelta(days=3));db.add(task);created.append(task)
    if created:
        from services.notification_service import safe_create_notification
        missing="、".join(result["missing_required_documents"][:8])
        safe_create_notification(db,"document_missing_customer",{"company_name":customer.company_name,
            "missing_documents":missing},recipient_customer_id=customer.id,related_type="document_collection",related_id=customer.lead_id)
        lead=db.get(Lead,customer.lead_id)
        case=db.query(ConsultingCase).filter(ConsultingCase.lead_id==lead.id).order_by(ConsultingCase.id.desc()).first()
        user_id=(case.consultant_user_id or case.consultant_id) if case else lead.owner_user_id
        if user_id:safe_create_notification(db,"document_uploaded_consultant",{"company_name":customer.company_name,
            "document_name":"资料缺失清单"},recipient_user_id=user_id,related_type="lead",related_id=lead.id)
    db.commit(); return created


def complete_document_tasks(db: Session, customer: CustomerAccount, document: UploadedDocument) -> None:
    tasks=db.query(CustomerTask).filter(CustomerTask.customer_id==customer.id,
        CustomerTask.task_type=="upload_document",CustomerTask.status=="pending").all()
    for task in tasks:
        keyword=task.task_title.replace("补充资料：","")
        aliases={"营业执照":"营业执照/工商资料","纳税/开票资料":"纳税资料",
                 "抵押物权属证明":"抵押物资料","抵押物评估资料":"抵押物资料",
                 "权属人资料":"法人/股东资料","发票":"纳税资料"}
        if keyword in document.document_category or aliases.get(keyword)==document.document_category:
            task.status="done";task.related_document_id=document.id
            task.completed_at=task.updated_at=datetime.now()


def send_customer_message(db: Session, customer: CustomerAccount, title: str, content: str,
                          message_type: str="system", sender_user_id: int | None=None,
                          commit: bool=True) -> CustomerMessage:
    item=CustomerMessage(customer_id=customer.id,lead_id=customer.lead_id,
        sender_user_id=sender_user_id,message_type=message_type,title=title,content=content,status="unread")
    db.add(item);db.flush();track_event(db,"customer_message_sent",customer.assessment_id,
        customer.lead_id,{"customer_id":customer.id,"message_id":item.id,"type":message_type},commit=False)
    if commit:db.commit();db.refresh(item)
    return item


def notify_project_status(db: Session, project: FinancingProject) -> None:
    customer=db.query(CustomerAccount).filter(CustomerAccount.lead_id==project.lead_id,
        CustomerAccount.is_active.is_(True)).first()
    if not customer:return
    labels={"preparing":"资料准备中","submitted":"已提交申请","bank_review":"金融机构审核中",
        "supplement_required":"需要补充资料","approved":"已获得批复","rejected":"暂未通过，正在优化方案",
        "disbursed":"已放款","archived":"已归档"}
    from services.notification_service import safe_create_notification
    data={"project_name":project.project_name,"status_label":labels.get(project.project_status,project.project_status),
          "company_name":customer.company_name}
    send_customer_message(db,customer,"融资项目进度更新",
        f"项目“{project.project_name}”已更新为：{data['status_label']}。","project_update",commit=False)
    safe_create_notification(db,"project_status_changed_customer",data,recipient_customer_id=customer.id,
        related_type="financing_project",related_id=project.id)
    consultant_id=project.consultant_user_id or project.owner_user_id or project.project_owner_id
    if consultant_id:safe_create_notification(db,"project_status_changed_consultant",data,
        recipient_user_id=consultant_id,related_type="financing_project",related_id=project.id)


def advisor_context(db: Session, lead_id: int) -> dict:
    case=db.query(ConsultingCase).filter(ConsultingCase.lead_id==lead_id).order_by(ConsultingCase.id.desc()).first()
    if not case:return {"name":"服务顾问待分配","organization":"沪上银","contact":"","next_meeting":None}
    from db.models import Organization, User
    user=db.get(User,case.consultant_user_id or case.consultant_id) if (case.consultant_user_id or case.consultant_id) else None
    org=db.get(Organization,case.owner_org_id or case.org_id) if (case.owner_org_id or case.org_id) else None
    return {"name":user.username if user else "服务顾问待分配","organization":org.org_name if org else "沪上银",
        "contact":"由平台统一联系" if not case.show_consultant_contact else (user.username if user else ""),
        "next_meeting":case.next_meeting_time,"case_status":case.case_status}
