import json
from typing import Any

from utils.report_render_formatter import format_report_value


KEY_DATA_TERMS = ["年营收", "负债", "现金流", "应收", "融资需求"]
BANK_TERMS = ["审批", "通过概率", "额度", "拒贷", "银行"]
ACTION_TERMS = ["30天", "90天", "12个月"]
RISK_TERMS = ["现金流", "短债", "征信", "纳税", "抵押"]
FORBIDDEN_TERMS = ["保证放款", "包过", "包装流水", "伪造材料", "虚假资料"]


def _text(report: dict[str, Any]) -> str:
    return format_report_value(report)


def evaluate_report_quality(
    report: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """确定性质量门禁；既可检查 Mock，也可检查真实 AI 输出。"""
    content = _text(report)
    chapters = report.get("chapters") or []
    missing: list[str] = []
    rewrite_sections: list[str] = []

    data_hits = sum(term in content for term in KEY_DATA_TERMS)
    data_score = round(data_hits / len(KEY_DATA_TERMS) * 20)
    if data_hits < 4:
        missing.append("关键经营数据引用不足")

    bank_hits = sum(term in content for term in BANK_TERMS)
    bank_score = round(bank_hits / len(BANK_TERMS) * 20)
    bank_approval = report.get("bank_approval") or {}
    if not bank_approval.get("estimated_credit_limit"):
        bank_score = max(0, bank_score - 5)
        missing.append("缺少预计授信额度")

    action_hits = sum(term in content for term in ACTION_TERMS)
    action_score = round(action_hits / len(ACTION_TERMS) * 20)
    if action_hits < 3:
        missing.append("缺少30天、90天或12个月行动计划")

    risk_hits = sum(term in content for term in RISK_TERMS)
    risk_score = round(risk_hits / len(RISK_TERMS) * 15)
    if risk_hits < 3:
        missing.append("风险提示覆盖不足")

    company_name = str((context or {}).get("company_name", ""))
    industry = str((context or {}).get("industry", ""))
    grade = str((context or {}).get("grade", ""))
    personalized_hits = sum(bool(value and value in content) for value in [company_name, industry, grade])
    personalized_score = min(15, 6 + personalized_hits * 3)

    compliance_score = 10
    violations = [term for term in FORBIDDEN_TERMS if term in content]
    if violations:
        compliance_score = 0
        missing.append("包含不合规承诺或材料包装建议")

    required_keys = {
        "section_title", "conclusion", "key_findings", "bank_view",
        "boss_action", "next_steps", "risk_warning", "upsell_hint",
    }
    for chapter in chapters:
        absent = [key for key in required_keys if not chapter.get(key)]
        if absent:
            rewrite_sections.append(chapter.get("section_title") or chapter.get("title") or "未知章节")
    if len(chapters) != 10:
        missing.append("报告章节不是10章")

    score = min(
        100,
        data_score + bank_score + action_score + risk_score
        + personalized_score + compliance_score,
    )
    if rewrite_sections:
        score = max(0, score - min(20, len(rewrite_sections) * 3))
        missing.append("部分章节结构字段不完整")
    level = "excellent" if score >= 90 else "good" if score >= 80 else "average" if score >= 70 else "poor"
    return {
        "quality_score": score,
        "quality_level": level,
        "missing_items": list(dict.fromkeys(missing)),
        "rewrite_required": score < 70 or bool(rewrite_sections),
        "rewrite_sections": list(dict.fromkeys(rewrite_sections)),
        "dimension_scores": {
            "data_reference": data_score,
            "bank_professionalism": bank_score,
            "actionability": action_score,
            "risk_completeness": risk_score,
            "personalization": personalized_score,
            "compliance": compliance_score,
        },
    }
