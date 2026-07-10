"""Final rendering helpers for customer-facing financing reports."""

from __future__ import annotations

import ast
import html
import json
import re
from copy import deepcopy
from typing import Any

from utils.report_display_mapper import sanitize_report_text


_ENUM_MAP = {
    "medium": "中等",
    "high": "高",
    "low": "低",
    "good": "良好",
    "poor": "较弱",
    "excellent": "优秀",
    "pending": "待处理",
    "approved": "已批复",
    "rejected": "未通过",
    "submitted": "已提交",
    "paid": "已支付",
    "unpaid": "未支付",
    "success": "成功",
    "failed": "失败",
    "pass": "通过",
    "fail": "未通过",
    "unknown": "待评估",
}
_ENUM_PATTERN = re.compile(
    r"(?<![A-Za-z])(" + "|".join(_ENUM_MAP) + r")(?![A-Za-z])", re.IGNORECASE
)
_NON_VISIBLE_BLOCK = re.compile(r"<(?:style|script)\b[^>]*>.*?</(?:style|script)>", re.IGNORECASE | re.DOTALL)
_HTML_TAG = re.compile(r"<[^>]+>")
_RAW_STRUCTURE_MARKERS = (
    "{'", "'}", "':", '\":', "[{", "}]", "_days", "owner", "actions",
    "outcome", "risk_level", "match_score", "next_steps", "product_code",
    "data_source", "document_checklist", "bank_approval", "30_days", "90_days",
    "180_days", "365_days",
)
_ACTION_SOURCE_FIELDS = (
    "formatted_action_plan", "action_plan", "action_steps", "timeline_plan",
    "next_steps", "next_actions", "recommendations", "formatted_action_steps",
)
_PERIOD_LABELS = {
    "30_days": "未来30天行动计划",
    "90_days": "未来90天行动计划",
    "180_days": "未来180天行动计划",
    "365_days": "未来12个月行动计划",
    "12_months": "未来12个月行动计划",
    "stage_1_30_days": "未来30天行动计划",
    "stage_2_90_days": "未来90天行动计划",
    "stage_3_180_days": "未来180天行动计划",
}

DEFAULT_ACTION_PLAN = [
    {
        "period": "未来30天行动计划",
        "owner": "企业负责人牵头，财务负责人配合",
        "actions": [
            "统一银行流水、纳税申报、财务报表与合同口径",
            "准备未来13周现金流预测",
            "明确新增融资的资金用途与还款来源",
            "优先置换短期高成本债务",
        ],
        "outcome": "形成统一资料包和现金流预测报告，债务置换方案初步落地。",
    },
    {
        "period": "未来90天行动计划",
        "owner": "财务负责人主责，企业负责人确认融资策略",
        "actions": [
            "先申请抵押类经营贷锁定核心额度",
            "再补充城商行或股份制信用贷",
            "最后评估国有大行低成本授信",
        ],
        "outcome": "完成2至3家银行预匹配并锁定核心额度，至少一家银行进入审批流程。",
    },
    {
        "period": "未来12个月行动计划",
        "owner": "企业负责人与财务负责人共同负责",
        "actions": [
            "完成年度资本规划",
            "形成多元融资渠道",
            "评估再融资、债务置换或股权路径",
            "持续优化融资成本",
        ],
        "outcome": "债务结构复盘完成，年度资金计划和融资成本优化目标达成。",
    },
]


def map_report_enum(value: Any) -> str:
    """Map an internal enum to a customer-safe Chinese label."""
    text = str(value or "").strip()
    return _ENUM_MAP.get(text.lower(), str(sanitize_report_text(text)))


