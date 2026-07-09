import csv,io,json,os,platform,sys,zipfile
from datetime import datetime,timedelta
from pathlib import Path

from fastapi import APIRouter,Depends,Form,HTTPException,Request
from fastapi.responses import FileResponse,HTMLResponse,RedirectResponse,Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import func,text
from sqlalchemy.orm import Session

from core.access_scope import effective_role,get_access_scope
from core.config import BASE_DIR,settings
from core.data_masking import mask_phone,mask_wechat
from db.database import engine,get_db
from db.models import (Assessment,AuditLog,CustomerAccount,CustomerConfirmation,Event,
    FinancingProject,InternalNotification,Lead,LegalAcceptance,LegalDocument,Order,
    Organization,Report,UploadedDocument,User,WorkerRun)
from services.audit_service import write_audit_log
from services.auth_service import hash_password,require_roles,update_password,verify_password
from services.backup_service import create_database_backup,list_backups,safe_backup_path
from services.customer_portal_service import require_customer
from services.event_service import track_event

router=APIRouter();templates=Jinja2Templates(directory=str(BASE_DIR/'templates'))
ADMIN=("admin","super_admin");USER_VIEW=("admin","super_admin","city_manager")
ROLES=("super_admin","city_manager","sales_manager","sales","consultant_manager","consultant","finance","viewer","partner")
MANAGED_USER_ROLES=("sales","sales_manager","viewer")

def _csv_bytes(headers,rows):
    out=io.StringIO();w=csv.writer(out);w.writerow(headers);w.writerows(rows);return ('\ufeff'+out.getvalue()).encode('utf-8')
def _user(db,id):
    x=db.get(User,id)
    if not x:raise HTTPException(404,'用户不存在')
    return x

@router.get('/admin/account/security',response_class=HTMLResponse)
def account_security(request:Request,user:User=Depends(require_roles(*ROLES,"admin"))):return templates.TemplateResponse(request=request,name='admin_account_security.html',context={'current_user':user})
@router.get('/admin/account/password',response_class=HTMLResponse)
def account_password(request:Request,user:User=Depends(require_roles(*ROLES,"admin"))):return templates.TemplateResponse(request=request,name='admin_account_password.html',context={'current_user':user,'error':''})
@router.post('/admin/account/password')
def account_password_update(request:Request,current_password:str=Form(...),new_password:str=Form(...),db:Session=Depends(get_db),user:User=Depends(require_roles(*ROLES,"admin"))):
    if not verify_password(current_password,user.password_hash):return templates.TemplateResponse(request=request,name='admin_account_password.html',context={'current_user':user,'error':'当前密码错误'},status_code=400)
    if len(new_password)<10 or new_password.lower() in {'admin123','password123'}:return templates.TemplateResponse(request=request,name='admin_account_password.html',context={'current_user':user,'error':'新密码至少10位且不能使用默认弱密码'},status_code=400)
    update_password(db,user,new_password);write_audit_log(db,'password_changed','user',user.id,user_id=user.id,request=request,risk_level='high',commit=False);db.commit();request.session['session_version']=user.session_version;track_event(db,'password_changed',data={'user_id':user.id});return RedirectResponse('/admin/account/security',303)
@router.post('/admin/account/logout-all')
def logout_all(request:Request,db:Session=Depends(get_db),user:User=Depends(require_roles(*ROLES,"admin"))):
    user.session_version=(user.session_version or 1)+1;write_audit_log(db,'logout_all_sessions','user',user.id,user_id=user.id,request=request,risk_level='high');db.commit();request.session.clear();return RedirectResponse('/login',303)

@router.get('/admin/users',response_class=HTMLResponse)
def managed_users_page(request:Request,db:Session=Depends(get_db),user:User=Depends(require_roles("admin","super_admin"))):
    return templates.TemplateResponse(request=request,name='admin_users.html',context={'items':db.query(User).order_by(User.id).all(),'organizations':db.query(Organization).filter_by(status='active').all(),'roles':MANAGED_USER_ROLES,'current_user':user,'can_edit':True})

