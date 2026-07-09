"""Parser for Markdown bank-product libraries."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


FIELD_ALIASES = {
    "银行": "bank_name",
    "银行/机构": "bank_name",
    "机构": "bank_name",
    "机构名称": "bank_name",
    "产品名称": "product_name",
    "产品类型": "product_type",
    "贷款类型": "product_type",
    "城市": "city",
    "省份": "province",
    "额度": "amount_description",
    "最高额度": "amount_description",
    "额度说明": "amount_description",
    "金额区间": "amount_description",
    "利率": "interest_rate_range",
    "年化利率": "interest_rate_range",
    "期限": "loan_term",
    "贷款期限": "loan_term",
    "准入条件": "access_conditions_json",
    "申请条件": "access_conditions_json",
    "办理条件": "access_conditions_json",
    "申请材料": "required_documents_json",
    "所需资料": "required_documents_json",
    "还款方式": "repayment_methods",
    "担保方式": "guarantee_method",
    "需抵押": "guarantee_method",
    "产品优势": "advantages",
    "备注": "risk_notes",
    "原章节": "institution_category",
    "原分组": "product_group",
}

KNOWN_FIELDS = set(FIELD_ALIASES.values()) | {
    "product_code",
    "product_name",
    "bank_name",
    "bank_type",
    "institution_category",
    "product_group",
    "city",
    "province",
    "data_source",
}


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _numbers(text: str) -> list[float]:
    return [float(x.replace(",", "")) for x in re.findall(r"\d[\d,]*(?:\.\d+)?", text)]


def parse_amount(value: str) -> tuple[float | None, float | None]:
    """Return amounts in ten-thousand-yuan units."""
    text = _clean(value)
    values = _numbers(text)
    if not values:
        return None, None
    if "亿" in text:
        values = [v * 10000 for v in values]
    elif "元" in text and "万" not in text:
        values = [v / 10000 for v in values]
    if len(values) >= 2 and re.search(r"[-~—至到]", text):
        return min(values[:2]), max(values[:2])
    if re.search(r"起|以上|最低", text):
        return values[0], max(values[1:]) if len(values) > 1 else None
    return None, max(values)


def parse_rate(value: str) -> tuple[float | None, float | None]:
    values = _numbers(_clean(value))
    if not values:
        return None, None
    if len(values) >= 2 and re.search(r"[-~—至到]", value):
        return min(values[:2]), max(values[:2])
    if "+" in value or re.search(r"起|以上|最低", value):
        return values[0], None
    return min(values), max(values)


def parse_term(value: str) -> tuple[int | None, int | None]:
    text = _clean(value)
    range_match = re.search(r"(\d+(?:\.\d+)?)\s*[-~—至到]\s*(\d+(?:\.\d+)?)\s*(年|个月|月)", text)
    if range_match:
        factor = 12 if range_match.group(3) == "年" else 1
        return round(float(range_match.group(1)) * factor), round(float(range_match.group(2)) * factor)
    pairs = re.findall(r"(\d+(?:\.\d+)?)\s*(年|个月|月)", text)
    if not pairs:
        return None, None
    months = [round(float(number) * (12 if unit == "年" else 1)) for number, unit in pairs]
    if re.search(r"最长|最高|以内|不超过", text) and len(months) == 1:
        return None, months[0]
    if len(months) > 1:
        return min(months), max(months)
    return months[0], months[0]


def normalize_bank_product(raw: dict[str, Any]) -> dict[str, Any]:
    row: dict[str, Any] = {}
    extra: dict[str, str] = {}
    for key, value in raw.items():
        key, value = _clean(key), _clean(value)
        field = FIELD_ALIASES.get(key) or key
        if field in KNOWN_FIELDS:
            row[field] = f"{row[field]}；{value}" if row.get(field) and value else value
        elif not key.startswith("_"):
            extra[key] = value
    row["min_amount"], row["max_amount"] = parse_amount(row.get("amount_description", ""))
    row["min_rate"], row["max_rate"] = parse_rate(row.get("interest_rate_range", ""))
    row["min_term_months"], row["max_term_months"] = parse_term(row.get("loan_term", ""))
    row["extra_fields_json"] = json.dumps(extra, ensure_ascii=False)
    row["data_source"] = "imported"
    return row


def _table(block: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in block.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) >= 2 and cells[0] not in {"字段", "---"} and not set(cells[0]) <= {"-", ":"}:
            result[cells[0]] = "|".join(cells[1:]).strip()
    return result


def _markdown_table_rows(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    lines = [line.strip() for line in text.splitlines() if line.strip().startswith("|")]
    index = 0
    while index + 2 < len(lines):
        headers = [cell.strip() for cell in lines[index].strip("|").split("|")]
        separator = [cell.strip() for cell in lines[index + 1].strip("|").split("|")]
        if headers and all(set(cell) <= {"-", ":"} for cell in separator):
            index += 2
            while index < len(lines):
                cells = [cell.strip() for cell in lines[index].strip("|").split("|")]
                if len(cells) != len(headers) or all(set(cell) <= {"-", ":"} for cell in cells):
                    break
                if headers[:2] == ["字段", "内容"]:
                    break
                rows.append({headers[i]: cells[i] for i in range(len(headers))})
                index += 1
            continue
        index += 1
    return rows


def _extract_field(text: str, labels: list[str]) -> str:
    for label in labels:
        found = re.search(rf"{re.escape(label)}[：:]\s*([^|\n]+)", text)
        if found:
            return _clean(found.group(1))
    return ""


def _normalize_product_code(value: str) -> str:
    code = _clean(value).strip("[]【】")
    if code.startswith("怋OCOM"):
        return "BOCOM" + code[len("怋OCOM"):]
    if code.startswith("怌CB"):
        return "CCB" + code[len("怌CB"):]
    return code


def _numbered_markdown_products(text: str) -> list[dict[str, Any]]:
    title_re = re.compile(r"^##\s*\d+\.\s*【([^】]+)】\s*(.+?)(?=\s+-\s*机构|$)", re.M)
    matches = list(title_re.finditer(text))
    products: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        block = text[match.end():matches[index + 1].start() if index + 1 < len(matches) else len(text)]
        raw: dict[str, Any] = {
            "product_code": _normalize_product_code(match.group(1)),
            "product_name": _clean(match.group(2)),
            "bank_name": _extract_field(block, ["机构"]),
            "institution_category": _extract_field(block, ["原章节"]),
            "product_group": _extract_field(block, ["原分组"]),
        }
        raw["bank_type"] = raw.get("institution_category", "")
        raw.update(_table(block))
        product = normalize_bank_product(raw)
        product["_title"] = match.group(0).strip()
        products.append(product)
    return products


def _fallback_markdown_products(text: str) -> list[dict[str, Any]]:
    products = [normalize_bank_product(row) for row in _markdown_table_rows(text)]
    heading_re = re.compile(r"^(#{2,3})\s*(.+)$", re.M)
    matches = list(heading_re.finditer(text))
    for index, match in enumerate(matches):
        heading = _clean(match.group(2))
        if heading.startswith(("1.", "2.")):
            continue
        block = text[match.end():matches[index + 1].start() if index + 1 < len(matches) else len(text)]
        parts = re.split(r"[｜|]", heading, maxsplit=1)
        bank_name = parts[0].strip()
        product_name = parts[1].strip() if len(parts) > 1 else heading
        if match.group(1) == "###":
            bank_name = "待补充机构"
        raw = {
            "bank_name": bank_name,
            "product_name": product_name,
            "product_type": _extract_field(f"{heading}\n{block}", ["产品类型"]),
            "city": _extract_field(block, ["城市"]),
            "amount_description": _extract_field(block, ["额度", "最高额度"]),
            "interest_rate_range": _extract_field(block, ["利率"]),
            "loan_term": _extract_field(block, ["期限", "贷款期限"]),
        }
        product = normalize_bank_product(raw)
        guarantee = _extract_field(block, ["需抵押", "担保方式"])
        product["requires_collateral"] = guarantee.lower() in {"true", "yes", "1"} or guarantee.startswith("是")
        products.append(product)
    return products


def parse_markdown_bank_products(markdown_text: str | bytes | Path) -> list[dict[str, Any]]:
    if isinstance(markdown_text, Path):
        text = markdown_text.read_text(encoding="utf-8-sig")
    elif isinstance(markdown_text, bytes):
        text = markdown_text.decode("utf-8-sig")
    else:
        text = markdown_text
    numbered_products = _numbered_markdown_products(text)
    if numbered_products:
        return numbered_products
    return _fallback_markdown_products(text)
