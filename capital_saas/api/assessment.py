from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from core.conversion_engine import result_conversion_copy
from core.config import settings
from db.database import get_db
from services.ab_test_service import assign_variant
from services.assessment_service import create_assessment, get_assessment
from services.attribution_service import attribution_from_session, capture_attribution
from services.event_service import track_event
from services.report_service import parse_customer_free_summary
from utils.report_display_mapper import display_value
from core.capital_health_report import build_capital_health_report
from services.tag_service import auto_tag_lead


router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))

LANDING_PAGES = {
    "rongzi": {
        "title": "企业融资测评",
        "headline": "3分钟测出企业能不能贷、能贷多少、为什么被银行压额度。",
        "subheadline": "从银行审批、现金流、负债结构和融资条件四个视角，找到真正影响额度的因素。",
    },
    "cashflow": {
        "title": "现金流风险测评",
        "headline": "企业不是没利润，而是现金流结构出了问题。",
        "subheadline": "识别回款、短债、预算和资金使用中的隐性风险，避免利润增长却越来越缺钱。",
    },
    "bank": {
        "title": "银行贷款通过率测评",
        "headline": "银行会不会批你，不是看你缺不缺钱，而是看你的结构够不够标准。",
        "subheadline": "模拟银行审批视角，提前判断通过概率、额度区间和可能被拒原因。",
    },
    "boss": {
        "title": "老板财商诊断",
        "headline": "老板真正要懂的不是贷款，而是资金结构、杠杆和现金流。",
        "subheadline": "看清融资工具背后的成本、期限与经营风险，把缺口融资升级为资本规划。",
    },
}


@router.get("/", response_class=HTMLResponse)
def home(request: Request):
    capture_attribution(request, "/")
    return templates.TemplateResponse(request=request, name="index.html")


@router.get("/lp/{page_key}", response_class=HTMLResponse)
def landing_page(request: Request, page_key: str, db: Session = Depends(get_db)):
    page = LANDING_PAGES.get(page_key)
    if not page:
        raise HTTPException(status_code=404, detail="落地页不存在")
    attribution = capture_attribution(request, f"/lp/{page_key}")
    track_event(
        db, "landing_page_viewed",
        data={"landing_page": f"/lp/{page_key}", "page_key": page_key},
        attribution=attribution,
    )
    return templates.TemplateResponse(
        request=request, name="landing_page.html",
        context={"page": page, "page_key": page_key}
    )


@router.get("/assessment", response_class=HTMLResponse)
def assessment_form(request: Request, trial_code: str = "", db: Session = Depends(get_db)):
    attribution = capture_attribution(request)
    if settings.trial_mode:
        allowed = {x.strip() for x in settings.trial_allowed_ips.split(",") if x.strip()}
        client_ip = request.client.host if request.client else ""
        if client_ip not in allowed and not request.session.get("trial_gate_passed"):
            if settings.trial_access_code and trial_code == settings.trial_access_code:
                request.session["trial_gate_passed"] = True
                track_event(db, "trial_gate_passed", data={"ip": client_ip}, attribution=attribution)
            else:
                if trial_code:
                    track_event(db, "trial_gate_blocked", data={"ip": client_ip}, attribution=attribution)
                return templates.TemplateResponse(request=request, name="trial_gate.html", context={"error": "访问码不正确，请联系服务顾问。" if trial_code else ""})
    track_event(db, "assessment_page_viewed", data={}, attribution=attribution)
    return templates.TemplateResponse(request=request, name="assessment_form.html")