@router.post('/admin/users/create')
def managed_user_create(request:Request,username:str=Form(...),password:str=Form(...),display_name:str=Form(''),phone:str=Form(''),role:str=Form('sales'),is_active:bool=Form(True),org_id:int=Form(0),db:Session=Depends(get_db),user:User=Depends(require_roles("admin","super_admin"))):
    if role not in MANAGED_USER_ROLES and user.role!='super_admin':raise HTTPException(403,'无权创建该角色')
    if db.query(User).filter_by(username=username.strip()).first():raise HTTPException(400,'用户名已存在')
    if len(password)<10:raise HTTPException(400,'初始密码至少10位')
    item=User(username=username.strip(),display_name=display_name.strip(),phone=phone.strip(),password_hash=hash_password(password),role=role,org_id=org_id or None,is_active=is_active,force_password_change=True,session_version=1);db.add(item);db.flush();write_audit_log(db,'user_created','user',item.id,user_id=user.id,after={'username':item.username,'display_name':item.display_name,'phone':item.phone,'role':role,'org_id':org_id,'is_active':is_active},request=request,risk_level='high');track_event(db,'user_created',data={'user_id':item.id},commit=False);db.commit();return RedirectResponse('/admin/users',303)

@router.post('/admin/users/{user_id}/update')
def managed_user_update(request:Request,user_id:int,display_name:str=Form(''),phone:str=Form(''),role:str=Form(...),is_active:bool=Form(False),org_id:int=Form(0),db:Session=Depends(get_db),operator:User=Depends(require_roles("admin","super_admin"))):
    if role not in MANAGED_USER_ROLES and operator.role!='super_admin':raise HTTPException(403,'无权分配该角色')
    item=_user(db,user_id);before={'display_name':item.display_name,'phone':item.phone,'role':item.role,'org_id':item.org_id,'is_active':item.is_active};item.display_name=display_name.strip();item.phone=phone.strip();item.role=role;item.org_id=org_id or None;item.is_active=is_active;item.updated_at=datetime.now();write_audit_log(db,'user_updated','user',item.id,user_id=operator.id,before=before,after={'display_name':item.display_name,'phone':item.phone,'role':role,'org_id':org_id,'is_active':is_active},request=request,risk_level='high');db.commit();return RedirectResponse('/admin/users',303)

@router.post('/admin/users/{user_id}/reset-password')
def managed_reset_password(request:Request,user_id:int,new_password:str=Form(...),db:Session=Depends(get_db),operator:User=Depends(require_roles("admin","super_admin"))):
    if len(new_password)<10:raise HTTPException(400,'密码至少10位')
    item=_user(db,user_id);item.password_hash=hash_password(new_password);item.force_password_change=True;item.password_changed_at=None;item.session_version=(item.session_version or 1)+1;write_audit_log(db,'user_password_reset','user',item.id,user_id=operator.id,request=request,risk_level='critical');db.commit();return RedirectResponse('/admin/users',303)

@router.post('/admin/users/{user_id}/disable')
def managed_disable_user(request:Request,user_id:int,db:Session=Depends(get_db),operator:User=Depends(require_roles("admin","super_admin"))):
    return _set_user_active(db,_user(db,user_id),False,operator,request)

@router.post('/admin/users/{user_id}/enable')
def managed_enable_user(request:Request,user_id:int,db:Session=Depends(get_db),operator:User=Depends(require_roles("admin","super_admin"))):
    return _set_user_active(db,_user(db,user_id),True,operator,request)

@router.get('/admin/users',response_class=HTMLResponse)
def users_page(request:Request,db:Session=Depends(get_db),user:User=Depends(require_roles(*USER_VIEW))):
    scope=get_access_scope(db,user);q=db.query(User)
    if not scope.can_view_all:q=q.filter(User.org_id.in_(scope.allowed_org_ids or [-1]))
    return templates.TemplateResponse(request=request,name='admin_users.html',context={'items':q.order_by(User.id).all(),'organizations':db.query(Organization).filter_by(status='active').all(),'roles':ROLES,'current_user':user,'can_edit':effective_role(user)=='super_admin'})
@router.post('/admin/users/create')
def user_create(request:Request,username:str=Form(...),password:str=Form(...),role:str=Form(...),org_id:int=Form(0),db:Session=Depends(get_db),user:User=Depends(require_roles(*ADMIN))):
    if db.query(User).filter_by(username=username.strip()).first():raise HTTPException(400,'用户名已存在')
    if len(password)<10:raise HTTPException(400,'初始密码至少10位')
    item=User(username=username.strip(),password_hash=hash_password(password),role=role,org_id=org_id or None,is_active=True,force_password_change=True,session_version=1);db.add(item);db.flush();write_audit_log(db,'user_created','user',item.id,user_id=user.id,after={'username':item.username,'role':role,'org_id':org_id},request=request,risk_level='high');track_event(db,'user_created',data={'user_id':item.id},commit=False);db.commit();return RedirectResponse('/admin/users',303)
