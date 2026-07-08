"""CSV、Excel、Markdown 银行产品导入服务。"""
from __future__ import annotations
import csv
import io
from pathlib import Path
from typing import Any
from openpyxl import load_workbook
from sqlalchemy.orm import Session
from db.models import BankProduct
from parsers.markdown_bank_product_parser import normalize_bank_product, parse_markdown_bank_products


def parse_bank_product_file(filename: str, content: bytes) -> list[dict[str, Any]]:
    suffix = Path(filename).suffix.lower()
    if suffix == ".md":
        return parse_markdown_bank_products(content)
    if suffix == ".csv":
        return [normalize_bank_product(row) for row in csv.DictReader(io.StringIO(content.decode("utf-8-sig")))]
    if suffix == ".xlsx":
        sheet = load_workbook(io.BytesIO(content), read_only=True, data_only=True).active
        values = sheet.iter_rows(values_only=True)
        headers = [str(value or "").strip() for value in next(values, [])]
        return [normalize_bank_product(dict(zip(headers, row))) for row in values if any(value is not None for value in row)]
    raise ValueError("仅支持 CSV、Excel（.xlsx）或 Markdown（.md）文件")


def validate_bank_product(row: dict[str, Any], row_number: int) -> str | None:
    if not row.get("product_name"):
        return f"第{row_number}条缺少产品名称"
    if not row.get("bank_name"):
        return f"第{row_number}条缺少银行或机构名称"
    return None


def import_bank_products(db: Session, rows: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {"parsed": len(rows), "success": 0, "failed": 0, "errors": []}
    seen: set[tuple[str, str, str]] = set()
    for index, row in enumerate(rows, 1):
        key = (row.get("bank_name", ""), row.get("product_name", ""), row.get("city", ""))
        error = validate_bank_product(row, index)
        if key in seen:
            error = f"第{index}条与本次文件内产品重复"
        seen.add(key)
        if error:
            result["failed"] += 1
            result["errors"].append(error)
            continue
        item = db.query(BankProduct).filter_by(bank_name=key[0], product_name=key[1], city=key[2]).first()
        if item is None:
            item = BankProduct()
            db.add(item)
        try:
            values = {
                "bank_name": key[0], "product_name": key[1], "city": key[2],
                "province": row.get("province", ""), "bank_type": row.get("bank_type", "银行") or "银行",
                "product_type": row.get("product_type", "待补充") or "待补充",
                "suitable_industry": row.get("suitable_industry", "通用") or "通用",
                "min_amount": (row.get("min_amount") or 0) * 10_000,
                "max_amount": (row.get("max_amount") or 0) * 10_000,
                "min_rate": row.get("min_rate"), "max_rate": row.get("max_rate"),
                "min_term_months": row.get("min_term_months"), "max_term_months": row.get("max_term_months"),
                "interest_rate_range": row.get("rate", "") or "以审批为准",
                "loan_term": row.get("term", "") or "以审批为准",
                "application_requirements": "；".join(filter(None, [row.get("access_conditions", ""), row.get("prohibited_conditions", "")])),
                "required_documents": row.get("required_documents", ""), "repayment_methods": row.get("repayment_methods", ""),
                "target_customer_type": row.get("target_customer_type", ""), "risk_notes": row.get("risk_notes", ""),
                "advantages": row.get("advantages", ""), "disadvantages": row.get("disadvantages", ""),
                "suitable_scenarios": row.get("suitable_scenarios", ""),
                "requires_tax_normal": bool(row.get("requires_tax_normal")),
                "requires_credit_normal": bool(row.get("requires_credit_normal")),
                "requires_collateral": bool(row.get("requires_collateral")),
                "data_source": "imported", "is_active": True,
            }
            for field, value in values.items():
                setattr(item, field, value)
            result["success"] += 1
        except Exception as exc:
            result["failed"] += 1
            result["errors"].append(f"第{index}条导入失败：{exc}")
    if result["success"]:
        db.commit()
    else:
        db.rollback()
    return result