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


def _profit_values(
    annual_revenue: float,
    net_profit_margin: float | None,
    legacy_net_profit: float | None,
) -> tuple[float, float | None]:
    """新测评使用净利润率；旧客户端仍可提交净利润金额。"""
    if net_profit_margin is not None:
        return annual_revenue * net_profit_margin / 100, net_profit_margin
    if legacy_net_profit is not None:
        margin = legacy_net_profit / annual_revenue * 100 if annual_revenue else None
        return legacy_net_profit, margin
    return 0, None


def _optional_percentage(value: float | None) -> float | None:
    return None if value is None else min(max(float(value), 0), 100)


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
    years: float = Form(...), employee_count: int = Form(0), annual_revenue: float = Form(...),
    net_profit_margin: float | None = Form(None), net_profit: float | None = Form(None),
    monthly_cashflow: float = Form(0),
    debt_total: float = Form(...), short_debt: float = Form(...),
    receivable_days: int = Form(0), funding_need: float = Form(...),
    funding_purpose: str = Form(""), funding_purposes: list[str] = Form([]),
    funding_purpose_other: str = Form(""), collateral_types: list[str] = Form([]),
    has_collateral: bool | None = Form(None),
    enterprise_credit_status: str = Form(""), legal_credit_status: str = Form("unknown"),
    credit_query_count_6m: int = Form(0), credit_card_usage_rate: float | None = Form(None),
    lender_count: int = Form(0), online_loan_status: str = Form("unknown"),
    public_inflow_monthly: float = Form(0), public_outflow_monthly: float = Form(0),
    operating_flow_ratio: float | None = Form(None), public_private_ratio: float | None = Form(None),
    internal_transfer_ratio: float | None = Form(None), fast_in_out_status: str = Form("unknown"),
    tax_credit_grade: str = Form("unknown"), tax_paid_12m: float = Form(0),
    invoiced_revenue_12m: float = Form(0), tax_arrears_status: str = Form("unknown"),
    revenue_growth_rate: float | None = Form(None),
    enforcement_status: str = Form("unknown"), dishonest_status: str = Form("unknown"),
    consumption_restriction_status: str = Form("unknown"),
    lawsuit_plaintiff_status: str = Form("unknown"), lawsuit_defendant_status: str = Form("unknown"),
    admin_penalty_status: str = Form("unknown"),
    property_value: float = Form(0), factory_value: float = Form(0), land_value: float = Form(0),
    vehicle_value: float = Form(0), equipment_value: float = Form(0),
    financeable_receivables: float = Form(0), inventory_value: float = Form(0),
    external_investment_value: float = Form(0), intellectual_property_types: list[str] = Form([]),
    tax_status: bool | None = Form(None), credit_status: bool | None = Form(None),
    knows_cashflow: bool = Form(False), has_budget: bool = Form(False),
    leverage_attitude: str = Form("适中"), asset_efficiency: str = Form("中"),
    fund_usage_plan: bool = Form(False), db: Session = Depends(get_db),
):
    capture_attribution(request)
    annual_revenue_value = max(annual_revenue, 0)
    profit_amount, profit_margin = _profit_values(
        annual_revenue_value, net_profit_margin, net_profit
    )
    purpose_values = [item.strip() for item in funding_purposes if item.strip()]
    if funding_purpose_other.strip():
        purpose_values.append(funding_purpose_other.strip())
    final_funding_purpose = "、".join(dict.fromkeys(purpose_values)) or funding_purpose.strip()
    collateral_values = [item.strip() for item in collateral_types if item.strip()]
    has_collateral_value = (
        bool(collateral_values and "暂无抵押物" not in collateral_values)
        if collateral_values else bool(has_collateral)
    )
    enterprise_credit = enterprise_credit_status or (
        "no_overdue" if credit_status else "current_overdue"
    )
    legal_credit = legal_credit_status or "unknown"
    credit_ok = enterprise_credit in {"no_overdue", "settled_overdue"} and legal_credit != "current_overdue"
    resolved_tax_arrears_status = tax_arrears_status
    if tax_arrears_status == "unknown" and tax_status is not None:
        resolved_tax_arrears_status = "none" if tax_status else "current"
    tax_ok = (
        resolved_tax_arrears_status in {"none", "rectified"}
        if resolved_tax_arrears_status != "unknown" else False
    )
    data = {
        "company_name": company_name.strip(), "contact_name": contact_name.strip(),
        "phone": phone.strip(), "wechat_id": wechat_id.strip(), "city": city.strip(),
        "industry": industry.strip(), "years": max(years, 0),
        "employee_count": max(employee_count, 0), "annual_revenue": annual_revenue_value,
        "net_profit": profit_amount, "net_profit_margin": profit_margin,
        "monthly_cashflow": max(monthly_cashflow, 0),
        "debt_total": max(debt_total, 0), "short_debt": max(short_debt, 0),
        "receivable_days": max(receivable_days, 0), "funding_need": max(funding_need, 0),
        "funding_purpose": final_funding_purpose, "has_collateral": has_collateral_value,
        "collateral_types": "、".join(collateral_values),
        "tax_status": tax_ok, "credit_status": credit_ok,
        "enterprise_credit_status": enterprise_credit, "legal_credit_status": legal_credit,
        "credit_query_count_6m": max(credit_query_count_6m, 0),
        "credit_card_usage_rate": _optional_percentage(credit_card_usage_rate),
        "lender_count": max(lender_count, 0), "online_loan_status": online_loan_status,
        "public_inflow_monthly": max(public_inflow_monthly, 0),
        "public_outflow_monthly": max(public_outflow_monthly, 0),
        "operating_flow_ratio": _optional_percentage(operating_flow_ratio),
        "public_private_ratio": _optional_percentage(public_private_ratio),
        "internal_transfer_ratio": _optional_percentage(internal_transfer_ratio),
        "fast_in_out_status": fast_in_out_status,
        "tax_credit_grade": tax_credit_grade,
        "tax_paid_12m": max(tax_paid_12m, 0),
        "invoiced_revenue_12m": max(invoiced_revenue_12m, 0),
        "tax_arrears_status": resolved_tax_arrears_status,
        "revenue_growth_rate": revenue_growth_rate,
        "enforcement_status": enforcement_status, "dishonest_status": dishonest_status,
        "consumption_restriction_status": consumption_restriction_status,
        "lawsuit_plaintiff_status": lawsuit_plaintiff_status,
        "lawsuit_defendant_status": lawsuit_defendant_status,
        "admin_penalty_status": admin_penalty_status,
        "property_value": max(property_value, 0), "factory_value": max(factory_value, 0),
        "land_value": max(land_value, 0), "vehicle_value": max(vehicle_value, 0),
        "equipment_value": max(equipment_value, 0),
        "financeable_receivables": max(financeable_receivables, 0),
        "inventory_value": max(inventory_value, 0),
        "external_investment_value": max(external_investment_value, 0),
        "intellectual_property_types": "、".join(intellectual_property_types),
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
    health_report = build_capital_health_report(db, assessment, include_extended=False)
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