@router.post('/admin/users/{user_id}/update')
def user_update(request:Request,user_id:int,role:str=Form(...),org_id:int=Form(0),db:Session=Depends(get_db),operator:User=Depends(require_roles(*ADMIN))):
    item=_user(db,user_id);before={'role':item.role,'org_id':item.org_id};item.role=role;item.org_id=org_id or None;write_audit_log(db,'user_updated','user',item.id,user_id=operator.id,before=before,after={'role':role,'org_id':org_id},request=request,risk_level='high');db.commit();return RedirectResponse('/admin/users',303)
@router.post('/admin/users/{user_id}/reset-password')
def reset_password(request:Request,user_id:int,new_password:str=Form(...),db:Session=Depends(get_db),operator:User=Depends(require_roles(*ADMIN))):
    if len(new_password)<10:raise HTTPException(400,'密码至少10位')
    item=_user(db,user_id);item.password_hash=hash_password(new_password);item.force_password_change=True;item.password_changed_at=None;item.session_version=(item.session_version or 1)+1;write_audit_log(db,'user_password_reset','user',item.id,user_id=operator.id,request=request,risk_level='critical');db.commit();return RedirectResponse('/admin/users',303)
def _set_user_active(db,item,active,operator,request):
    item.is_active=active;item.session_version=(item.session_version or 1)+(0 if active else 1);write_audit_log(db,'user_enabled' if active else 'user_disabled','user',item.id,user_id=operator.id,request=request,risk_level='high');track_event(db,'user_disabled' if not active else 'user_enabled',data={'user_id':item.id},commit=False);db.commit();return RedirectResponse('/admin/users',303)
@router.post('/admin/users/{user_id}/disable')
def disable_user(request:Request,user_id:int,db:Session=Depends(get_db),operator:User=Depends(require_roles(*ADMIN))):return _set_user_active(db,_user(db,user_id),False,operator,request)
@router.post('/admin/users/{user_id}/enable')
def enable_user(request:Request,user_id:int,db:Session=Depends(get_db),operator:User=Depends(require_roles(*ADMIN))):return _set_user_active(db,_user(db,user_id),True,operator,request)

@router.get('/admin/audit-logs',response_class=HTMLResponse)
def audit_logs(request:Request,user_id:int=0,action:str='',risk_level:str='',target_type:str='',date_from:str='',date_to:str='',db:Session=Depends(get_db),user:User=Depends(require_roles(*ADMIN))):
    q=db.query(AuditLog)
    if user_id:q=q.filter(AuditLog.user_id==user_id)
    if action:q=q.filter(AuditLog.action.contains(action))
    if risk_level:q=q.filter(AuditLog.risk_level==risk_level)
    if target_type:q=q.filter(AuditLog.target_type==target_type)
    if date_from:q=q.filter(AuditLog.created_at>=datetime.fromisoformat(date_from))
    if date_to:q=q.filter(AuditLog.created_at<datetime.fromisoformat(date_to)+timedelta(days=1))
    return templates.TemplateResponse(request=request,name='admin_audit_logs.html',context={'items':q.order_by(AuditLog.created_at.desc()).limit(500).all(),'users':db.query(User).all(),'current_user':user,'filters':{'user_id':user_id,'action':action,'risk_level':risk_level,'target_type':target_type,'date_from':date_from,'date_to':date_to}})

@router.get('/admin/legal-documents',response_class=HTMLResponse)
def legal_documents(request:Request,db:Session=Depends(get_db),user:User=Depends(require_roles(*ADMIN))):return templates.TemplateResponse(request=request,name='admin_legal_documents.html',context={'items':db.query(LegalDocument).order_by(LegalDocument.id).all(),'current_user':user})
@router.post('/admin/legal-documents/{document_id}/update')
def legal_update(request:Request,document_id:int,title:str=Form(...),content:str=Form(...),version:str=Form(...),is_active:bool=Form(False),db:Session=Depends(get_db),user:User=Depends(require_roles(*ADMIN))):
    item=db.get(LegalDocument,document_id)
    if not item:raise HTTPException(404,'法律文档不存在')
    item.title=title.strip();item.content=content.strip();item.version=version.strip();item.is_active=is_active;item.updated_at=datetime.now();write_audit_log(db,'legal_document_updated','legal_document',item.id,user_id=user.id,request=request,risk_level='high');db.commit();return RedirectResponse('/admin/legal-documents',303)
