"""Customer-safe Chinese display values for generated financing reports."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any


RISK_LEVEL_MAP = {
    "high": "高风险",
    "medium": "中等风险",
    "low": "低风险",
    "critical": "严重风险",
}
FINANCE_FEASIBILITY_MAP = {
    "excellent": "优秀",
    "good": "良好",
    "medium": "一般",
    "poor": "较弱",
    "high": "较高",
    "low": "较低",
}
COMPANY_GRADE_MAP = {
    "S": "优秀",
    "A": "优秀",
    "B": "良好",
    "C": "一般",
    "D": "较弱",
}
STATUS_MAP = {
    "pass": "通过",
    "fail": "未通过",
    "pending": "待评估",
    "approved": "已通过",
    "rejected": "未通过",
    "pending_review": "待审核",
}
PRIORITY_MAP = {"high": "高优先级", "medium": "中优先级", "low": "低优先级"}
TREND_MAP = {"up": "提升", "down": "下降", "stable": "稳定"}
CONFIDENCE_MAP = {"high": "高置信度", "medium": "中等置信度", "low": "低置信度"}
CREDIT_LEVEL_MAP = {"high": "信用良好", "medium": "信用一般", "low": "信用较弱"}
MATCH_LEVEL_MAP = {"high": "高度匹配", "medium": "适配", "low": "适配度较低"}

FIELD_MAPPERS = {
    "risk_level": RISK_LEVEL_MAP,
    "finance_feasibility": FINANCE_FEASIBILITY_MAP,
    "funding_probability": FINANCE_FEASIBILITY_MAP,
    "approval_probability": FINANCE_FEASIBILITY_MAP,
    "credit_level": CREDIT_LEVEL_MAP,
    "company_grade": COMPANY_GRADE_MAP,
    "grade": COMPANY_GRADE_MAP,
    "status": STATUS_MAP,
    "priority": PRIORITY_MAP,
    "trend": TREND_MAP,
    "confidence": CONFIDENCE_MAP,
    "warning_level": RISK_LEVEL_MAP,
    "match_level": MATCH_LEVEL_MAP,
}

DISPLAY_FIELD_NAMES = {
    "grade": "company_grade_display",
    "funding_probability": "finance_feasibility_display",
    "warning_level": "risk_level_display",
}
INTERNAL_DISPLAY_FIELDS = frozenset(FIELD_MAPPERS)
INTERNAL_REPORT_KEYS = frozenset({
    "schema_version", "pipeline_version", "generated_by", "quality", "rewrite_attempts",
    "product_code", "data_source", "debug_scores", "eliminated", "eliminated_reason",
    "details", "customer_profile",
})

TEXT_ENUM_REPLACEMENTS = {
    "medium": "一般",
    "high": "较高",
    "low": "较低",
    "pending": "待评估",
    "approved": "已通过",
    "rejected": "未通过",
    "strong": "较强",
    "weak": "较弱",
    "normal": "正常",
    "excellent": "优秀",
    "unknown": "待评估",
    "good": "良好",
    "poor": "较弱",
    "pass": "通过",
    "fail": "未通过",
    "stable": "稳定",
    "up": "提升",
    "down": "下降",
}
_TEXT_ENUM_PATTERN = re.compile(
    r"(?<![A-Za-z])(" + "|".join(TEXT_ENUM_REPLACEMENTS) + r")(?![A-Za-z])",
    re.IGNORECASE,
)


def _normalized(value: Any) -> str:
    return str(value or "").strip().lower()


def sanitize_report_text(value: Any) -> Any:
    """Replace accidental English enum tokens inside AI-authored narrative text."""
    if not isinstance(value, str):
        return value
    return _TEXT_ENUM_PATTERN.sub(
        lambda match: TEXT_ENUM_REPLACEMENTS[match.group(1).lower()], value
    )


def display_report_text(value: Any) -> str:
    """Render structured source fields as plain customer-facing text without JSON keys."""
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return str(sanitize_report_text(value))
        return display_report_text(parsed)
    if isinstance(value, dict):
        return "；".join(
            text for item in value.values() if (text := display_report_text(item))
        )
    if isinstance(value, (list, tuple, set)):
        return "；".join(
            text for item in value if (text := display_report_text(item))
        )
    return "" if value is None else str(sanitize_report_text(value))


def display_value(field_name: str, value: Any) -> str:
    """Return a customer-facing Chinese label for one internal report value."""
    if value is None or value == "":
        return "待评估"
    if field_name == "approval_probability" and isinstance(value, (int, float)):
        probability = float(value)
        return f"{probability * 100:.0f}%" if 0 <= probability <= 1 else f"{probability:.0f}%"
    if field_name == "confidence" and isinstance(value, (int, float)):
        confidence = float(value)
        return f"置信度{confidence * 100:.0f}%" if 0 <= confidence <= 1 else f"置信度{confidence:.0f}%"

    mapping = FIELD_MAPPERS.get(field_name, {})
    normalized = _normalized(value)
    if field_name in {"grade", "company_grade"}:
        normalized = str(value).strip().upper()
    return mapping.get(normalized, sanitize_report_text(str(value)))


def enrich_report_display_fields(report: dict[str, Any] | None) -> dict[str, Any] | None:
    """Attach Chinese ``*_display`` fields without discarding internal source values."""
    if report is None:
        return None

    def convert(value: Any) -> Any:
        if isinstance(value, list):
            return [convert(item) for item in value]
        if not isinstance(value, dict):
            return sanitize_report_text(value)

        result: dict[str, Any] = {}
        for key, item in value.items():
            result[key] = convert(item)
            if key in FIELD_MAPPERS:
                display_key = DISPLAY_FIELD_NAMES.get(key, f"{key}_display")
                result[display_key] = display_value(key, item)
        return result

    return convert(deepcopy(report))


def build_customer_report_display(report: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return the report model exposed to templates, PDF output, and customer APIs."""
    enriched = enrich_report_display_fields(report)
    if enriched is None:
        return None

    def strip_internal(value: Any) -> Any:
        if isinstance(value, list):
            return [strip_internal(item) for item in value]
        if not isinstance(value, dict):
            return value
        return {
            key: strip_internal(item)
            for key, item in value.items()
            if key not in INTERNAL_DISPLAY_FIELDS and key not in INTERNAL_REPORT_KEYS
        }

    return strip_internal(enriched)
