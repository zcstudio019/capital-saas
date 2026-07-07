import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT))
from db.database import SessionLocal
from services.reminder_service import scan_reminders
from services.worker_service import finish_worker_run,start_worker_run

if __name__=="__main__":
    with SessionLocal() as db:
        run=start_worker_run(db,"reminder_scan")
        try:
            result=scan_reminders(db);total=sum(result.values());finish_worker_run(db,run,total,total,0);print(result)
        except Exception as exc:
            finish_worker_run(db,run,error=f"{type(exc).__name__}: {exc}");raise
