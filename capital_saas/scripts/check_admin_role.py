import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db.database import Base, SessionLocal, engine
from db.migrations import migrate_database
from db.models import User
from services.auth_service import ensure_default_admin, repair_default_admin_user


def main() -> None:
    Base.metadata.create_all(bind=engine)
    migrate_database()
    with SessionLocal() as db:
        admin = db.query(User).filter(User.username == "admin").first()
        if not admin:
            admin = ensure_default_admin(db)
        else:
            repair_default_admin_user(db, admin)
        db.refresh(admin)
        errors: list[str] = []
        if admin.role not in {"admin", "super_admin"}:
            errors.append(f"admin.role={admin.role}")
        if not admin.is_active:
            errors.append("admin.is_active=false")
        if errors:
            raise SystemExit("ADMIN_ROLE_ERROR " + ", ".join(errors))
    print("ADMIN_ROLE_OK")


if __name__ == "__main__":
    main()
