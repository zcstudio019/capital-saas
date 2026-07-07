from typing import Any


CATEGORY_ALIASES = {
    "营业执照": ["营业执照/工商资料", "企业基础资料", "营业执照"],
    "纳税/开票资料": ["纳税资料", "发票", "开票"],
    "银行流水": ["银行流水"],
    "财务报表": ["财务报表", "财务资料"],
    "征信资料": ["征信资料", "征信"],
    "抵押物权属证明": ["抵押物资料", "房产证", "产权"],
    "抵押物评估资料": ["抵押物资料", "评估"],
    "权属人资料": ["法人/股东资料", "权属人"],
    "经营合同": ["经营合同", "应收账款资料", "合同"],
    "发票": ["纳税资料", "应收账款资料", "发票"],
    "应收账款明细": ["应收账款资料", "应收账款"],
    "上下游客户证明": ["经营合同", "应收账款资料", "客户证明"],
}


def _has_document(documents: list[Any], required: str) -> bool:
    aliases = CATEGORY_ALIASES.get(required, [required])
    for document in documents:
        haystack = f"{document.document_category} {document.file_name} {document.note or ''}"
        if any(alias in haystack for alias in aliases):
            return True
    return False


def check_document_completeness(
    lead: Any,
    assessment: Any,
    uploaded_documents: list[Any],
    recommended_product: str = "",
    matched_bank_products: dict | None = None,
) -> dict:
    required = ["营业执照", "纳税/开票资料", "银行流水", "财务报表", "征信资料"]
    optional = ["法人/股东资料", "经营合同", "融资用途说明"]
    product_types = " ".join(
        item.get("product_type", "")
        for item in (matched_bank_products or {}).get("matched_products", [])[:3]
    )
    if assessment.has_collateral or "抵押" in product_types:
        required += ["抵押物权属证明", "抵押物评估资料", "权属人资料"]
    if assessment.receivable_days >= 60 or "应收" in product_types or "供应链" in product_types:
        required += ["经营合同", "发票", "应收账款明细", "上下游客户证明"]
    required = list(dict.fromkeys(required))
    present = [item for item in required if _has_document(uploaded_documents, item)]
    missing = [item for item in required if item not in present]
    optional_missing = [item for item in optional if not _has_document(uploaded_documents, item)]
    required_score = (len(present) / len(required) * 85) if required else 85
    verified = sum(document.verify_status == "verified" for document in uploaded_documents)
    verification_score = min(15, verified * 5)
    score = round(required_score + verification_score)
    score = min(100, score)
    risk_notes = []
    if missing:
        risk_notes.append(f"尚缺{len(missing)}项核心融资资料，可能影响预审与额度判断")
    if any(document.parse_status == "parse_failed" for document in uploaded_documents):
        risk_notes.append("存在解析失败资料，需要人工核验原件")
    if not assessment.credit_status:
        risk_notes.append("测评征信状态异常，需提供征信报告及说明")
    if not assessment.tax_status:
        risk_notes.append("测评纳税状态异常，需核验申报与完税记录")
    level = "complete" if score >= 85 else "partial" if score >= 60 else "weak"
    return {
        "completeness_score": score,
        "level": level,
        "required_documents": required,
        "present_required_documents": present,
        "missing_required_documents": missing,
        "missing_optional_documents": optional_missing,
        "risk_notes": risk_notes,
        "next_collect_actions": [f"向客户补充收集：{item}" for item in missing[:6]],
        "high_value_action_required": (
            recommended_product in {"1999_structure_plan", "high_ticket_consulting"}
            and score < 70
        ),
    }
