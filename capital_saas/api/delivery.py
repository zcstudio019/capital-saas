import json
from datetime import date, datetime, time, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from core.config import BASE_DIR
from core.access_scope import get_access_scope
from core.financing_offer_compare_engine import compare_financing_offers
from core.loan_cost_calculator import calculate_loan_cost
from core.project_message_engine import generate_project_message
from db.database import get_db
from db.models import (BankProduct, ConsultingCase, DueDiligenceReport,
    FinancingApplicationPackage, FinancingProject, FundingApplication, Lead,
    ProjectReview, ProjectTask, ProjectTimelineEvent, RejectionReasonLibrary,
    SuccessCase, User)
from services.auth_service import require_roles
from services.event_service import track_event
from services.project_service import (add_timeline, create_funding_application,
    create_project, ensure_sop_tasks, update_application_result,
    update_application_status, update_project_status)

router = APIRouter()
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
READ_ROLES = ("admin","super_admin","city_manager","sales_manager","sales","consultant_manager","consultant","finance","viewer","partner")
WRITE_ROLES = ("admin","super_admin","city_manager","sales_manager","sales","consultant_manager","consultant")
PROJECT_STATUSES = ["draft", "preparing", "submitted", "bank_review", "supplement_required",
                    "approved", "rejected", "disbursed", "cancelled", "archived"]
APPLICATION_STATUSES = ["planned", "submitted", "reviewing", "supplement_required",
                        "approved", "rejected", "disbursed", "withdrawn"]


def _project(db: Session, project_id: int) -> FinancingProject:
    item = db.get(FinancingProject, project_id)
    if not item: raise HTTPException(404, "融资项目不存在")
    return item


def _check_access(project: FinancingProject, user: User, write=False):
    if write and user.role == "viewer": raise HTTPException(403, "只读用户不能修改项目")
    from db.database import SessionLocal
    with SessionLocal() as scope_db: scope=get_access_scope(scope_db,user)
    if scope.can_view_all:return
    if scope.role=="partner":
        lead=scope_db.get(Lead,project.lead_id)
        if not lead or lead.source_partner_id not in scope.allowed_partner_ids:raise HTTPException(403,"伙伴只能查看推荐项目")
    elif scope.role in {"sales","consultant"}:
        allowed={project.project_owner_id,project.owner_user_id,project.consultant_user_id}
        if user.id not in allowed:raise HTTPException(403,"只能访问自己负责的项目")
    elif project.owner_org_id not in scope.allowed_org_ids and project.org_id not in scope.allowed_org_ids:
        raise HTTPException(403,"无权访问该组织项目")


def _lead(db, lead_id):
    lead = db.get(Lead, lead_id)
    if not lead: raise HTTPException(404, "线索不存在")
    return lead


def _parse_dt(value: str): return datetime.fromisoformat(value) if value else None


@router.get("/admin/financing-projects", response_class=HTMLResponse)
def project_list(request: Request, project_status: str = "", project_owner_id: int = 0,
    priority: str = "", success_result: str = "", date_from: str = "", date_to: str = "",
    db: Session = Depends(get_db), user: User = Depends(require_roles(*READ_ROLES))):
    query = db.query(FinancingProject)
    scope=get_access_scope(db,user)
    if not scope.can_view_all:
        if scope.role in {"sales","consultant"}: query=query.filter((FinancingProject.project_owner_id==user.id)|(FinancingProject.owner_user_id==user.id)|(FinancingProject.consultant_user_id==user.id))
        else: query=query.filter((FinancingProject.owner_org_id.in_(scope.allowed_org_ids or [-1]))|(FinancingProject.org_id.in_(scope.allowed_org_ids or [-1])))
    if project_status: query = query.filter(FinancingProject.project_status == project_status)
    if project_owner_id: query = query.filter(FinancingProject.project_owner_id == project_owner_id)
    if priority: query = query.filter(FinancingProject.priority == priority)
    if success_result: query = query.filter(FinancingProject.success_result == success_result)
    if date_from: query = query.filter(FinancingProject.created_at >= datetime.fromisoformat(date_from))
    if date_to: query = query.filter(FinancingProject.created_at <= datetime.fromisoformat(date_to) + timedelta(days=1))
    projects = query.order_by(FinancingProject.updated_at.desc()).all()
    leads = {x.id: db.get(Lead, x.lead_id) for x in projects}
    owners = {x.id: db.get(User, x.project_owner_id) if x.project_owner_id else None for x in projects}
    return templates.TemplateResponse(request=request, name="admin_financing_projects.html", context={
        "projects": projects, "leads": leads, "owners": owners, "current_user": user,
        "statuses": PROJECT_STATUSES, "users": db.query(User).filter(User.role.in_(["admin", "sales"]), User.is_active.is_(True)).all(),
        "filters": {"project_status":project_status,"project_owner_id":project_owner_id,"priority":priority,
                    "success_result":success_result,"date_from":date_from,"date_to":date_to}})


