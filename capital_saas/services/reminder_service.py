from datetime import datetime, time, timedelta

from sqlalchemy.orm import Session

from db.models import (CustomerAccount, CustomerTask, FollowTask, InternalNotification, Lead,
    NotificationJob, ProjectTask)
from services.event_service import track_event
from services.notification_service import create_internal_notification, safe_create_notification


def _created_today(db,template_key,related_type,related_id):
    start=datetime.combine(datetime.now().date(),time.min)
    return db.query(NotificationJob).filter(NotificationJob.template_key==template_key,
        NotificationJob.related_type==related_type,NotificationJob.related_id==related_id,
        NotificationJob.created_at>=start).first() is not None

def _internal_created_today(db,notification_type,related_type,related_id,user_id):
    start=datetime.combine(datetime.now().date(),time.min)
    return db.query(InternalNotification).filter(InternalNotification.notification_type==notification_type,
        InternalNotification.related_type==related_type,InternalNotification.related_id==related_id,
        InternalNotification.user_id==user_id,InternalNotification.created_at>=start).first() is not None

def _notify_task(db,user_id,company,notification_type,related_type,related_id,action_url):
    if not user_id or _internal_created_today(db,notification_type,related_type,related_id,user_id):
        return False
    title = "跟进任务已逾期" if notification_type == "task_overdue" else "跟进任务即将到期"
    content = f"客户 {company or '客户'} 的跟进任务已逾期，请尽快处理。" if notification_type == "task_overdue" else f"客户 {company or '客户'} 的跟进任务即将到期，请及时处理。"
    return bool(create_internal_notification(db,user_id,title,content,notification_type,
        related_type=related_type,related_id=related_id,action_url=action_url,commit=False))

def scan_reminders(db:Session,hours_ahead:int=24)->dict:
    now=datetime.now();deadline=now+timedelta(hours=hours_ahead);counts={"customer":0,"follow":0,"project":0}
    customer_tasks=db.query(CustomerTask).filter(CustomerTask.status=="pending",
        CustomerTask.due_time.is_not(None),CustomerTask.due_time<=deadline).all()
    for task in customer_tasks:
        if not _created_today(db,"customer_task_due_customer","customer_task",task.id):
            safe_create_notification(db,"customer_task_due_customer",{"task_title":task.task_title},
                recipient_customer_id=task.customer_id,related_type="customer_task",related_id=task.id);counts["customer"]+=1
        lead=db.get(Lead,task.lead_id)
        user_id=(lead.owner_user_id or lead.assigned_sales_id) if lead else None
        notification_type="task_overdue" if task.due_time and task.due_time<now else "task_due"
        if _notify_task(db,user_id,lead.company_name if lead else "",notification_type,"customer_task",task.id,
            f"/sales/leads/{lead.id}" if lead else "/admin/notifications"):
            counts["customer"]+=1
    follow_tasks=db.query(FollowTask).filter(FollowTask.status=="pending",FollowTask.due_time<=deadline).all()
    for task in follow_tasks:
        lead=db.get(Lead,task.lead_id);user_id=lead.owner_user_id or lead.assigned_sales_id if lead else None
        if user_id and not _created_today(db,"follow_task_due_sales","follow_task",task.id):
            safe_create_notification(db,"follow_task_due_sales",{"company_name":lead.company_name,
                "task_title":task.task_title},recipient_user_id=user_id,related_type="follow_task",related_id=task.id);counts["follow"]+=1
        if lead:
            notification_type="task_overdue" if task.due_time<now else "task_due"
            if _notify_task(db,user_id,lead.company_name,notification_type,"follow_task",task.id,f"/sales/leads/{lead.id}"):
                counts["follow"]+=1
    project_tasks=db.query(ProjectTask).filter(ProjectTask.status=="pending",ProjectTask.due_time<=deadline).all()
    for task in project_tasks:
        if task.task_type not in {"repayment_reminder","renewal_prepare","cashflow_review","post_loan_check"}:continue
        customer=db.query(CustomerAccount).filter(CustomerAccount.lead_id==task.project.lead_id).first() if hasattr(task,"project") else None
        if not customer:
            from db.models import FinancingProject
            project=db.get(FinancingProject,task.project_id);customer=db.query(CustomerAccount).filter(CustomerAccount.lead_id==project.lead_id).first() if project else None
        key="renewal_prepare_customer" if task.task_type=="renewal_prepare" else "repayment_reminder_customer"
        if customer and not _created_today(db,key,"project_task",task.id):
            safe_create_notification(db,key,{"task_title":task.task_title},recipient_customer_id=customer.id,
                related_type="project_task",related_id=task.id);counts["project"]+=1
        from db.models import FinancingProject
        project=db.get(FinancingProject,task.project_id)
        lead=db.get(Lead,project.lead_id) if project else None
        user_id=task.assigned_user_id or (project.consultant_user_id or project.owner_user_id if project else None)
        notification_type="task_overdue" if task.due_time<now else "task_due"
        if _notify_task(db,user_id,lead.company_name if lead else "",notification_type,"project_task",task.id,
            f"/admin/financing-projects/{project.id}" if project else "/admin/notifications"):
            counts["project"]+=1
    track_event(db,"reminder_scan_run",data=counts,commit=False);db.commit();return counts
