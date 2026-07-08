from __future__ import annotations

from copy import deepcopy
from typing import Any

from sqlalchemy.orm import Session

from db.models import Assessment, BankProduct, Order


BANK_MATCH_PRODUCTS = {"699_bank_match", "1999_structure_plan"}
DOCUMENT_CHECKLIST_PRODUCTS = {"1999_structure_plan"}
PAID_STATUSES = {"paid", "completed", "success"}


DEFAULT_CHECKLIST_PREVIEW = {
    "intro": "系统已根据企业融资情况生成资料准备方向，完整资料明细、优先级和执行计划将在1999结构优化方案中解锁。",
    "preview_cards": [
        {
            "category": "企业基础资料",
            "description": "用于确认企业主体、经营资质和实际控制人信息。",
            "items": ["营业执照", "法人/实控人身份证明", "公司基本工商信息"],
        },
        {
            "category": "银行与经营流水",
            "description": "用于判断企业现金流质量、经营稳定性和还款能力。",
            "items": ["对公流水", "个人经营流水", "收款流水"],
        },
        {
            "category": "纳税与经营证明",
            "description": "用于判断企业纳税连续性、开票稳定性和真实经营情况。",
            "items": ["纳税申报记录", "开票记录", "经营合同或订单"],
        },
    ],
    "hidden_title": "更多资料类别已隐藏",
    "hidden_items": [
        "财务报表明细",
        "应收应付资料",
        "抵押物资料",
        "资金用途证明",
        "银行申请材料包",
        "资料准备优先级",
        "30/90/180天执行计划",
    ],
    "upgrade_title": "高级交付内容",
    "upgrade_text": "1999结构优化方案将解锁完整资料清单、每类资料的用途说明、准备优先级、缺失风险提醒，以及30/90/180天执行计划。",
    "upgrade_product": "1999_structure_plan",
    "preview_only": True,
}


DEFAULT_CHECKLIST_FULL = [
    {
        "category": "企业基础资料",
        "purpose": "用于确认企业主体、经营资质、股权结构和实际控制人信息。",
        "priority": "高",
        "items": ["营业执照", "公司章程", "法人身份证", "股东/实控人信息", "开户许可证或基本户信息", "企业工商变更记录"],
        "missing_risk": "如果缺少该类资料，可能影响银行对企业主体真实性、控制权和基础准入的判断。",
    },
    {
        "category": "财务资料",
        "purpose": "用于判断企业盈利能力、资产负债结构、偿债压力和财务稳定性。",
        "priority": "高",
        "items": ["最近一年财务报表", "最近6个月科目余额表", "应收账款明细", "应付账款明细", "主要资产负债明细", "利润表/现金流相关资料"],
        "missing_risk": "如果缺少该类资料，银行难以判断真实经营规模和偿债能力，可能压低额度或要求补充材料。",
    },
    {
        "category": "银行流水",
        "purpose": "用于判断企业现金流质量、经营稳定性、回款能力和还款来源。",
        "priority": "高",
        "items": ["最近6-12个月对公流水", "最近6-12个月个人经营流水", "主要收款账户流水", "主要付款账户流水", "大额进出账说明"],
        "missing_risk": "如果缺少该类资料，可能影响银行对收入真实性、现金流连续性和还款能力的判断。",
    },
    {
        "category": "纳税资料",
        "purpose": "用于判断企业纳税连续性、开票稳定性和税务合规情况。",
        "priority": "高",
        "items": ["近12个月纳税申报表", "完税证明", "增值税申报记录", "企业所得税申报记录", "开票明细"],
        "missing_risk": "如果缺少该类资料，税贷、信用贷和线上化产品可能无法准确核额，甚至无法准入。",
    },
    {
        "category": "经营证明",
        "purpose": "用于证明企业真实经营、上下游交易关系和订单履约能力。",
        "priority": "中",
        "items": ["主要销售合同", "采购合同", "订单记录", "发票", "场地租赁合同", "经营照片或经营场所证明"],
        "missing_risk": "如果缺少该类资料，银行可能认为经营真实性不足，要求补充核验或现场尽调。",
    },
    {
        "category": "资金用途资料",
        "purpose": "用于说明贷款资金用途、资金安排和后续还款来源。",
        "priority": "中",
        "items": ["采购计划", "备货计划", "工资/租金/货款支付计划", "项目投入预算", "还款来源说明"],
        "missing_risk": "如果缺少该类资料，银行可能无法确认资金闭环，影响审批通过率和放款节奏。",
    },
    {
        "category": "抵押物资料（如适用）",
        "purpose": "用于评估可抵押资产价值、权属清晰度和增信能力。",
        "priority": "中",
        "items": ["房产证或不动产权证", "抵押物评估资料", "权属人身份证明", "共有权人同意材料", "房贷/抵押情况说明"],
        "missing_risk": "如果融资方案需要抵押增信但资料不完整，可能导致评估延迟、额度下降或无法办理抵押。",
    },
    {
        "category": "补充资料",
        "purpose": "用于补充说明征信、司法、股东和银行个性化审查要求。",
        "priority": "低",
        "items": ["企业征信", "法人征信", "股东征信", "诉讼/执行情况说明", "其他银行要求补充材料"],
        "missing_risk": "如果存在征信、诉讼或执行瑕疵但没有说明材料，可能影响银行风险判断和审批结论。",
    },
]


