import base64
import hashlib
import hmac
import os
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from core.config import settings
from db.database import get_db
from db.models import User
from utils.logger import logger


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    iterations = 260_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return "pbkdf2_sha256${}${}${}".format(
        iterations,
        base64.b64encode(salt).decode(),
        base64.b64encode(digest).decode(),
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt_value, digest_value = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(salt_value)
        expected = base64.b64decode(digest_value)
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), salt, int(iterations)
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def repair_default_admin_user(db: Session, user: User | None) -> bool:
    if not user or (user.username or "").strip().lower() != "admin":
        return False
    changed = False
    if user.role not in {"admin", "super_admin"}:
        logger.warning(
            "DEFAULT_ADMIN_ROLE_REPAIR username=%s old_role=%s new_role=super_admin",
            user.username,
            user.role,
        )
        user.role = "super_admin"
        changed = True
    if not user.is_active:
        logger.warning("DEFAULT_ADMIN_ACTIVE_REPAIR username=%s", user.username)
        user.is_active = True
        changed = True
    if changed:
        user.updated_at = datetime.now()
        db.commit()
        db.refresh(user)
    return changed


def ensure_default_admin(db: Session) -> User:
    user = db.query(User).filter(User.username == settings.admin_default_username).first()
    if user:
        repair_default_admin_user(db, user)
        if settings.force_password_change and not user.password_changed_at and verify_password(settings.admin_default_password,user.password_hash):
            user.force_password_change=True;db.commit()
        return user
    user = User(
        username=settings.admin_default_username,
        password_hash=hash_password(settings.admin_default_password),
        role="admin",
        is_active=True,
        force_password_change=settings.force_password_change,
        session_version=1,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, username: str, password: str, request=None) -> User | None:
    from services.audit_service import write_audit_log
    user = db.query(User).filter(User.username == username).first()
    now=datetime.now()
    if user and user.locked_until and user.locked_until>now:
        write_audit_log(db,"login_failed","user",user.id,user_id=user.id,request=request,risk_level="high");db.commit();return None
    if not user or not user.is_active or not verify_password(password, user.password_hash):
        if user:
            user.failed_login_count=(user.failed_login_count or 0)+1
            if user.failed_login_count>=5:user.locked_until=now+timedelta(minutes=15)
        write_audit_log(db,"login_failed","user",user.id if user else None,user_id=user.id if user else None,
            request=request,risk_level="medium");db.commit()
        return None
    user.failed_login_count=0;user.locked_until=None;user.last_login_at=now
    user.last_login_ip=request.client.host if request and request.client else ""
    write_audit_log(db,"login_success","user",user.id,user_id=user.id,request=request);db.commit()
    return user


def current_user_optional(request: Request, db: Session) -> User | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    user = db.get(User, int(user_id))
    if user and (user.username or "").strip().lower() == "admin":
        repair_default_admin_user(db, user)
        request.session["role"] = user.role
    return user if user and user.is_active else None


def require_login(request: Request, db: Session = Depends(get_db)) -> User:
    user = current_user_optional(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="请先登录")
    if int(request.session.get("session_version",0)) != int(user.session_version or 1):
        request.session.clear();raise HTTPException(status_code=401,detail="会话已失效，请重新登录")
    return user


def require_roles(*allowed_roles: str):
    def dependency(user: User = Depends(require_login)) -> User:
        from core.access_scope import effective_role
        effective = effective_role(user)
        allowed = set(allowed_roles)
        if "admin" in allowed: allowed.add("super_admin")
        if effective not in allowed and user.role not in allowed:
            raise HTTPException(status_code=403, detail="没有执行此操作的权限")
        return user

    return dependency


def update_password(db: Session, user: User, new_password: str) -> None:
    user.password_hash = hash_password(new_password)
    user.updated_at = datetime.now()
    user.password_changed_at=datetime.now();user.force_password_change=False
    user.session_version=(user.session_version or 1)+1
    db.commit()
