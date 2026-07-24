from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from core.pricing_engine import get_product, products, public_products
from db.database import get_db
from db.models import Order
from services.assessment_service import get_assessment
from services.event_service import track_event
from services.notification_service import notify_payment_success
from services.payment_service import create_order, mark_order_paid
from services.report_service import generate_full_report
from services.settings_service import get_setting
from utils.logger import logger


router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


@router.get("/products", response_class=HTMLResponse)
def product_list(request: Request, db: Session = Depends(get_db)):
    runtime_products = public_products(db)
    return templates.TemplateResponse(
        request=request, name="products.html", context={"products": runtime_products}
    )


@router.get("/checkout/{assessment_id}", response_class=HTMLResponse)
def checkout(
    request: Request,
    assessment_id: int,
    product: str = "980_capital_health_report",
    from_product: str = "",
    upgrade: int = 0,
    db: Session = Depends(get_db),
):
    assessment = get_assessment(db, assessment_id)
    if not assessment:
        raise HTTPException(status_code=404, detail="测评不存在")
    if product not in products:
        raise HTTPException(status_code=404, detail="产品不存在")
    product_code, product_info = get_product(product, db, assessment.id)
    if not product_info.get("is_active", True):
        raise HTTPException(status_code=404, detail="该产品当前未启用")
    payment_mode = get_setting(db, "payment_mode", "mock")
    track_event(
        db,
        "checkout_viewed",
        assessment_id=assessment.id,
        lead_id=assessment.lead.id if assessment.lead else None,
        data={"product_code": product_code, "price": product_info["price"], "mode": payment_mode},
    )
    if upgrade:
        track_event(
            db,
            "upgrade_clicked",
            assessment_id=assessment.id,
            lead_id=assessment.lead.id if assessment.lead else None,
            data={"from_product": from_product, "target_product": product_code},
        )
    return templates.TemplateResponse(
        request=request,
        name="checkout.html",
        context={
            "assessment": assessment,
            "product_code": product_code,
            "product": product_info,
            "payment_mode": payment_mode,
        },
    )


@router.post("/payment/mock-pay/{assessment_id}")
def pay(
    assessment_id: int,
    product: str = "980_capital_health_report",
    db: Session = Depends(get_db),
):
    assessment = get_assessment(db, assessment_id)
    if not assessment:
        raise HTTPException(status_code=404, detail="测评不存在")
    if product not in products:
        raise HTTPException(status_code=404, detail="产品不存在")
    product_code, product_info = get_product(product, db)
    if not product_info.get("is_active", True):
        raise HTTPException(status_code=404, detail="该产品当前未启用")
    payment_mode = get_setting(db, "payment_mode", "mock")
    order = create_order(
        db,
        assessment,
        product_code,
        payment_mode,
        assessment.phone,
    )
    if payment_mode == "mock":
        mark_order_paid(db, order, operator="mock")
        generate_full_report(db, assessment)
        return RedirectResponse(url=f"/payment/success/{order.id}", status_code=303)
    if payment_mode == "manual_transfer":
        return RedirectResponse(url=f"/payment/success/{order.id}", status_code=303)
    # TODO: 调用微信支付/支付宝统一下单接口，保存平台预支付信息。
    logger.warning("真实支付渠道尚未接入 order_id=%s channel=%s", order.id, payment_mode)
    return RedirectResponse(url=f"/payment/fail/{order.id}", status_code=303)


@router.get("/payment/success/{order_id}", response_class=HTMLResponse)
def payment_success(request: Request, order_id: int, db: Session = Depends(get_db)):
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    if order.status == "paid":
        notify_payment_success(db, order, commit=True)
    return templates.TemplateResponse(
        request=request,
        name="payment_success.html",
        context={
            "order": order,
            "assessment": order.assessment,
            "payment_mode": order.pay_channel,
            "contact_phone": get_setting(db, "contact_phone", ""),
            "contact_wechat": get_setting(db, "contact_wechat", ""),
        },
    )


@router.get("/payment/fail/{order_id}", response_class=HTMLResponse)
def payment_fail(request: Request, order_id: int, db: Session = Depends(get_db)):
    order = db.get(Order, order_id)
    return templates.TemplateResponse(
        request=request,
        name="payment_failed.html",
        context={"order": order},
        status_code=400,
    )


@router.post("/payment/webhook/wechat")
async def wechat_webhook(request: Request, db: Session = Depends(get_db)):
    payload = (await request.body()).decode("utf-8", errors="replace")[:2000]
    # TODO: 验证微信支付签名、商户号、金额和订单状态后再更新订单。
    track_event(db, "payment_webhook_wechat", data={"payload": payload})
    logger.info("收到微信支付预留回调")
    return JSONResponse({"code": "SUCCESS", "message": "recorded"})


@router.post("/payment/webhook/alipay")
async def alipay_webhook(request: Request, db: Session = Depends(get_db)):
    payload = (await request.body()).decode("utf-8", errors="replace")[:2000]
    # TODO: 验证支付宝签名、应用ID、金额和订单状态后再更新订单。
    track_event(db, "payment_webhook_alipay", data={"payload": payload})
    logger.info("收到支付宝预留回调")
    return JSONResponse({"code": "success", "message": "recorded"})


@router.get("/api/order/{assessment_id}")
def order_api(assessment_id: int, db: Session = Depends(get_db)):
    order = (
        db.query(Order)
        .filter(Order.assessment_id == assessment_id)
        .order_by(Order.id.desc())
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    return {
        "id": order.id,
        "assessment_id": order.assessment_id,
        "product_code": order.product_code,
        "product_name": order.product_name,
        "amount": order.amount,
        "status": order.status,
        "pay_channel": order.pay_channel,
        "transaction_id": order.transaction_id,
        "paid_at": order.paid_at,
        "refund_at": order.refund_at,
        "created_at": order.created_at,
    }
