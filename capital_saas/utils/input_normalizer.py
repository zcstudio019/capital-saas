"""客户输入的统一数值清洗工具。

空值与数值 0 必须保持不同语义；非法内容必须显式报错，不能降级为 0。
"""

from __future__ import annotations

from typing import Any


class InputNormalizationError(ValueError):
    """可直接展示给客户的输入校验错误。"""


def _numeric_text(value: Any, field_name: str, *, allow_percent: bool = False) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise InputNormalizationError(f"{field_name}请输入数字")
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return None
        if allow_percent and normalized.endswith("%"):
            normalized = normalized[:-1].strip()
        if not normalized:
            return None
        return normalized
    return str(value)


def normalize_optional_float(value: Any, field_name: str = "该字段") -> float | None:
    normalized = _numeric_text(value, field_name)
    if normalized is None:
        return None
    try:
        number = float(normalized)
    except (TypeError, ValueError) as exc:
        raise InputNormalizationError(f"{field_name}请输入数字") from exc
    if number != number or number in {float("inf"), float("-inf")}:
        raise InputNormalizationError(f"{field_name}请输入有效数字")
    return number


def normalize_required_float(value: Any, field_name: str) -> float:
    number = normalize_optional_float(value, field_name)
    if number is None:
        raise InputNormalizationError(f"请输入{field_name}")
    return number


def normalize_optional_int(value: Any, field_name: str = "该字段") -> int | None:
    number = normalize_optional_float(value, field_name)
    if number is None:
        return None
    if not number.is_integer():
        raise InputNormalizationError(f"{field_name}请输入整数")
    return int(number)


def normalize_optional_percentage(value: Any, field_name: str = "该比例") -> float | None:
    normalized = _numeric_text(value, field_name, allow_percent=True)
    if normalized is None:
        return None
    try:
        number = float(normalized)
    except (TypeError, ValueError) as exc:
        raise InputNormalizationError(f"{field_name}请输入数字") from exc
    if number != number or number in {float("inf"), float("-inf")}:
        raise InputNormalizationError(f"{field_name}请输入有效数字")
    return number