DEFAULT_DOCUMENT_EXECUTION_PLAN = [
    {
        "period": "30天执行计划",
        "goal": "完成融资申请的基础资料补齐，先把主体、流水、纳税和经营真实性资料整理到可初审状态。",
        "actions": [
            "补齐企业基础资料",
            "统一营业执照、法人信息、公司章程等主体资料",
            "整理近6-12个月银行流水",
            "整理近12个月纳税申报记录",
            "归集近期经营合同、订单、开票记录",
            "明确本轮融资金额、用途与还款来源",
            "对明显缺失项做第一轮补齐",
        ],
        "owner": "企业负责人牵头，财务负责人和行政/资料负责人配合",
        "deliverable": "形成基础资料包、流水与纳税资料包、经营证明资料包，以及本轮融资用途说明。",
    },
    {
        "period": "90天执行计划",
        "goal": "完成银行申请前的资料适配和内部复核，围绕目标产品准备可提交的申请材料包。",
        "actions": [
            "完善财务报表及应收应付资料",
            "补齐银行所需申请材料包",
            "根据目标产品准备针对性准入资料",
            "处理征信、负债、查询次数等可能影响审批的问题",
            "根据不同银行产品调整申请顺序",
            "完成融资申请前的内部复核",
            "对重点银行产品进行资料适配",
        ],
        "owner": "财务负责人主责，企业负责人确认融资策略，顾问或销售协助银行适配",
        "deliverable": "形成目标银行申请材料包、问题修复清单、产品适配表和申请顺序建议。",
    },
    {
        "period": "180天执行计划",
        "goal": "建立长期融资资料管理机制，提升额度稳定性、续贷能力和融资成本控制能力。",
        "actions": [
            "建立长期资料归档机制",
            "优化纳税、开票、流水和财务口径一致性",
            "逐步提升可贷额度和融资稳定性",
            "优化融资结构（短中长期组合）",
            "降低融资成本",
            "为后续续贷或新增授信做好准备",
            "建立常态化融资资料更新节奏",
        ],
        "owner": "企业负责人和财务负责人共同负责，必要时由外部顾问做季度复盘",
        "deliverable": "形成长期资料台账、季度融资复盘表、续贷准备清单和下一轮授信优化方案。",
    },
]


def _product_code(value: Any) -> str:
    if isinstance(value, str):
        return value
    return getattr(value, "product_code", "") or ""


