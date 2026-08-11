import secrets
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import text

from core.document_completeness_engine import check_document_completeness
from db.database import get_db
from db.models import (AdvisorBooking, Assessment, ConsultingCase, CustomerAccessToken, CustomerAccount,
    CustomerMessage, CustomerTask, FinancingProject, Lead, Order, Report, UploadedDocument)
from services.event_service import track_event


def normalize_customer_phone(value: str | None) -> str:
    """Return a stable phone identity without changing the submitted lead value."""
    return "".join(ch for ch in str(value or "").strip() if ch.isdigit() or ch == "+")


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


def backfill_customer_account_links(db: Session, customer: CustomerAccount | None = None) -> int:
    """Adopt historical data by canonical phone without deleting old records."""
    customers = [customer] if customer else db.query(CustomerAccount).order_by(CustomerAccount.id).all()
    if customer is None:
        primary_by_phone: dict[str, CustomerAccount] = {}
        for account in customers:
            if not account.is_active or account.status == "disabled":
                if not str(account.login_phone or "").startswith("merged-account-"):
                    account.login_phone = f"merged-account-{account.id}"
                continue
            normalized = normalize_customer_phone(account.login_phone or account.phone)
            if not normalized:
                continue
            primary = primary_by_phone.get(normalized)
            if primary is None:
                primary_by_phone[normalized] = account
                continue
            for table in (Report, Order, UploadedDocument, AdvisorBooking, FinancingProject,
                          CustomerTask, CustomerMessage):
                db.query(table).filter(table.customer_id == account.id).update(
                    {"customer_id": primary.id}, synchronize_session=False)
            db.query(Lead).filter(Lead.customer_id == account.id).update(
                {"customer_id": primary.id}, synchronize_session=False)
            db.query(Assessment).filter(Assessment.customer_id == account.id).update(
                {"customer_id": primary.id}, synchronize_session=False)
            account.login_phone = f"merged-account-{account.id}"
            account.status = "disabled"
            account.is_active = False
    changed = 0
    assessments = db.query(Assessment).all()
    if customer is None:
        for assessment in assessments:
            report = db.query(Report).filter(Report.assessment_id == assessment.id).first()
            order = db.query(Order).filter(
                Order.assessment_id == assessment.id, Order.customer_id.isnot(None)
            ).order_by(Order.id.desc()).first()
            lead = assessment.lead
            candidate_id = (
                (report.customer_id if report else None)
                or (order.customer_id if order else None)
                or (lead.customer_id if lead else None)
                or assessment.customer_id
            )
            account = db.get(CustomerAccount, candidate_id) if candidate_id else None
            if account and lead:
                bind_customer_records(db, account, lead)
        # Historical assessments may predate customer_accounts entirely.  Build
        # a password-less account per canonical phone so that a later password
        # setup/login immediately recovers every report for that identity.
        primary_by_phone = {
            normalize_customer_phone(item.login_phone or item.phone): item
            for item in customers
            if item.is_active and item.status != "disabled"
            and normalize_customer_phone(item.login_phone or item.phone)
        }
        for assessment in assessments:
            lead = assessment.lead
            normalized = normalize_customer_phone(assessment.phone)
            if not lead or not normalized:
                continue
            account = primary_by_phone.get(normalized)
            if account is None:
                # 旧库可能已有以 lead/assessment 为锚点、但手机号格式不同或
                # 已停用的账号。锚点账号仍拥有历史数据，不能再次插入同一
                # lead_id/assessment_id，否则会触发唯一约束并中断启动迁移。
                account = next(
                    (
                        item for item in customers
                        if item.lead_id == lead.id or item.assessment_id == assessment.id
                    ),
                    None,
                )
            if account is None:
                account = CustomerAccount(
                    lead_id=lead.id, assessment_id=assessment.id,
                    company_name=lead.company_name, name=lead.contact_name,
                    contact_name=lead.contact_name, phone=lead.phone,
                    wechat_id=lead.wechat_id, login_phone=normalized,
                    status="pending_activation", is_active=True,
                    registration_method="password", registration_source="historical_data",
                )
                db.add(account)
                db.flush()
                customers.append(account)
                primary_by_phone[normalized] = account
                changed += 1
            elif account.is_active and account.status != "disabled":
                primary_by_phone.setdefault(normalized, account)
            bind_customer_records(db, account, lead)
    for account in customers:
        if not account.is_active or account.status == "disabled":
            continue
        if not account.password_hash and account.status == "active":
            account.status = "pending_activation"
        normalized = normalize_customer_phone(account.login_phone or account.phone)
        if not normalized:
            continue
        account.login_phone = normalized
        if not account.name:
            account.name = account.contact_name
        for assessment in assessments:
            if normalize_customer_phone(assessment.phone) != normalized or not assessment.lead:
                continue
            if assessment.customer_id != account.id or assessment.lead.customer_id != account.id:
                changed += 1
            bind_customer_records(db, account, assessment.lead)
    db.commit()
    if customer is None and db.bind and db.bind.dialect.name == "sqlite":
        db.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_customer_accounts_login_phone_nonblank "
            "ON customer_accounts(login_phone) WHERE login_phone <> ''"
        ))
        db.commit()
    return changed


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
    if customer and customer.is_active:
        if customer.status == "active":
            return customer
        if customer.status == "pending_activation" and request.session.get("token_login_notice"):
            return customer
    from services.customer_auth_service import customer_from_remember_cookie
    return customer_from_remember_cookie(request, db)


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
