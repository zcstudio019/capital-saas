import csv
import io
import secrets
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from core.access_scope import effective_role, get_access_scope
from core.config import BASE_DIR, settings
from db.database import get_db
from db.models import (ChannelPartner, CommissionRecord, CommissionRule, ConsultingCase,
    FinancingProject, FollowTask, FundingApplication, InstitutionContact, Lead,
    LeadFollowLog, Order, Organization, ProjectTask, User)
from services.auth_service import require_roles
from services.event_service import track_event
from services.follow_log_service import add_follow_log

router=APIRouter(); templates=Jinja2Templates(directory=str(BASE_DIR/'templates'))
READ=("admin","super_admin","city_manager","sales_manager","sales","consultant_manager","consultant","finance","viewer","partner")

def _org(db,id):
    x=db.get(Organization,id)
    if not x: raise HTTPException(404,"组织不存在")
    return x
def _partner(db,id):
    x=db.get(ChannelPartner,id)
    if not x: raise HTTPException(404,"渠道伙伴不存在")
    return x
def _super(user): return effective_role(user)=="super_admin"
def _csv(name,headers,rows):
    out=io.StringIO(); w=csv.writer(out); w.writerow(headers); w.writerows(rows)
    return Response(content=("\ufeff"+out.getvalue()).encode(),media_type="text/csv; charset=utf-8",headers={"Content-Disposition":f'attachment; filename="{name}"'})

@router.get('/admin/organizations',response_class=HTMLResponse)
def organizations(request:Request,db:Session=Depends(get_db),user:User=Depends(require_roles("admin","super_admin"))):
    orgs=db.query(Organization).order_by(Organization.parent_id,Organization.id).all()
    stats={o.id:{"users":db.query(User).filter(User.org_id==o.id).count(),"leads":db.query(Lead).filter(Lead.owner_org_id==o.id).count(),"orders":db.query(Order).filter(Order.owner_org_id==o.id).count(),"projects":db.query(FinancingProject).filter(FinancingProject.owner_org_id==o.id).count()} for o in orgs}
    return templates.TemplateResponse(request=request,name='admin_organizations.html',context={'orgs':orgs,'stats':stats,'users':db.query(User).all(),'current_user':user})

@router.post('/admin/organizations/create')
def organization_create(org_name:str=Form(...),org_type:str=Form(...),parent_id:int=Form(0),city:str=Form(''),province:str=Form(''),address:str=Form(''),manager_user_id:int=Form(0),db:Session=Depends(get_db),user:User=Depends(require_roles("admin","super_admin"))):
    item=Organization(org_name=org_name.strip(),org_type=org_type,parent_id=parent_id or None,city=city.strip(),province=province.strip(),address=address.strip(),manager_user_id=manager_user_id or None,status='active'); db.add(item); db.flush(); track_event(db,'organization_created',data={'org_id':item.id,'operator':user.username},commit=False); db.commit(); return RedirectResponse('/admin/organizations',303)

@router.get('/admin/organizations/{org_id}',response_class=HTMLResponse)
def organization_detail(request:Request,org_id:int,db:Session=Depends(get_db),user:User=Depends(require_roles(*READ))):
    org=_org(db,org_id); scope=get_access_scope(db,user)
    if not scope.can_view_all and org.id not in scope.allowed_org_ids: raise HTTPException(403,'无权查看该组织')
    orders=db.query(Order).filter(Order.owner_org_id==org.id).all()
    return templates.TemplateResponse(request=request,name='admin_organization_detail.html',context={'org':org,'children':db.query(Organization).filter(Organization.parent_id==org.id).all(),'users':db.query(User).filter(User.org_id==org.id).all(),'lead_count':db.query(Lead).filter(Lead.owner_org_id==org.id).count(),'order_count':len(orders),'project_count':db.query(FinancingProject).filter(FinancingProject.owner_org_id==org.id).count(),'revenue':sum(o.amount for o in orders if o.status=='paid'),'current_user':user})

@router.post('/admin/organizations/{org_id}/update')
def organization_update(org_id:int,org_name:str=Form(...),status:str=Form('active'),city:str=Form(''),province:str=Form(''),address:str=Form(''),manager_user_id:int=Form(0),db:Session=Depends(get_db),user:User=Depends(require_roles("admin","super_admin"))):
    item=_org(db,org_id); item.org_name=org_name.strip(); item.status=status; item.city=city.strip(); item.province=province.strip(); item.address=address.strip(); item.manager_user_id=manager_user_id or None; item.updated_at=datetime.now(); track_event(db,'organization_updated',data={'org_id':item.id,'operator':user.username},commit=False); db.commit(); return RedirectResponse(f'/admin/organizations/{item.id}',303)