def _product_codes(order_or_product: Any) -> set[str]:
    if order_or_product is None:
        return set()
    if isinstance(order_or_product, (list, tuple, set)):
        return {_product_code(item) for item in order_or_product if _product_code(item)}
    return {_product_code(order_or_product)} if _product_code(order_or_product) else set()


def get_paid_product_codes(db: Session, assessment_id: int) -> set[str]:
    orders = (
        db.query(Order)
        .filter(Order.assessment_id == assessment_id, Order.status.in_(PAID_STATUSES))
        .all()
    )
    return _product_codes(orders)


def can_view_full_bank_match(order_or_product: Any) -> bool:
    return bool(_product_codes(order_or_product) & BANK_MATCH_PRODUCTS)


def can_view_full_document_checklist(order_or_product: Any) -> bool:
    return bool(_product_codes(order_or_product) & DOCUMENT_CHECKLIST_PRODUCTS)


def can_view_full_bank_product_detail(order_or_product: Any) -> bool:
    return can_view_full_bank_match(order_or_product)


def _short_text(value: Any, default: str = "", limit: int = 72) -> str:
    text = str(value or default).strip()
    if not text:
        return default
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _detail_url(base_path: str, product_id: Any) -> str:
    if not product_id:
        return "#"
    return f"{base_path}/bank-products/{product_id}"


def _decorate_match(item: dict[str, Any], base_path: str) -> dict[str, Any]:
    decorated = dict(item)
    decorated["product_id"] = item.get("product_id") or item.get("id")
    decorated["detail_url"] = _detail_url(base_path, decorated.get("product_id"))
    decorated["preview_reason"] = _short_text(
        item.get("reason"),
        "该产品与当前企业融资需求存在基础匹配，可进入详情查看预览。",
        68,
    )
    decorated["access_hint"] = _short_text(
        item.get("access_hint") or item.get("risk_notes"),
        "需结合征信、纳税、流水和经营资料进一步核验准入。",
        58,
    )
    decorated["preview_note"] = _short_text(
        item.get("note") or item.get("risk_notes"),
        "完整准入规则、申请顺序和额度预测需解锁后查看。",
        58,
    )
    return decorated


def build_bank_match_preview(matches: dict[str, Any] | None, base_path: str = "") -> dict[str, Any]:
    matches = matches or {}
    products = [_decorate_match(item, base_path) for item in matches.get("matched_products", [])[:1]]
    return {
        "matched_products": products,
        "fallback_notice": matches.get("fallback_notice", ""),
        "preview_only": True,
        "upgrade_product": "699_bank_match",
        "upgrade_title": "当前为基础版预览",
        "upgrade_text": "升级699版本可查看完整产品匹配、申请顺序和额度预测。",
    }


def build_bank_match_full(matches: dict[str, Any] | None, base_path: str = "") -> dict[str, Any]:
    full = deepcopy(matches or {})
    full["matched_products"] = [
        _decorate_match(item, base_path) for item in full.get("matched_products", [])
    ]
    full["preview_only"] = False
    return full


def build_document_checklist_preview(
    checklist: dict[str, Any] | None = None,
    assessment: Assessment | None = None,
) -> dict[str, Any]:
    preview = deepcopy(DEFAULT_CHECKLIST_PREVIEW)
    if assessment and assessment.has_collateral and "抵押物资料" not in preview["hidden_items"]:
        preview["hidden_items"].insert(2, "抵押物资料")
    return preview


def _normalize_full_group(group: Any) -> dict[str, Any] | None:
    if not isinstance(group, dict):
        return None
    category = str(group.get("category") or "").strip()
    items = group.get("items") or []
    if not category or not isinstance(items, list) or not items:
        return None
    default = next((item for item in DEFAULT_CHECKLIST_FULL if item["category"] == category), {})
    return {
        "category": category,
        "purpose": group.get("purpose") or default.get("purpose") or f"用于银行审核{category}相关信息。",
        "priority": group.get("priority") or default.get("priority") or "中",
        "items": [str(item) for item in items if str(item).strip()],
        "missing_risk": group.get("missing_risk") or default.get("missing_risk") or "如果缺少该类资料，可能影响银行审批判断或导致补件。",
    }


