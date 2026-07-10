from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy.orm import Session

from db.models import BankProduct


REAL_PRODUCT_SOURCES = ("imported", "manual")
GENERAL_REGION_WORDS = ("全国", "通用", "不限", "全市", "全省")
GENERAL_INDUSTRY_WORDS = ("通用", "不限", "全行业", "小微", "企业")
TAX_PRODUCT_WORDS = ("税", "票", "发票", "纳税", "银税")
COLLATERAL_PRODUCT_WORDS = ("抵押", "房", "不动产", "按揭")
WEAK_CUSTOMER_WORDS = ("弱", "瑕疵", "担保", "保证", "助贷")


@dataclass
class CustomerProfile:
    company_name: str = ""
    industry: str = ""
    city: str = ""
    province: str = ""
    annual_revenue: float = 0
    financing_amount: float = 0
    business_years: int = 0
    tax_status: bool = False
    invoice_status: bool = False
    credit_status: bool = False
    bank_flow_status: str = "unknown"
    debt_level: float = 0
    query_count: int = 0
    has_collateral: bool = False
    funding_purpose: str = ""
    company_type: str = ""
    legal_person_credit: bool = True
    document_completeness: float = 0.5


def _text(value: Any) -> str:
    return str(value or "").strip()


def _lower_text(value: Any) -> str:
    return _text(value).lower()


def _float(value: Any, default: float = 0) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return default


def _bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return value > 0
    text = _lower_text(value)
    if text in {"true", "1", "yes", "y", "normal", "good", "正常", "良好", "有"}:
        return True
    if text in {"false", "0", "no", "n", "bad", "poor", "异常", "无", "差"}:
        return False
    return default


def _amount_yuan(value: Any) -> float:
    amount = _float(value)
    if 0 < amount <= 10_000:
        return amount * 10_000
    return amount


def _amount_text(value: float) -> str:
    return f"{max(value, 0) / 10000:,.0f}万元"


def _json_value(raw: Any) -> Any:
    if isinstance(raw, (dict, list)):
        return raw
    text = _text(raw)
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _contains_any(text: str, words: tuple[str, ...] | list[str]) -> bool:
    haystack = _lower_text(text)
    return any(_lower_text(word) and _lower_text(word) in haystack for word in words)


def _append_unique(target: list[str], value: str) -> None:
    if value and value not in target:
        target.append(value)


def build_customer_profile(assessment: Any) -> dict[str, Any]:
    revenue = _amount_yuan(getattr(assessment, "annual_revenue", 0))
    debt_total = _amount_yuan(getattr(assessment, "debt_total", 0))
    monthly_cashflow = _amount_yuan(getattr(assessment, "monthly_cashflow", 0))
    profile = CustomerProfile(
        company_name=_text(getattr(assessment, "company_name", "")),
        industry=_text(getattr(assessment, "industry", "")),
        city=_text(getattr(assessment, "city", "")),
        province=_text(getattr(assessment, "province", "")),
        annual_revenue=revenue,
        financing_amount=_amount_yuan(
            getattr(assessment, "financing_amount", None)
            or getattr(assessment, "funding_need", 0)
        ),
        business_years=int(_float(getattr(assessment, "business_years", None) or getattr(assessment, "years", 0))),
        tax_status=_bool(getattr(assessment, "tax_status", False)),
        invoice_status=_bool(getattr(assessment, "invoice_status", None), _bool(getattr(assessment, "tax_status", False))),
        credit_status=_bool(getattr(assessment, "credit_status", False)),
        bank_flow_status=_text(getattr(assessment, "bank_flow_status", "")) or ("good" if monthly_cashflow > 0 else "weak"),
        debt_level=_float(getattr(assessment, "debt_level", None), debt_total / max(revenue, 1)),
        query_count=int(_float(getattr(assessment, "query_count", 0))),
        has_collateral=_bool(getattr(assessment, "has_collateral", False)),
        funding_purpose=_text(getattr(assessment, "funding_purpose", "")),
        company_type=_text(getattr(assessment, "company_type", "")),
        legal_person_credit=_bool(getattr(assessment, "legal_person_credit", None), _bool(getattr(assessment, "credit_status", False))),
        document_completeness=_float(getattr(assessment, "document_completeness", 0.5), 0.5),
    )
    if not profile.province and profile.city.endswith("市"):
        profile.province = profile.city
    return asdict(profile)