@router.post("/admin/financing-projects/create")
def create_project_route(lead_id: int = Form(...), project_name: str = Form(...), target_amount: float = Form(...),
    consulting_case_id: int = Form(0), application_package_id: int = Form(0), priority: str = Form("high"),
    expected_rate: float = Form(0), expected_term: int = Form(12), expected_close_date: str = Form(""),
    db: Session = Depends(get_db), user: User = Depends(require_roles(*WRITE_ROLES))):
    lead = _lead(db, lead_id)
    project = create_project(db, lead, user, project_name.strip(), target_amount,
        consulting_case_id or None, application_package_id or None, priority, expected_rate,
        expected_term, _parse_dt(expected_close_date))
    return RedirectResponse(f"/admin/financing-projects/{project.id}", 303)


@router.get("/admin/financing-projects/{project_id}", response_class=HTMLResponse)
def project_detail(request: Request, project_id: int, db: Session = Depends(get_db),
    user: User = Depends(require_roles(*READ_ROLES))):
    project = _project(db, project_id); _check_access(project, user)
    lead = db.get(Lead, project.lead_id)
    applications = db.query(FundingApplication).filter(FundingApplication.project_id == project.id).order_by(FundingApplication.created_at.desc()).all()
    timeline = db.query(ProjectTimelineEvent).filter(ProjectTimelineEvent.project_id == project.id).order_by(ProjectTimelineEvent.created_at.desc()).all()
    tasks = db.query(ProjectTask).filter(ProjectTask.project_id == project.id).order_by(ProjectTask.due_time).all()
    costs = {a.id: calculate_loan_cost(a.final_amount or a.approved_amount or a.apply_amount,
        a.approved_rate or a.expected_rate, a.loan_term, a.repayment_method) for a in applications}
    offer_compare = compare_financing_offers(applications)
    track_event(db, "offer_compared", project.assessment_id, project.lead_id,
                {"project_id": project.id, "offer_count": len(offer_compare["ranking"])})
    return templates.TemplateResponse(request=request, name="admin_financing_project_detail.html", context={
        "project": project, "lead": lead, "assessment": lead.assessment,
        "dd": db.query(DueDiligenceReport).filter(DueDiligenceReport.lead_id == lead.id).first(),
        "package": db.get(FinancingApplicationPackage, project.application_package_id) if project.application_package_id else None,
        "case": db.get(ConsultingCase, project.consulting_case_id) if project.consulting_case_id else None,
        "applications": applications, "timeline": timeline, "tasks": tasks, "costs": costs,
        "offer_compare": offer_compare, "message": generate_project_message(project.project_status),
        "bank_products": db.query(BankProduct).filter(BankProduct.is_active.is_(True)).all(),
        "users": db.query(User).filter(User.role.in_(["admin","sales"]), User.is_active.is_(True)).all(),
        "statuses": PROJECT_STATUSES, "application_statuses": APPLICATION_STATUSES,
        "current_user": user, "can_edit": user.role in {"admin","sales"}})


@router.post("/admin/financing-projects/{project_id}/update")
def update_project_route(project_id: int, project_status: str = Form(...), target_amount: float = Form(...),
    approved_amount: float = Form(0), actual_disbursed_amount: float = Form(0), expected_rate: float = Form(0),
    final_rate: float = Form(0), expected_term: int = Form(12), final_term: int = Form(0),
    priority: str = Form("medium"), project_owner_id: int = Form(0), expected_close_date: str = Form(""),
    project_summary: str = Form(""), failure_reason: str = Form(""),
    db: Session = Depends(get_db), user: User = Depends(require_roles(*WRITE_ROLES))):
    project = _project(db, project_id); _check_access(project, user, True)
    old_status = project.project_status
    project.target_amount, project.approved_amount = target_amount, approved_amount
    project.actual_disbursed_amount, project.expected_rate, project.final_rate = actual_disbursed_amount, expected_rate, final_rate
    project.expected_term, project.final_term, project.priority = expected_term, final_term, priority
    if user.role == "admin": project.project_owner_id = project_owner_id or project.project_owner_id
    project.expected_close_date, project.failure_reason = _parse_dt(expected_close_date), failure_reason.strip()
    if project_status != old_status: update_project_status(db, project, project_status, user, project_summary.strip())
    else: project.project_summary, project.updated_at = project_summary.strip(), datetime.now()
    db.commit(); return RedirectResponse(f"/admin/financing-projects/{project.id}", 303)


