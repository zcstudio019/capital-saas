"""Safe formatting helpers for report presentation data."""
from __future__ import annotations

import ast
import json
import re
from typing import Any

_ACTION_FIELDS = (
    "formatted_action_steps",
    "next_steps",
    "action_steps",
    "action_plan",
    "recommendations",
    "timeline_plan",
    "next_actions",
)
_PERIOD_ORDER = {"30_days": 0, "90_days": 1, "180_days": 2, "365_days": 3}
_PERIOD_ALIASES = {
    "30_days": "30天行动计划",
    "90_days": "90天行动计划",
    "180_days": "180天行动计划",
    "365_days": "365天行动计划",
    "12_months": "365天行动计划",
    "stage_1_30_days": "30天行动计划",
    "stage_2_90_days": "90天行动计划",
    "stage_3_180_days": "180天行动计划",
    "stage_4_365_days": "365天行动计划",
}


def _safe_text(value: Any) -> str:
    """Return readable scalar text without ever exposing a container repr."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, (list, tuple)):
        parts = [_safe_text(item) for item in value]
        return "；".join(part for part in parts if part)
    return ""


def _period_label(value: Any, fallback: str = "行动建议") -> str:
    raw = _safe_text(value)
    if not raw:
        return fallback
    normalized = raw.lower().strip().replace("-", "_").replace(" ", "_")
    if normalized in _PERIOD_ALIASES:
        return _PERIOD_ALIASES[normalized]
    match = re.search(r"(30|90|180|365)\s*(?:天|_?days?)?", normalized)
    if match:
        return f"{match.group(1)}天行动计划"
    if raw in {"行动建议", "行动计划"}:
        return raw
    return raw if raw.endswith(("行动计划", "行动建议")) else f"{raw}行动计划"


def _step_from_mapping(item: dict[str, Any], period: Any = None) -> dict[str, str]:
    owner = item.get("owner") or item.get("负责人")
    action = item.get("action") or item.get("动作") or item.get("行动")
    goal = item.get("goal") or item.get("目标")
    note = (
        item.get("note")
        or item.get("说明")
        or item.get("注意事项")
        or item.get("注意")
    )
    if not action:
        action = item.get("content") or item.get("建议")
    return {
        "period": _period_label(item.get("period") or item.get("阶段") or period),
        "owner": _safe_text(owner),
        "action": _safe_text(action),
        "goal": _safe_text(goal),
        "note": _safe_text(note),
    }


def _parse_string(value: str) -> Any:
    stripped = value.strip()
    if not stripped:
        return ""
    if not stripped.startswith(("{", "[")):
        return stripped
    for parser in (json.loads, ast.literal_eval):
        try:
            parsed = parser(stripped)
            if isinstance(parsed, (dict, list, tuple)):
                return parsed
        except (ValueError, SyntaxError, TypeError, json.JSONDecodeError):
            continue
    return "行动建议内容暂无法解析，请联系顾问核验。"


def format_action_steps(value: Any) -> list[dict[str, str]]:
    """Normalize dict/list/JSON/text action advice into safe template records."""
    if isinstance(value, str):
        value = _parse_string(value)

    steps: list[dict[str, str]] = []
    if isinstance(value, dict):
        for wrapper in _ACTION_FIELDS[1:]:
            nested = value.get(wrapper)
            if nested not in (None, "", [], {}):
                return format_action_steps(nested)

        if any(key in value for key in ("owner", "负责人", "action", "动作", "行动", "goal", "目标")):
            steps.append(_step_from_mapping(value))
        else:
            ordered = sorted(
                value.items(),
                key=lambda pair: _PERIOD_ORDER.get(
                    next((key for key in _PERIOD_ORDER if key in str(pair[0]).lower()), ""),
                    len(_PERIOD_ORDER),
                ),
            )
            for period, detail in ordered:
                if isinstance(detail, dict):
                    step = _step_from_mapping(detail, period)
                else:
                    step = {
                        "period": _period_label(period),
                        "owner": "",
                        "action": _safe_text(detail),
                        "goal": "",
                        "note": "",
                    }
                if any(step[field] for field in ("owner", "action", "goal", "note")):
                    steps.append(step)
    elif isinstance(value, (list, tuple)):
        for item in value:
            if isinstance(item, dict):
                steps.extend(format_action_steps(item))
            else:
                text = _safe_text(item)
                if text:
                    parsed = _parse_string(text)
                    if parsed != text:
                        steps.extend(format_action_steps(parsed))
                    else:
                        steps.append({
                            "period": "行动建议",
                            "owner": "",
                            "action": text,
                            "goal": "",
                            "note": "",
                        })
    else:
        text = _safe_text(value)
        if text:
            steps.append({
                "period": "行动建议",
                "owner": "",
                "action": text,
                "goal": "",
                "note": "",
            })

    return steps or [{
        "period": "行动建议",
        "owner": "",
        "action": "暂无明确行动建议，请结合企业实际情况由融资顾问进一步完善。",
        "goal": "",
        "note": "",
    }]


def normalize_report_action_steps(report: dict[str, Any] | None) -> dict[str, Any] | None:
    """Attach formatted_action_steps to action-plan chapters in a report."""
    if not isinstance(report, dict):
        return report
    chapters = report.get("chapters")
    if not isinstance(chapters, list):
        return report
    for index, chapter in enumerate(chapters):
        if not isinstance(chapter, dict):
            continue
        title = str(chapter.get("title") or chapter.get("section_title") or "")
        if index != 9 and "行动建议" not in title and "行动计划" not in title:
            continue
        details = chapter.get("details") if isinstance(chapter.get("details"), dict) else {}
        source = None
        for field in _ACTION_FIELDS:
            candidate = chapter.get(field)
            if candidate not in (None, "", [], {}):
                source = candidate
                break
            candidate = details.get(field)
            if candidate not in (None, "", [], {}):
                source = candidate
                break
        chapter["formatted_action_steps"] = format_action_steps(source)
    return report