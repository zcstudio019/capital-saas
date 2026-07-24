import hashlib
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_
from sqlalchemy.orm import Session

from core.access_scope import get_access_scope
from core.config import BASE_DIR, settings
from core.pricing_engine import PRODUCT_RANK, products
from core.data_masking import mask_phone
from core.capital_health_report import build_capital_health_report
from db.database import get_db
from db.models import (ConsultingCase, CustomerAccessToken, CustomerAccount,
    CustomerConfirmation, CustomerMessage, CustomerTask, Event, FinancingProject,
    FundingApplication, Lead, Order, ProjectTimelineEvent, Report, UploadedDocument, User)
from services.auth_service import require_roles
from services.customer_portal_service import (advisor_context, complete_document_tasks,
    ensure_customer_account, ensure_document_tasks, generate_login_token, portal_completeness,
    require_customer, send_customer_message)
from services.document_parse_service import classify_document, run_parse_task
from services.event_service import track_event
from services.pilot_service import set_pilot_stage
from services.report_access_service import (
    build_bank_product_detail_context,
    build_report_access_context,
)
from services.report_service import generate_full_report, parse_customer_report, parse_report
from services.settings_service import get_setting

router=APIRouter();templates=Jinja2Templates(directory=str(BASE_DIR/"templates"))
UPLOAD_DIR=BASE_DIR/"data"/"uploads"
ALLOWED={".pdf",".doc",".docx",".xls",".xlsx",".png",".jpg",".jpeg"}
BACKEND=("admin","super_admin","city_manager","sales_manager","sales","consultant_manager","consultant","viewer")
WRITE=("admin","super_admin","city_manager","sales_manager","sales","consultant_manager","consultant")
CLIENT_PROJECT_STATUS={"draft":"服务准备中","preparing":"资料准备中","submitted":"已提交申请",
 "bank_review":"金融机构审核中","supplement_required":"需要补充资料","approved":"已获得批复",
 "rejected":"暂未通过，正在优化方案","disbursed":"已放款","cancelled":"服务已取消","archived":"已归档"}

def _lead(db,id):
    x=db.get(Lead,id)
    if not x:raise HTTPException(404,"线索不存在")
    return x
def _customer(db,id):
    x=db.get(CustomerAccount,id)
    if not x:raise HTTPException(404,"客户门户不存在")
    return x
def _customer_access(db,user,customer):
    lead=_lead(db,customer.lead_id);scope=get_access_scope(db,user)
    if scope.can_view_all:return lead
    if scope.role=="sales" and lead.owner_user_id!=user.id:raise HTTPException(403,"无权查看该客户")
    if scope.role=="consultant":
        case=db.query(ConsultingCase).filter(ConsultingCase.lead_id==lead.id,
            or_(ConsultingCase.consultant_user_id==user.id,ConsultingCase.consultant_id==user.id)).first()
        if not case:raise HTTPException(403,"无权查看该客户")
    elif lead.owner_org_id not in scope.allowed_org_ids:raise HTTPException(403,"无权查看该客户")
    return lead
def _latest_product(orders):
    paid=[x for x in orders if x.status=="paid"]
    return max((x.product_code for x in paid),key=lambda x:PRODUCT_RANK.get(x,0),default="未购买")
def _client_context(db,customer):
    lead=_lead(db,customer.lead_id);orders=db.query(Order).filter(Order.assessment_id==customer.assessment_id).all()
    project=db.query(FinancingProject).filter(FinancingProject.lead_id==lead.id).order_by(FinancingProject.id.desc()).first()
    report=db.query(Report).filter(Report.assessment_id==customer.assessment_id).first()
    completeness=portal_completeness(db,customer)
    return {"customer":customer,"lead":lead,"assessment":lead.assessment,"orders":orders,
        "product":_latest_product(orders),"project":project,"report_item":report,"completeness":completeness,
        "advisor":advisor_context(db,lead.id),"project_status":CLIENT_PROJECT_STATUS}

@router.get('/client/login-token/{token}')
def client_login(request:Request,token:str,db:Session=Depends(get_db)):
    item=db.query(CustomerAccessToken).filter(CustomerAccessToken.token==token,
        CustomerAccessToken.is_active.is_(True)).first()
    if not item or item.expired_at<datetime.now():raise HTTPException(401,"客户登录链接不存在或已过期")
    customer=_customer(db,item.customer_id)
    if not customer.is_active:raise HTTPException(403,"客户门户已停用")
    request.session.clear();request.session['customer_id']=customer.id;request.session['customer_lead_id']=customer.lead_id
    item.used_at=datetime.now();customer.last_login_at=datetime.now()
    track_event(db,'customer_logged_in',customer.assessment_id,customer.lead_id,{"customer_id":customer.id},commit=False)
    db.commit();return RedirectResponse('/client/dashboard',303)

