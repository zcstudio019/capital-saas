"""Create/link customer accounts for historical assessments without deleting data."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from db.database import Base, SessionLocal, engine
from db.migrations import migrate_database
from db import models  # noqa: F401 - register every mapped table before create_all
from db.models import CustomerAccount, Report
from services.customer_portal_service import backfill_customer_account_links


def main() -> None:
    Base.metadata.create_all(bind=engine)
    migrate_database()
    with SessionLocal() as db:
        changed = backfill_customer_account_links(db)
        accounts = db.query(CustomerAccount).count()
        linked_reports = db.query(Report).filter(Report.customer_id.isnot(None)).count()
    print(f"CUSTOMER_ACCOUNT_BACKFILL_OK accounts={accounts} linked_reports={linked_reports} changed={changed}")


if __name__ == "__main__":
    main()
