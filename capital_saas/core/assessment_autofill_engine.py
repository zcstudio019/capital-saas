import json
import re
from typing import Any


FINANCIAL_MAP = {
    "annual_revenue": "annual_revenue",
    "net_profit": "net_profit",
    "monthly_cashflow": "monthly_cashflow",
    "debt_total": "debt_total",
    "short_debt": "short_debt",
    "receivable_days": "receivable_days",
}


def build_autofill_suggestions(assessment: Any, documents: list[Any]) -> dict:
    candidates: dict[str, list[dict]] = {}
    for document in documents:
        try:
            parsed = json.loads(document.parsed_json or "{}")
        except json.JSONDecodeError:
            continue
        fields = parsed.get("financial_fields", {})
        for source_key, target_key in FINANCIAL_MAP.items():
            if source_key in fields:
                candidates.setdefault(target_key, []).append({
                    "value": fields[source_key], "source": document.file_name,
                    "confidence": 0.9 if document.verify_status == "verified" else 0.82,
                })
        text = json.dumps(parsed, ensure_ascii=False)
        category = document.document_category
        if "纳税" in category:
            candidates.setdefault("tax_status", []).append({"value": True, "source": document.file_name, "confidence": 0.72})
        if "征信" in category:
            candidates.setdefault("credit_status", []).append({"value": True, "source": document.file_name, "confidence": 0.65})
        if "抵押" in category or any(term in text for term in ["房产证", "产权证明"]):
            candidates.setdefault("has_collateral", []).append({"value": True, "source": document.file_name, "confidence": 0.75})
        purpose = re.search(r"融资用途[：:]\s*([^，。\n]{2,100})", text)
        if purpose:
            candidates.setdefault("funding_purpose", []).append({"value": purpose.group(1), "source": document.file_name, "confidence": 0.7})
    suggestions = {}
    conflicts = []
    for field, values in candidates.items():
        distinct = {str(item["value"]) for item in values}
        if len(distinct) > 1:
            conflicts.append({"field": field, "values": list(distinct), "sources": [x["source"] for x in values]})
        best = max(values, key=lambda item: item["confidence"])
        old = getattr(assessment, field)
        if str(old) != str(best["value"]):
            suggestions[field] = {
                "old_value": old, "new_value": best["value"],
                "confidence": best["confidence"], "source_document": best["source"],
            }
    return {
        "suggested_updates": suggestions,
        "conflicts": conflicts,
        "need_manual_review": bool(suggestions or conflicts),
    }