@router.get('/client/logout')
def client_logout(request:Request):request.session.clear();return RedirectResponse('/',303)

@router.get('/client/dashboard',response_class=HTMLResponse)
def client_dashboard(request:Request,db:Session=Depends(get_db),customer:CustomerAccount=Depends(require_customer)):
    from services.legal_service import missing_acceptances
    legal_pending=missing_acceptances(db,customer,['user_agreement','privacy_policy','data_authorization'])
    if settings.app_env=='production' and legal_pending:return RedirectResponse('/client/legal',303)
    ensure_document_tasks(db,customer);ctx=_client_context(db,customer)
    ctx.update({"legal_pending":legal_pending,"tasks":db.query(CustomerTask).filter(CustomerTask.customer_id==customer.id,CustomerTask.status=='pending').order_by(CustomerTask.due_time).limit(8).all(),
        "messages":db.query(CustomerMessage).filter(CustomerMessage.customer_id==customer.id).order_by(CustomerMessage.created_at.desc()).limit(5).all(),
        "confirmations":db.query(CustomerConfirmation).filter(CustomerConfirmation.customer_id==customer.id,CustomerConfirmation.status=='pending').all()})
    track_event(db,'client_dashboard_viewed',customer.assessment_id,customer.lead_id,{"customer_id":customer.id})
    return templates.TemplateResponse(request=request,name='client_dashboard.html',context=ctx)

@router.get('/client/reports',response_class=HTMLResponse)
def client_reports(request:Request,db:Session=Depends(get_db),customer:CustomerAccount=Depends(require_customer)):
    reports=db.query(Report).filter(Report.assessment_id==customer.assessment_id).all()
    orders=db.query(Order).filter(Order.assessment_id==customer.assessment_id,Order.status=='paid').all()
    return templates.TemplateResponse(request=request,name='client_reports.html',context={'customer':customer,'reports':reports,'unlocked':bool(orders)})

def _client_report(db,customer,report_id):
    report=db.get(Report,report_id)
    if not report or report.assessment_id!=customer.assessment_id:raise HTTPException(404,"报告不存在")
    return report
@router.get('/client/reports/{report_id}',response_class=HTMLResponse)
def client_report(request:Request,report_id:int,db:Session=Depends(get_db),customer:CustomerAccount=Depends(require_customer)):
    report=_client_report(db,customer,report_id);paid=db.query(Order).filter(Order.assessment_id==customer.assessment_id,Order.status=='paid').first()
    if not paid:return templates.TemplateResponse(request=request,name='client_notice.html',context={'customer':customer,'title':'报告尚未解锁','message':'该报告尚未解锁。'})
    if report.review_status!='approved':return templates.TemplateResponse(request=request,name='client_notice.html',context={'customer':customer,'title':'报告审核中','message':'报告正在生成/审核中，请稍后查看。'})
    generate_full_report(db, report.assessment)
    full=parse_customer_report(report);health_report=build_capital_health_report(db,report.assessment);track_event(db,'client_report_viewed',customer.assessment_id,customer.lead_id,{'report_id':report.id});set_pilot_stage(db,db.get(Lead,customer.lead_id),'report_viewed',commit=True)
    access_context=build_report_access_context(db,report.assessment,full,base_path=f'/client/reports/{report.id}')
    return templates.TemplateResponse(request=request,name='client_report.html',context={'customer':customer,'assessment':report.assessment,'report':full,'health_report':health_report,'print_mode':False,**access_context})
@router.get('/client/reports/{report_id}/print',response_class=HTMLResponse)
def client_report_print(request:Request,report_id:int,db:Session=Depends(get_db),customer:CustomerAccount=Depends(require_customer)):
    report=_client_report(db,customer,report_id)
    if report.review_status!='approved' or not db.query(Order).filter(Order.assessment_id==customer.assessment_id,Order.status=='paid').first():raise HTTPException(403,"报告尚不可打印")
    generate_full_report(db, report.assessment)
    full=parse_customer_report(report);health_report=build_capital_health_report(db,report.assessment);access_context=build_report_access_context(db,report.assessment,full,base_path=f'/client/reports/{report.id}')
    return templates.TemplateResponse(request=request,name='client_report.html',context={'customer':customer,'assessment':report.assessment,'report':full,'health_report':health_report,'print_mode':True,**access_context})

