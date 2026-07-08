import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from services.report_access_service import (
    build_bank_match_full,
    build_bank_match_preview,
    build_document_execution_plan,
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


def test_document_checklist_preview_and_full_structure():
    preview = build_document_checklist_preview()
    full = build_document_checklist_full({})
    assert preview["preview_only"] is True
    assert len(preview["preview_cards"]) == 3
    assert preview["preview_cards"][0]["items"] == ["营业执照", "法人/实控人身份证明", "公司基本工商信息"]
    assert "30/90/180天执行计划" in preview["hidden_items"]
    assert full["preview_only"] is False
    assert len(full["required_documents"]) >= 8
    assert full["required_documents"][0]["category"] == "企业基础资料"
    assert full["required_documents"][0]["purpose"]
    assert full["required_documents"][0]["priority"] == "高"
    assert len(full["required_documents"][0]["items"]) >= 6
    assert full["required_documents"][0]["missing_risk"]
    assert len(full["execution_plan"]) == 3
    assert full["execution_plan"][0]["period"] == "30天执行计划"
    assert full["execution_plan"][0]["goal"]
    assert full["execution_plan"][0]["actions"]
    assert full["execution_plan"][0]["owner"]
    assert full["execution_plan"][0]["deliverable"]


def test_document_execution_plan_reuses_structure_plan():
    plan = build_document_execution_plan(
        {
            "structure_plan": {
                "stage_1_30_days": ["统一资料口径", "完成银行预匹配"],
                "stage_2_90_days": ["提交核心授信", "复核现金流"],
                "stage_3_180_days": ["建立续贷资料台账"],
            }
        },
        {},
    )
    assert [item["period"] for item in plan] == ["30天执行计划", "90天执行计划", "180天执行计划"]
    assert plan[0]["actions"] == ["统一资料口径", "完成银行预匹配"]


if __name__ == "__main__":
    test_paid_unlock_rules()
    test_bank_match_preview_is_one_clickable_product()
    test_document_checklist_preview_and_full_structure()
    test_document_execution_plan_reuses_structure_plan()
    print("PHASE_PAID_UNLOCK_OK")
