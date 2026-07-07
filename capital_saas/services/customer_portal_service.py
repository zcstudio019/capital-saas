import secrets
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from core.document_completeness_engine import check_document_completeness
from db.database import get_db
from db.models import (ConsultingCase, CustomerAccessToken, CustomerAccount,
    CustomerMessage, CustomerTask, FinancingProject, Lead, UploadedDocument)
from services.event_service import track_event


def ensure_customer_account(db: Session, lead: Lead, commit: bool = True) -> CustomerAccount:
    customer = db.query(CustomerAccount).filter(CustomerAccount.lead_id == lead.id).first()
    if not customer:
        customer = CustomerAccount(lead_id=lead.id, assessment_id=lead.assessment_id,
            company_name=lead.company_name, contact_name=lead.contact_name, phone=lead.phone,
            wechat_id=lead.wechat_id, login_phone=lead.phone, is_active=True)
        db.add(customer); db.flush()
        track_event(db, "customer_portal_created", lead.assessment_id, lead.id,
                    {"customer_id": customer.id}, commit=False)
    if commit: db.commit(); db.refresh(customer)
    return customer


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
    if not customer_id: return None
    customer = db.get(CustomerAccount, int(customer_id))
    return customer if customer and customer.is_active else None


def require_customer(request: Request, db: Session = Depends(get_db)) -> CustomerAccount:
    customer = customer_from_session(request, db)
    if not customer: raise HTTPException(401, "请通过专属链接登录客户门户")
    return customer


def portal_completeness(db: Session, customer: CustomerAccount) -> dict:
    lead = db.get(Lead, customer.lead_id)
    docs = db.query(UploadedDocument).filter(UploadedDocument.lead_id == lead.id).all()
    return check_document_completeness(lead, lead.assessment, docs, lead.recommended_product, {})


def ensure_document_tasks(db: Session, customer: CustomerAccount) -> list[CustomerTask]:
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