@router.post("/assessment/submit")
def submit_assessment(
    request: Request,
    company_name: str = Form(...), contact_name: str = Form(...), phone: str = Form(...),
    wechat_id: str = Form(""), city: str = Form(""), industry: str = Form(...),
    years: int = Form(...), employee_count: int = Form(...), annual_revenue: float = Form(...),
    net_profit: float = Form(...), monthly_cashflow: float = Form(...),
    debt_total: float = Form(...), short_debt: float = Form(...),
    receivable_days: int = Form(...), funding_need: float = Form(...),
    funding_purpose: str = Form(...), has_collateral: bool = Form(...),
    tax_status: bool = Form(...), credit_status: bool = Form(...),
    knows_cashflow: bool = Form(...), has_budget: bool = Form(...),
    leverage_attitude: str = Form(...), asset_efficiency: str = Form(...),
    fund_usage_plan: bool = Form(...), db: Session = Depends(get_db),
):
    capture_attribution(request)
    data = {
        "company_name": company_name.strip(), "contact_name": contact_name.strip(),
        "phone": phone.strip(), "wechat_id": wechat_id.strip(), "city": city.strip(),
        "industry": industry.strip(), "years": max(years, 0),
        "employee_count": max(employee_count, 0), "annual_revenue": max(annual_revenue, 0),
        "net_profit": net_profit, "monthly_cashflow": monthly_cashflow,
        "debt_total": max(debt_total, 0), "short_debt": max(short_debt, 0),
        "receivable_days": max(receivable_days, 0), "funding_need": max(funding_need, 0),
        "funding_purpose": funding_purpose.strip(), "has_collateral": has_collateral,
        "tax_status": tax_status, "credit_status": credit_status,
        "knows_cashflow": knows_cashflow, "has_budget": has_budget,
        "leverage_attitude": leverage_attitude, "asset_efficiency": asset_efficiency,
        "fund_usage_plan": fund_usage_plan,
        "partner_source_code": str(request.session.get("partner_source_code", ""))[:100],
        "pilot_invite_code": str(request.session.get("pilot_invite_code", ""))[:100],
        "qr_promotion_id": str(request.session.get("qr_promotion_id", ""))[:20],
        "qr_sales_id": str(request.session.get("qr_sales_id", ""))[:20],
        **attribution_from_session(request),
    }
    assessment = create_assessment(db, data)
    auto_tag_lead(db, assessment.lead, commit=True)
    return RedirectResponse(url=f"/result/{assessment.id}", status_code=303)


@router.get("/result/{assessment_id}", response_class=HTMLResponse)
def free_result(request: Request, assessment_id: int, db: Session = Depends(get_db)):
    assessment = get_assessment(db, assessment_id)
    if not assessment or not assessment.report:
        raise HTTPException(status_code=404, detail="测评不存在")
    free = parse_customer_free_summary(assessment.report)
    health_report = build_capital_health_report(db, assessment)
    session_id = request.session.get("visitor_session_id") or request.session.get("session_id") or "anonymous"
    variant = assign_variant(
        db, session_id, assessment.id, assessment.lead.id if assessment.lead else None
    )
    track_event(
        db, "free_result_viewed", assessment_id=assessment.id,
        lead_id=assessment.lead.id if assessment.lead else None,
        data={"score": assessment.score, "grade": assessment.grade, "variant": variant},
        attribution=attribution_from_session(request),
    )
    return templates.TemplateResponse(
        request=request, name="result_free.html",
        context={
            "assessment": assessment, "result": free, "health_report": health_report, "variant": variant,
            "conversion_copy": result_conversion_copy(assessment.grade),
        },
    )


@router.get("/api/assessment/{assessment_id}")
def assessment_api(assessment_id: int, db: Session = Depends(get_db)):
    item = get_assessment(db, assessment_id)
    if not item:
        raise HTTPException(status_code=404, detail="测评不存在")
    return {
        "id": item.id, "company_name": item.company_name, "contact_name": item.contact_name,
        "phone": item.phone, "wechat_id": item.wechat_id, "city": item.city,
        "industry": item.industry, "score": item.score,
        "company_grade_display": display_value("company_grade", item.grade),
        "risk_level_display": display_value("risk_level", item.risk_level),
        "finance_feasibility_display": display_value(
            "finance_feasibility", item.funding_probability
        ),
        "source_channel": item.source_channel, "utm_source": item.utm_source,
        "utm_campaign": item.utm_campaign, "source_landing_page": item.source_landing_page,
        "created_at": item.created_at,
    }
