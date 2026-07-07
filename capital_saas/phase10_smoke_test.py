"""Phase 10 客户门户、资料协同、项目进度、消息与确认回执验收。"""
import os
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent
TEST_DB=ROOT/"phase10_test.db"
if TEST_DB.exists():TEST_DB.unlink()
os.environ["DATABASE_URL"]=f"sqlite:///{TEST_DB.as_posix()}"
sys.path.insert(0,str(ROOT))

from fastapi.testclient import TestClient
from db.database import SessionLocal,engine
from db.models import (CustomerAccount,CustomerConfirmation,CustomerMessage,CustomerTask,
    DocumentParseTask,FinancingProject,Lead,Report,UploadedDocument)
from main import app

PAYLOAD={"company_name":"Phase10客户协同企业","contact_name":"客户张总","phone":"13600136000","wechat_id":"phase10","city":"上海","industry":"制造业","years":"6","employee_count":"45","annual_revenue":"18000000","net_profit":"1500000","monthly_cashflow":"500000","debt_total":"4200000","short_debt":"1900000","receivable_days":"45","funding_need":"5000000","funding_purpose":"订单扩产","has_collateral":"true","tax_status":"true","credit_status":"true","knows_cashflow":"true","has_budget":"true","leverage_attitude":"适中","asset_efficiency":"中","fund_usage_plan":"true"}
def login(c):return c.post('/login',data={'username':'admin','password':'admin123','next_url':'/admin'},follow_redirects=False)
def run():
 with TestClient(app) as c:
  assert login(c).status_code==303
  submit=c.post('/assessment/submit',data=PAYLOAD,follow_redirects=False);assert submit.status_code==303
  aid=int(submit.headers['location'].rsplit('/',1)[-1])
  with SessionLocal() as db:
   lead=db.query(Lead).filter_by(assessment_id=aid).one();lead_id=lead.id
   customer=db.query(CustomerAccount).filter_by(lead_id=lead.id).one();customer_id=customer.id
  assert c.get('/admin/client-portals').status_code==200
  assert c.post(f'/admin/leads/{lead_id}/client-portal/open',follow_redirects=False).status_code==303
  token_response=c.post(f'/admin/client-portals/{customer_id}/generate-token',follow_redirects=False);assert token_response.status_code==303
  token_path=token_response.headers['location'].split('login_link=',1)[1]
  assert 'customer_access_tokens' not in c.get('/admin/client-portals').text
  assert c.post(f'/payment/mock-pay/{aid}?product=1999_structure_plan',follow_redirects=False).status_code==303
  with SessionLocal() as db:report=db.query(Report).filter_by(assessment_id=aid).one();report_id=report.id
  assert c.post(f'/admin/reports/{report_id}/approve',data={'review_note':'Phase10验收通过'},follow_redirects=False).status_code==303
  assert c.post(f'/admin/leads/{lead_id}/customer-tasks/create',data={'task_type':'upload_document','task_title':'补充资料：营业执照','task_content':'请上传营业执照','priority':'high','due_time':''},follow_redirects=False).status_code==303
  assert c.post(f'/admin/leads/{lead_id}/messages/send',data={'message_type':'advisor','title':'欢迎进入客户门户','content':'您的融资服务已进入资料准备阶段。'},follow_redirects=False).status_code==303
  assert c.post(f'/admin/leads/{lead_id}/confirmations/create',data={'confirmation_type':'application_submit_authorized','title':'资料提交授权','content':'同意将已确认资料提交给拟申请金融机构。'},follow_redirects=False).status_code==303
  project=c.post('/admin/financing-projects/create',data={'lead_id':lead_id,'project_name':'Phase10融资项目','target_amount':'5000000'},follow_redirects=False);project_id=int(project.headers['location'].rsplit('/',1)[-1])
  update={'project_status':'submitted','target_amount':'5000000','approved_amount':'0','actual_disbursed_amount':'0','expected_rate':'5','final_rate':'0','expected_term':'12','final_term':'0','priority':'high','project_owner_id':'0','expected_close_date':'','project_summary':'资料已提交金融机构','failure_reason':''}
  assert c.post(f'/admin/financing-projects/{project_id}/update',data=update,follow_redirects=False).status_code==303
  c.get('/logout');assert c.get(token_path,follow_redirects=False).status_code==303
  assert c.get('/client/dashboard').status_code==200
  assert c.get('/client/reports').status_code==200
  report_page=c.get(f'/client/reports/{report_id}');assert report_page.status_code==200 and PAYLOAD['company_name'] in report_page.text
  upload=c.post('/client/documents/upload',data={'document_category':'营业执照/工商资料','note':'客户上传'},files=[('files',('营业执照.png',b'not-real-image','image/png'))],follow_redirects=False);assert upload.status_code==303
  tasks=c.get('/client/tasks');assert tasks.status_code==200
  with SessionLocal() as db:
   doc=db.query(UploadedDocument).filter_by(customer_id=customer_id).one();assert doc.uploaded_source=='customer'
   assert db.query(DocumentParseTask).filter_by(document_id=doc.id).count()==1
   task=db.query(CustomerTask).filter_by(customer_id=customer_id,task_title='补充资料：营业执照').one();assert task.status=='done'
   message=db.query(CustomerMessage).filter_by(customer_id=customer_id,title='欢迎进入客户门户').one();message_id=message.id
   confirmation=db.query(CustomerConfirmation).filter_by(customer_id=customer_id).one();confirmation_id=confirmation.id
  assert c.get(f'/client/messages/{message_id}').status_code==200
  assert c.post(f'/client/confirmations/{confirmation_id}/confirm',follow_redirects=False).status_code==303
  project_page=c.get(f'/client/projects/{project_id}');assert project_page.status_code==200 and '已提交申请' in project_page.text
  c.get('/client/logout');assert c.get('/client/dashboard').status_code==401
  with SessionLocal() as db:
   assert db.get(CustomerMessage,message_id).status=='read'
   assert db.get(CustomerConfirmation,confirmation_id).status=='confirmed'
   assert db.query(CustomerMessage).filter_by(customer_id=customer_id,message_type='project_update').count()>=1
   assert db.query(UploadedDocument).filter_by(customer_id=customer_id).count()==1
  print({'assessment_id':aid,'lead_id':lead_id,'customer_id':customer_id,'report_id':report_id,'project_id':project_id})
 print('PHASE10_CLIENT_PORTAL_OK')
 engine.dispose()
 if TEST_DB.exists():TEST_DB.unlink()
if __name__=='__main__':run()
