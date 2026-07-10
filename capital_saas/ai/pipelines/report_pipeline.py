from copy import deepcopy
from typing import Any

from ai.pipelines.report_quality_checker import ReportQualityChecker
from ai.pipelines.report_rewriter import ReportRewriter
from ai.pipelines.section_generator import SectionGenerator
from core.bank_approval_engine import simulate_bank_approval
from core.bank_product_matcher import match_bank_products
from core.document_checklist_engine import generate_document_checklist
from utils.report_display_mapper import build_customer_report_display, enrich_report_display_fields
from utils.report_formatters import normalize_report_action_steps
from utils.report_render_formatter import format_report_for_render, validate_report_for_delivery


class ReportPipeline:
    def __init__(self, db, report):
        self.db = db
        self.report = report

    def build_context(self, assessment, product_code: str) -> dict[str, Any]:
        data = {
            key: getattr(assessment, key)
            for key in [
                "company_name", "industry", "years", "employee_count",
                "annual_revenue", "net_profit", "monthly_cashflow", "debt_total",
                "short_debt", "receivable_days", "funding_need", "funding_purpose",
                "has_collateral", "tax_status", "credit_status", "score", "grade",
                "risk_level", "funding_probability",
            ]
        }
        data["lead_grade"] = assessment.lead.lead_grade if assessment.lead else ""
        data["product_code"] = product_code
        data["bank_approval"] = simulate_bank_approval(data, assessment.score).to_dict()
        data["bank_product_matches"] = match_bank_products(self.db, assessment)
        data["document_checklist"] = generate_document_checklist(assessment, product_code)
        return data

    def run(self, assessment, product_code: str, fallback_report: dict) -> tuple[dict, dict]:
        context = self.build_context(assessment, product_code)
        report = deepcopy(fallback_report)
        generator = SectionGenerator(self.db, self.report.id, assessment.id)
        report["chapters"] = generator.generate(context, report.get("chapters", []))
        report["bank_approval"] = context["bank_approval"]
        report["bank_product_matches"] = context["bank_product_matches"]
        report["document_checklist"] = context["document_checklist"]
        report["company_grade"] = context["grade"]
        report["risk_level"] = context["risk_level"]
        report["finance_feasibility"] = context["funding_probability"]
        report["product_code"] = product_code
        report["pipeline_version"] = 6
        if len(report["chapters"]) >= 5:
            report["chapters"][4]["details"]["bank_product_matches"] = context["bank_product_matches"]
            report["chapters"][4]["details"]["best_application_order"] = context[
                "bank_product_matches"
            ]["best_application_order"]
        if len(report["chapters"]) >= 10:
            report["chapters"][9]["details"]["document_checklist"] = context["document_checklist"]

        checker = ReportQualityChecker()
        rewriter = ReportRewriter()
        report = format_report_for_render(report)
        quality = checker.check(report, context)
        attempts = 0
        while quality["rewrite_required"] and attempts < 2:
            report = rewriter.rewrite(report, context, quality)
            report = format_report_for_render(report)
            quality = checker.check(report, context)
            attempts += 1
        report["quality"] = quality
        report["rewrite_attempts"] = attempts
        normalize_report_action_steps(report)
        report = format_report_for_render(report)
        delivery_view = format_report_for_render(build_customer_report_display(report))
        delivery_quality = validate_report_for_delivery(delivery_view)
        report["delivery_quality"] = {
            "valid": delivery_quality["valid"],
            "issues": delivery_quality["issues"],
        }
        quality["delivery_quality"] = report["delivery_quality"]
        report["compliance_disclaimer"] = (
            "本报告基于用户提交信息及系统模型生成，仅用于企业融资规划参考，不构成贷款承诺、"
            "授信承诺、投资建议或法律意见。实际融资结果以银行、金融机构及相关审批结果为准。"
        )
        return enrich_report_display_fields(report), quality