def _parse_structure(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text.startswith(("{", "[")):
        return text
    for parser in (json.loads, ast.literal_eval):
        try:
            parsed = parser(text)
        except (ValueError, SyntaxError, TypeError, json.JSONDecodeError):
            continue
        if isinstance(parsed, (dict, list, tuple)):
            return parsed
    return text


def _clean_text(value: Any) -> str:
    text = str(sanitize_report_text(value or "")).strip()
    return _ENUM_PATTERN.sub(lambda match: _ENUM_MAP[match.group(1).lower()], text)


def format_report_value(value: Any) -> str:
    """Safely flatten report values so dict/list/JSON repr never reaches templates."""
    value = _parse_structure(value)
    if value is None:
        return ""
    if isinstance(value, dict):
        return "；".join(
            part for item in value.values() if (part := format_report_value(item))
        )
    if isinstance(value, (list, tuple, set)):
        return "；".join(
            part for item in value if (part := format_report_value(item))
        )
    return _clean_text(value)


def _period_label(value: Any, fallback_index: int) -> str:
    text = format_report_value(value).lower().replace("-", "_").replace(" ", "_")
    if text in _PERIOD_LABELS:
        return _PERIOD_LABELS[text]
    for key, label in _PERIOD_LABELS.items():
        if key in text:
            return label
    match = re.search(r"(30|90|180|365|12)\s*(?:天|个月|months?|days?)?", text)
    if match:
        number = match.group(1)
        return "未来12个月行动计划" if number in {"365", "12"} else f"未来{number}天行动计划"
    return DEFAULT_ACTION_PLAN[min(fallback_index, len(DEFAULT_ACTION_PLAN) - 1)]["period"]


def _action_list(value: Any) -> list[str]:
    value = _parse_structure(value)
    if isinstance(value, dict):
        return [part for item in value.values() if (part := format_report_value(item))]
    if isinstance(value, (list, tuple, set)):
        return [part for item in value if (part := format_report_value(item))]
    text = format_report_value(value)
    return [text] if text else []


def _action_step(value: Any, period: Any, index: int) -> dict[str, Any]:
    value = _parse_structure(value)
    source = value if isinstance(value, dict) else {}
    actions = _action_list(
        source.get("actions")
        or source.get("core_actions")
        or source.get("action")
        or source.get("next_steps")
        or source.get("content")
        or source.get("建议")
        or (value if not source else None)
    )
    return {
        "period": _period_label(source.get("period") or source.get("stage") or period, index),
        "owner": format_report_value(source.get("owner") or source.get("负责人")),
        "actions": actions,
        "outcome": format_report_value(
            source.get("outcome")
            or source.get("deliverable")
            or source.get("result")
            or source.get("goal")
            or source.get("交付结果")
        ),
    }


def format_action_plan(value: Any) -> list[dict[str, Any]]:
    """Normalize action-plan source values into customer-renderable phase cards."""
    value = _parse_structure(value)
    if isinstance(value, dict):
        for field in _ACTION_SOURCE_FIELDS:
            if field in value and value[field] not in (None, "", [], {}):
                return format_action_plan(value[field])
        if any(key in value for key in ("period", "stage", "owner", "actions", "action")):
            steps = [_action_step(value, None, 0)]
        else:
            ordered = sorted(
                value.items(),
                key=lambda item: next(
                    (index for index, key in enumerate(_PERIOD_LABELS) if key in str(item[0]).lower()),
                    len(_PERIOD_LABELS),
                ),
            )
            steps = [_action_step(item, period, index) for index, (period, item) in enumerate(ordered)]
    elif isinstance(value, (list, tuple)):
        steps = [_action_step(item, None, index) for index, item in enumerate(value)]
    elif value:
        steps = [_action_step(value, None, 0)]
    else:
        steps = []

    steps = [step for step in steps if step["actions"] or step["outcome"] or step["owner"]]
    if not steps:
        return deepcopy(DEFAULT_ACTION_PLAN)
    for index, step in enumerate(steps):
        fallback = DEFAULT_ACTION_PLAN[min(index, len(DEFAULT_ACTION_PLAN) - 1)]
        step["owner"] = step["owner"] or fallback["owner"]
        step["actions"] = step["actions"] or fallback["actions"]
        step["outcome"] = step["outcome"] or fallback["outcome"]
    return steps


def contains_raw_structure_text(text: Any) -> bool:
    content = str(text or "").lower()
    return any(marker in content for marker in _RAW_STRUCTURE_MARKERS)


def _format_items(value: Any) -> list[str]:
    parsed = _parse_structure(value)
    if isinstance(parsed, (list, tuple, set)):
        return [item for raw in parsed if (item := format_report_value(raw))]
    item = format_report_value(parsed)
    return [item] if item else []


def format_report_for_render(report: dict[str, Any] | None) -> dict[str, Any] | None:
    """Attach template-only display fields and neutralize nested raw structures."""
    if not isinstance(report, dict):
        return report
    rendered = deepcopy(report)
    for index, chapter in enumerate(rendered.get("chapters") or []):
        if not isinstance(chapter, dict):
            continue
        chapter["conclusion"] = format_report_value(chapter.get("conclusion"))
        chapter["bank_view"] = format_report_value(chapter.get("bank_view"))
        chapter["risk_warning"] = format_report_value(chapter.get("risk_warning"))
        chapter["formatted_key_issues"] = _format_items(chapter.get("key_issues") or chapter.get("key_findings"))
        chapter["formatted_owner_actions"] = _format_items(chapter.get("owner_actions") or chapter.get("boss_action"))
        chapter["formatted_next_steps"] = _format_items(chapter.get("next_steps") or chapter.get("next_actions"))
        chapter["formatted_risk_items"] = _format_items(chapter.get("risk_warning"))
        title = str(chapter.get("title") or chapter.get("section_title") or "")
        if index == 9 or "行动建议" in title or "行动计划" in title:
            source = next(
                (
                    chapter.get(field)
                    for field in _ACTION_SOURCE_FIELDS
                    if chapter.get(field) not in (None, "", [], {})
                ),
                None,
            )
            if source is None and isinstance(chapter.get("details"), dict):
                source = next(
                    (
                        chapter["details"].get(field)
                        for field in _ACTION_SOURCE_FIELDS
                        if chapter["details"].get(field) not in (None, "", [], {})
                    ),
                    None,
                )
            chapter["formatted_action_plan"] = format_action_plan(source)

    matches = rendered.get("bank_product_matches")
    if isinstance(matches, dict):
        matches["formatted_bank_products"] = [
            {
                **item,
                "match_score_display": (
                    f"{int(item.get('match_score'))}分"
                    if str(item.get("match_score", "")).isdigit()
                    else format_report_value(item.get("match_score"))
                ),
                "recommendation_reason": format_report_value(item.get("recommendation_reason") or item.get("reason")),
                "risk_notes": format_report_value(item.get("risk_notes")),
            }
            for item in matches.get("matched_products", [])
            if isinstance(item, dict)
        ]
    return rendered


def validate_report_for_delivery(report_html_or_text: Any) -> dict[str, Any]:
    """Validate a customer-facing report payload before it is delivered."""
    if isinstance(report_html_or_text, dict):
        report = report_html_or_text
        text = format_report_value(report)
        empty_chapters = [
            str(chapter.get("title") or chapter.get("section_title") or "未命名章节")
            for chapter in report.get("chapters", [])
            if isinstance(chapter, dict) and not format_report_value(chapter.get("conclusion"))
        ]
    else:
        html_text = str(report_html_or_text or "")
        text = html.unescape(_HTML_TAG.sub(" ", _NON_VISIBLE_BLOCK.sub(" ", html_text)))
        empty_chapters = []

    issues: list[str] = []
    lowered = text.lower()
    if contains_raw_structure_text(text):
        issues.append("检测到原始结构或内部字段")
    if _ENUM_PATTERN.search(text):
        issues.append("检测到英文内部枚举")
    if re.search(r"\b(?:none|null|undefined)\b", text, re.IGNORECASE):
        issues.append("检测到空值占位文本")
    if "�" in text or text.count("?") >= 8:
        issues.append("检测到乱码或异常问号")
    if text.count("暂无数据") > 2:
        issues.append("检测到过多暂无数据占位")
    if empty_chapters:
        issues.append(f"存在空章节：{'、'.join(empty_chapters)}")
    return {"valid": not issues, "issues": issues, "text": lowered}
