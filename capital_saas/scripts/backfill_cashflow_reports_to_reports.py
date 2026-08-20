"""Idempotently expose historical cashflow reports in the unified report center."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.database import SessionLocal
from services.cashflow_service import backfill_unified_cashflow_reports

with SessionLocal() as db:
    stats=backfill_unified_cashflow_reports(db)
print(stats)
if stats["errors"]:
    raise SystemExit(1)
print("CASHFLOW_REPORT_BACKFILL_OK")