@router.post("/admin/financing-projects/{project_id}/archive")
def archive_project(project_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("admin"))):
    project = _project(db, project_id); update_project_status(db, project, "archived", user, "项目已归档")
    db.commit(); return RedirectResponse("/admin/financing-projects", 303)


@router.post("/admin/financing-projects/{project_id}/applications/create")
def create_application_route(project_id: int, bank_product_id: int = Form(0), institution_name: str = Form(""),
    institution_type: str = Form("bank"), product_name: str = Form(""), apply_amount: float = Form(...),
    expected_rate: float = Form(0), loan_term: int = Form(12), repayment_method: str = Form("interest_first"),
    contact_person: str = Form(""), contact_phone: str = Form(""), advisor_note: str = Form(""),
    institution_contact_id: int = Form(0),
    db: Session = Depends(get_db), user: User = Depends(require_roles(*WRITE_ROLES))):
    project = _project(db, project_id); _check_access(project, user, True)
    application = create_funding_application(db, project, user, institution_name, institution_type, product_name,
        apply_amount, bank_product_id or None, expected_rate, loan_term, repayment_method)
    application.contact_person, application.contact_phone = contact_person.strip(), contact_phone.strip()
    application.advisor_note = advisor_note.strip(); application.institution_contact_id = institution_contact_id or None; db.commit()
    return RedirectResponse(f"/admin/financing-projects/{project.id}", 303)


@router.post("/admin/funding-applications/{application_id}/update-status")
def update_application_status_route(application_id: int, application_status: str = Form(...),
    supplement_note: str = Form(""), db: Session = Depends(get_db), user: User = Depends(require_roles(*WRITE_ROLES))):
    application = db.get(FundingApplication, application_id)
    if not application: raise HTTPException(404, "资金方申请不存在")
    project = _project(db, application.project_id); _check_access(project, user, True)
    update_application_status(db, application, application_status, user, supplement_note); db.commit()
    if application.institution_contact_id and application_status in {"approved","rejected","disbursed"}:
        from db.models import InstitutionContact
        contact=db.get(InstitutionContact,application.institution_contact_id)
        if contact:
            if application_status in {"approved","disbursed"}: contact.success_count += 1
            else: contact.rejection_count += 1
            db.commit()
    return RedirectResponse(f"/admin/financing-projects/{project.id}", 303)


@router.post("/admin/funding-applications/{application_id}/update-result")
def update_application_result_route(application_id: int, approved_amount: float = Form(0), final_amount: float = Form(0),
    approved_rate: float = Form(0), loan_term: int = Form(12), rejection_reason: str = Form(""),
    reason_category: str = Form("其他"), improvement_suggestion: str = Form(""),
    db: Session = Depends(get_db), user: User = Depends(require_roles(*WRITE_ROLES))):
    application = db.get(FundingApplication, application_id)
    if not application: raise HTTPException(404, "资金方申请不存在")
    project = _project(db, application.project_id); _check_access(project, user, True)
    update_application_result(db, application, user, approved_amount, final_amount, approved_rate,
                              loan_term, rejection_reason, reason_category, improvement_suggestion)
    db.commit(); return RedirectResponse(f"/admin/financing-projects/{project.id}", 303)


@router.post("/admin/project-tasks/{task_id}/done")
def project_task_done(task_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles(*WRITE_ROLES))):
    task = db.get(ProjectTask, task_id)
    if not task: raise HTTPException(404, "项目任务不存在")
    project = _project(db, task.project_id); _check_access(project, user, True)
    task.status, task.updated_at = "done", datetime.now()
    add_timeline(db, project, "note_added", f"完成项目任务：{task.task_title}", user)
    track_event(db, "project_task_done", project.assessment_id, project.lead_id,
                {"project_id": project.id, "task_id": task.id}, commit=False)
    db.commit(); return RedirectResponse(f"/admin/financing-projects/{project.id}", 303)


