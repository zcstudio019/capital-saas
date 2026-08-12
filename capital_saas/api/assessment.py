from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from core.conversion_engine import result_conversion_copy
from core.config import settings
from db.database import get_db
from db.models import CustomerAccount
from services.ab_test_service import assign_variant
from services.assessment_service import create_assessment, get_assessment
from services.attribution_service import attribution_from_session, capture_attribution
from services.event_service import track_event
from services.report_service import parse_customer_free_summary
from utils.report_display_mapper import display_value
from core.capital_health_report import ensure_capital_health_snapshot
from services.customer_portal_service import customer_from_session, customer_owns_report
from services.tag_service import auto_tag_lead
from utils.input_normalizer import (
    InputNormalizationError,
    normalize_optional_float,
    normalize_optional_int,
    normalize_optional_percentage,
    normalize_required_float,
)


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


NUMERIC_FIELD_LABELS = {
    "registered_capital": "注册资本",
    "years": "经营年限",
    "employee_count": "当前员工人数",
    "annual_revenue": "近12个月营业收入",
    "net_profit_margin": "近12个月净利润率",
    "net_profit": "近12个月净利润金额",
    "monthly_cashflow": "近6个月月均经营性现金流入",
    "debt_total": "当前有息负债总额",
    "short_debt": "一年内到期的短期负债",
    "receivable_days": "平均应收账款回款周期",
    "funding_need": "本次计划融资金额",
    "credit_query_count_6m": "法人近6个月贷款审批类征信查询次数",
    "credit_card_usage_rate": "法人信用卡平均额度使用率",
    "lender_count": "当前有贷款余额的金融机构数量",
    "public_inflow_monthly": "近6个月月均对公账户经营性流入",
    "public_outflow_monthly": "近6个月月均对公账户经营性流出",
    "operating_flow_ratio": "经营性流水占比",
    "public_private_ratio": "公私往来占比",
    "internal_transfer_ratio": "内部转账占比",
    "tax_paid_12m": "近12个月实际纳税总额",
    "invoiced_revenue_12m": "近12个月开票收入",
    "revenue_growth_rate": "营收增长率",
    "property_value": "企业名下房产估值",
    "factory_value": "企业名下厂房估值",
    "land_value": "企业名下土地估值",
    "vehicle_value": "企业名下车辆估值",
    "equipment_value": "企业名下设备估值",
    "financeable_receivables": "可融资应收账款余额",
    "inventory_value": "存货估值",
    "external_investment_value": "对外投资或子公司股权估值",
}

OPTIONAL_FLOAT_FIELDS = (
    "registered_capital",
    "net_profit",
    "monthly_cashflow",
    "public_inflow_monthly",
    "public_outflow_monthly",
    "tax_paid_12m",
    "invoiced_revenue_12m",
    "property_value",
    "factory_value",
    "land_value",
    "vehicle_value",
    "equipment_value",
    "financeable_receivables",
    "inventory_value",
    "external_investment_value",
)
OPTIONAL_INT_FIELDS = ("employee_count", "receivable_days", "lender_count")
OPTIONAL_PERCENTAGE_FIELDS = (
    "net_profit_margin",
    "credit_card_usage_rate",
    "operating_flow_ratio",
    "public_private_ratio",
    "internal_transfer_ratio",
    "revenue_growth_rate",
)


def _text(value, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _bool_value(value, default: bool | None = False) -> bool | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "on"}


def _legacy_numeric_default(value: float | int | None) -> float | int:
    """兼容现有非空数值列；校验层中的空值在进入此层前始终保持 None。"""
    return 0 if value is None else value


def _validation_response(request: Request, errors: dict[str, str], values: dict):
    message = "部分数值填写格式不正确，请检查标红字段。"
    if request.headers.get("x-assessment-ajax") == "1":
        return JSONResponse(
            status_code=422,
            content={"ok": False, "message": message, "errors": errors},
        )
    return templates.TemplateResponse(
        request=request,
        name="assessment_form.html",
        context={"form_errors": errors, "form_values": values, "submit_error": message},
        status_code=422,
    )


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
    customer = customer_from_session(request, db)
    form_values = {}
    if customer:
        form_values = {
            "contact_name": customer.name or customer.contact_name,
            "phone": customer.login_phone or customer.phone,
            "wechat_id": customer.wechat_id,
            "city": customer.city,
        }
    return templates.TemplateResponse(request=request, name="assessment_form.html", context={
        "form_values": form_values, "customer": customer,
    })