@router.get('/client/reports/{report_id}/bank-products/{product_id}',response_class=HTMLResponse)
def client_bank_product_detail(request:Request,report_id:int,product_id:int,db:Session=Depends(get_db),customer:CustomerAccount=Depends(require_customer)):
    report=_client_report(db,customer,report_id)
    paid=db.query(Order).filter(Order.assessment_id==customer.assessment_id,Order.status=='paid').first()
    if not paid:return templates.TemplateResponse(request=request,name='client_notice.html',context={'customer':customer,'title':'报告尚未解锁','message':'该报告尚未解锁。'})
    if report.review_status!='approved':return templates.TemplateResponse(request=request,name='client_notice.html',context={'customer':customer,'title':'报告审核中','message':'报告正在生成/审核中，请稍后查看。'})
    generate_full_report(db, report.assessment)
    full=parse_customer_report(report)
    detail_context=build_bank_product_detail_context(db,report.assessment,full,product_id)
    if detail_context is None:raise HTTPException(404,'银行产品不存在')
    return templates.TemplateResponse(request=request,name='report_bank_product_detail.html',context={'customer':customer,'assessment':report.assessment,'report':full,'back_url':f'/client/reports/{report.id}','checkout_base':f'/checkout/{customer.assessment_id}',**detail_context})

@router.get('/client/documents',response_class=HTMLResponse)
def client_documents(request:Request,db:Session=Depends(get_db),customer:CustomerAccount=Depends(require_customer)):
    ensure_document_tasks(db,customer);ctx=_client_context(db,customer);ctx['documents']=db.query(UploadedDocument).filter(UploadedDocument.lead_id==customer.lead_id,UploadedDocument.deleted_at.is_(None)).order_by(UploadedDocument.created_at.desc()).all()
    ctx['max_mb']=int(get_setting(db,'upload_max_mb',str(settings.upload_max_mb)))
    return templates.TemplateResponse(request=request,name='client_documents.html',context=ctx)

@router.post('/client/documents/upload')
async def client_document_upload(request:Request,document_category:str=Form('其他资料'),note:str=Form(''),files:list[UploadFile]=File(...),
    db:Session=Depends(get_db),customer:CustomerAccount=Depends(require_customer)):
    from services.legal_service import missing_acceptances
    if settings.app_env=='production' and missing_acceptances(db,customer,['document_submission_authorization']):raise HTTPException(403,'上传资料前请先确认资料提交授权')
    from utils.file_security import enforce_lead_total,validate_upload_metadata
    from services.audit_service import write_audit_log
    root=UPLOAD_DIR/str(customer.lead_id);root.mkdir(parents=True,exist_ok=True);max_size=int(get_setting(db,'upload_max_mb',str(settings.upload_max_mb)))*1024*1024
    for upload in files:
        try:original,ext=validate_upload_metadata(upload)
        except HTTPException as exc:track_event(db,'file_security_rejected',customer.assessment_id,customer.lead_id,{'reason':str(exc.detail)});raise
        data=await upload.read(max_size+1)
        if not data:raise HTTPException(400,'文件内容为空')
        if len(data)>max_size:raise HTTPException(400,'文件超过上传大小限制')
        enforce_lead_total(db,customer.lead_id,len(data),int(get_setting(db,'max_lead_upload_mb',str(settings.max_lead_upload_mb))))
        saved=root/f'{uuid.uuid4().hex}{ext}';saved.write_bytes(data)
        doc=UploadedDocument(lead_id=customer.lead_id,assessment_id=customer.assessment_id,
            file_name=original,file_path=str(saved.relative_to(BASE_DIR)).replace('\\','/'),
            file_type=ext.lstrip('.'),document_category=classify_document(upload.filename or '',document_category),
            uploaded_by=None,customer_id=customer.id,uploaded_source='customer',file_size=len(data),
            file_hash=hashlib.sha256(data).hexdigest(),note=note.strip())
        db.add(doc);db.flush();complete_document_tasks(db,customer,doc)
        from services.notification_service import notify_document_uploaded, safe_create_notification
        lead=db.get(Lead,customer.lead_id);case=db.query(ConsultingCase).filter(ConsultingCase.lead_id==lead.id).order_by(ConsultingCase.id.desc()).first()
        recipients={lead.owner_user_id,(case.consultant_user_id or case.consultant_id) if case else None}
        for user_id in recipients:
            if user_id:safe_create_notification(db,'document_uploaded_consultant',{'company_name':customer.company_name,'document_name':doc.file_name},recipient_user_id=user_id,related_type='uploaded_document',related_id=doc.id)
        notify_document_uploaded(db, lead, doc, commit=False)
        write_audit_log(db,'customer_document_uploaded','uploaded_document',doc.id,customer_id=customer.id,actor_type='customer',after={'file_name':doc.file_name,'size':doc.file_size},request=request,risk_level='medium')
        track_event(db,'client_document_uploaded',customer.assessment_id,customer.lead_id,{'document_id':doc.id,'customer_id':customer.id},commit=False);set_pilot_stage(db,db.get(Lead,customer.lead_id),'documents_uploaded',commit=False);db.commit();run_parse_task(db,doc)
    return RedirectResponse('/client/documents',303)

