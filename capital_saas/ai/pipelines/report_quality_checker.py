from core.report_quality_engine import evaluate_report_quality


class ReportQualityChecker:
    def check(self, report: dict, context: dict) -> dict:
        return evaluate_report_quality(report, context)