def _product_text(product: BankProduct) -> str:
    return " ".join(
        _text(getattr(product, field, ""))
        for field in [
            "product_name",
            "product_type",
            "bank_type",
            "suitable_industry",
            "target_customer_type",
            "suitable_scenarios",
            "access_conditions_json",
            "company_requirements",
            "credit_requirements",
            "tax_requirements",
            "invoice_requirements",
            "cashflow_requirements",
            "advantages",
            "risk_notes",
        ]
    )


def _required_documents(product: BankProduct) -> list[str]:
    docs: list[str] = []
    parsed = _json_value(getattr(product, "required_documents_json", ""))
    if isinstance(parsed, dict):
        for value in parsed.values():
            if isinstance(value, list):
                docs.extend(_text(item) for item in value)
            else:
                docs.append(_text(value))
    elif isinstance(parsed, list):
        docs.extend(_text(item) for item in parsed)
    elif parsed:
        docs.append(_text(parsed))
    raw = _text(getattr(product, "required_documents", ""))
    if raw:
        docs.extend(item.strip() for item in raw.replace("、", ",").replace("；", ",").split(","))
    return [item for item in docs if item]


def _region_score(product: BankProduct, profile: dict[str, Any], matched: list[str], risks: list[str]) -> tuple[int, str]:
    product_city = _text(product.city)
    product_province = _text(product.province)
    customer_city = _text(profile.get("city"))
    customer_province = _text(profile.get("province"))
    region_text = f"{product_city} {product_province}"
    if not region_text.strip() or _contains_any(region_text, GENERAL_REGION_WORDS):
        _append_unique(matched, "产品区域为全国或通用范围")
        return 8, "通用区域"
    if product_city and customer_city and (product_city in customer_city or customer_city in product_city):
        _append_unique(matched, "城市准入范围匹配")
        return 10, "城市匹配"
    if product_province and customer_province and (product_province in customer_province or customer_province in product_province):
        _append_unique(matched, "省份准入范围匹配")
        return 10, "省份匹配"
    if customer_city or customer_province:
        _append_unique(risks, "产品区域与客户所在地不完全一致")
        return 0, "区域不匹配"
    return 4, "客户区域信息不足"


def _industry_score(product: BankProduct, profile: dict[str, Any], matched: list[str], risks: list[str]) -> tuple[int, bool]:
    industry = _text(profile.get("industry"))
    suitable = _text(product.suitable_industry)
    prohibited = _json_value(product.prohibited_conditions_json)
    prohibited_text = json.dumps(prohibited, ensure_ascii=False) if isinstance(prohibited, (dict, list)) else _text(prohibited)
    if industry and industry in prohibited_text:
        _append_unique(risks, "客户行业命中产品禁入条件")
        return -20, True
    if industry and suitable and industry in suitable:
        _append_unique(matched, "所属行业符合产品适用行业")
        return 10, False
    if suitable and _contains_any(suitable, GENERAL_INDUSTRY_WORDS):
        _append_unique(matched, "产品适用通用经营行业")
        return 7, False
    if not suitable:
        return 5, False
    _append_unique(risks, "行业适配度需要进一步确认")
    return 4, False


def _years_score(product: BankProduct, profile: dict[str, Any], matched: list[str], risks: list[str]) -> int:
    years = int(profile.get("business_years") or 0)
    min_years = int(_float(product.min_years, 0))
    if years >= min_years:
        _append_unique(matched, "经营年限满足产品准入要求")
        return 10
    if years + 1 >= min_years:
        _append_unique(risks, "经营年限接近但略低于产品要求")
        return 4
    _append_unique(risks, "经营年限明显低于产品准入要求")
    return 0


