from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy import func

from db.models import UploadedDocument
from services.event_service import track_event

ALLOWED={".pdf",".doc",".docx",".xls",".xlsx",".png",".jpg",".jpeg"}
FORBIDDEN={".exe",".bat",".cmd",".sh",".php",".jsp",".asp",".aspx",".js",".html",".htm",".svg",".com",".msi"}
MIME={".pdf":{"application/pdf","application/octet-stream"},".doc":{"application/msword","application/octet-stream"},
 ".docx":{"application/vnd.openxmlformats-officedocument.wordprocessingml.document","application/zip","application/octet-stream"},
 ".xls":{"application/vnd.ms-excel","application/octet-stream"},".xlsx":{"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet","application/zip","application/octet-stream"},
 ".png":{"image/png","application/octet-stream"},".jpg":{"image/jpeg","application/octet-stream"},".jpeg":{"image/jpeg","application/octet-stream"}}

def validate_upload_metadata(upload:UploadFile):
    raw=upload.filename or "";safe=Path(raw).name;ext=Path(safe).suffix.lower()
    if not safe or safe!=raw or ".." in raw or "/" in raw or "\\" in raw:raise HTTPException(400,"文件名不安全，禁止路径字符")
    if ext in FORBIDDEN or ext not in ALLOWED:raise HTTPException(400,f"禁止上传此文件类型：{ext or '未知'}")
    content_type=(upload.content_type or "application/octet-stream").split(";",1)[0].lower()
    if content_type not in MIME.get(ext,{"application/octet-stream"}):raise HTTPException(400,f"文件MIME类型与扩展名不匹配：{content_type}")
    return safe,ext
def enforce_lead_total(db,lead_id:int,new_bytes:int,max_total_mb:int):
    used=db.query(func.coalesce(func.sum(UploadedDocument.file_size),0)).filter(UploadedDocument.lead_id==lead_id,UploadedDocument.deleted_at.is_(None)).scalar() or 0
    if used+new_bytes>max_total_mb*1024*1024:raise HTTPException(400,f"该客户资料总量超过{max_total_mb}MB限制")
def audit_rejection(db,assessment_id,lead_id,reason):
    track_event(db,"file_security_rejected",assessment_id,lead_id,{"reason":reason})
