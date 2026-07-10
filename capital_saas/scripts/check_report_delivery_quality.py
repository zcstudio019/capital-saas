"""Scan recently generated customer reports for delivery-quality violations."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db.database import SessionLocal
from db.models import Report
from services.report_service import parse_customer_report
from utils.report_render_formatter import validate_report_for_delivery


def main() -> int:
    parser = argparse.ArgumentParser(description="检查最近生成的客户报告交付质量")
    parser.add_argument("--limit", type=int, default=20, help="检查最近报告数量")
    args = parser.parse_args()

    failures: list[tuple[int, list[str]]] = []
    with SessionLocal() as db:
        reports = (
            db.query(Report)
            .filter(Report.full_report_json.is_not(None))
            .order_by(Report.created_at.desc())
            .limit(max(args.limit, 1))
            .all()
        )
        for report in reports:
            content = report.html_content or parse_customer_report(report) or {}
            validation = validate_report_for_delivery(content)
            if not validation["valid"]:
                failures.append((report.id, validation["issues"]))

    if failures:
        for report_id, issues in failures:
            print(f"REPORT_DELIVERY_QUALITY_FAILED report_id={report_id} issues={'；'.join(issues)}")
        return 1
    print("REPORT_DELIVERY_QUALITY_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