@router.get('/client/tasks',response_class=HTMLResponse)
def client_tasks(request:Request,db:Session=Depends(get_db),customer:CustomerAccount=Depends(require_customer)):
    ensure_document_tasks(db,customer);items=db.query(CustomerTask).filter(CustomerTask.customer_id==customer.id).order_by(CustomerTask.status,CustomerTask.due_time).all()
    return templates.TemplateResponse(request=request,name='client_tasks.html',context={'customer':customer,'tasks':items})
@router.post('/client/tasks/{task_id}/complete')
def client_task_complete(task_id:int,db:Session=Depends(get_db),customer:CustomerAccount=Depends(require_customer)):
    task=db.get(CustomerTask,task_id)
    if not task or task.customer_id!=customer.id:raise HTTPException(404,'任务不存在')
    task.status='done';task.completed_at=task.updated_at=datetime.now();track_event(db,'client_task_completed',customer.assessment_id,customer.lead_id,{'task_id':task.id},commit=False);db.commit();return RedirectResponse('/client/tasks',303)

@router.get('/client/projects',response_class=HTMLResponse)
def client_projects(request:Request,db:Session=Depends(get_db),customer:CustomerAccount=Depends(require_customer)):
    items=db.query(FinancingProject).filter(FinancingProject.lead_id==customer.lead_id).order_by(FinancingProject.updated_at.desc()).all()
    return templates.TemplateResponse(request=request,name='client_projects.html',context={'customer':customer,'projects':items,'status_map':CLIENT_PROJECT_STATUS})
@router.get('/client/projects/{project_id}',response_class=HTMLResponse)
def client_project(request:Request,project_id:int,db:Session=Depends(get_db),customer:CustomerAccount=Depends(require_customer)):
    project=db.get(FinancingProject,project_id)
    if not project or project.lead_id!=customer.lead_id:raise HTTPException(404,'项目不存在')
    apps=db.query(FundingApplication).filter(FundingApplication.project_id==project.id).all();timeline=db.query(ProjectTimelineEvent).filter(ProjectTimelineEvent.project_id==project.id).order_by(ProjectTimelineEvent.created_at.desc()).limit(12).all()
    track_event(db,'client_project_viewed',customer.assessment_id,customer.lead_id,{'project_id':project.id})
    return templates.TemplateResponse(request=request,name='client_project_detail.html',context={'customer':customer,'project':project,'applications':apps,'timeline':timeline,'status_map':CLIENT_PROJECT_STATUS,'advisor':advisor_context(db,customer.lead_id)})

@router.get('/client/messages',response_class=HTMLResponse)
def client_messages(request:Request,db:Session=Depends(get_db),customer:CustomerAccount=Depends(require_customer)):
    items=db.query(CustomerMessage).filter(CustomerMessage.customer_id==customer.id,CustomerMessage.status!='archived').order_by(CustomerMessage.created_at.desc()).all();return templates.TemplateResponse(request=request,name='client_messages.html',context={'customer':customer,'messages':items})
@router.get('/client/messages/{message_id}',response_class=HTMLResponse)
def client_message(request:Request,message_id:int,db:Session=Depends(get_db),customer:CustomerAccount=Depends(require_customer)):
    item=db.get(CustomerMessage,message_id)
    if not item or item.customer_id!=customer.id:raise HTTPException(404,'消息不存在')
    if item.status=='unread':item.status='read';item.read_at=datetime.now();track_event(db,'customer_message_read',customer.assessment_id,customer.lead_id,{'message_id':item.id},commit=False);db.commit()
    return templates.TemplateResponse(request=request,name='client_message_detail.html',context={'customer':customer,'message':item})