@router.post("/api/loan-cost/calculate")
def loan_cost_api(project_id: int = Form(...), loan_amount: float = Form(...), annual_rate: float = Form(...),
    months: int = Form(...), repayment_method: str = Form("interest_first"),
    db: Session = Depends(get_db), user: User = Depends(require_roles(*READ_ROLES))):
    project = _project(db, project_id); _check_access(project, user)
    result = calculate_loan_cost(loan_amount, annual_rate, months, repayment_method)
    track_event(db, "loan_cost_calculated", project.assessment_id, project.lead_id,
                {"project_id": project.id, "loan_amount": loan_amount, "annual_rate": annual_rate})
    return JSONResponse(result)


@router.get("/admin/financing-projects/{project_id}/review", response_class=HTMLResponse)
def project_review_page(request: Request, project_id: int, db: Session = Depends(get_db),
    user: User = Depends(require_roles(*READ_ROLES))):
    project = _project(db, project_id); _check_access(project, user)
    return templates.TemplateResponse(request=request, name="admin_project_review.html", context={
        "project": project, "lead": db.get(Lead, project.lead_id),
        "review": db.query(ProjectReview).filter(ProjectReview.project_id == project.id).first(),
        "current_user": user, "can_edit": user.role in {"admin","sales"}})


@router.post("/admin/financing-projects/{project_id}/review/generate")
def generate_review(project_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles(*WRITE_ROLES))):
    project = _project(db, project_id); _check_access(project, user, True)
    applications = db.query(FundingApplication).filter(FundingApplication.project_id == project.id).all()
    review = db.query(ProjectReview).filter(ProjectReview.project_id == project.id).first() or ProjectReview(project_id=project.id, created_by=user.id)
    if not review.id: db.add(review)
    review.review_status = "generated"; review.target_amount = project.target_amount
    review.approved_amount = project.approved_amount; review.disbursed_amount = project.actual_disbursed_amount
    review.approval_days = max(0, ((project.closed_at or datetime.now()) - project.start_date).days)
    review.final_rate = project.final_rate
    review.success_factors_json = json.dumps(["资料口径一致", "申请顺序合理", "客户配合及时"] if project.success_result in {"success","partial_success"} else [], ensure_ascii=False)
    review.failure_reasons_json = json.dumps([x.rejection_reason for x in applications if x.rejection_reason] or ([project.failure_reason] if project.failure_reason else []), ensure_ascii=False)
    review.reusable_case_summary = f"{db.get(Lead, project.lead_id).assessment.industry}企业目标融资{project.target_amount/10000:,.0f}万元，实际放款{project.actual_disbursed_amount/10000:,.0f}万元。"
    track_event(db, "project_review_generated", project.assessment_id, project.lead_id, {"project_id":project.id}, commit=False)
    db.commit(); return RedirectResponse(f"/admin/financing-projects/{project.id}/review", 303)


@router.post("/admin/financing-projects/{project_id}/review/update")
def update_review(project_id: int, review_status: str = Form("completed"), lessons_learned: str = Form(""),
    reusable_case_summary: str = Form(""), db: Session = Depends(get_db), user: User = Depends(require_roles(*WRITE_ROLES))):
    project = _project(db, project_id); _check_access(project, user, True)
    review = db.query(ProjectReview).filter(ProjectReview.project_id == project.id).first()
    if not review: raise HTTPException(404, "请先生成项目复盘")
    review.review_status, review.lessons_learned = review_status, lessons_learned.strip()
    review.reusable_case_summary, review.updated_at = reusable_case_summary.strip(), datetime.now(); db.commit()
    return RedirectResponse(f"/admin/financing-projects/{project.id}/review", 303)


@router.post("/admin/financing-projects/{project_id}/success-case/create")
def create_success_case(project_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("admin"))):
    project = _project(db, project_id)
    if project.success_result not in {"success", "partial_success"}: raise HTTPException(400, "只有成功或部分成功项目可生成案例")
    existing = db.query(SuccessCase).filter(SuccessCase.project_id == project.id).first()
    if not existing:
        lead = db.get(Lead, project.lead_id); application = db.query(FundingApplication).filter(
            FundingApplication.project_id == project.id, FundingApplication.application_status == "disbursed").first()
        case = SuccessCase(project_id=project.id, industry=lead.assessment.industry,
            company_scale=f"年营收约{lead.assessment.annual_revenue/10000:,.0f}万元",
            funding_amount=project.actual_disbursed_amount,
            product_type=application.product_name if application else "组合融资",
            institution_type=application.institution_type if application else "bank",
            approval_days=max(0, ((project.closed_at or datetime.now()) - project.start_date).days),
            rate_range=f"{project.final_rate:.2f}%" if project.final_rate else "以实际合同为准",
            case_title=f"{lead.assessment.industry}企业融资交付案例",
            case_summary=f"某{lead.assessment.industry}企业完成{project.actual_disbursed_amount/10000:,.0f}万元融资。",
            key_success_factors="资料口径一致、申请顺序合理、审批响应及时", anonymized=True, is_public=False)
        db.add(case); track_event(db, "success_case_created", project.assessment_id, project.lead_id,
                                  {"project_id":project.id}, commit=False); db.commit()
    return RedirectResponse("/admin/success-cases", 303)


