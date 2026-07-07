"""Phase 11 通知中台、业务联动、偏好、Worker 与提醒扫描验收。"""
import os,sys
from datetime import datetime,timedelta
from pathlib import Path
ROOT=Path(__file__).resolve().parent;DB=ROOT/'phase11_test.db'
if DB.exists():DB.unlink()
os.environ['DATABASE_URL']=f"sqlite:///{DB.as_posix()}";sys.path.insert(0,str(ROOT))
from fastapi.testclient import TestClient
from db.database import SessionLocal,engine
from db.models import (CustomerAccount,CustomerTask,InternalNotification,Lead,NotificationJob,
    NotificationPreference,NotificationTemplate,Report,User)
from main import app
from services.customer_portal_service import generate_login_token
from services.notification_service import create_notification_job,retry_failed_jobs,send_notification_job
from services.reminder_service import scan_reminders

P={"company_name":"Phase11通知企业","contact_name":"通知客户","phone":"13500135000","wechat_id":"n11","city":"上海","industry":"服务业","years":"5","employee_count":"30","annual_revenue":"12000000","net_profit":"900000","monthly_cashflow":"350000","debt_total":"3000000","short_debt":"1400000","receivable_days":"50","funding_need":"3000000","funding_purpose":"经营周转","has_collateral":"true","tax_status":"true","credit_status":"true","knows_cashflow":"true","has_budget":"true","leverage_attitude":"适中","asset_efficiency":"中","fund_usage_plan":"true"}
def login(c):return c.post('/login',data={'username':'admin','password':'admin123','next_url':'/admin'},follow_redirects=False)
def run():
 with TestClient(app) as c:
  assert login(c).status_code==303
  with SessionLocal() as db:assert db.query(NotificationTemplate).count()>=15
  bad=c.post('/admin/notification-templates/create',data={'template_key':'bad','template_name':'违规','audience_type':'customer','channel':'mock','category':'marketing','title_template':'保证放款','content_template':'测试'});assert bad.status_code==400
  ok=c.post('/admin/notification-templates/create',data={'template_key':'phase11_test','template_name':'测试模板','audience_type':'admin','channel':'mock','category':'service','title_template':'测试 {{company_name}}','content_template':'通知系统测试'} ,follow_redirects=False);assert ok.status_code==303
  submit=c.post('/assessment/submit',data=P,follow_redirects=False);aid=int(submit.headers['location'].rsplit('/',1)[-1])
  with SessionLocal() as db:
   lead=db.query(Lead).filter_by(assessment_id=aid).one();lead_id=lead.id;customer=db.query(CustomerAccount).filter_by(lead_id=lead.id).one();customer_id=customer.id;admin=db.query(User).filter_by(username='admin').one();lead.owner_user_id=admin.id
   customer_task=CustomerTask(customer_id=customer.id,lead_id=lead.id,assessment_id=aid,task_type='confirm_info',task_title='确认企业信息',task_content='请确认',priority='high',due_time=datetime.now()+timedelta(hours=1));db.add(customer_task);db.commit()
   job=create_notification_job(db,'phase11_test',{'company_name':P['company_name']},recipient_user_id=admin.id,channel='mock');job_id=job.id;send_notification_job(db,job);assert job.send_status=='success'
   token=generate_login_token(db,customer).token
  assert c.get('/admin/notification-templates').status_code==200
  assert c.get('/admin/notification-jobs').status_code==200
  assert c.get('/admin/notification-dashboard').status_code==200
  assert c.get('/admin/notifications').status_code==200
  assert c.get('/admin/my-notification-preferences').status_code==200
  assert c.post('/payment/mock-pay/%s?product=299_report'%aid,follow_redirects=False).status_code==303
  with SessionLocal() as db:report=db.query(Report).filter_by(assessment_id=aid).one();report_id=report.id
  assert c.post(f'/admin/reports/{report_id}/approve',data={'review_note':'通知验收'},follow_redirects=False).status_code==303
  project=c.post('/admin/financing-projects/create',data={'lead_id':lead_id,'project_name':'Phase11融资项目','target_amount':'3000000'},follow_redirects=False);project_id=int(project.headers['location'].rsplit('/',1)[-1])
  update={'project_status':'submitted','target_amount':'3000000','approved_amount':'0','actual_disbursed_amount':'0','expected_rate':'5','final_rate':'0','expected_term':'12','final_term':'0','priority':'high','project_owner_id':'0','expected_close_date':'','project_summary':'已提交','failure_reason':''}
  assert c.post(f'/admin/financing-projects/{project_id}/update',data=update,follow_redirects=False).status_code==303
  with SessionLocal() as db:
   counts=scan_reminders(db);assert counts['customer']>=1
   retry_failed_jobs(db)
   assert db.query(NotificationJob).filter(NotificationJob.template_key=='report_approved_customer').count()>=1
   assert db.query(NotificationJob).filter(NotificationJob.template_key=='project_status_changed_customer').count()>=1
   assert db.query(InternalNotification).filter_by(user_id=1).count()>=1
  c.get('/logout');assert c.get(f'/client/login-token/{token}',follow_redirects=False).status_code==303
  assert c.get('/client/preferences').status_code==200
  assert c.post('/client/preferences/update',data={'receive_in_app':'true','quiet_hours_start':'22:00','quiet_hours_end':'08:00','is_unsubscribed':'true'},follow_redirects=False).status_code==303
  with SessionLocal() as db:
   marketing=create_notification_job(db,'upgrade_recommend_customer',{},recipient_customer_id=customer_id,scheduled_at=datetime.now());send_notification_job(db,marketing);assert marketing.send_status=='skipped'
   assert db.query(NotificationPreference).filter_by(customer_id=customer_id).one().is_unsubscribed is True
  print({'customer_id':customer_id,'job_id':job_id,'templates':16,'project_id':project_id})
 print('PHASE11_NOTIFICATION_AUTOMATION_OK');engine.dispose()
 if DB.exists():DB.unlink()
if __name__=='__main__':run()
