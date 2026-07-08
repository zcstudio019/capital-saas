import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))

from services.report_access_service import (
    build_bank_match_full,
    build_bank_match_preview,
    build_document_checklist_full,
    build_document_checklist_preview,
    can_view_full_bank_match,
    can_view_full_bank_product_detail,
    can_view_full_document_checklist,
)


def test_paid_unlock_rules():
    assert not can_view_full_bank_match(["299_report"])
    assert not can_view_full_document_checklist(["299_report"])
    assert can_view_full_bank_match(["699_bank_match"])
    assert can_view_full_bank_product_detail(["699_bank_match"])
    assert not can_view_full_document_checklist(["699_bank_match"])
    assert can_view_full_bank_match(["1999_structure_plan"])
    assert can_view_full_bank_product_detail(["1999_structure_plan"])
    assert can_view_full_document_checklist(["1999_structure_plan"])


def test_bank_match_preview_is_one_clickable_product():
    matches = {
        "matched_products": [
            {
                "product_id": 1,
                "product_name": "普惠e贷1.0",
                "match_score": 91,
                "reason": "收入、年限、征信均满足基础准入",
                "risk_notes": "需进一步核验纳税与流水",
            },
            {
                "product_id": 2,
                "product_name": "建设银行善营贷",
                "match_score": 86,
                "reason": "经营年限较好",
            },
        ]
    }
    preview = build_bank_match_preview(matches, "/report/7")
    full = build_bank_match_full(matches, "/report/7")
    assert preview["preview_only"] is True
    assert len(preview["matched_products"]) == 1
    assert preview["matched_products"][0]["detail_url"] == "/report/7/bank-products/1"
    assert len(full["matched_products"]) == 2


def test_document_checklist_preview_hides_children():
    checklist = {
        "required_documents": [
            {"category": "企业基础资料", "items": ["营业执照", "公司章程"]},
            {"category": "财务资料", "items": ["近1年财务报表"]},
        ],
        "missing_risk": ["流水缺失会影响审批"],
        "preparation_priority": ["P0：先补基础资料"],
    }
    assessment = SimpleNamespace(has_collateral=True)
    preview = build_document_checklist_preview(checklist, assessment)
    full = build_document_checklist_full(checklist)
    assert preview["preview_only"] is True
    assert any(item["category"] == "抵押物资料" for item in preview["required_documents"])
    assert all(not item["items"] for item in preview["required_documents"])
    assert full["required_documents"][0]["items"] == ["营业执照", "公司章程"]


if __name__ == "__main__":
    test_paid_unlock_rules()
    test_bank_match_preview_is_one_clickable_product()
    test_document_checklist_preview_hides_children()
    print("PHASE_PAID_UNLOCK_OK")