@router.post("/assessment/submit")
async def submit_assessment(request: Request, db: Session = Depends(get_db)):
    content_type = request.headers.get("content-type", "").lower()
    if "application/json" in content_type:
        try:
            payload = await request.json()
        except Exception:
            return _validation_response(request, {"form": "提交内容格式不正确，请重新提交"}, {})
        if not isinstance(payload, dict):
            return _validation_response(request, {"form": "提交内容格式不正确，请重新提交"}, {})
        get_value = lambda name, default=None: payload.get(name, default)
        get_values = lambda name: (
            payload.get(name, []) if isinstance(payload.get(name, []), list)
            else [payload.get(name)] if payload.get(name) not in (None, "") else []
        )
        submitted_values = payload
    else:
        form = await request.form()
        get_value = lambda name, default=None: form.get(name, default)
        get_values = lambda name: list(form.getlist(name))
        submitted_values = {
            key: (form.getlist(key) if len(form.getlist(key)) > 1 else form.get(key))
            for key in form.keys()
        }

    errors: dict[str, str] = {}
    parsed_numbers: dict[str, float | int | None] = {}

    def parse_field(name: str, normalizer):
        try:
            parsed_numbers[name] = normalizer(
                get_value(name), NUMERIC_FIELD_LABELS[name]
            )
        except InputNormalizationError as exc:
            errors[name] = str(exc)

    for name in OPTIONAL_FLOAT_FIELDS:
        parse_field(name, normalize_optional_float)
    for name in OPTIONAL_INT_FIELDS:
        parse_field(name, normalize_optional_int)
    for name in OPTIONAL_PERCENTAGE_FIELDS:
        parse_field(name, normalize_optional_percentage)
    for name in ("years", "annual_revenue", "debt_total", "short_debt", "funding_need"):
        parse_field(name, normalize_required_float)
    try:
        raw_credit_query_count = get_value("credit_query_count_6m")
        credit_query_count_6m = normalize_optional_int(
            raw_credit_query_count,
            NUMERIC_FIELD_LABELS["credit_query_count_6m"],
        )
        if credit_query_count_6m is None:
            if raw_credit_query_count is None:
                credit_query_count_6m = 0  # 兼容未包含该新字段的历史客户端。
            else:
                raise InputNormalizationError("请输入法人近6个月贷款审批类征信查询次数")
        parsed_numbers["credit_query_count_6m"] = credit_query_count_6m
    except InputNormalizationError as exc:
        errors["credit_query_count_6m"] = str(exc)

    company_name = _text(get_value("company_name")).strip()
    contact_name = _text(get_value("contact_name")).strip()
    phone = _text(get_value("phone")).strip()
    industry = _text(get_value("industry")).strip()
    for field, value, message in (
        ("company_name", company_name, "请输入企业名称"),
        ("contact_name", contact_name, "请输入联系人姓名"),
        ("phone", phone, "请输入手机号"),
        ("industry", industry, "请输入所属行业"),
    ):
        if not value:
            errors[field] = message

    for name in (
        "years", "annual_revenue", "debt_total", "short_debt",
        "registered_capital", "employee_count", "monthly_cashflow", "receivable_days",
        "credit_query_count_6m", "lender_count", "public_inflow_monthly",
        "public_outflow_monthly", "tax_paid_12m", "invoiced_revenue_12m",
        "property_value", "factory_value", "land_value", "vehicle_value",
        "equipment_value", "financeable_receivables", "inventory_value",
        "external_investment_value",
    ):
        value = parsed_numbers.get(name)
        if value is not None and value < 0:
            errors[name] = f"{NUMERIC_FIELD_LABELS[name]}不能小于0"
    if parsed_numbers.get("funding_need") is not None and parsed_numbers["funding_need"] <= 0:
        errors["funding_need"] = "本次计划融资金额必须大于0"

    for name in (
        "credit_card_usage_rate",
        "operating_flow_ratio",
        "public_private_ratio",
        "internal_transfer_ratio",
    ):
        value = parsed_numbers.get(name)
        if value is not None and not 0 <= value <= 100:
            errors[name] = f"{NUMERIC_FIELD_LABELS[name]}应在0到100之间"

    if (
        parsed_numbers.get("net_profit_margin") is None
        and parsed_numbers.get("net_profit") is None
        and "net_profit_margin" not in errors
        and "net_profit" not in errors
    ):
        errors["net_profit_margin"] = "请输入近12个月净利润率"

    funding_purposes = [_text(item).strip() for item in get_values("funding_purposes")]
    funding_purpose_other = _text(get_value("funding_purpose_other"))
    funding_purpose = _text(get_value("funding_purpose"))
    collateral_types = [_text(item).strip() for item in get_values("collateral_types")]
    if not any(funding_purposes) and not funding_purpose_other.strip() and not funding_purpose.strip():
        errors["funding_purposes"] = "请至少选择一个融资用途"
    if not any(collateral_types) and get_value("has_collateral") is None:
        errors["collateral_types"] = "请选择至少一项资产，或选择“暂无抵押物”"

    if errors:
        return _validation_response(request, errors, submitted_values)

    years = float(parsed_numbers["years"])
    registered_capital = parsed_numbers["registered_capital"]
    employee_count = parsed_numbers["employee_count"]
    annual_revenue = float(parsed_numbers["annual_revenue"])
    net_profit_margin = parsed_numbers["net_profit_margin"]
    net_profit = parsed_numbers["net_profit"]
    monthly_cashflow = parsed_numbers["monthly_cashflow"]
    debt_total = float(parsed_numbers["debt_total"])
    short_debt = float(parsed_numbers["short_debt"])
    receivable_days = parsed_numbers["receivable_days"]
    funding_need = float(parsed_numbers["funding_need"])
    credit_card_usage_rate = parsed_numbers["credit_card_usage_rate"]
    lender_count = parsed_numbers["lender_count"]
    public_inflow_monthly = parsed_numbers["public_inflow_monthly"]
    public_outflow_monthly = parsed_numbers["public_outflow_monthly"]
    operating_flow_ratio = parsed_numbers["operating_flow_ratio"]
    public_private_ratio = parsed_numbers["public_private_ratio"]
    internal_transfer_ratio = parsed_numbers["internal_transfer_ratio"]
    tax_paid_12m = parsed_numbers["tax_paid_12m"]
    invoiced_revenue_12m = parsed_numbers["invoiced_revenue_12m"]
    revenue_growth_rate = parsed_numbers["revenue_growth_rate"]
    property_value = parsed_numbers["property_value"]
    factory_value = parsed_numbers["factory_value"]
    land_value = parsed_numbers["land_value"]
    vehicle_value = parsed_numbers["vehicle_value"]
    equipment_value = parsed_numbers["equipment_value"]
    financeable_receivables = parsed_numbers["financeable_receivables"]
    inventory_value = parsed_numbers["inventory_value"]
    external_investment_value = parsed_numbers["external_investment_value"]

    wechat_id = _text(get_value("wechat_id"))
    city = _text(get_value("city"))
    has_collateral = _bool_value(get_value("has_collateral"), None)
    enterprise_credit_status = _text(get_value("enterprise_credit_status"))
    legal_credit_status = _text(get_value("legal_credit_status"), "unknown") or "unknown"
    online_loan_status = _text(get_value("online_loan_status"), "unknown") or "unknown"
    fast_in_out_status = _text(get_value("fast_in_out_status"), "unknown") or "unknown"
    tax_credit_grade = _text(get_value("tax_credit_grade"), "unknown") or "unknown"
    tax_arrears_status = _text(get_value("tax_arrears_status"), "unknown") or "unknown"
    enforcement_status = _text(get_value("enforcement_status"), "unknown") or "unknown"
    dishonest_status = _text(get_value("dishonest_status"), "unknown") or "unknown"
    consumption_restriction_status = _text(
        get_value("consumption_restriction_status"), "unknown"
    ) or "unknown"
    lawsuit_plaintiff_status = _text(
        get_value("lawsuit_plaintiff_status"), "unknown"
    ) or "unknown"
    lawsuit_defendant_status = _text(
        get_value("lawsuit_defendant_status"), "unknown"
    ) or "unknown"
    admin_penalty_status = _text(get_value("admin_penalty_status"), "unknown") or "unknown"
    intellectual_property_types = [
        _text(item).strip() for item in get_values("intellectual_property_types")
    ]
    tax_status = _bool_value(get_value("tax_status"), None)
    credit_status = _bool_value(get_value("credit_status"), None)
    knows_cashflow = bool(_bool_value(get_value("knows_cashflow"), False))
    has_budget = bool(_bool_value(get_value("has_budget"), False))
    leverage_attitude = _text(get_value("leverage_attitude"), "适中") or "适中"
    asset_efficiency = _text(get_value("asset_efficiency"), "中") or "中"
    fund_usage_plan = bool(_bool_value(get_value("fund_usage_plan"), False))

    capture_attribution(request)
    annual_revenue_value = annual_revenue
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
        "industry": industry.strip(), "registered_capital": registered_capital, "years": years,
        "employee_count": _legacy_numeric_default(employee_count),
        "annual_revenue": annual_revenue_value,
        "net_profit": profit_amount, "net_profit_margin": profit_margin,
        "monthly_cashflow": _legacy_numeric_default(monthly_cashflow),
        "debt_total": debt_total, "short_debt": short_debt,
        "receivable_days": _legacy_numeric_default(receivable_days),
        "funding_need": funding_need,
        "funding_purpose": final_funding_purpose, "has_collateral": has_collateral_value,
        "collateral_types": "、".join(collateral_values),
        "tax_status": tax_ok, "credit_status": credit_ok,
        "enterprise_credit_status": enterprise_credit, "legal_credit_status": legal_credit,
        "credit_query_count_6m": credit_query_count_6m,
        "credit_card_usage_rate": credit_card_usage_rate,
        "lender_count": _legacy_numeric_default(lender_count),
        "online_loan_status": online_loan_status,
        "public_inflow_monthly": _legacy_numeric_default(public_inflow_monthly),
        "public_outflow_monthly": _legacy_numeric_default(public_outflow_monthly),
        "operating_flow_ratio": operating_flow_ratio,
        "public_private_ratio": public_private_ratio,
        "internal_transfer_ratio": internal_transfer_ratio,
        "fast_in_out_status": fast_in_out_status,
        "tax_credit_grade": tax_credit_grade,
        "tax_paid_12m": _legacy_numeric_default(tax_paid_12m),
        "invoiced_revenue_12m": _legacy_numeric_default(invoiced_revenue_12m),
        "tax_arrears_status": resolved_tax_arrears_status,
        "revenue_growth_rate": revenue_growth_rate,
        "enforcement_status": enforcement_status, "dishonest_status": dishonest_status,
        "consumption_restriction_status": consumption_restriction_status,
        "lawsuit_plaintiff_status": lawsuit_plaintiff_status,
        "lawsuit_defendant_status": lawsuit_defendant_status,
        "admin_penalty_status": admin_penalty_status,
        "property_value": _legacy_numeric_default(property_value),
        "factory_value": _legacy_numeric_default(factory_value),
        "land_value": _legacy_numeric_default(land_value),
        "vehicle_value": _legacy_numeric_default(vehicle_value),
        "equipment_value": _legacy_numeric_default(equipment_value),
        "financeable_receivables": _legacy_numeric_default(financeable_receivables),
        "inventory_value": _legacy_numeric_default(inventory_value),
        "external_investment_value": _legacy_numeric_default(external_investment_value),
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
    authenticated_customer = customer_from_session(request, db)
    if authenticated_customer:
        data["customer_id"] = authenticated_customer.id
        data["phone"] = authenticated_customer.login_phone or authenticated_customer.phone
    assessment = create_assessment(db, data)
    if assessment.report and assessment.report.customer_id:
        account = assessment.report.customer_id
        authenticated_customer_id = request.session.get("customer_id") if request.session.get("customer_authenticated") else None
        if authenticated_customer_id == account:
            request.session["customer_lead_id"] = assessment.lead.id if assessment.lead else None
        else:
            request.session["pending_customer_id"] = account
            request.session["pending_assessment_id"] = assessment.id
    accessible = [int(item) for item in request.session.get("assessment_access_ids", []) if str(item).isdigit()]
    if assessment.id not in accessible:
        accessible.append(assessment.id)
    request.session["assessment_access_ids"] = accessible[-20:]
    auto_tag_lead(db, assessment.lead, commit=True)
    if request.headers.get("x-assessment-ajax") == "1":
        return JSONResponse(
            {"ok": True, "assessment_id": assessment.id, "redirect_url": f"/result/{assessment.id}"}
        )
    return RedirectResponse(url=f"/result/{assessment.id}", status_code=303)