@router.get('/client/confirmations',response_class=HTMLResponse)
def client_confirmations(request:Request,db:Session=Depends(get_db),customer:CustomerAccount=Depends(require_customer)):
    items=db.query(CustomerConfirmation).filter(CustomerConfirmation.customer_id==customer.id).order_by(CustomerConfirmation.created_at.desc()).all();return templates.TemplateResponse(request=request,name='client_confirmations.html',context={'customer':customer,'confirmations':items})
def _confirmation_action(request,db,customer,id,status):
    item=db.get(CustomerConfirmation,id)
    if not item or item.customer_id!=customer.id:raise HTTPException(404,'确认事项不存在')
    item.status=status;item.confirmed_at=datetime.now();item.ip_address=request.client.host if request.client else '';item.user_agent=request.headers.get('user-agent','')[:500]
    track_event(db,f'customer_confirmation_{status}',customer.assessment_id,customer.lead_id,{'confirmation_id':item.id},commit=False);db.commit();return RedirectResponse('/client/confirmations',303)
@router.post('/client/confirmations/{confirmation_id}/confirm')
def confirmation_confirm(request:Request,confirmation_id:int,db:Session=Depends(get_db),customer:CustomerAccount=Depends(require_customer)):return _confirmation_action(request,db,customer,confirmation_id,'confirmed')
@router.post('/client/confirmations/{confirmation_id}/reject')
def confirmation_reject(request:Request,confirmation_id:int,db:Session=Depends(get_db),customer:CustomerAccount=Depends(require_customer)):return _confirmation_action(request,db,customer,confirmation_id,'rejected')

@router.get('/client/orders',response_class=HTMLResponse)
def client_orders(request:Request,db:Session=Depends(get_db),customer:CustomerAccount=Depends(require_customer)):
    items=db.query(Order).filter(Order.assessment_id==customer.assessment_id).order_by(Order.created_at.desc()).all();return templates.TemplateResponse(request=request,name='client_orders.html',context={'customer':customer,'orders':items})
@router.get('/client/upgrade',response_class=HTMLResponse)
def client_upgrade(request:Request,db:Session=Depends(get_db),customer:CustomerAccount=Depends(require_customer)):
    track_event(db,'client_upgrade_viewed',customer.assessment_id,customer.lead_id,{'customer_id':customer.id});return templates.TemplateResponse(request=request,name='client_upgrade.html',context={'customer':customer,'products':products})
@router.get('/client/upgrade/{product_code}')
def client_upgrade_click(product_code:str,db:Session=Depends(get_db),customer:CustomerAccount=Depends(require_customer)):
    if product_code not in products:raise HTTPException(404,'产品不存在')
    track_event(db,'client_upgrade_clicked',customer.assessment_id,customer.lead_id,{'product_code':product_code});return RedirectResponse(f'/checkout/{customer.assessment_id}?product={product_code}&upgrade=1&from_product=client_portal',303)

@router.get('/admin/client-portals',response_class=HTMLResponse)
def admin_portals(request:Request,db:Session=Depends(get_db),user:User=Depends(require_roles(*BACKEND))):
    scope=get_access_scope(db,user);q=db.query(CustomerAccount).join(Lead,Lead.id==CustomerAccount.lead_id)
    if not scope.can_view_all:
        if scope.role=='sales':q=q.filter(Lead.owner_user_id==user.id)
        elif scope.role=='consultant':q=q.join(ConsultingCase,ConsultingCase.lead_id==Lead.id).filter(or_(ConsultingCase.consultant_user_id==user.id,ConsultingCase.consultant_id==user.id))
        else:q=q.filter(Lead.owner_org_id.in_(scope.allowed_org_ids or [-1]))
    customers=q.order_by(CustomerAccount.created_at.desc()).all();stats={c.id:{'tasks':db.query(CustomerTask).filter_by(customer_id=c.id,status='pending').count(),'messages':db.query(CustomerMessage).filter_by(customer_id=c.id,status='unread').count(),'documents':db.query(UploadedDocument).filter_by(lead_id=c.lead_id).count()} for c in customers};role=get_access_scope(db,user).role;phones={c.id:(c.phone if role=='super_admin' or db.get(Lead,c.lead_id).owner_user_id==user.id else mask_phone(c.phone)) for c in customers}
    return templates.TemplateResponse(request=request,name='admin_client_portals.html',context={'customers':customers,'stats':stats,'phones':phones,'current_user':user})
