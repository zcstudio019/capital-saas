"""Parser for the structured Markdown bank-product library."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

TITLE_RE = re.compile(r"^##\s*\d+\.\s*【([^】]+)】\s*(.+?)\s*$", re.M)

FIELD_MAP = {
    "贷款类型": "product_type", "担保方式": "guarantee_method",
    "利率": "interest_rate_range", "最高额度": "amount_description", "额度说明": "amount_description",
    "期限": "loan_term", "贷款期限": "loan_term", "贷款授信最长期限": "loan_term",
    "还款方式": "repayment_methods", "操作流程": "application_process", "申请入口": "application_process",
    "准入条件": "access_conditions_json", "申请条件": "access_conditions_json", "办理条件": "access_conditions_json",
    "公司要求": "company_requirements", "企业要求": "company_requirements",
    "担保人要求": "guarantor_requirements", "申请人要求": "borrower_requirements", "个人要求": "borrower_requirements",
    "征信要求": "credit_requirements", "纳税要求": "tax_requirements", "开票要求": "invoice_requirements",
    "流水要求": "cashflow_requirements", "收入要求": "revenue_requirements",
    "营业执照要求": "business_license_requirements", "禁入行业": "prohibited_conditions_json",
    "准入行业": "suitable_industry", "重点支持行业": "suitable_industry",
    "适用对象": "target_customer_type", "目标客户": "target_customer_type", "适合客户": "suitable_scenarios",
    "申请材料": "required_documents_json", "进件材料": "required_documents_json", "前期初审材料": "required_documents_json",
    "产品优势": "advantages", "特殊优势及备注": "advantages", "经验总结": "risk_notes", "备注": "risk_notes",
}

CSV_ALIASES = {
    "银行": "bank_name", "银行/机构": "bank_name", "机构名称": "bank_name", "产品名称": "product_name",
    "产品类型": "product_type", "贷款类型": "product_type", "城市": "city", "省份": "province",
    "额度": "amount_description", "最高额度": "amount_description", "金额区间": "amount_description",
    "利率": "interest_rate_range", "年化利率": "interest_rate_range", "期限": "loan_term", "贷款期限": "loan_term",
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
    # Product libraries normally express limits in 万; support explicit 元/亿 too.
    factor = 10000 if "亿" in text else (0.0001 if "元" in text and "万" not in text else 1)
    values = [v * factor for v in values]
    if len(values) == 2 and re.search(r"\d\s*(?:万)?\s*[-~—至到]\s*\d", text):
        return min(values), max(values)
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
    pairs = re.findall(r"(\d+(?:\.\d+)?)\s*(年|个月|月)", text)
    if not pairs:
        return None, None
    months = [round(float(n) * (12 if unit == "年" else 1)) for n, unit in pairs]
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
        field = FIELD_MAP.get(key) or CSV_ALIASES.get(key) or key
        if field in FIELD_MAP.values() or field in {"product_code", "product_name", "bank_name", "bank_type", "institution_category", "product_group", "city", "province", "data_source"}:
            if row.get(field) and value:
                row[field] += "；" + value
            else:
                row[field] = value
        elif not key.startswith("_"):
            extra[key] = value
    amount_text = row.get("amount_description", "")
    row["min_amount"], row["max_amount"] = parse_amount(amount_text)
    row["min_rate"], row["max_rate"] = parse_rate(row.get("interest_rate_range", ""))
    row["min_term_months"], row["max_term_months"] = parse_term(row.get("loan_term", ""))
    row["extra_fields_json"] = json.dumps(extra, ensure_ascii=False)
    row["data_source"] = "imported"
    return row

def _table(block: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in block.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 2 and cells[0] not in {"字段", "---"} and not set(cells[0]) <= {"-", ":"}:
            result[cells[0]] = "|".join(cells[1:]).strip()
    return result

def parse_markdown_bank_products(markdown_text: str | bytes | Path) -> list[dict[str, Any]]:
    if isinstance(markdown_text, Path):
        text = markdown_text.read_text(encoding="utf-8-sig")
    elif isinstance(markdown_text, bytes):
        text = markdown_text.decode("utf-8-sig")
    else:
        text = markdown_text
    matches = list(TITLE_RE.finditer(text))
    products: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        block = text[match.end():matches[index + 1].start() if index + 1 < len(matches) else len(text)]
        raw: dict[str, Any] = {"product_code": match.group(1).strip(), "product_name": match.group(2).strip(), "_title": match.group(0).strip()}
        for label, field in (("机构", "bank_name"), ("原章节", "institution_category"), ("原分组", "product_group")):
            found = re.search(rf"^\s*-\s*{label}\s*[：:]\s*(.+?)\s*$", block, re.M)
            if found:
                raw[field] = found.group(1).strip()
        raw["bank_type"] = raw.get("institution_category", "")
        raw.update(_table(block))
        product = normalize_bank_product(raw)
        product["_title"] = raw["_title"]
        products.append(product)
    return products
