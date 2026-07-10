from typing import Any

from ai.pipelines.section_generator import normalize_section
from utils.report_display_mapper import display_value


class ReportRewriter:
    """最多由流水线调用两次；Mock 下执行确定性补强，OpenAI 异常仍可用。"""

    def rewrite(self, report: dict[str, Any], context: dict[str, Any], quality: dict) -> dict[str, Any]:
        company = context["company_name"]
        revenue = context["annual_revenue"] / 10000
        debt = context["debt_total"] / 10000
        cashflow = context["monthly_cashflow"] / 10000
        receivable = context["receivable_days"]
        funding = context["funding_need"] / 10000
        grade = display_value("company_grade", context["grade"])
        enriched = []
        for raw in report.get("chapters", []):
            section = normalize_section(raw, raw.get("title", "报告章节"))
            prefix = (
                f"{company}当前企业等级为{grade}级，年营收约{revenue:,.0f}万元、"
                f"总负债约{debt:,.0f}万元、月均现金流约{cashflow:,.0f}万元、"
                f"应收账款周期{receivable}天，本次融资需求约{funding:,.0f}万元。"
            )
            if prefix not in section["conclusion"]:
                section["conclusion"] = prefix + section["conclusion"]
            section["risk_warning"] = (
                section["risk_warning"]
                + " 不得伪造资料或包装流水，不保证额度、利率及贷款审批结果。"
            )
            if section["section_title"] == "行动建议":
                required = ["未来30天：完成资料口径统一与风险修复。",
                            "未来90天：按匹配顺序完成预审和核心额度申请。",
                            "未来12个月：复盘债务结构并建立年度资本计划。"]
                section["next_steps"] = required
                section["next_actions"] = required
            enriched.append(section)
        report["chapters"] = enriched
        return report
