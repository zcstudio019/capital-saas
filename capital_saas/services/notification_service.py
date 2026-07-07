import json
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from db.models import (CustomerAccount, NotificationJob, NotificationLog,
    NotificationPreference, NotificationTemplate)
from notifications.email_channel import EmailChannel
from notifications.in_app_channel import InAppChannel
from notifications.mock_channel import MockChannel
from notifications.sms_channel import SmsChannel
from notifications.wecom_channel import WecomChannel
from services.event_service import track_event
from services.settings_service import get_setting
from utils.logger import logger

FORBIDDEN_WORDS=("包过","保证放款","绝对通过","无视征信","包装资料","伪造流水")
CHANNELS={"in_app":InAppChannel(),"email":EmailChannel(),"sms":SmsChannel(),
          "wecom_webhook":WecomChannel(),"mock":MockChannel()}
DEFAULT_TEMPLATES=[
 ("report_approved_customer","报告已审核通过","customer","in_app","service","您的融资诊断报告已可查看","{{company_name}}的融资诊断报告已完成审核，请登录客户门户查看。"),
 ("document_missing_customer","资料补充提醒","customer","in_app","service","融资资料需要补充","当前尚缺：{{missing_documents}}。请登录客户门户上传，顾问将在收到后核验。"),
 ("document_uploaded_consultant","客户上传资料","consultant","in_app","service","客户已上传新资料","{{company_name}}已上传{{document_name}}，请及时核验。"),
 ("customer_task_due_customer","客户待办到期提醒","customer","in_app","service","待办事项即将到期","您的待办“{{task_title}}”即将到期，请登录门户处理。"),
 ("follow_task_due_sales","销售跟进到期提醒","sales","in_app","service","销售跟进任务即将到期","{{company_name}}的跟进任务“{{task_title}}”即将到期。"),
 ("project_status_changed_customer","项目进度更新","customer","in_app","service","融资项目进度已更新","项目“{{project_name}}”已更新为：{{status_label}}。"),
 ("project_status_changed_consultant","项目状态内部提醒","consultant","in_app","service","融资项目状态更新","{{company_name}}项目已更新为{{status_label}}，请安排下一步交付。"),
 ("funding_application_supplement_required","资金方要求补资料","customer","in_app","service","申请需要补充资料","金融机构正在补充审核，请按顾问通知完善所需资料。"),
 ("funding_application_approved_customer","申请批复通知","customer","in_app","service","融资申请已获得批复","申请已获得批复，请与顾问确认额度、期限、成本和签约条件。"),
 ("funding_application_rejected_internal","申请方案优化提醒","consultant","in_app","service","融资方案需要优化","当前申请未通过，请复盘资料、准入条件并优化下一申请方案。"),
 ("funding_application_disbursed_customer","放款完成通知","customer","in_app","service","融资款项已完成放款","请按约定用途使用资金，并预留还款现金流、保存贷后资料。"),
 ("repayment_reminder_customer","还款提醒","customer","in_app","service","还款计划提醒","近期有还款安排，请提前核对还款账户并预留足额资金。"),
 ("renewal_prepare_customer","续贷准备提醒","customer","in_app","service","建议开始续贷准备","距离续贷节点较近，请提前准备流水、纳税和经营资料。"),
 ("payment_pending_customer","待支付提醒","customer","in_app","service","订单尚待支付","您创建的服务订单尚未完成支付，可登录门户继续处理。"),
 ("upgrade_recommend_customer","服务升级建议","customer","in_app","marketing","融资服务升级建议","基于当前服务进度，可查看更深入的银行匹配或融资结构优化服务。"),
]

class SafeDict(dict):
    def __missing__(self,key):return "{"+key+"}"

def validate_template_content(title:str,content:str):
    hit=[x for x in FORBIDDEN_WORDS if x in f"{title}{content}"]
    if hit:raise ValueError(f"模板包含禁止表达：{'、'.join(hit)}")

def ensure_default_notification_templates(db:Session):
    existing={x[0] for x in db.query(NotificationTemplate.template_key).all()}
    for key,name,audience,channel,category,title,content in DEFAULT_TEMPLATES:
        if key not in existing:db.add(NotificationTemplate(template_key=key,template_name=name,
            audience_type=audience,channel=channel,category=category,title_template=title,
            content_template=content,is_active=True))
    db.commit()

def render_template(template:NotificationTemplate,data:dict)->tuple[str,str]:
    values=SafeDict({k:str(v) for k,v in (data or {}).items()})
    return template.title_template.replace("{{","{").replace("}}","}").format_map(values),template.content_template.replace("{{","{").replace("}}","}").format_map(values)

def get_preference(db:Session,user_id=None,customer_id=None)->NotificationPreference:
    q=db.query(NotificationPreference)
    pref=q.filter(NotificationPreference.user_id==user_id).first() if user_id else q.filter(NotificationPreference.customer_id==customer_id).first()
    if not pref:
        pref=NotificationPreference(user_id=user_id,customer_id=customer_id);db.add(pref);db.flush()
    return pref

def respect_notification_preferences(db:Session,job:NotificationJob)->bool:
    pref=get_preference(db,job.recipient_user_id,job.recipient_customer_id)
    if job.category=="marketing" and pref.is_unsubscribed:return False
    if job.category=="service" and job.channel=="in_app":return True
    return {"in_app":pref.receive_in_app,"email":pref.receive_email,"sms":pref.receive_sms,
            "wecom_webhook":pref.receive_wecom,"mock":True}.get(job.channel,True)

