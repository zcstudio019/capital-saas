from datetime import datetime
from sqlalchemy.orm import Session
from db.models import WorkerRun

def start_worker_run(db:Session,name:str)->WorkerRun:
    item=WorkerRun(worker_name=name,run_status="running",started_at=datetime.now());db.add(item);db.commit();db.refresh(item);return item
def finish_worker_run(db:Session,item:WorkerRun,processed=0,success=0,failed=0,error=""):
    item.run_status="failed" if error else "success";item.finished_at=datetime.now();item.processed_count=processed;item.success_count=success;item.failed_count=failed;item.error_message=error;db.commit();return item