@router.get('/admin/channel-partners',response_class=HTMLResponse)
def partners(request:Request,db:Session=Depends(get_db),user:User=Depends(require_roles("admin","super_admin","city_manager","finance"))):
    scope=get_access_scope(db,user); q=db.query(ChannelPartner)
    if not scope.can_view_all:q=q.filter(ChannelPartner.org_id.in_(scope.allowed_org_ids or [-1]))
    return templates.TemplateResponse(request=request,name='admin_channel_partners.html',context={'partners':q.all(),'orgs':db.query(Organization).all(),'base_url':settings.site_base_url.rstrip('/'),'current_user':user})

@router.post('/admin/channel-partners/create')
def partner_create(org_id:int=Form(...),partner_name:str=Form(...),contact_name:str=Form(''),phone:str=Form(''),wechat_id:str=Form(''),city:str=Form(''),source_code:str=Form(''),commission_rate:float=Form(0),settlement_mode:str=Form('manual'),db:Session=Depends(get_db),user:User=Depends(require_roles("admin","super_admin","city_manager"))):
    code=source_code.strip().upper() or 'PARTNER'+secrets.token_hex(3).upper(); item=ChannelPartner(org_id=org_id,partner_name=partner_name.strip(),contact_name=contact_name.strip(),phone=phone.strip(),wechat_id=wechat_id.strip(),city=city.strip(),source_code=code,commission_rate=commission_rate,settlement_mode=settlement_mode,status='active'); db.add(item); db.flush(); track_event(db,'channel_partner_created',data={'partner_id':item.id,'source_code':code},commit=False); db.commit(); return RedirectResponse('/admin/channel-partners',303)

@router.get('/admin/channel-partners/{partner_id}',response_class=HTMLResponse)
def partner_detail(request:Request,partner_id:int,db:Session=Depends(get_db),user:User=Depends(require_roles(*READ))):
    p=_partner(db,partner_id); scope=get_access_scope(db,user)
    if not scope.can_view_all and p.id not in scope.allowed_partner_ids: raise HTTPException(403,'无权查看该伙伴')
    leads=db.query(Lead).filter(Lead.source_partner_id==p.id).all(); orders=db.query(Order).filter(Order.source_partner_id==p.id).all()
    return templates.TemplateResponse(request=request,name='admin_channel_partner_detail.html',context={'partner':p,'leads':leads,'orders':orders,'projects':db.query(FinancingProject).filter(FinancingProject.lead_id.in_([x.id for x in leads] or [-1])).all(),'base_url':settings.site_base_url.rstrip('/'),'current_user':user})

@router.post('/admin/channel-partners/{partner_id}/update')
def partner_update(partner_id:int,partner_name:str=Form(...),commission_rate:float=Form(0),settlement_mode:str=Form('manual'),status:str=Form('active'),db:Session=Depends(get_db),_:User=Depends(require_roles("admin","super_admin","city_manager"))):
    p=_partner(db,partner_id); p.partner_name=partner_name.strip();p.commission_rate=commission_rate;p.settlement_mode=settlement_mode;p.status=status;p.updated_at=datetime.now();db.commit();return RedirectResponse(f'/admin/channel-partners/{p.id}',303)

@router.get('/admin/institution-contacts',response_class=HTMLResponse)
def contacts(request:Request,institution_type:str='',db:Session=Depends(get_db),user:User=Depends(require_roles(*READ))):
    query=db.query(InstitutionContact)
    if institution_type:
        query=query.filter(InstitutionContact.institution_type==institution_type)
    return templates.TemplateResponse(request=request,name='admin_institution_contacts.html',context={'contacts':query.order_by(InstitutionContact.cooperation_level).all(),'institution_type':institution_type,'current_user':user})
@router.post('/admin/institution-contacts/create')
def contact_create(institution_name:str=Form(...),institution_type:str=Form('bank'),bank_type:str=Form(''),city:str=Form(''),contact_name:str=Form(...),contact_role:str=Form('客户经理'),phone:str=Form(''),wechat_id:str=Form(''),email:str=Form(''),product_focus:str=Form(''),cooperation_level:str=Form('B'),note:str=Form(''),db:Session=Depends(get_db),user:User=Depends(require_roles("admin","super_admin","city_manager","consultant_manager"))):
    x=InstitutionContact(institution_name=institution_name.strip(),institution_type=institution_type,bank_type=bank_type,city=city,contact_name=contact_name.strip(),contact_role=contact_role,phone=phone,wechat_id=wechat_id,email=email,product_focus=product_focus,cooperation_level=cooperation_level,note=note,status='active');db.add(x);db.flush();track_event(db,'institution_contact_created',data={'contact_id':x.id},commit=False);db.commit();return RedirectResponse('/admin/institution-contacts',303)