def _quiet_until(pref:NotificationPreference,now:datetime)->datetime|None:
    try:
        start=datetime.strptime(pref.quiet_hours_start,"%H:%M").time();end=datetime.strptime(pref.quiet_hours_end,"%H:%M").time()
    except (TypeError,ValueError):return None
    current=now.time()
    inside=(start<=current<end) if start<end else (current>=start or current<end)
    if not inside:return None
    target=datetime.combine(now.date(),end)
    if target<=now:target+=timedelta(days=1)
    return target

def create_notification_job(db:Session,template_key:str,data:dict|None=None,
    recipient_user_id:int|None=None,recipient_customer_id:int|None=None,
    channel:str|None=None,scheduled_at:datetime|None=None,related_type:str="",
    related_id:int|None=None,commit:bool=True)->NotificationJob:
    template=db.query(NotificationTemplate).filter(NotificationTemplate.template_key==template_key).first()
    if not template:raise ValueError(f"通知模板不存在：{template_key}")
    if not template.is_active:raise ValueError(f"通知模板已停用：{template_key}")
    title,content=render_template(template,data or {});validate_template_content(title,content)
    final_channel=channel or template.channel
    if final_channel in {"email","sms"}:content += "\n\n如不希望接收营销信息，请在客户门户通知偏好中退订。"
    customer=db.get(CustomerAccount,recipient_customer_id) if recipient_customer_id else None
    max_retries=int(get_setting(db,"notification_max_retries","3"))
    payload=dict(data or {})
    if customer:payload.setdefault("lead_id",customer.lead_id)
    job=NotificationJob(template_key=template_key,audience_type=template.audience_type,
        channel=final_channel,category=template.category,
        recipient_type="customer" if customer else "user",recipient_user_id=recipient_user_id,
        recipient_customer_id=recipient_customer_id,recipient_phone=customer.phone if customer else "",
        recipient_email=customer.email if customer else "",recipient_wechat_id=customer.wechat_id if customer else "",
        title=title,content=content,payload_json=json.dumps(payload,ensure_ascii=False),
        related_type=related_type,related_id=related_id,send_status="queued",max_retries=max_retries,
        scheduled_at=scheduled_at or datetime.now())
    db.add(job);db.flush();track_event(db,"notification_job_created",customer.assessment_id if customer else None,
        customer.lead_id if customer else None,{"job_id":job.id,"template_key":template_key,"channel":job.channel},commit=False)
    if commit:db.commit();db.refresh(job)
    return job

def send_notification_job(db:Session,job:NotificationJob,force:bool=False)->NotificationJob:
    if job.send_status in {"success","cancelled","skipped"}:return job
    pref=get_preference(db,job.recipient_user_id,job.recipient_customer_id)
    quiet_until=_quiet_until(pref,datetime.now()) if not force else None
    if quiet_until:
        job.send_status="queued";job.scheduled_at=quiet_until;job.error_message="勿扰时间内已顺延";db.commit();return job
    if not respect_notification_preferences(db,job):
        job.send_status="skipped";job.error_message="接收人通知偏好已关闭";db.commit();return job
    job.send_status="sending";db.flush();request_payload={"title":job.title,"content":job.content,"channel":job.channel}
    try:
        adapter=CHANNELS.get(job.channel,CHANNELS["mock"]);response=adapter.send(db,job)
        job.send_status="success";job.sent_at=datetime.now();job.error_message=""
        db.add(NotificationLog(job_id=job.id,channel=job.channel,status="success",
            request_payload_json=json.dumps(request_payload,ensure_ascii=False),response_json=json.dumps(response,ensure_ascii=False)))
        track_event(db,"notification_sent",data={"job_id":job.id,"channel":job.channel},commit=False)
    except Exception as exc:
        job.retry_count+=1;job.failed_at=datetime.now();job.error_message=f"{type(exc).__name__}: {exc}"
        job.send_status="queued" if job.retry_count<job.max_retries else "failed"
        db.add(NotificationLog(job_id=job.id,channel=job.channel,status="failed",
            request_payload_json=json.dumps(request_payload,ensure_ascii=False),error_message=job.error_message))
        track_event(db,"notification_failed",data={"job_id":job.id,"error":job.error_message},commit=False)
        logger.warning("通知发送失败 job_id=%s error=%s",job.id,job.error_message)
    job.updated_at=datetime.now();db.commit();db.refresh(job);return job

def send_now(db:Session,job:NotificationJob):job.scheduled_at=datetime.now();job.send_status="queued";db.commit();return send_notification_job(db,job,force=True)
def retry_failed_jobs(db:Session,limit:int=100):
    jobs=db.query(NotificationJob).filter(NotificationJob.send_status.in_(["failed","queued"]),
        NotificationJob.retry_count<NotificationJob.max_retries,NotificationJob.scheduled_at<=datetime.now()).limit(limit).all()
    for job in jobs:
        if job.retry_count:track_event(db,"notification_retried",data={"job_id":job.id,"retry":job.retry_count+1})
        send_notification_job(db,job)
    track_event(db,"notification_worker_run",data={"jobs":len(jobs)});return jobs
def cancel_notification_job(db:Session,job:NotificationJob):
    if job.send_status not in {"success","cancelled"}:job.send_status="cancelled";job.updated_at=datetime.now();track_event(db,"notification_cancelled",data={"job_id":job.id},commit=False);db.commit()
    return job
def safe_create_notification(db:Session,*args,**kwargs):
    try:
        kwargs["commit"]=False
        with db.begin_nested(): return create_notification_job(db,*args,**kwargs)
    except Exception as exc:
        logger.warning("通知任务创建降级 template=%s error=%s",args[0] if args else kwargs.get('template_key'),exc)
        return None