@router.get("/result/{assessment_id}", response_class=HTMLResponse)
def free_result(request: Request, assessment_id: int, db: Session = Depends(get_db)):
    assessment = get_assessment(db, assessment_id)
    if not assessment or not assessment.report:
        raise HTTPException(status_code=404, detail="测评不存在")
    customer = customer_from_session(request, db)
    session_assessments = {
        int(item) for item in request.session.get("assessment_access_ids", []) if str(item).isdigit()
    }
    authorized = bool(request.session.get("user_id")) or assessment.id in session_assessments
    if customer and customer_owns_report(db, customer, assessment.report):
        authorized = True
        db.commit()
    if not authorized:
        return RedirectResponse(url=f"/my-reports?next=/result/{assessment.id}", status_code=303)
    free = parse_customer_free_summary(assessment.report)
    health_report = ensure_capital_health_snapshot(db, assessment)
    linked_customer = db.get(CustomerAccount, assessment.report.customer_id) if assessment.report.customer_id else None
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
            "customer": customer,
            "linked_customer": linked_customer,
            "customer_account_ready": bool(linked_customer and linked_customer.password_hash),
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
        "industry": item.industry, "registered_capital": item.registered_capital, "score": item.score,
        "company_grade_display": display_value("company_grade", item.grade),
        "risk_level_display": display_value("risk_level", item.risk_level),
        "finance_feasibility_display": display_value(
            "finance_feasibility", item.funding_probability
        ),
        "source_channel": item.source_channel, "utm_source": item.utm_source,
        "utm_campaign": item.utm_campaign, "source_landing_page": item.source_landing_page,
        "created_at": item.created_at,
    }
