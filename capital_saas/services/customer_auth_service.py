from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta

from fastapi import Request
from sqlalchemy.orm import Session

from db.models import CustomerAccount, CustomerSession
from services.auth_service import hash_password, verify_password
from services.customer_phone_service import normalize_phone


CUSTOMER_REMEMBER_COOKIE = "capital_customer_remember"


def normalize_login_phone(value: str | None) -> str:
    return normalize_phone(value) or ""


def customer_can_login(customer: CustomerAccount | None) -> bool:
    return bool(
        customer
        and not customer.deleted_at
        and customer.is_active
        and customer.status == "active"
        and customer.password_hash
        and (not customer.locked_until or customer.locked_until <= datetime.now())
    )


def set_customer_password(db: Session, customer: CustomerAccount, password: str) -> None:
    if len(password) < 8:
        raise ValueError("密码至少需要8位")
    customer.password_hash = hash_password(password)
    customer.password_changed_at = datetime.now()
    customer.activated_at = customer.activated_at or datetime.now()
    if customer.status in {"locked", "pending_activation"}:
        customer.status = "active"
    customer.failed_login_count = 0
    customer.locked_until = None
    customer.client_login_method = "password"
    db.query(CustomerSession).filter(
        CustomerSession.customer_id == customer.id,
        CustomerSession.revoked_at.is_(None),
    ).update({"revoked_at": datetime.now()}, synchronize_session=False)


def authenticate_customer(db: Session, phone: str, password: str) -> CustomerAccount | None:
    normalized = normalize_login_phone(phone)
    customer = db.query(CustomerAccount).filter(CustomerAccount.login_phone == normalized).first()
    if not customer and normalized:
        customer = next((item for item in db.query(CustomerAccount).all()
                         if normalize_phone(item.login_phone or item.phone) == normalized), None)
    if not customer or customer.deleted_at or not customer.password_hash:
        return None
    if customer.status == "disabled" or not customer.is_active:
        return None
    if customer.locked_until and customer.locked_until > datetime.now():
        return None
    if customer.status == "locked":
        customer.status = "active"
    if not verify_password(password, customer.password_hash):
        customer.failed_login_count = (customer.failed_login_count or 0) + 1
        if customer.failed_login_count >= 5:
            customer.locked_until = datetime.now() + timedelta(minutes=30)
            customer.status = "locked"
        db.commit()
        return None
    customer.failed_login_count = 0
    customer.locked_until = None
    customer.status = "active"
    customer.last_login_at = datetime.now()
    db.commit()
    db.refresh(customer)
    return customer


def create_customer_session(db: Session, customer: CustomerAccount, remember_me: bool) -> str:
    raw_token = secrets.token_urlsafe(48)
    expires = datetime.now() + (timedelta(days=30) if remember_me else timedelta(hours=12))
    db.add(CustomerSession(
        customer_id=customer.id,
        token_hash=hashlib.sha256(raw_token.encode()).hexdigest(),
        remember_me=remember_me,
        expired_at=expires,
    ))
    db.commit()
    return raw_token


def customer_from_remember_cookie(request: Request, db: Session) -> CustomerAccount | None:
    raw_token = request.cookies.get(CUSTOMER_REMEMBER_COOKIE, "")
    if not raw_token:
        return None
    item = db.query(CustomerSession).filter(
        CustomerSession.token_hash == hashlib.sha256(raw_token.encode()).hexdigest(),
        CustomerSession.revoked_at.is_(None),
        CustomerSession.expired_at > datetime.now(),
    ).first()
    if not item:
        return None
    customer = db.get(CustomerAccount, item.customer_id)
    if not customer or not customer_can_login(customer):
        return None
    item.last_used_at = datetime.now()
    request.session["customer_id"] = customer.id
    request.session["customer_authenticated"] = True
    db.commit()
    return customer


def revoke_customer_session(request: Request, db: Session) -> None:
    raw_token = request.cookies.get(CUSTOMER_REMEMBER_COOKIE, "")
    if raw_token:
        item = db.query(CustomerSession).filter(
            CustomerSession.token_hash == hashlib.sha256(raw_token.encode()).hexdigest(),
            CustomerSession.revoked_at.is_(None),
        ).first()
        if item:
            item.revoked_at = datetime.now()
            db.commit()