@router.get('/client/legal',response_class=HTMLResponse)
def client_legal(request:Request,db:Session=Depends(get_db),customer:CustomerAccount=Depends(require_customer)):
    docs=db.query(LegalDocument).filter(LegalDocument.is_active.is_(True),LegalDocument.document_key.in_(['user_agreement','privacy_policy','data_authorization','document_submission_authorization'])).all();accepted={(x.document_key,x.document_version) for x in db.query(LegalAcceptance).filter_by(customer_id=customer.id).all()};return templates.TemplateResponse(request=request,name='client_legal.html',context={'customer':customer,'documents':docs,'accepted':accepted})
@router.post('/client/legal/{document_id}/accept')
def legal_accept(request:Request,document_id:int,db:Session=Depends(get_db),customer:CustomerAccount=Depends(require_customer)):
    doc=db.get(LegalDocument,document_id)
    if not doc or not doc.is_active:raise HTTPException(404,'协议不存在')
    exists=db.query(LegalAcceptance).filter_by(customer_id=customer.id,document_key=doc.document_key,document_version=doc.version).first()
    if not exists:db.add(LegalAcceptance(customer_id=customer.id,lead_id=customer.lead_id,document_key=doc.document_key,document_version=doc.version,ip_address=request.client.host if request.client else '',user_agent=request.headers.get('user-agent','')[:500]));write_audit_log(db,'legal_document_accepted','legal_document',doc.id,customer_id=customer.id,actor_type='customer',request=request);track_event(db,'legal_document_accepted',customer.assessment_id,customer.lead_id,{'document_key':doc.document_key},commit=False);db.commit()
    return RedirectResponse('/client/legal',303)

@router.get('/admin/backups',response_class=HTMLResponse)
def backups_page(request:Request,user:User=Depends(require_roles(*ADMIN))):return templates.TemplateResponse(request=request,name='admin_backups.html',context={'items':list_backups(),'current_user':user})
@router.post('/admin/backups/create')
def backup_create(request:Request,db:Session=Depends(get_db),user:User=Depends(require_roles(*ADMIN))):
    result=create_database_backup();write_audit_log(db,'backup_created','backup',None,user_id=user.id,after={'name':result['name'],'sha256':result['sha256']},request=request,risk_level='high');track_event(db,'backup_created',data={'name':result['name']},commit=False);db.commit();return RedirectResponse('/admin/backups',303)
@router.get('/admin/backups/{name}/download')
def backup_download(request:Request,name:str,db:Session=Depends(get_db),user:User=Depends(require_roles(*ADMIN))):
    path=safe_backup_path(name);write_audit_log(db,'backup_downloaded','backup',None,user_id=user.id,after={'name':path.name},request=request,risk_level='critical');track_event(db,'backup_downloaded',data={'name':path.name},commit=False);db.commit();return FileResponse(path,filename=path.name,media_type='application/octet-stream')
@router.post('/admin/backups/{name}/delete')
def backup_delete(request:Request,name:str,db:Session=Depends(get_db),user:User=Depends(require_roles(*ADMIN))):
    path=safe_backup_path(name);path.unlink();write_audit_log(db,'backup_deleted','backup',None,user_id=user.id,after={'name':name},request=request,risk_level='critical');track_event(db,'backup_deleted',data={'name':name},commit=False);db.commit();return RedirectResponse('/admin/backups',303)

def _dir_size(path:Path):return sum(x.stat().st_size for x in path.rglob('*') if x.is_file()) if path.exists() else 0
def health_payload(db:Session):
    db.execute(text('SELECT 1'));upload=BASE_DIR/'data'/'uploads';upload.mkdir(parents=True,exist_ok=True);last_worker=db.query(WorkerRun).filter_by(worker_name='notification_worker').order_by(WorkerRun.id.desc()).first()
    return {'status':'ok','version':settings.app_version,'database':'ok','storage':'ok' if os.access(upload,os.W_OK) else 'failed','notification_worker':last_worker.run_status if last_worker else 'unknown','timestamp':datetime.now().isoformat()}
@router.get('/admin/system-health',response_class=HTMLResponse)
def system_health(request:Request,db:Session=Depends(get_db),user:User=Depends(require_roles(*ADMIN))):
    database=Path(engine.url.database);workers={name:db.query(WorkerRun).filter_by(worker_name=name).order_by(WorkerRun.id.desc()).first() for name in ['notification_worker','reminder_scan','daily_backup']};backups=list_backups();track_event(db,'system_health_viewed',data={'user_id':user.id});return templates.TemplateResponse(request=request,name='admin_system_health.html',context={'health':health_payload(db),'python':sys.version.split()[0],'db_size':database.stat().st_size if database.exists() else 0,'upload_size':_dir_size(BASE_DIR/'data'/'uploads'),'backups':backups,'workers':workers,'routes':len(request.app.routes),'app_env':settings.app_env,'default_secret':settings.secret_key=='change-me-in-production','default_admin':verify_password(settings.admin_default_password,user.password_hash),'current_user':user})
