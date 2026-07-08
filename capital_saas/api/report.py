from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from core.pricing_engine import PRODUCT_RANK
from db.database import get_db
from db.models import Order, Report
from services.assessment_service import get_assessment
from services.auth_service import current_user_optional
from services.event_service import track_event
from services.pilot_service import set_pilot_stage
from services.payment_service import has_paid_order
from services.report_access_service import (
    build_bank_product_detail_context,
    build_report_access_context,
)
from services.report_service import generate_full_report, parse_report
from services.settings_service import get_bool_setting
from utils.logger import logger


router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


def _admin_override(request: Request, db: Session) -> bool:
    user = current_user_optional(request, db)
    return bool(user and user.role == "admin")


def _report_access_allowed(request: Request, db: Session, assessment_id: int) -> bool:
    return has_paid_order(db, assessment_id) or _admin_override(request, db)


def _review_blocks_customer(request: Request, db: Session, report: Report) -> bool:
    if _admin_override(request, db):
        return False
    return (
        get_bool_setting(db, "report_review_required", False)
        and report.review_status != "approved"
    )


def _current_product(db: Session, assessment_id: int) -> str:
    paid_orders = (
        db.query(Order)
        .filter(Order.assessment_id == assessment_id, Order.status == "paid")
        .all()
    )
    return max(
        (order.product_code or "299_report" for order in paid_orders),
        key=lambda code: PRODUCT_RANK.get(code, 0),
        default="299_report",
    )


@router.get("/report/{assessment_id}", response_class=HTMLResponse)
def full_report(request: Request, assessment_id: int, db: Session = Depends(get_db)):
    assessment = get_assessment(db, assessment_id)
    if not assessment or not assessment.report:
        raise HTTPException(status_code=404, detail="报告不存在")
    if not _report_access_allowed(request, db, assessment_id):
        logger.warning("报告访问被拒 assessment_id=%s path=full", assessment_id)
        return RedirectResponse(url=f"/checkout/{assessment_id}", status_code=303)
    generate_full_report(db, assessment)
    if _review_blocks_customer(request, db, assessment.report):
        return templates.TemplateResponse(
            request=request,
            name="report_pending.html",
            context={"assessment": assessment, "report_item": assessment.report},
            status_code=202,
        )
    _, full = parse_report(assessment.report)
    current_product = _current_product(db, assessment_id)
    access_context = build_report_access_context(
        db,
        assessment,
        full,
        base_path=f"/report/{assessment.id}",
    )
    track_event(
        db,
        "report_viewed",
        assessment_id=assessment.id,
        lead_id=assessment.lead.id if assessment.lead else None,
        data={"current_product": current_product},
    )
    set_pilot_stage(db, assessment.lead if assessment else None, "report_viewed", commit=True)
    return templates.TemplateResponse(
        request=request,
        name="report_full.html",
        context={
            "assessment": assessment,
            "report": full,
            "current_product": current_product,
            **access_context,
        },
    )


@router.get("/report/{assessment_id}/print", response_class=HTMLResponse)
def print_report(request: Request, assessment_id: int, db: Session = Depends(get_db)):
    assessment = get_assessment(db, assessment_id)
    if not assessment or not assessment.report:
        raise HTTPException(status_code=404, detail="报告不存在")
    if not _report_access_allowed(request, db, assessment_id):
        logger.warning("报告访问被拒 assessment_id=%s path=print", assessment_id)
        return RedirectResponse(url=f"/checkout/{assessment_id}", status_code=303)
    generate_full_report(db, assessment)
    if _review_blocks_customer(request, db, assessment.report):
        return templates.TemplateResponse(
            request=request,
            name="report_pending.html",
            context={"assessment": assessment, "report_item": assessment.report},
            status_code=202,
        )
    _, full = parse_report(assessment.report)
    current_product = _current_product(db, assessment_id)
    access_context = build_report_access_context(
        db,
        assessment,
        full,
        base_path=f"/report/{assessment.id}",
    )
    return templates.TemplateResponse(
        request=request,
        name="report_print.html",
        context={
            "assessment": assessment,
            "report": full,
            "current_product": current_product,
            **access_context,
        },
    )


@router.get("/report/{assessment_id}/bank-products/{product_id}", response_class=HTMLResponse)
def bank_product_detail(
    request: Request,
    assessment_id: int,
    product_id: int,
    db: Session = Depends(get_db),
):
    assessment = get_assessment(db, assessment_id)
    if not assessment or not assessment.report:
        raise HTTPException(status_code=404, detail="报告不存在")
    if not _report_access_allowed(request, db, assessment_id):
        return RedirectResponse(url=f"/checkout/{assessment_id}", status_code=303)
    generate_full_report(db, assessment)
    if _review_blocks_customer(request, db, assessment.report):
        return templates.TemplateResponse(
            request=request,
            name="report_pending.html",
            context={"assessment": assessment, "report_item": assessment.report},
            status_code=202,
        )
    _, full = parse_report(assessment.report)
    detail_context = build_bank_product_detail_context(db, assessment, full, product_id)
    if detail_context is None:
        raise HTTPException(status_code=404, detail="银行产品不存在")
    return templates.TemplateResponse(
        request=request,
        name="report_bank_product_detail.html",
        context={
            "assessment": assessment,
            "report": full,
            "back_url": f"/report/{assessment.id}",
            "checkout_base": f"/checkout/{assessment.id}",
            **detail_context,
        },
    )


@router.get("/public/report/{public_token}", response_class=HTMLResponse)
def public_report(request: Request, public_token: str, db: Session = Depends(get_db)):
    report = db.query(Report).filter(Report.public_token == public_token).first()
    if not report or not report.token_expired_at or report.token_expired_at < datetime.now():
        raise HTTPException(status_code=404, detail="公开报告链接不存在或已过期")
    if not has_paid_order(db, report.assessment_id):
        raise HTTPException(status_code=403, detail="该报告尚未解锁")
    if report.review_status != "approved":
        raise HTTPException(status_code=403, detail="报告正在生成或审核中")
    generate_full_report(db, report.assessment)
    _, full = parse_report(report)
    access_context = build_report_access_context(
        db,
        report.assessment,
        full,
        base_path=f"/report/{report.assessment_id}",
    )
    return templates.TemplateResponse(
        request=request,
        name="report_print.html",
        context={
            "assessment": report.assessment,
            "report": full,
            "current_product": _current_product(db, report.assessment_id),
            **access_context,
        },
    )


@router.get("/api/report/{assessment_id}")
def report_api(request: Request, assessment_id: int, db: Session = Depends(get_db)):
    report = db.query(Report).filter(Report.assessment_id == assessment_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")
    free, full = parse_report(report)
    unlocked = _report_access_allowed(request, db, assessment_id)
    reviewed = not _review_blocks_customer(request, db, report)
    return {
        "assessment_id": assessment_id,
        "is_unlocked": unlocked,
        "free_summary": free,
        "full_report": full if unlocked and reviewed else None,
        "review_status": report.review_status,
        "reviewed_for_customer": reviewed,
        "created_at": report.created_at,
    }