@router.get('/admin/institution-contacts/{contact_id}',response_class=HTMLResponse)
def contact_detail(request:Request,contact_id:int,db:Session=Depends(get_db),user:User=Depends(require_roles(*READ))):
    x=db.get(InstitutionContact,contact_id)
    if not x:raise HTTPException(404,'联系人不存在')
    total=x.success_count+x.rejection_count
    return templates.TemplateResponse(request=request,name='admin_institution_contact_detail.html',context={'contact':x,'success_rate':round(x.success_count/total*100,1) if total else 0,'current_user':user})
@router.post('/admin/institution-contacts/{contact_id}/update')
def contact_update(contact_id:int,cooperation_level:str=Form('B'),success_count:int=Form(0),rejection_count:int=Form(0),note:str=Form(''),status:str=Form('active'),db:Session=Depends(get_db),_:User=Depends(require_roles("admin","super_admin","city_manager","consultant_manager"))):
    x=db.get(InstitutionContact,contact_id);x.cooperation_level=cooperation_level;x.success_count=success_count;x.rejection_count=rejection_count;x.note=note;x.status=status;x.updated_at=datetime.now();db.commit();return RedirectResponse(f'/admin/institution-contacts/{x.id}',303)

@router.post('/admin/leads/{lead_id}/assign-owner')
def assign_lead(lead_id:int,owner_user_id:int=Form(...),owner_org_id:int=Form(...),db:Session=Depends(get_db),user:User=Depends(require_roles("admin","super_admin","city_manager","sales_manager"))):
    lead=db.get(Lead,lead_id);old=f'{lead.owner_user_id}/{lead.owner_org_id}';lead.owner_user_id=owner_user_id;lead.owner_org_id=owner_org_id;lead.org_id=owner_org_id;lead.assigned_sales_id=owner_user_id;add_follow_log(db,lead.id,user,'owner_changed','重新分配线索负责人',old,f'{owner_user_id}/{owner_org_id}');track_event(db,'lead_owner_changed',lead.assessment_id,lead.id,{'owner_user_id':owner_user_id,'owner_org_id':owner_org_id},commit=False);db.commit();return RedirectResponse(f'/admin/leads/{lead.id}',303)
@router.post('/admin/consulting-cases/{case_id}/assign-consultant')
def assign_case(case_id:int,consultant_user_id:int=Form(...),owner_org_id:int=Form(...),db:Session=Depends(get_db),_:User=Depends(require_roles("admin","super_admin","city_manager","consultant_manager"))):
    x=db.get(ConsultingCase,case_id);x.consultant_user_id=consultant_user_id;x.consultant_id=consultant_user_id;x.owner_org_id=owner_org_id;x.org_id=owner_org_id;track_event(db,'case_consultant_assigned',x.assessment_id,x.lead_id,{'case_id':x.id,'consultant_user_id':consultant_user_id},commit=False);db.commit();return RedirectResponse(f'/admin/consulting-cases/{x.id}',303)
@router.post('/admin/financing-projects/{project_id}/assign-owner')
def assign_project(project_id:int,owner_user_id:int=Form(...),owner_org_id:int=Form(...),consultant_user_id:int=Form(0),db:Session=Depends(get_db),_:User=Depends(require_roles("admin","super_admin","city_manager","consultant_manager"))):
    x=db.get(FinancingProject,project_id);x.owner_user_id=owner_user_id;x.project_owner_id=owner_user_id;x.owner_org_id=owner_org_id;x.org_id=owner_org_id;x.consultant_user_id=consultant_user_id or None;track_event(db,'project_owner_changed',x.assessment_id,x.lead_id,{'project_id':x.id,'owner_user_id':owner_user_id},commit=False);db.commit();return RedirectResponse(f'/admin/financing-projects/{x.id}',303)