@router.get("/admin/success-cases", response_class=HTMLResponse)
def success_cases(request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles(*READ_ROLES))):
    return templates.TemplateResponse(request=request, name="admin_success_cases.html", context={
        "cases":db.query(SuccessCase).order_by(SuccessCase.created_at.desc()).all(),"current_user":user})


@router.get("/admin/rejection-reasons", response_class=HTMLResponse)
def rejection_reasons(request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles(*READ_ROLES))):
    return templates.TemplateResponse(request=request, name="admin_rejection_reasons.html", context={
        "reasons":db.query(RejectionReasonLibrary).order_by(RejectionReasonLibrary.created_at.desc()).all(),"current_user":user})


@router.get("/admin/delivery", response_class=HTMLResponse)
def delivery_dashboard(request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles(*READ_ROLES))):
    projects_query = db.query(FinancingProject)
    scope=get_access_scope(db,user)
    if not scope.can_view_all:
        if scope.role in {"sales","consultant"}: projects_query=projects_query.filter((FinancingProject.project_owner_id==user.id)|(FinancingProject.consultant_user_id==user.id))
        else: projects_query=projects_query.filter(FinancingProject.owner_org_id.in_(scope.allowed_org_ids or [-1]))
    projects = projects_query.all(); project_ids = [p.id for p in projects]
    applications = db.query(FundingApplication).filter(FundingApplication.project_id.in_(project_ids or [-1])).all()
    month_start = datetime.combine(date.today().replace(day=1), time.min)
    approved_month = sum(a.approved_amount for a in applications if a.approved_at and a.approved_at >= month_start)
    disbursed_month = sum(a.final_amount for a in applications if a.disbursed_at and a.disbursed_at >= month_start)
    decided = [a for a in applications if a.application_status in {"approved","rejected","disbursed"}]
    passed = [a for a in decided if a.application_status in {"approved","disbursed"}]
    institution_stats = {}
    for a in decided:
        row = institution_stats.setdefault(a.institution_name, {"total":0,"passed":0,"amount":0})
        row["total"] += 1; row["passed"] += int(a.application_status in {"approved","disbursed"}); row["amount"] += a.final_amount or a.approved_amount
    status_counts = {status: sum(p.project_status == status for p in projects) for status in PROJECT_STATUSES}
    owner_stats = {}
    for p in projects:
        owner = db.get(User, p.project_owner_id) if p.project_owner_id else None
        row = owner_stats.setdefault(owner.username if owner else "未分配", {"projects":0,"success":0,"disbursed":0})
        row["projects"] += 1; row["success"] += int(p.success_result in {"success","partial_success"})
        row["disbursed"] += p.actual_disbursed_amount
    tasks = db.query(ProjectTask).filter(ProjectTask.project_id.in_(project_ids or [-1]), ProjectTask.status == "pending").order_by(ProjectTask.due_time).limit(12).all()
    return templates.TemplateResponse(request=request, name="admin_delivery_dashboard.html", context={
        "projects":projects,"project_count":len(projects),"status_counts":status_counts,
        "approved_month":approved_month,"disbursed_month":disbursed_month,
        "average_days":round(sum(max(0,((p.closed_at or datetime.now())-p.start_date).days) for p in projects)/len(projects),1) if projects else 0,
        "pass_rate":round(len(passed)/len(decided)*100,1) if decided else 0,"institution_stats":institution_stats,
        "owner_stats":owner_stats,
        "tasks":tasks,"recent_disbursed":[p for p in projects if p.project_status=="disbursed"][-10:],
        "recent_rejected":[p for p in projects if p.project_status=="rejected"][-10:],"current_user":user})


@router.post("/api/events/project-message-copied")
def project_message_copied(project_id: int = Form(...), db: Session = Depends(get_db),
    user: User = Depends(require_roles(*WRITE_ROLES))):
    project = _project(db, project_id); _check_access(project,user)
    track_event(db,"project_message_copied",project.assessment_id,project.lead_id,
                {"project_id":project.id,"operator":user.username}); return {"ok":True}
