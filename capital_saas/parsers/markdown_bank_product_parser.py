"""Markdown 银行产品库解析与字段标准化。"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


FIELD_ALIASES = {
    "bank_name": {"银行", "银行/机构", "机构名称", "bank_name"},
    "product_name": {"产品", "产品名称", "product_name"},
    "product_type": {"产品类型", "贷款类型", "product_type"},
    "city": {"城市", "city"}, "province": {"省份", "province"},
    "amount": {"额度", "最高额度", "金额区间", "max_amount"},
    "rate": {"利率", "年化利率", "rate"},
    "term": {"期限", "贷款期限", "term"},
    "access_conditions": {"准入条件", "申请条件", "access_conditions"},
    "prohibited_conditions": {"禁入条件", "prohibited_conditions"},
    "required_documents": {"所需资料", "资料清单", "required_documents"},
    "repayment_methods": {"还款方式", "repayment_methods"},
    "suitable_industry": {"适用行业", "suitable_industry"},
    "target_customer_type": {"适用客户", "target_customer_type"},
    "risk_notes": {"风险提示", "risk_notes"},
    "advantages": {"产品优势", "advantages"},
    "disadvantages": {"产品劣势", "disadvantages"},
    "suitable_scenarios": {"适合场景", "suitable_scenarios"},
    "requires_tax_normal": {"要求纳税正常", "纳税正常", "requires_tax_normal"},
    "requires_credit_normal": {"征信正常", "要求征信正常", "requires_credit_normal"},
    "requires_collateral": {"需抵押", "要求抵押", "requires_collateral"},
}
ALIAS_TO_FIELD = {alias.lower(): field for field, aliases in FIELD_ALIASES.items() for alias in aliases}


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _number(value: str) -> float | None:
    match = re.search(r"\d+(?:\.\d+)?", value.replace(",", ""))
    return float(match.group()) if match else None


def parse_amount(value: str) -> tuple[float | None, float | None]:
    """将中文额度解析为万元单位。"""
    text = _clean(value)
    numbers = [float(item) for item in re.findall(r"\d+(?:\.\d+)?", text.replace(",", ""))]
    if not numbers:
        return None, None
    factor = 1.0
    if "亿" in text:
        factor = 10_000.0
    elif "元" in text and "万" not in text:
        factor = 0.0001
    numbers = [item * factor for item in numbers]
    if len(numbers) >= 2 and re.search(r"[-~—至到]", text):
        return min(numbers[:2]), max(numbers[:2])
    if re.search(r"起|以上|最低", text):
        return numbers[0], None
    return None, numbers[-1]


def parse_rate(value: str) -> tuple[float | None, float | None]:
    text = _clean(value)
    numbers = [float(item) for item in re.findall(r"\d+(?:\.\d+)?", text)]
    if not numbers:
        return None, None
    if len(numbers) >= 2 and re.search(r"[-~—至到]", text):
        return min(numbers[:2]), max(numbers[:2])
    if re.search(r"起|以上|最低", text):
        return numbers[0], None
    return numbers[0], numbers[0]


def parse_term(value: str) -> tuple[int | None, int | None]:
    text = _clean(value)
    numbers = [float(item) for item in re.findall(r"\d+(?:\.\d+)?", text)]
    if not numbers:
        return None, None
    multiplier = 12 if "年" in text else 1
    months = [round(item * multiplier) for item in numbers]
    if len(months) >= 2 and re.search(r"[-~—至到]", text):
        return min(months[:2]), max(months[:2])
    if re.search(r"最长|以内|最高", text):
        return None, months[-1]
    if re.search(r"起|以上|最低", text):
        return months[0], None
    return months[0], months[0]


def _truthy(value: Any) -> bool:
    return _clean(value).lower() in {"是", "true", "1", "yes", "需要", "要求"}

def _title_names(title: str) -> tuple[str, str]:
    parts = re.split(r"\s+(?:-|—|–)\s+|[｜|：:]", _clean(title), maxsplit=1)
    if len(parts) == 2 and all(parts):
        return parts[0].strip(), parts[1].strip()
    return "待补充机构", _clean(title)


def normalize_bank_product(raw: dict[str, Any]) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for key, value in raw.items():
        field = ALIAS_TO_FIELD.get(_clean(key).lower(), _clean(key))
        row[field] = _clean(value)
    row.setdefault("bank_name", "待补充机构")
    row.setdefault("product_name", "")
    row.setdefault("product_type", "待补充")
    row.setdefault("city", "")
    row.setdefault("province", "")
    row["min_amount"], row["max_amount"] = parse_amount(row.get("amount", ""))
    row["min_rate"], row["max_rate"] = parse_rate(row.get("rate", ""))
    row["min_term_months"], row["max_term_months"] = parse_term(row.get("term", ""))
    conditions = "；".join(filter(None, [row.get("access_conditions", ""), row.get("prohibited_conditions", "")]))
    row["requires_tax_normal"] = _truthy(row.get("requires_tax_normal", "")) or bool(re.search(r"纳税.*(?:正常|是|要求)", conditions))
    row["requires_credit_normal"] = _truthy(row.get("requires_credit_normal", "")) or bool(re.search(r"征信.*(?:正常|是|要求)", conditions))
    collateral_text = "；".join(filter(None, [conditions, row.get("requires_collateral", "")]))
    row["requires_collateral"] = (_truthy(row.get("requires_collateral", "")) or bool(re.search(r"(?:需|要求|有)抵押", collateral_text))) and not bool(re.search(r"无抵押|免抵押", collateral_text))
    row["data_source"] = "imported"
    return row


def _parse_tables(lines: list[str]) -> list[dict[str, Any]]:
    products: list[dict[str, Any]] = []
    index = 0
    while index + 1 < len(lines):
        header, separator = lines[index], lines[index + 1]
        if "|" not in header or not re.match(r"^\s*\|?\s*:?-{3,}", separator):
            index += 1
            continue
        headers = [_clean(cell) for cell in header.strip().strip("|").split("|")]
        index += 2
        while index < len(lines) and "|" in lines[index] and lines[index].strip():
            cells = [_clean(cell) for cell in lines[index].strip().strip("|").split("|")]
            if len(cells) == len(headers):
                products.append(normalize_bank_product(dict(zip(headers, cells))))
            index += 1
    return products


def _parse_blocks(lines: list[str]) -> list[dict[str, Any]]:
    products: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in lines + ["## __END__"]:
        heading = re.match(r"^\s*#{2,3}\s+(.+?)\s*$", line)
        if heading:
            if current and current.get("product_name") and current.get("_field_count", 0):
                products.append(normalize_bank_product(current))
            title = heading.group(1)
            if title == "__END__":
                current = None
                continue
            bank, product = _title_names(title)
            current = {"bank_name": bank, "product_name": product, "_field_count": 0}
            continue
        if current:
            field = re.match(r"^\s*[-*]?\s*([^：:]+)[：:]\s*(.*?)\s*$", line)
            if field and field.group(1).strip().lower() in ALIAS_TO_FIELD:
                current[field.group(1).strip()] = field.group(2).strip()
                current["_field_count"] += 1
    return products


def parse_markdown_bank_products(file_path_or_content: str | bytes | Path) -> list[dict[str, Any]]:
    if isinstance(file_path_or_content, Path):
        text = file_path_or_content.read_text(encoding="utf-8-sig")
    elif isinstance(file_path_or_content, bytes):
        text = file_path_or_content.decode("utf-8-sig")
    else:
        candidate = Path(file_path_or_content)
        text = candidate.read_text(encoding="utf-8-sig") if "\n" not in file_path_or_content and candidate.is_file() else file_path_or_content
    lines = text.splitlines()
    rows = _parse_tables(lines) + _parse_blocks(lines)
    unique: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (row.get("bank_name", ""), row.get("product_name", ""), row.get("city", ""))
        if row.get("product_name") and key not in unique:
            unique[key] = row
    return list(unique.values())
