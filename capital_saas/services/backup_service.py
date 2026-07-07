import hashlib
import shutil
import sqlite3
from datetime import datetime,timedelta
from pathlib import Path

from core.config import BASE_DIR,settings
from db.database import engine

BACKUP_DIR=BASE_DIR/"data"/"backups"
def file_hash(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):h.update(chunk)
    return h.hexdigest()
def create_database_backup()->dict:
    BACKUP_DIR.mkdir(parents=True,exist_ok=True);source=Path(engine.url.database).resolve()
    if not source.exists():raise FileNotFoundError("SQLite数据库不存在")
    target=BACKUP_DIR/f"capital_saas_{datetime.now():%Y%m%d_%H%M%S}.db"
    src=sqlite3.connect(str(source));dst=sqlite3.connect(str(target))
    try:src.backup(dst)
    finally:dst.close();src.close()
    return {"path":target,"name":target.name,"size":target.stat().st_size,"sha256":file_hash(target)}
def list_backups():
    BACKUP_DIR.mkdir(parents=True,exist_ok=True)
    return [{"path":p,"name":p.name,"size":p.stat().st_size,"created_at":datetime.fromtimestamp(p.stat().st_mtime),"sha256":file_hash(p)} for p in sorted(BACKUP_DIR.glob("*.db"),key=lambda x:x.stat().st_mtime,reverse=True)]
def delete_expired_backups(days:int|None=None)->int:
    cutoff=datetime.now()-timedelta(days=days or settings.backup_retention_days);count=0
    for item in list_backups():
        if item["created_at"]<cutoff:item["path"].unlink();count+=1
    return count
def safe_backup_path(name:str)->Path:
    path=(BACKUP_DIR/Path(name).name).resolve()
    if path.parent!=BACKUP_DIR.resolve() or not path.exists():raise FileNotFoundError("备份不存在")
    return path