@router.get('/admin/production-checklist',response_class=HTMLResponse)
def production_checklist(request:Request,db:Session=Depends(get_db),user:User=Depends(require_roles(*ADMIN))):
    from services.release_service import flatten_preflight, preflight_groups
    groups=preflight_groups(db);track_event(db,'production_checklist_viewed',data={'user_id':user.id});return templates.TemplateResponse(request=request,name='admin_production_checklist.html',context={'groups':groups,'checks':flatten_preflight(groups),'current_user':user})

@router.post('/admin/documents/{document_id}/soft-delete')
def soft_delete_document(request:Request,document_id:int,delete_reason:str=Form(...),db:Session=Depends(get_db),user:User=Depends(require_roles(*ADMIN))):
    item=db.get(UploadedDocument,document_id)
    if not item:raise HTTPException(404,'资料不存在')
    item.deleted_at=datetime.now();item.deleted_by=user.id;item.delete_reason=delete_reason.strip();write_audit_log(db,'data_soft_deleted','uploaded_document',item.id,user_id=user.id,after={'reason':item.delete_reason},request=request,risk_level='critical');track_event(db,'data_soft_deleted',item.assessment_id,item.lead_id,{'document_id':item.id},commit=False);db.commit();return RedirectResponse(f'/admin/leads/{item.lead_id}/document-center',303)

@router.get('/admin/leads/{lead_id}/compliance-export.zip')
def compliance_export(request:Request,lead_id:int,db:Session=Depends(get_db),user:User=Depends(require_roles(*ADMIN))):
    lead=db.get(Lead,lead_id)
    if not lead:raise HTTPException(404,'线索不存在')
    assessment=db.get(Assessment,lead.assessment_id);memory=io.BytesIO()
    with zipfile.ZipFile(memory,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('lead.csv',_csv_bytes(['id','company_name','contact_name','phone','wechat_id','lead_grade'],[[lead.id,lead.company_name,lead.contact_name,lead.phone,lead.wechat_id,lead.lead_grade]]))
        z.writestr('assessment.csv',_csv_bytes(['id','company_name','industry','annual_revenue','debt_total','funding_need','score'],[[assessment.id,assessment.company_name,assessment.industry,assessment.annual_revenue,assessment.debt_total,assessment.funding_need,assessment.score]]))
        z.writestr('reports.csv',_csv_bytes(['id','review_status','is_unlocked','created_at'],[[x.id,x.review_status,x.is_unlocked,x.created_at] for x in db.query(Report).filter_by(assessment_id=assessment.id).all()]))
        z.writestr('orders.csv',_csv_bytes(['id','product','amount','status','paid_at'],[[x.id,x.product_code,x.amount,x.status,x.paid_at] for x in db.query(Order).filter_by(assessment_id=assessment.id).all()]))
        z.writestr('documents_manifest.csv',_csv_bytes(['id','file_name','category','size','hash','status'],[[x.id,x.file_name,x.document_category,x.file_size,x.file_hash,x.verify_status] for x in db.query(UploadedDocument).filter_by(lead_id=lead.id).all()]))
        z.writestr('projects.csv',_csv_bytes(['id','name','status','target','approved','disbursed'],[[x.id,x.project_name,x.project_status,x.target_amount,x.approved_amount,x.actual_disbursed_amount] for x in db.query(FinancingProject).filter_by(lead_id=lead.id).all()]))
        z.writestr('confirmations.csv',_csv_bytes(['id','type','title','status','confirmed_at'],[[x.id,x.confirmation_type,x.title,x.status,x.confirmed_at] for x in db.query(CustomerConfirmation).filter_by(lead_id=lead.id).all()]))
        z.writestr('audit_summary.csv',_csv_bytes(['id','action','target','risk','created_at'],[[x.id,x.action,x.target_type,x.risk_level,x.created_at] for x in db.query(AuditLog).filter(AuditLog.target_id.in_([lead.id,assessment.id])).all()]))
    write_audit_log(db,'compliance_export_downloaded','lead',lead.id,user_id=user.id,request=request,risk_level='critical');track_event(db,'compliance_export_downloaded',assessment.id,lead.id,{},commit=False);db.commit();return Response(memory.getvalue(),media_type='application/zip',headers={'Content-Disposition':f'attachment; filename="lead-{lead.id}-compliance.zip"'})
