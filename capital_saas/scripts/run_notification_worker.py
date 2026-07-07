import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT))
from db.database import SessionLocal
from services.notification_service import retry_failed_jobs
from services.worker_service import finish_worker_run,start_worker_run

if __name__=="__main__":
    with SessionLocal() as db:
        run=start_worker_run(db,"notification_worker")
        try:
            jobs=retry_failed_jobs(db);success=sum(x.send_status=="success" for x in jobs);failed=sum(x.send_status=="failed" for x in jobs)
            finish_worker_run(db,run,len(jobs),success,failed);print({"processed":len(jobs),"success":success,"failed":failed})
        except Exception as exc:
            finish_worker_run(db,run,error=f"{type(exc).__name__}: {exc}");raise