@router.get('/admin/commission-rules',response_class=HTMLResponse)
def rules(request:Request,db:Session=Depends(get_db),user:User=Depends(require_roles("admin","super_admin","finance"))):return templates.TemplateResponse(request=request,name='admin_commission_rules.html',context={'rules':db.query(CommissionRule).all(),'current_user':user})
@router.post('/admin/commission-rules/create')
def rule_create(rule_name:str=Form(...),role_type:str=Form(...),product_code:str=Form(''),trigger_event:str=Form(...),commission_type:str=Form(...),commission_value:float=Form(...),db:Session=Depends(get_db),_:User=Depends(require_roles("admin","super_admin","finance"))):db.add(CommissionRule(rule_name=rule_name,role_type=role_type,product_code=product_code,trigger_event=trigger_event,commission_type=commission_type,commission_value=commission_value));db.commit();return RedirectResponse('/admin/commission-rules',303)
@router.get('/admin/commissions',response_class=HTMLResponse)
def commissions(request:Request,db:Session=Depends(get_db),user:User=Depends(require_roles("admin","super_admin","finance","city_manager"))):
    scope=get_access_scope(db,user);q=db.query(CommissionRecord)
    if not scope.can_view_all:q=q.filter(CommissionRecord.org_id.in_(scope.allowed_org_ids or [-1]))
    return templates.TemplateResponse(request=request,name='admin_commissions.html',context={'records':q.order_by(CommissionRecord.created_at.desc()).all(),'current_user':user})
def _commission_status(db,id,status,user):
    x=db.get(CommissionRecord,id)
    if not x:raise HTTPException(404,'提成记录不存在')
    x.settlement_status=status;x.updated_at=datetime.now()
    if status=='paid':track_event(db,'commission_record_paid',data={'record_id':x.id,'operator':user.username},commit=False)
    db.commit();return RedirectResponse('/admin/commissions',303)
@router.post('/admin/commission-records/{record_id}/confirm')
def commission_confirm(record_id:int,db:Session=Depends(get_db),user:User=Depends(require_roles("admin","super_admin","finance"))):return _commission_status(db,record_id,'confirmed',user)
@router.post('/admin/commission-records/{record_id}/mark-paid')
def commission_paid(record_id:int,db:Session=Depends(get_db),user:User=Depends(require_roles("admin","super_admin","finance"))):return _commission_status(db,record_id,'paid',user)
@router.post('/admin/commission-records/{record_id}/cancel')
def commission_cancel(record_id:int,db:Session=Depends(get_db),user:User=Depends(require_roles("admin","super_admin","finance"))):return _commission_status(db,record_id,'cancelled',user)

def _dashboard_rows(db,scope):
    orgs=db.query(Organization).filter(Organization.id.in_(scope.allowed_org_ids or [-1])).all() if not scope.can_view_all else db.query(Organization).all();rows=[]
    for o in orgs:
        leads=db.query(Lead).filter(Lead.owner_org_id==o.id).all();orders=db.query(Order).filter(Order.owner_org_id==o.id).all();projects=db.query(FinancingProject).filter(FinancingProject.owner_org_id==o.id).all();paid=[x for x in orders if x.status=='paid']; revenue=sum(x.amount for x in paid); users=db.query(User).filter(User.org_id==o.id).count();rows.append({'org':o,'assessments':len(leads),'leads':len(leads),'orders':len(paid),'revenue':revenue,'projects':len(projects),'approved':sum(x.approved_amount for x in projects),'disbursed':sum(x.actual_disbursed_amount for x in projects),'conversion':round(len(paid)/len(leads)*100,1) if leads else 0,'users':users,'efficiency':round(revenue/max(users,1),1),'partners':db.query(Lead).filter(Lead.owner_org_id==o.id,Lead.source_partner_id.is_not(None)).count()})
    return rows
@router.get('/admin/city-dashboard',response_class=HTMLResponse)
def city_dashboard(request:Request,db:Session=Depends(get_db),user:User=Depends(require_roles(*READ))):
    scope=get_access_scope(db,user);track_event(db,'city_dashboard_viewed',data={'user_id':user.id});return templates.TemplateResponse(request=request,name='admin_city_dashboard.html',context={'rows':_dashboard_rows(db,scope),'current_user':user})
@router.get('/admin/team-performance',response_class=HTMLResponse)
def team_performance(request:Request,db:Session=Depends(get_db),user:User=Depends(require_roles(*READ))):
    scope=get_access_scope(db,user);users=db.query(User).filter(User.id.in_(scope.allowed_user_ids or [-1])).all() if not scope.can_view_all else db.query(User).all();rows=[]
    for u in users:
        leads=db.query(Lead).filter(Lead.owner_user_id==u.id).count();orders=db.query(Order).filter(Order.owner_user_id==u.id,Order.status=='paid').all();projects=db.query(FinancingProject).filter((FinancingProject.owner_user_id==u.id)|(FinancingProject.consultant_user_id==u.id)).all();commission=db.query(func.coalesce(func.sum(CommissionRecord.commission_amount),0)).filter(CommissionRecord.user_id==u.id,CommissionRecord.settlement_status!='cancelled').scalar();rows.append({'user':u,'leads':leads,'orders':len(orders),'revenue':sum(x.amount for x in orders),'cases':db.query(ConsultingCase).filter(ConsultingCase.consultant_user_id==u.id).count(),'approved':sum(x.approved_amount for x in projects),'disbursed':sum(x.actual_disbursed_amount for x in projects),'success':round(sum(x.success_result in {'success','partial_success'} for x in projects)/len(projects)*100,1) if projects else 0,'commission':commission})
    track_event(db,'team_performance_viewed',data={'user_id':user.id});return templates.TemplateResponse(request=request,name='admin_team_performance.html',context={'rows':rows,'current_user':user})