def build_document_checklist_full(checklist: dict[str, Any] | None = None) -> dict[str, Any]:
    checklist = checklist or {}
    groups = []
    for group in checklist.get("required_documents", []):
        normalized = _normalize_full_group(group)
        if normalized:
            groups.append(normalized)
    existing = {group["category"] for group in groups}
    for default_group in DEFAULT_CHECKLIST_FULL:
        if default_group["category"] not in existing:
            groups.append(deepcopy(default_group))
    return {
        "required_documents": groups,
        "optional_documents": checklist.get("optional_documents", []),
        "missing_risk": checklist.get("missing_risk", []),
        "preparation_priority": checklist.get("preparation_priority", []),
        "execution_plan": build_document_execution_plan({}, checklist),
        "detail_level": "full",
        "preview_only": False,
    }


def _normalize_execution_plan_item(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    period = str(item.get("period") or item.get("stage") or "").strip()
    actions = item.get("actions") or item.get("core_actions") or []
    if isinstance(actions, str):
        actions = [actions]
    actions = [str(action).strip() for action in actions if str(action).strip()]
    if not period or not actions:
        return None
    return {
        "period": period,
        "goal": str(item.get("goal") or "按阶段完成资料补齐、融资准备与申请执行。").strip(),
        "actions": actions,
        "owner": str(item.get("owner") or "企业负责人 / 财务负责人").strip(),
        "deliverable": str(item.get("deliverable") or item.get("result") or "形成阶段性交付材料包与复核清单。").strip(),
    }


def _plan_from_structure_plan(structure_plan: dict[str, Any] | None) -> list[dict[str, Any]]:
    structure_plan = structure_plan or {}
    mapping = [
        ("stage_1_30_days", "30天执行计划", "完成基础资料补齐和银行预匹配准备。"),
        ("stage_2_90_days", "90天执行计划", "完成重点银行申请材料适配和内部复核。"),
        ("stage_3_180_days", "180天执行计划", "建立长期融资资料更新和续贷准备机制。"),
    ]
    sections = []
    for key, period, goal in mapping:
        actions = structure_plan.get(key) or []
        if isinstance(actions, str):
            actions = [actions]
        actions = [str(action).strip() for action in actions if str(action).strip()]
        if actions:
            sections.append(
                {
                    "period": period,
                    "goal": goal,
                    "actions": actions,
                    "owner": "企业负责人 / 财务负责人",
                    "deliverable": "形成阶段性资料清单、问题修复结果和融资推进记录。",
                }
            )
    return sections


def build_document_execution_plan(
    report: dict[str, Any] | None = None,
    checklist: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    report = report or {}
    checklist = checklist or {}
    raw_plan = (
        checklist.get("execution_plan")
        or checklist.get("document_execution_plan")
        or report.get("document_execution_plan")
        or report.get("execution_plan_sections")
        or report.get("execution_plan")
        or []
    )
    if isinstance(raw_plan, dict):
        raw_plan = raw_plan.get("sections") or raw_plan.get("items") or []
    sections = [_normalize_execution_plan_item(item) for item in raw_plan]
    sections = [item for item in sections if item]
    if sections:
        return sections
    sections = _plan_from_structure_plan(report.get("structure_plan"))
    return sections or deepcopy(DEFAULT_DOCUMENT_EXECUTION_PLAN)


def build_report_access_context(
    db: Session,
    assessment: Assessment,
    report: dict[str, Any],
    base_path: str | None = None,
) -> dict[str, Any]:
    paid_product_codes = get_paid_product_codes(db, assessment.id)
    bank_unlocked = can_view_full_bank_match(paid_product_codes)
    checklist_unlocked = can_view_full_document_checklist(paid_product_codes)
    base_path = base_path or f"/report/{assessment.id}"
    matches = report.get("bank_product_matches") or {}
    checklist = report.get("document_checklist") or {}
    document_execution_plan = build_document_execution_plan(report, checklist)
    document_checklist_full = build_document_checklist_full(checklist)
    document_checklist_full["execution_plan"] = document_execution_plan
    return {
        "paid_product_codes": paid_product_codes,
        "bank_match_unlocked": bank_unlocked,
        "bank_match_preview": build_bank_match_preview(matches, base_path),
        "bank_match_full": build_bank_match_full(matches, base_path),
        "document_checklist_unlocked": checklist_unlocked,
        "document_checklist_preview": build_document_checklist_preview(checklist, assessment),
        "document_checklist_full": document_checklist_full,
        "execution_plan_unlocked": checklist_unlocked,
        "execution_plan_sections": document_execution_plan if checklist_unlocked else [],
        "document_execution_plan": document_execution_plan if checklist_unlocked else [],
        "product_detail_unlocked": can_view_full_bank_product_detail(paid_product_codes),
    }


def find_report_matched_product(report: dict[str, Any], product_id: int) -> dict[str, Any] | None:
    for item in (report.get("bank_product_matches") or {}).get("matched_products", []):
        try:
            if int(item.get("product_id") or item.get("id") or 0) == int(product_id):
                return dict(item)
        except (TypeError, ValueError):
            continue
    return None


def build_bank_product_detail_context(
    db: Session,
    assessment: Assessment,
    report: dict[str, Any],
    product_id: int,
) -> dict[str, Any] | None:
    product = db.get(BankProduct, product_id)
    matched = find_report_matched_product(report, product_id)
    if not product and not matched:
        return None
    matched = matched or {}
    paid_product_codes = get_paid_product_codes(db, assessment.id)
    unlocked = can_view_full_bank_product_detail(paid_product_codes)
    product_data = {
        "id": product_id,
        "product_code": getattr(product, "product_code", "") if product else matched.get("product_code", ""),
        "bank_name": getattr(product, "bank_name", "") if product else matched.get("bank_name", ""),
        "bank_type": getattr(product, "bank_type", "") if product else matched.get("bank_type", ""),
        "product_name": getattr(product, "product_name", "") if product else matched.get("product_name", ""),
        "product_type": getattr(product, "product_type", "") if product else matched.get("product_type", ""),
        "guarantee_method": getattr(product, "guarantee_method", "") if product else "",
        "amount_description": getattr(product, "amount_description", "") if product else "",
        "max_amount": getattr(product, "max_amount", "") if product else "",
        "min_amount": getattr(product, "min_amount", "") if product else "",
        "interest_rate_range": getattr(product, "interest_rate_range", "") if product else matched.get("interest_rate_range", ""),
        "loan_term": getattr(product, "loan_term", "") if product else matched.get("loan_term", ""),
        "repayment_methods": getattr(product, "repayment_methods", "") if product else "",
        "application_requirements": getattr(product, "application_requirements", "") if product else "",
        "access_conditions_json": getattr(product, "access_conditions_json", "") if product else "",
        "prohibited_conditions_json": getattr(product, "prohibited_conditions_json", "") if product else "",
        "suitable_scenarios": getattr(product, "suitable_scenarios", "") if product else "",
        "target_customer_type": getattr(product, "target_customer_type", "") if product else "",
        "required_documents": getattr(product, "required_documents", "") if product else "",
        "required_documents_json": getattr(product, "required_documents_json", "") if product else "",
        "risk_notes": getattr(product, "risk_notes", "") if product else matched.get("risk_notes", ""),
        "update_note": getattr(product, "update_note", "") if product else "",
        "match_score": matched.get("match_score", ""),
        "reason": matched.get("reason", ""),
        "estimated_amount": matched.get("estimated_amount", ""),
    }
    if not product_data["amount_description"]:
        product_data["amount_description"] = matched.get("estimated_amount", "")
    return {
        "product": product_data,
        "matched_product": matched,
        "product_detail_unlocked": unlocked,
        "upgrade_product": "699_bank_match",
    }
