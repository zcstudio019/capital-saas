"""Phase 8：融资项目、资金方申请、SOP、方案比选、放款与复盘验收。"""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent; sys.path.insert(0,str(ROOT))
from fastapi.testclient import TestClient
from db.database import SessionLocal
from db.models import (ConsultingCase, Event, FinancingProject, FundingApplication,
    ProjectReview, ProjectTask, ProjectTimelineEvent, RejectionReasonLibrary, SuccessCase)
from main import app

PAYLOAD={"company_name":"Phase8融资交付测试企业有限公司","contact_name":"项目负责人","phone":"13300133000",
"wechat_id":"phase8_delivery","city":"上海","industry":"制造业","years":"8","employee_count":"80",
"annual_revenue":"26000000","net_profit":"2300000","monthly_cashflow":"680000","debt_total":"8000000",
"short_debt":"4500000","receivable_days":"75","funding_need":"5000000","funding_purpose":"订单周转和设备投入",
"has_collateral":"true","tax_status":"true","credit_status":"true","knows_cashflow":"true","has_budget":"true",
"leverage_attitude":"适中","asset_efficiency":"高","fund_usage_plan":"true"}

def login(c): assert c.post('/login',data={'username':'admin','password':'admin123','next_url':'/admin'},follow_redirects=False).status_code==303

def run():
  with TestClient(app) as c:
    s=c.post('/assessment/submit',data=PAYLOAD,follow_redirects=False); aid=int(s.headers['location'].rsplit('/',1)[-1])
    assert c.post(f'/payment/mock-pay/{aid}?product=1999_structure_plan',follow_redirects=False).status_code==303
    login(c)
    with SessionLocal() as db:
      case=db.query(ConsultingCase).filter(ConsultingCase.assessment_id==aid).one(); case_id=case.id; lead_id=case.lead_id
    created=c.post('/admin/financing-projects/create',data={'lead_id':lead_id,'consulting_case_id':case_id,
      'project_name':'Phase8融资交付项目','target_amount':'5000000','priority':'high','expected_rate':'6','expected_term':'24'},follow_redirects=False)
    assert created.status_code==303; project_id=int(created.headers['location'].rsplit('/',1)[-1])
    assert c.get('/admin/financing-projects').status_code==200
    assert c.get('/admin/delivery').status_code==200
    page=c.get(f'/admin/financing-projects/{project_id}'); assert page.status_code==200 and '项目SOP' in page.text
    with SessionLocal() as db:
      assert db.query(ProjectTask).filter(ProjectTask.project_id==project_id).count()>=4
      assert db.query(ProjectTimelineEvent).filter(ProjectTimelineEvent.project_id==project_id).count()>=1

    apps=[]
    for name,itype,rate in [('模拟城商行','bank','5.2'),('模拟担保机构','guarantee','6.5'),('模拟供应链机构','factoring','7.2')]:
      r=c.post(f'/admin/financing-projects/{project_id}/applications/create',data={'institution_name':name,
        'institution_type':itype,'product_name':name+'经营方案','apply_amount':'5000000','expected_rate':rate,
        'loan_term':'24','repayment_method':'equal_installment'},follow_redirects=False); assert r.status_code==303
    with SessionLocal() as db: apps=[x.id for x in db.query(FundingApplication).filter(FundingApplication.project_id==project_id).all()]
    for app_id in apps[:2]:
      assert c.post(f'/admin/funding-applications/{app_id}/update-status',data={'application_status':'approved'},follow_redirects=False).status_code==303
    assert c.post(f'/admin/funding-applications/{apps[0]}/update-result',data={'approved_amount':'4500000','final_amount':'4500000','approved_rate':'5.2','loan_term':'24'},follow_redirects=False).status_code==303
    assert c.post(f'/admin/funding-applications/{apps[1]}/update-result',data={'approved_amount':'3500000','final_amount':'0','approved_rate':'6.5','loan_term':'36'},follow_redirects=False).status_code==303
    assert c.post(f'/admin/funding-applications/{apps[2]}/update-status',data={'application_status':'rejected'},follow_redirects=False).status_code==303
    assert c.post(f'/admin/funding-applications/{apps[2]}/update-result',data={'approved_amount':'0','final_amount':'0','approved_rate':'0','loan_term':'12','reason_category':'银行政策不匹配','rejection_reason':'行业授信政策临时收紧','improvement_suggestion':'调整申请机构和申请顺序'},follow_redirects=False).status_code==303
    detail=c.get(f'/admin/financing-projects/{project_id}'); assert '多方案比选' in detail.text and '模拟城商行' in detail.text
    cost=c.post('/api/loan-cost/calculate',data={'project_id':project_id,'loan_amount':'4500000','annual_rate':'5.2','months':'24','repayment_method':'equal_installment'})
    assert cost.status_code==200 and cost.json()['total_interest']>0 and len(cost.json()['repayment_schedule'])==24

    update={'project_status':'disbursed','target_amount':'5000000','approved_amount':'8000000','actual_disbursed_amount':'4500000',
      'expected_rate':'6','final_rate':'5.2','expected_term':'24','final_term':'24','priority':'high','project_owner_id':'1',
      'expected_close_date':'','project_summary':'已完成首笔放款','failure_reason':''}
    assert c.post(f'/admin/financing-projects/{project_id}/update',data=update,follow_redirects=False).status_code==303
    with SessionLocal() as db:
      project=db.get(FinancingProject,project_id); assert project.success_result=='partial_success'
      post_tasks=db.query(ProjectTask).filter(ProjectTask.project_id==project_id,ProjectTask.task_type.in_(['repayment_reminder','post_loan_check','renewal_prepare','cashflow_review'])).all()
      assert len(post_tasks)>=6; task_id=post_tasks[0].id
    assert c.post(f'/admin/project-tasks/{task_id}/done',follow_redirects=False).status_code==303
    assert c.post(f'/admin/financing-projects/{project_id}/review/generate',follow_redirects=False).status_code==303
    assert c.get(f'/admin/financing-projects/{project_id}/review').status_code==200
    assert c.post(f'/admin/financing-projects/{project_id}/review/update',data={'review_status':'completed','lessons_learned':'先做预审再正式提交','reusable_case_summary':'制造业企业融资交付案例'},follow_redirects=False).status_code==303
    assert c.post(f'/admin/financing-projects/{project_id}/success-case/create',follow_redirects=False).status_code==303
    assert c.get('/admin/success-cases').status_code==200 and c.get('/admin/rejection-reasons').status_code==200
    assert c.post('/api/events/project-message-copied',data={'project_id':project_id}).status_code==200
    with SessionLocal() as db:
      assert db.query(ProjectReview).filter(ProjectReview.project_id==project_id).count()==1
      assert db.query(SuccessCase).filter(SuccessCase.project_id==project_id).count()==1
      assert db.query(RejectionReasonLibrary).filter(RejectionReasonLibrary.related_project_id==project_id).count()==1
      types={e.event_type for e in db.query(Event).filter(Event.assessment_id==aid).all()}
      assert {'financing_project_created','funding_application_created','funding_application_approved',
        'funding_application_rejected','project_task_created','offer_compared','loan_cost_calculated',
        'project_review_generated','success_case_created','rejection_reason_added','project_message_copied'}<=types
      timeline_count=db.query(ProjectTimelineEvent).filter(ProjectTimelineEvent.project_id==project_id).count()
    print({'assessment_id':aid,'project_id':project_id,'applications':len(apps),'timeline_events':timeline_count,'post_loan_tasks':len(post_tasks)})
  print('PHASE8_FINANCING_DELIVERY_OK')

if __name__=='__main__': run()
