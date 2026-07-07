import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT))
from db.database import SessionLocal
from services.backup_service import create_database_backup,delete_expired_backups
from services.event_service import track_event
from services.worker_service import finish_worker_run,start_worker_run

if __name__=="__main__":
    with SessionLocal() as db:
        run=start_worker_run(db,"daily_backup")
        try:
            result=create_database_backup();deleted=delete_expired_backups();track_event(db,"daily_backup_run",data={"file":result["name"],"deleted":deleted});finish_worker_run(db,run,1,1,0);print({"backup":result["name"],"sha256":result["sha256"],"expired_deleted":deleted})
        except Exception as exc:
            finish_worker_run(db,run,error=f"{type(exc).__name__}: {exc}");raise
