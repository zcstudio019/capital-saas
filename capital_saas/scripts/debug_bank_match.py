from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.bank_product_matcher import match_bank_products
from db.database import SessionLocal
from db.models import Assessment


def main() -> None:
    parser = argparse.ArgumentParser(description="调试银行产品动态匹配结果")
    parser.add_argument("--assessment-id", type=int, required=True)
    args = parser.parse_args()

    with SessionLocal() as db:
        assessment = db.get(Assessment, args.assessment_id)
        if not assessment:
            raise SystemExit(f"assessment_id={args.assessment_id} 不存在")

        result = match_bank_products(db, assessment, include_debug=True)
        payload = {
            "assessment_id": assessment.id,
            "customer_profile": result.get("customer_profile", {}),
            "final_recommendations": [
                {
                    "product_id": item.get("product_id"),
                    "bank_name": item.get("bank_name"),
                    "product_name": item.get("product_name"),
                    "match_score": item.get("match_score"),
                    "match_level": item.get("match_level"),
                    "recommendation_reason": item.get("recommendation_reason"),
                    "matched_points": item.get("matched_points"),
                    "risk_points": item.get("risk_points"),
                    "missing_requirements": item.get("missing_requirements"),
                    "suggested_next_step": item.get("suggested_next_step"),
                }
                for item in result.get("matched_products", [])
            ],
            "candidate_score_details": [
                {
                    "product_id": item.get("product_id"),
                    "product_name": item.get("product_name"),
                    "data_source": item.get("data_source"),
                    "match_score": item.get("match_score"),
                    "match_level": item.get("match_level"),
                    "eliminated": item.get("eliminated"),
                    "eliminated_reason": item.get("eliminated_reason"),
                    "debug_scores": item.get("debug_scores"),
                    "risk_points": item.get("risk_points"),
                }
                for item in result.get("candidate_products", [])
            ],
            "fallback_notice": result.get("fallback_notice", ""),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        print("BANK_MATCH_DEBUG_OK")


if __name__ == "__main__":
    main()
