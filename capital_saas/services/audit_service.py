import json

from sqlalchemy.orm import Session

from db.models import AuditLog
from services.event_service import track_event


def write_audit_log(db:Session,action:str,target_type:str="",target_id:int|None=None,
    user_id:int|None=None,customer_id:int|None=None,actor_type:str="admin_user",
    before:dict|None=None,after:dict|None=None,request=None,risk_level:str="low",
    commit:bool=False)->AuditLog:
    item=AuditLog(user_id=user_id,customer_id=customer_id,actor_type=actor_type,action=action,
        target_type=target_type,target_id=target_id,before_json=json.dumps(before or {},ensure_ascii=False),
        after_json=json.dumps(after or {},ensure_ascii=False),ip_address=(request.client.host if request and request.client else ""),
        user_agent=(request.headers.get("user-agent","")[:500] if request else ""),risk_level=risk_level)
    db.add(item);db.flush();track_event(db,"audit_log_created",data={"audit_id":item.id,"action":action,
        "risk_level":risk_level},commit=False)
    if commit:db.commit();db.refresh(item)
    return item