def _revenue_score(product: BankProduct, profile: dict[str, Any], matched: list[str], risks: list[str]) -> int:
    revenue = _amount_yuan(profile.get("annual_revenue"))
    min_revenue = _amount_yuan(product.min_revenue)
    if min_revenue <= 0:
        _append_unique(matched, "产品未设置刚性营收门槛")
        return 8
    if revenue >= min_revenue:
        _append_unique(matched, "年营业收入达到产品基础门槛")
        return 10
    if revenue >= min_revenue * 0.7:
        _append_unique(risks, "营业收入接近产品门槛，需补充流水或订单证明")
        return 5
    _append_unique(risks, "营业收入低于产品准入门槛")
    return 0


def _amount_score(product: BankProduct, profile: dict[str, Any], matched: list[str], risks: list[str]) -> int:
    need = _amount_yuan(profile.get("financing_amount"))
    min_amount = _amount_yuan(product.min_amount)
    max_amount = _amount_yuan(product.max_amount) or need
    if min_amount <= need <= max_amount:
        _append_unique(matched, "融资需求金额处于产品额度区间内")
        return 15
    if need > max_amount and max_amount > 0 and need <= max_amount * 2:
        _append_unique(risks, "融资需求高于产品上限，可作为组合融资的一部分")
        return 8
    if min_amount and need < min_amount:
        _append_unique(risks, "融资需求低于产品起贷金额")
        return 3
    _append_unique(risks, "融资金额与产品额度区间差异较大")
    return 3


def _credit_score(product: BankProduct, profile: dict[str, Any], matched: list[str], risks: list[str]) -> int:
    credit_ok = bool(profile.get("credit_status")) and bool(profile.get("legal_person_credit"))
    query_count = int(profile.get("query_count") or 0)
    requires_normal = bool(product.requires_credit_normal) or _contains_any(_product_text(product), ("征信正常", "无逾期", "信用良好"))
    if requires_normal and credit_ok and query_count <= 6:
        _append_unique(matched, "企业及法人征信满足正常准入要求")
        return 15
    if requires_normal and credit_ok:
        _append_unique(risks, "征信状态正常但查询次数偏多")
        return 10
    if requires_normal and not credit_ok:
        _append_unique(risks, "产品强要求征信正常，当前征信存在瑕疵")
        return 0
    if not credit_ok:
        _append_unique(risks, "征信瑕疵会影响额度和审批条件")
        return 6
    _append_unique(matched, "征信未触发明显硬性限制")
    return 12


def _tax_invoice_score(product: BankProduct, profile: dict[str, Any], matched: list[str], risks: list[str]) -> int:
    product_text = _product_text(product)
    tax_related = bool(product.requires_tax_normal) or _contains_any(product_text, TAX_PRODUCT_WORDS)
    tax_ok = bool(profile.get("tax_status"))
    invoice_ok = bool(profile.get("invoice_status"))
    if tax_related and tax_ok and invoice_ok:
        _append_unique(matched, "纳税和开票状态适配税票类产品")
        return 10
    if tax_related and (tax_ok or invoice_ok):
        _append_unique(risks, "税票资料需要进一步补齐核验")
        return 6
    if tax_related:
        _append_unique(risks, "税票要求较强但客户纳税或开票条件不足")
        return 0
    if tax_ok or invoice_ok:
        _append_unique(matched, "纳税或开票记录可作为经营真实性辅助证明")
        return 8
    _append_unique(risks, "纳税和开票资料较弱，需用流水或合同补强")
    return 6


def _collateral_score(product: BankProduct, profile: dict[str, Any], matched: list[str], risks: list[str]) -> int:
    product_text = _product_text(product)
    requires_collateral = bool(product.requires_collateral) or _contains_any(product_text, COLLATERAL_PRODUCT_WORDS)
    if requires_collateral and profile.get("has_collateral"):
        _append_unique(matched, "具备抵押物，可满足抵押或增信要求")
        return 10
    if requires_collateral:
        _append_unique(risks, "产品要求抵押或强增信，但客户暂未提供抵押物")
        return 0
    _append_unique(matched, "产品无强制抵押要求")
    return 8


