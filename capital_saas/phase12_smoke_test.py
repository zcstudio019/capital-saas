"""Phase 12 安全、合规、备份、健康与生产运维验收。"""
import os,sys,zipfile,io
from pathlib import Path
ROOT=Path(__file__).resolve().parent;DB=ROOT/'phase12_test.db'
if DB.exists():DB.unlink()
os.environ['DATABASE_URL']=f"sqlite:///{DB.as_posix()}";os.environ['APP_ENV']='development';sys.path.insert(0,str(ROOT))
from fastapi.testclient import TestClient
from core.data_masking import mask_bank_account,mask_email,mask_identity,mask_phone,mask_wechat
from db.database import SessionLocal,engine
from db.models import (AuditLog,CustomerAccount,Event,LegalAcceptance,LegalDocument,Lead,
    UploadedDocument,User,WorkerRun)
from main import app
from services.customer_portal_service import generate_login_token
from services.worker_service import finish_worker_run,start_worker_run

P={"company_name":"Phase12安全企业","contact_name":"安全客户","phone":"13812345678","wechat_id":"securewx88","city":"上海","industry":"制造业","years":"8","employee_count":"50","annual_revenue":"20000000","net_profit":"1800000","monthly_cashflow":"600000","debt_total":"4000000","short_debt":"1500000","receivable_days":"40","funding_need":"5000000","funding_purpose":"设备扩产","has_collateral":"true","tax_status":"true","credit_status":"true","knows_cashflow":"true","has_budget":"true","leverage_attitude":"适中","asset_efficiency":"高","fund_usage_plan":"true"}
def login(c,p='admin123'):return c.post('/login',data={'username':'admin','password':p,'next_url':'/admin'},follow_redirects=False)
def run():
 with TestClient(app) as c:
  with SessionLocal() as db:admin=db.query(User).filter_by(username='admin').one();assert admin.force_password_change is True
  for _ in range(5):assert login(c,'wrong-password').status_code==400
  assert login(c).status_code==400
  with SessionLocal() as db:
   admin=db.query(User).filter_by(username='admin').one();assert admin.failed_login_count>=5 and admin.locked_until;admin.failed_login_count=0;admin.locked_until=None;db.commit()
  assert login(c).status_code==303
  assert c.get('/admin/account/security').status_code==200
  changed=c.post('/admin/account/password',data={'current_password':'admin123','new_password':'Phase12-Strong-Pass!'},follow_redirects=False);assert changed.status_code==303
  c.get('/logout');assert login(c,'Phase12-Strong-Pass!').status_code==303
  assert c.get('/admin/users').status_code==200
  created=c.post('/admin/users/create',data={'username':'phase12_viewer','password':'Viewer-Strong-12','role':'viewer','org_id':'1'},follow_redirects=False);assert created.status_code==303
  submit=c.post('/assessment/submit',data=P,follow_redirects=False);aid=int(submit.headers['location'].rsplit('/',1)[-1])
  with SessionLocal() as db:
   lead=db.query(Lead).filter_by(assessment_id=aid).one();lead_id=lead.id;customer=db.query(CustomerAccount).filter_by(lead_id=lead.id).one();customer_id=customer.id;token=generate_login_token(db,customer).token
  c.get('/logout');assert c.post('/login',data={'username':'phase12_viewer','password':'Viewer-Strong-12','next_url':'/admin/leads'},follow_redirects=False).status_code==303
  masked=c.get('/admin/leads');assert masked.status_code==200 and '138****5678' in masked.text and '13812345678' not in masked.text
  c.get('/logout');assert c.get(f'/client/login-token/{token}',follow_redirects=False).status_code==303
  legal=c.get('/client/legal');assert legal.status_code==200
  with SessionLocal() as db:doc_ids=[x.id for x in db.query(LegalDocument).filter_by(is_active=True).all()]
  for doc_id in doc_ids:assert c.post(f'/client/legal/{doc_id}/accept',follow_redirects=False).status_code==303
  bad=c.post('/client/documents/upload',data={'document_category':'其他资料','note':'bad'},files=[('files',('attack.exe',b'MZ','application/octet-stream'))]);assert bad.status_code==400
  good=c.post('/client/documents/upload',data={'document_category':'营业执照/工商资料','note':'安全上传'},files=[('files',('营业执照.png',b'png-data','image/png'))],follow_redirects=False);assert good.status_code==303
  with SessionLocal() as db:
   document=db.query(UploadedDocument).filter_by(customer_id=customer_id).one();document_id=document.id
   assert db.query(LegalAcceptance).filter_by(customer_id=customer_id).count()>=3
   assert db.query(Event).filter_by(event_type='file_security_rejected').count()>=1
  c.get('/client/logout');assert login(c,'Phase12-Strong-Pass!').status_code==303
  assert c.get('/admin/audit-logs').status_code==200
  assert c.get('/admin/legal-documents').status_code==200
  assert c.post('/admin/backups/create',follow_redirects=False).status_code==303
  backups=c.get('/admin/backups');assert backups.status_code==200 and 'capital_saas_' in backups.text
  assert c.get('/health').status_code==200 and c.get('/healthz').status_code==200 and c.get('/ready').status_code==200
  assert c.get('/admin/system-health').status_code==200
  assert c.get('/admin/production-checklist').status_code==200
  export=c.get(f'/admin/leads/{lead_id}/compliance-export.zip');assert export.status_code==200
  with zipfile.ZipFile(io.BytesIO(export.content)) as z:assert {'lead.csv','assessment.csv','reports.csv','documents_manifest.csv','audit_summary.csv'}<=set(z.namelist())
  deleted=c.post(f'/admin/documents/{document_id}/soft-delete',data={'delete_reason':'Phase12测试软删除'},follow_redirects=False);assert deleted.status_code==303
  with SessionLocal() as db:
   assert db.get(UploadedDocument,document_id).deleted_at
   run=start_worker_run(db,'notification_worker');finish_worker_run(db,run,2,2,0);assert db.query(WorkerRun).count()>=1
   assert db.query(AuditLog).filter(AuditLog.action=='login_failed').count()>=5
  assert mask_phone('13812345678')=='138****5678';assert mask_identity('913100001234567890')[:4]=='9131';assert mask_bank_account('6222021234567890').endswith('7890');assert mask_email('a@example.com')=='a***@example.com';assert mask_wechat('secure88')=='se***88'
  print({'assessment_id':aid,'lead_id':lead_id,'customer_id':customer_id,'document_id':document_id})
 print('PHASE12_SECURITY_OPERATIONS_OK');engine.dispose()
 if DB.exists():DB.unlink()
if __name__=='__main__':run()