@router.get('/admin/hq-dashboard',response_class=HTMLResponse)
def hq_dashboard(request:Request,db:Session=Depends(get_db),user:User=Depends(require_roles("admin","super_admin"))):
    if not _super(user):raise HTTPException(403,'仅总部超级管理员可访问')
    rows=_dashboard_rows(db,get_access_scope(db,user));projects=db.query(FinancingProject).all();track_event(db,'hq_dashboard_viewed',data={'user_id':user.id});return templates.TemplateResponse(request=request,name='admin_hq_dashboard.html',context={'rows':rows,'total_leads':db.query(Lead).count(),'total_orders':db.query(Order).filter(Order.status=='paid').count(),'total_revenue':db.query(func.coalesce(func.sum(Order.amount),0)).filter(Order.status=='paid').scalar(),'projects':projects,'approved':sum(x.approved_amount for x in projects),'disbursed':sum(x.actual_disbursed_amount for x in projects),'pending_commission':db.query(func.coalesce(func.sum(CommissionRecord.commission_amount),0)).filter(CommissionRecord.settlement_status=='pending').scalar(),'current_user':user})

@router.get('/admin/export/organization/{org_id}/{kind}.csv')
def org_export(org_id:int,kind:str,db:Session=Depends(get_db),user:User=Depends(require_roles(*READ))):
    scope=get_access_scope(db,user)
    if not scope.can_view_all and org_id not in scope.allowed_org_ids:raise HTTPException(403,'无权导出该组织')
    if kind=='leads':return _csv('org-leads.csv',['ID','企业','联系人','负责人','组织'],[[x.id,x.company_name,x.contact_name,x.owner_user_id,x.owner_org_id] for x in db.query(Lead).filter(Lead.owner_org_id==org_id).all()])
    if kind=='orders':return _csv('org-orders.csv',['ID','产品','金额','状态','组织'],[[x.id,x.product_name,x.amount,x.status,x.owner_org_id] for x in db.query(Order).filter(Order.owner_org_id==org_id).all()])
    if kind=='projects':return _csv('org-projects.csv',['ID','项目','状态','批复','放款'],[[x.id,x.project_name,x.project_status,x.approved_amount,x.actual_disbursed_amount] for x in db.query(FinancingProject).filter(FinancingProject.owner_org_id==org_id).all()])
    if kind=='commissions':return _csv('org-commissions.csv',['ID','用户','金额','状态'],[[x.id,x.user_id,x.commission_amount,x.settlement_status] for x in db.query(CommissionRecord).filter(CommissionRecord.org_id==org_id).all()])
    raise HTTPException(404,'不支持的导出类型')

@router.get('/admin/export/partner/{partner_id}.csv')
def partner_export(partner_id:int,db:Session=Depends(get_db),user:User=Depends(require_roles(*READ))):
    scope=get_access_scope(db,user)
    if not scope.can_view_all and partner_id not in scope.allowed_partner_ids:
        raise HTTPException(403,'无权导出该渠道伙伴数据')
    partner=_partner(db,partner_id)
    leads=db.query(Lead).filter(Lead.source_partner_id==partner.id).order_by(Lead.created_at.desc()).all()
    rows=[]
    for lead in leads:
        paid=db.query(Order).filter(Order.assessment_id==lead.assessment_id,Order.status=='paid').all()
        project=db.query(FinancingProject).filter(FinancingProject.lead_id==lead.id).first()
        rows.append([lead.id,lead.company_name,lead.contact_name,lead.phone,lead.lead_grade,
            len(paid),sum(x.amount for x in paid),project.project_status if project else '',
            project.actual_disbursed_amount if project else 0])
    track_event(db,'partner_exported',data={'partner_id':partner.id,'operator':user.username})
    return _csv('partner-referrals.csv',['线索ID','企业','联系人','手机号','等级','订单数','成交金额','项目状态','放款金额'],rows)