@router.get('/admin/client-portals/{customer_id}',response_class=HTMLResponse)
def admin_portal_detail(request:Request,customer_id:int,db:Session=Depends(get_db),user:User=Depends(require_roles(*BACKEND))):
    customer=_customer(db,customer_id);lead=_customer_access(db,user,customer);ctx=_client_context(db,customer);ctx.update({'current_user':user,'documents':db.query(UploadedDocument).filter_by(lead_id=lead.id).all(),'tasks':db.query(CustomerTask).filter_by(customer_id=customer.id).all(),'messages':db.query(CustomerMessage).filter_by(customer_id=customer.id).order_by(CustomerMessage.created_at.desc()).all(),'confirmations':db.query(CustomerConfirmation).filter_by(customer_id=customer.id).all(),'events':db.query(Event).filter(Event.lead_id==lead.id,Event.event_type.like('client_%')).order_by(Event.created_at.desc()).limit(20).all()});return templates.TemplateResponse(request=request,name='admin_client_portal_detail.html',context=ctx)
@router.post('/admin/leads/{lead_id}/client-portal/open')
def open_portal(lead_id:int,db:Session=Depends(get_db),user:User=Depends(require_roles(*WRITE))):
    customer=ensure_customer_account(db,_lead(db,lead_id));customer.is_active=True;db.commit();return RedirectResponse(f'/admin/client-portals/{customer.id}',303)
@router.post('/admin/client-portals/{customer_id}/generate-token')
def admin_generate_token(customer_id:int,db:Session=Depends(get_db),user:User=Depends(require_roles(*WRITE))):
    customer=_customer(db,customer_id);_customer_access(db,user,customer);token=generate_login_token(db,customer);return RedirectResponse(f'/admin/client-portals/{customer.id}?login_link=/client/login-token/{token.token}',303)
@router.post('/admin/client-portals/{customer_id}/toggle')
def toggle_portal(customer_id:int,db:Session=Depends(get_db),user:User=Depends(require_roles(*WRITE))):
    customer=_customer(db,customer_id);_customer_access(db,user,customer);customer.is_active=not customer.is_active;db.commit();return RedirectResponse(f'/admin/client-portals/{customer.id}',303)
@router.post('/admin/leads/{lead_id}/messages/send')
def admin_send_message(lead_id:int,title:str=Form(...),content:str=Form(...),message_type:str=Form('advisor'),db:Session=Depends(get_db),user:User=Depends(require_roles(*WRITE))):
    customer=ensure_customer_account(db,_lead(db,lead_id));_customer_access(db,user,customer);send_customer_message(db,customer,title.strip(),content.strip(),message_type,user.id);return RedirectResponse(f'/admin/client-portals/{customer.id}',303)
@router.post('/admin/leads/{lead_id}/customer-tasks/create')
def admin_create_customer_task(lead_id:int,task_type:str=Form('other'),task_title:str=Form(...),task_content:str=Form(''),priority:str=Form('medium'),due_time:str=Form(''),related_project_id:int=Form(0),db:Session=Depends(get_db),user:User=Depends(require_roles(*WRITE))):
    customer=ensure_customer_account(db,_lead(db,lead_id));_customer_access(db,user,customer);db.add(CustomerTask(customer_id=customer.id,lead_id=lead_id,assessment_id=customer.assessment_id,related_project_id=related_project_id or None,task_type=task_type,task_title=task_title.strip(),task_content=task_content.strip(),priority=priority,due_time=datetime.fromisoformat(due_time) if due_time else datetime.now()+timedelta(days=3)));db.commit();return RedirectResponse(f'/admin/client-portals/{customer.id}',303)
@router.post('/admin/leads/{lead_id}/confirmations/create')
def admin_create_confirmation(lead_id:int,confirmation_type:str=Form(...),title:str=Form(...),content:str=Form(...),related_project_id:int=Form(0),db:Session=Depends(get_db),user:User=Depends(require_roles(*WRITE))):
    customer=ensure_customer_account(db,_lead(db,lead_id));_customer_access(db,user,customer);item=CustomerConfirmation(customer_id=customer.id,lead_id=lead_id,assessment_id=customer.assessment_id,related_project_id=related_project_id or None,confirmation_type=confirmation_type,title=title.strip(),content=content.strip());db.add(item);db.flush();track_event(db,'customer_confirmation_created',customer.assessment_id,lead_id,{'confirmation_id':item.id},commit=False);db.commit();return RedirectResponse(f'/admin/client-portals/{customer.id}',303)
