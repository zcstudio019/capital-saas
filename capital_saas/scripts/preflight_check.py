import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db.database import SessionLocal
from services.event_service import track_event
from services.release_service import flatten_preflight, preflight_groups


def main() -> int:
    with SessionLocal() as db:
        groups = preflight_groups(db)
        rows = flatten_preflight(groups)
        print("=== Capital SaaS Preflight Check ===")
        for row in rows:
            print(f"[{row['status'].upper():7}] {row['group']} - {row['name']} :: {row['message']}")
        track_event(db, "preflight_check_run", data={"fail": sum(1 for x in rows if x["status"] == "fail"), "warning": sum(1 for x in rows if x["status"] == "warning")})
        has_fail = any(row["status"] == "fail" for row in rows)
        print("RESULT:", "FAIL" if has_fail else "PASS_WITH_WARNINGS" if any(row["status"] == "warning" for row in rows) else "PASS")
        return 1 if has_fail else 0


if __name__ == "__main__":
    sys.exit(main())
