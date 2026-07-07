"""Phase 9：组织、多城市、伙伴归因、资源联系人、提成与数据隔离验收。"""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT))
from fastapi.testclient import TestClient
from core.access_scope import get_access_scope
from db.database import SessionLocal
from db.models import (ChannelPartner,CommissionRecord,ConsultingCase,FinancingProject,
    InstitutionContact,Lead,Order,Organization,User)
from main import app
from services.auth_service import hash_password

PAYLOAD={"company_name":"Phase9伙伴推荐企业有限公司","contact_name":"伙伴客户","phone":"13200132000","wechat_id":"p9","city":"苏州","industry":"制造业","years":"5","employee_count":"40","annual_revenue":"16000000","net_profit":"1200000","monthly_cashflow":"420000","debt_total":"5000000","short_debt":"2800000","receivable_days":"70","funding_need":"4000000","funding_purpose":"订单周转","has_collateral":"true","tax_status":"true","credit_status":"true","knows_cashflow":"true","has_budget":"true","leverage_attitude":"适中","asset_efficiency":"中","fund_usage_plan":"true"}
def login(c,u='admin',p='admin123'):return c.post('/login',data={'username':u,'password':p,'next_url':'/admin'},follow_redirects=False)
def run():
 with TestClient(app) as c:
  assert login(c).status_code==303
  with SessionLocal() as db:
   hq=db.query(Organization).filter_by(org_type='headquarters').one();hq_id=hq.id;admin=db.query(User).filter_by(username='admin').one();assert hq.org_name=='沪上银总部' and admin.org_id==hq.id and get_access_scope(db,admin).role=='super_admin'
  assert c.post('/admin/organizations/create',data={'org_name':'苏州分公司','org_type':'branch','parent_id':hq_id,'city':'苏州','province':'江苏'},follow_redirects=False).status_code==303
  with SessionLocal() as db:suzhou=db.query(Organization).filter_by(org_name='苏州分公司').one();suzhou_id=suzhou.id
  assert c.post('/admin/organizations/create',data={'org_name':'苏州销售一组','org_type':'team','parent_id':suzhou_id,'city':'苏州'},follow_redirects=False).status_code==303
  assert c.post('/admin/organizations/create',data={'org_name':'苏州渠道伙伴组织','org_type':'partner','parent_id':hq_id,'city':'苏州'},follow_redirects=False).status_code==303
  with SessionLocal() as db:
   porg=db.query(Organization).filter_by(org_name='苏州渠道伙伴组织').one();porg_id=porg.id
   for username,role,org in [('p9_manager','city_manager',suzhou_id),('p9_sales','sales',suzhou_id),('p9_consultant','consultant',suzhou_id),('p9_partner','partner',porg_id),('p9_finance','finance',hq_id)]:
    db.add(User(username=username,password_hash=hash_password('phase9-pass'),role=role,org_id=org,is_active=True))
   db.commit()
  partner_create=c.post('/admin/channel-partners/create',data={'org_id':porg_id,'partner_name':'苏州商会渠道','contact_name':'渠道张总','phone':'13800000000','city':'苏州','source_code':'PARTNER001','commission_rate':'10','settlement_mode':'per_paid_order'},follow_redirects=False);assert partner_create.status_code==303
  with SessionLocal() as db:partner=db.query(ChannelPartner).filter_by(source_code='PARTNER001').one();partner_id=partner.id;sales=db.query(User).filter_by(username='p9_sales').one();consultant=db.query(User).filter_by(username='p9_consultant').one();sales_id=sales.id;consultant_id=consultant.id
  c.get('/logout');c.get('/lp/rongzi?partner=PARTNER001&utm_source=partner');submit=c.post('/assessment/submit',data=PAYLOAD,follow_redirects=False);aid=int(submit.headers['location'].rsplit('/',1)[-1])
  with SessionLocal() as db:lead=db.query(Lead).filter_by(assessment_id=aid).one();lead_id=lead.id;assert lead.source_partner_id==partner_id and lead.owner_org_id==porg_id
  assert c.post(f'/payment/mock-pay/{aid}?product=299_report',follow_redirects=False).status_code==303
  assert login(c).status_code==303
  assert c.post(f'/admin/leads/{lead_id}/assign-owner',data={'owner_user_id':sales_id,'owner_org_id':suzhou_id},follow_redirects=False).status_code==303
  assert c.post(f'/payment/mock-pay/{aid}?product=1999_structure_plan',follow_redirects=False).status_code==303
  with SessionLocal() as db:case=db.query(ConsultingCase).filter_by(assessment_id=aid).one();case_id=case.id
  assert c.post(f'/admin/consulting-cases/{case_id}/assign-consultant',data={'consultant_user_id':consultant_id,'owner_org_id':suzhou_id},follow_redirects=False).status_code==303
  contact=c.post('/admin/institution-contacts/create',data={'institution_name':'苏州模拟城商行','institution_type':'bank','bank_type':'城商行','city':'苏州','contact_name':'王经理','phone':'13900000000','product_focus':'经营贷','cooperation_level':'A'},follow_redirects=False);assert contact.status_code==303
  with SessionLocal() as db:contact_id=db.query(InstitutionContact).filter_by(contact_name='王经理').one().id
  project=c.post('/admin/financing-projects/create',data={'lead_id':lead_id,'consulting_case_id':case_id,'project_name':'Phase9苏州融资项目','target_amount':'4000000'},follow_redirects=False);project_id=int(project.headers['location'].rsplit('/',1)[-1])
  assert c.post(f'/admin/financing-projects/{project_id}/assign-owner',data={'owner_user_id':sales_id,'owner_org_id':suzhou_id,'consultant_user_id':consultant_id},follow_redirects=False).status_code==303
  application_response=c.post(f'/admin/financing-projects/{project_id}/applications/create',data={'institution_contact_id':contact_id,'institution_name':'苏州模拟城商行','institution_type':'bank','product_name':'经营贷','apply_amount':'4000000','expected_rate':'5','loan_term':'24'},follow_redirects=False);assert application_response.status_code==303
  update={'project_status':'disbursed','target_amount':'4000000','approved_amount':'4000000','actual_disbursed_amount':'4000000','expected_rate':'5','final_rate':'5','expected_term':'24','final_term':'24','priority':'high','project_owner_id':sales_id,'expected_close_date':'','project_summary':'已放款','failure_reason':''}
  assert c.post(f'/admin/financing-projects/{project_id}/update',data=update,follow_redirects=False).status_code==303
  for url in ['/admin/organizations','/admin/channel-partners','/admin/institution-contacts','/admin/commissions','/admin/commission-rules','/admin/city-dashboard','/admin/team-performance','/admin/hq-dashboard']:
   assert c.get(url).status_code==200,url
  for kind in ['leads','orders','projects','commissions']:
   r=c.get(f'/admin/export/organization/{suzhou_id}/{kind}.csv');assert r.status_code==200 and r.content.startswith(b'\xef\xbb\xbf')
  with SessionLocal() as db:
   lead=db.get(Lead,lead_id);case_check=db.get(ConsultingCase,case_id);project=db.get(FinancingProject,project_id);assert lead.owner_user_id==sales_id and lead.owner_org_id==suzhou_id;assert case_check.consultant_user_id==consultant_id;assert project.consultant_user_id==consultant_id and project.owner_org_id==suzhou_id;assert db.query(CommissionRecord).count()>=3;record=db.query(CommissionRecord).first();record_id=record.id
  assert c.post(f'/admin/commission-records/{record_id}/confirm',follow_redirects=False).status_code==303
  assert c.post(f'/admin/commission-records/{record_id}/mark-paid',follow_redirects=False).status_code==303
  c.get('/logout');assert login(c,'p9_partner','phase9-pass').status_code==303
  partner_page=c.get(f'/admin/channel-partners/{partner_id}');assert partner_page.status_code==200 and PAYLOAD['company_name'] in partner_page.text
  partner_csv=c.get(f'/admin/export/partner/{partner_id}.csv');assert partner_csv.status_code==200 and partner_csv.content.startswith(b'\xef\xbb\xbf')
  leads_page=c.get('/admin/leads');assert leads_page.status_code==200 and PAYLOAD['company_name'] in leads_page.text
  c.get('/logout');assert login(c,'p9_manager','phase9-pass').status_code==303
  city=c.get('/admin/city-dashboard');assert city.status_code==200 and '苏州分公司' in city.text and '沪上银总部' not in city.text
  print({'hq_id':hq_id,'branch_id':suzhou_id,'partner_id':partner_id,'lead_id':lead_id,'project_id':project_id,'commission_records':3})
 print('PHASE9_MULTI_CITY_ORG_OK')
if __name__=='__main__':run()