def _document_score(product: BankProduct, profile: dict[str, Any], matched: list[str], risks: list[str], missing: list[str]) -> int:
    completeness = _float(profile.get("document_completeness"), 0.5)
    docs = _required_documents(product)
    if docs:
        missing.extend(docs[:4])
    if completeness >= 0.8:
        _append_unique(matched, "资料完整度较高，便于进入银行预审")
        return 5
    if completeness >= 0.45:
        _append_unique(risks, "资料仍需补齐后再提交正式申请")
        return 3
    _append_unique(risks, "资料完整度偏低，可能触发补件或预审失败")
    return 1


def _risk_deduction(product: BankProduct, profile: dict[str, Any], risks: list[str]) -> int:
    deduction = 0
    if int(profile.get("query_count") or 0) > 8:
        deduction += 2
        _append_unique(risks, "近期征信查询次数偏多")
    if _float(profile.get("debt_level"), 0) > 0.75:
        deduction += 2
        _append_unique(risks, "负债水平偏高")
    product_text = _product_text(product)
    if _contains_any(product_text, WEAK_CUSTOMER_WORDS) and not profile.get("credit_status"):
        deduction = max(0, deduction - 2)
    if _contains_any(_text(product.risk_notes), ("禁入", "诉讼", "执行")):
        deduction += 1
    return min(deduction, 5)


def _match_level(score: int) -> str:
    if score >= 85:
        return "高度匹配"
    if score >= 70:
        return "较匹配"
    if score >= 55:
        return "可尝试"
    return "不推荐"


def _recommendation_reason(product: BankProduct, matched: list[str], risks: list[str]) -> str:
    points = "、".join(matched[:4]) if matched else "客户基础信息与产品存在部分适配"
    product_label = f"{product.bank_name or product.bank_type}的{product.product_name}"
    if risks:
        return f"{product_label}（{product.product_type}）适合当前企业的主要依据是：{points}。同时需要关注：{'、'.join(risks[:2])}。"
    return f"{product_label}（{product.product_type}）适合当前企业的主要依据是：{points}，可优先进入资料核验和银行预沟通。"


def _next_step(product: BankProduct, risks: list[str], missing: list[str]) -> str:
    if missing:
        return f"建议先补齐{missing[0]}等核心材料，再与{product.bank_name or '银行'}确认准入细则。"
    if risks:
        return f"建议先处理“{risks[0]}”，再安排该产品的预审或额度测算。"
    return f"建议优先与{product.bank_name or '目标机构'}沟通预审口径，并准备正式申请资料。"


