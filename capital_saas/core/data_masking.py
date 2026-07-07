import re


def mask_phone(value:str|None)->str:
    value=value or "";return f"{value[:3]}****{value[-4:]}" if len(value)>=7 else "****"
def mask_identity(value:str|None)->str:
    value=value or "";return f"{value[:4]}{'*'*max(4,len(value)-8)}{value[-4:]}" if len(value)>8 else "****"
def mask_bank_account(value:str|None)->str:
    value=value or "";return f"**** **** **** {value[-4:]}" if len(value)>=4 else "****"
def mask_email(value:str|None)->str:
    value=value or ""
    if "@" not in value:return "***"
    name,domain=value.split("@",1);return f"{name[:1]}***@{domain}"
def mask_wechat(value:str|None)->str:
    value=value or "";return f"{value[:2]}***{value[-2:]}" if len(value)>4 else "****"
def can_view_full_contact(user,lead=None)->bool:
    role="super_admin" if getattr(user,"role","")=="admin" else getattr(user,"role","")
    if role=="super_admin":return True
    if role=="sales" and lead and lead.owner_user_id==user.id:return True
    return role in {"city_manager","sales_manager","consultant_manager","consultant"}
