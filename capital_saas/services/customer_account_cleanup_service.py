from __future__ import annotations

from datetime import datetime

from sqlalchemy import or_
from sqlalchemy.orm import Session

from core.data_masking import mask_phone
from db.models import (
    AdvisorBooking,
    Assessment,
    AuditLog,
    CustomerAccessToken,
    CustomerAccount,
    CustomerConfirmation,
    CustomerFeedback,
    CustomerMessage,
    CustomerSession,
    CustomerTask,
    FinancingProject,
    Lead,
    LegalAcceptance,
    NotificationJob,
    NotificationPreference,
    OperationIssue,
    Order,
    Report,
    UploadedDocument,
    User,
)
from services.audit_service import write_audit_log


def _count(db: Session, model, criterion) -> int:
    return db.query(model).filter(criterion).count()


def customer_dependency_counts(db: Session, customer: CustomerAccount) -> dict[str, int]:
    """Count business records without changing their historical customer_id links."""
    customer_id = customer.id
    assessment_filter = Assessment.customer_id == customer_id
    if customer.assessment_id:
        assessment_filter = or_(assessment_filter, Assessment.id == customer.assessment_id)
    lead_filter = Lead.customer_id == customer_id
    if customer.lead_id:
        lead_filter = or_(lead_filter, Lead.id == customer.lead_id)

    counts = {
        "reports": _count(db, Report, Report.customer_id == customer_id),
        "orders": _count(db, Order, Order.customer_id == customer_id),
        "assessments": _count(db, Assessment, assessment_filter),
        "leads": _count(db, Lead, lead_filter),
        "documents": _count(db, UploadedDocument, UploadedDocument.customer_id == customer_id),
        "bookings": _count(db, AdvisorBooking, AdvisorBooking.customer_id == customer_id),
        "projects": _count(db, FinancingProject, FinancingProject.customer_id == customer_id),
        "messages": _count(db, CustomerMessage, CustomerMessage.customer_id == customer_id),
        "tasks": _count(db, CustomerTask, CustomerTask.customer_id == customer_id),
        "notifications": _count(db, NotificationJob, NotificationJob.recipient_customer_id == customer_id),
        "confirmations": _count(db, CustomerConfirmation, CustomerConfirmation.customer_id == customer_id),
        "legal_acceptances": _count(db, LegalAcceptance, LegalAcceptance.customer_id == customer_id),
        "feedback": _count(db, CustomerFeedback, CustomerFeedback.customer_id == customer_id),
        "operation_issues": _count(db, OperationIssue, OperationIssue.related_customer_id == customer_id),
    }
    counts["business_total"] = sum(counts.values())
    counts["sessions"] = _count(db, CustomerSession, CustomerSession.customer_id == customer_id)
    counts["access_tokens"] = _count(db, CustomerAccessToken, CustomerAccessToken.customer_id == customer_id)
    counts["notification_preferences"] = _count(
        db, NotificationPreference, NotificationPreference.customer_id == customer_id
    )
    return counts


def historical_unactivated_accounts(db: Session) -> list[CustomerAccount]:
    return db.query(CustomerAccount).filter(
        CustomerAccount.registration_source == "historical_data",
        CustomerAccount.password_hash == "",
        CustomerAccount.last_login_at.is_(None),
        CustomerAccount.deleted_at.is_(None),
    ).order_by(CustomerAccount.created_at.asc()).all()


def cleanup_preview(db: Session) -> dict:
    items = []
    totals = {
        "accounts": 0,
        "with_reports": 0,
        "with_orders": 0,
        "without_business": 0,
        "reports": 0,
        "orders": 0,
    }
    for customer in historical_unactivated_accounts(db):
        counts = customer_dependency_counts(db, customer)
        items.append({"customer": customer, "counts": counts})
        totals["accounts"] += 1
        totals["reports"] += counts["reports"]
        totals["orders"] += counts["orders"]
        totals["with_reports"] += int(counts["reports"] > 0)
        totals["with_orders"] += int(counts["orders"] > 0)
        totals["without_business"] += int(counts["business_total"] == 0)
    return {"items": items, "totals": totals}


def _audit(
    db: Session,
    action: str,
    customer: CustomerAccount,
    operator: User,
    reason: str,
    request=None,
    *,
    attach_customer: bool = True,
    extra: dict | None = None,
) -> None:
    write_audit_log(
        db,
        action,
        "customer_account",
        customer.id,
        user_id=operator.id,
        customer_id=customer.id if attach_customer else None,
        before={
            "status": customer.status,
            "is_active": customer.is_active,
            "deleted_at": customer.deleted_at.isoformat() if customer.deleted_at else None,
        },
        after={
            "phone_masked": mask_phone(customer.login_phone or customer.phone),
            "reason": reason,
            **(extra or {}),
        },
        request=request,
        risk_level="high" if action in {"customer_account_permanently_deleted", "customer_accounts_bulk_cleaned"} else "medium",
    )


def soft_delete_customer_account(
    db: Session,
    customer: CustomerAccount,
    operator: User,
    reason: str,
    request=None,
    *,
    action: str = "customer_account_deleted",
) -> bool:
    if customer.deleted_at:
        return False
    now = datetime.now()
    _audit(db, action, customer, operator, reason, request)
    customer.deleted_at = now
    customer.deleted_by = operator.id
    customer.delete_reason = reason.strip()
    customer.status = "deleted"
    customer.is_active = False
    db.query(CustomerSession).filter(
        CustomerSession.customer_id == customer.id,
        CustomerSession.revoked_at.is_(None),
    ).update({"revoked_at": now}, synchronize_session=False)
    db.query(CustomerAccessToken).filter(
        CustomerAccessToken.customer_id == customer.id,
        CustomerAccessToken.is_active.is_(True),
    ).update({"is_active": False}, synchronize_session=False)
    return True


def restore_customer_account(
    db: Session,
    customer: CustomerAccount,
    operator: User,
    reason: str,
    request=None,
) -> bool:
    if not customer.deleted_at:
        return False
    _audit(db, "customer_account_restored", customer, operator, reason, request)
    customer.deleted_at = None
    customer.deleted_by = None
    customer.delete_reason = ""
    customer.is_active = True
    customer.status = "active" if customer.password_hash else "pending_activation"
    customer.failed_login_count = 0
    customer.locked_until = None
    return True


def permanently_delete_customer_account(
    db: Session,
    customer: CustomerAccount,
    operator: User,
    reason: str,
    request=None,
) -> None:
    counts = customer_dependency_counts(db, customer)
    if counts["business_total"]:
        raise ValueError("该账号仍有关联业务数据，不能永久删除")

    # 身份会话和偏好不属于业务档案；永久删除空账号时一并清理。
    db.query(CustomerSession).filter(CustomerSession.customer_id == customer.id).delete(synchronize_session=False)
    db.query(CustomerAccessToken).filter(CustomerAccessToken.customer_id == customer.id).delete(synchronize_session=False)
    db.query(NotificationPreference).filter(
        NotificationPreference.customer_id == customer.id
    ).delete(synchronize_session=False)

    # 审计记录必须保留，但不让外键阻止空账号的永久删除。
    db.query(AuditLog).filter(AuditLog.customer_id == customer.id).update(
        {"customer_id": None}, synchronize_session=False
    )
    _audit(
        db,
        "customer_account_permanently_deleted",
        customer,
        operator,
        reason,
        request,
        attach_customer=False,
        extra={"permanent": True},
    )
    db.flush()
    db.delete(customer)