def score_bank_product(product: BankProduct, customer_profile: dict[str, Any]) -> dict[str, Any]:
    matched_points: list[str] = []
    risk_points: list[str] = []
    missing_requirements: list[str] = []
    score = 0
    debug: list[dict[str, Any]] = []

    region, region_note = _region_score(product, customer_profile, matched_points, risk_points)
    debug.append({"item": "region", "score": region, "note": region_note})
    score += region

    industry, eliminated = _industry_score(product, customer_profile, matched_points, risk_points)
    debug.append({"item": "industry", "score": industry, "note": "命中禁入" if eliminated else ""})
    score += industry

    for name, points in [
        ("business_years", _years_score(product, customer_profile, matched_points, risk_points)),
        ("annual_revenue", _revenue_score(product, customer_profile, matched_points, risk_points)),
        ("financing_amount", _amount_score(product, customer_profile, matched_points, risk_points)),
        ("credit", _credit_score(product, customer_profile, matched_points, risk_points)),
        ("tax_invoice", _tax_invoice_score(product, customer_profile, matched_points, risk_points)),
        ("collateral", _collateral_score(product, customer_profile, matched_points, risk_points)),
        ("documents", _document_score(product, customer_profile, matched_points, risk_points, missing_requirements)),
    ]:
        debug.append({"item": name, "score": points})
        score += points

    deduction = _risk_deduction(product, customer_profile, risk_points)
    debug.append({"item": "risk_deduction", "score": -deduction})
    score -= deduction
    score = max(0, min(100, int(round(score))))

    financing_amount = _amount_yuan(customer_profile.get("financing_amount"))
    max_amount = _amount_yuan(product.max_amount) or financing_amount
    min_amount = _amount_yuan(product.min_amount)
    estimated = min(max_amount, financing_amount) if financing_amount else max_amount
    if min_amount and estimated < min_amount:
        estimated = min_amount
    recommendation_reason = _recommendation_reason(product, matched_points, risk_points)

    return {
        "product_id": product.id,
        "id": product.id,
        "product_code": product.product_code,
        "product_name": product.product_name,
        "bank_name": product.bank_name,
        "bank_type": product.bank_type,
        "product_type": product.product_type,
        "match_score": score,
        "match_level": _match_level(score),
        "recommendation_reason": recommendation_reason,
        "reason": recommendation_reason,
        "matched_points": matched_points[:6],
        "risk_points": risk_points[:6],
        "missing_requirements": missing_requirements[:6],
        "suggested_next_step": _next_step(product, risk_points, missing_requirements),
        "estimated_amount": f"参考可覆盖{_amount_text(estimated)}，实际以审批为准",
        "amount_range": f"{_amount_text(min_amount)}-{_amount_text(max_amount)}" if max_amount else "以审批为准",
        "interest_rate_range": product.interest_rate_range,
        "loan_term": product.loan_term,
        "min_rate": product.min_rate,
        "max_rate": product.max_rate,
        "min_term_months": product.min_term_months,
        "max_term_months": product.max_term_months,
        "repayment_methods": product.repayment_methods,
        "advantages": product.advantages,
        "disadvantages": product.disadvantages,
        "suitable_scenarios": product.suitable_scenarios,
        "risk_notes": "；".join(risk_points[:3]) or product.risk_notes or "暂无明显硬性风险，仍需以银行预审为准",
        "data_source": product.data_source,
        "debug_scores": debug,
        "eliminated": eliminated,
        "eliminated_reason": "客户行业命中产品禁入条件" if eliminated else "",
    }


def _candidate_products(db: Session) -> tuple[list[BankProduct], str]:
    products = (
        db.query(BankProduct)
        .filter(BankProduct.is_active.is_(True), BankProduct.data_source.in_(REAL_PRODUCT_SOURCES))
        .all()
    )
    if products:
        return products, ""
    fallback = (
        db.query(BankProduct)
        .filter(BankProduct.is_active.is_(True), BankProduct.data_source == "mock")
        .all()
    )
    return fallback, "当前暂无真实银行产品库，以下为模拟产品规则参考。"


def match_bank_products(db: Session, assessment: Any, limit: int = 5, include_debug: bool = False) -> dict[str, Any]:
    customer_profile = build_customer_profile(assessment)
    products, fallback_notice = _candidate_products(db)
    scored = [score_bank_product(product, customer_profile) for product in products]
    scored.sort(key=lambda item: (item["eliminated"], -item["match_score"], item["product_id"] or 0))

    visible = [item for item in scored if not item["eliminated"] and item["match_score"] >= 55]
    if not visible:
        visible = [item for item in scored if not item["eliminated"]][:limit] or scored[:limit]
    top = visible[:limit]

    result = {
        "customer_profile": customer_profile,
        "matched_products": top,
        "fallback_notice": fallback_notice,
        "best_application_order": [
            f"第{index}顺位：{item['bank_name'] or item['bank_type']} - {item['product_name']}（{item['match_level']}，{item['match_score']}分）"
            for index, item in enumerate(top[:3], 1)
        ],
    }
    if include_debug:
        result["candidate_products"] = scored
    return result
