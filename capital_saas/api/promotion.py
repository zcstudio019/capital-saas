from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from core.config import BASE_DIR
from db.database import get_db
from db.models import PromotionQRCode, User
from services.auth_service import require_roles
from services.promotion_qrcode_service import LANDING_PAGE_OPTIONS, create_promotion_qrcode, qrcode_image_file


router = APIRouter()
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
READ_ROLES = ("admin", "super_admin", "sales", "viewer")


def _can_manage(user: User) -> bool:
    return user.role in {"admin", "super_admin"}


def _qrcode_or_404(db: Session, qrcode_id: int) -> PromotionQRCode:
    record = db.get(PromotionQRCode, qrcode_id)
    if not record:
        raise HTTPException(status_code=404, detail="推广二维码不存在")
    return record


def _assert_qrcode_access(record: PromotionQRCode, user: User) -> None:
    if _can_manage(user) or user.role == "viewer":
        return
    if user.role == "sales" and record.sales_id == user.id:
        return
    raise HTTPException(status_code=403, detail="无权查看该推广二维码")


@router.get("/admin/qrcodes", response_class=HTMLResponse)
def promotion_qrcodes(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*READ_ROLES)),
):
    query = db.query(PromotionQRCode).order_by(PromotionQRCode.created_at.desc())
    if user.role == "sales":
        query = query.filter(PromotionQRCode.sales_id == user.id)
    records = query.all()
    sales_users = db.query(User).filter(User.role == "sales", User.is_active.is_(True)).order_by(User.id).all()
    return templates.TemplateResponse(
        request=request,
        name="admin_promotion_qrcodes.html",
        context={
            "qrcodes": records,
            "landing_pages": LANDING_PAGE_OPTIONS,
            "landing_labels": {item["path"]: item["label"] for item in LANDING_PAGE_OPTIONS.values()},
            "sales_users": sales_users,
            "can_manage": _can_manage(user),
            "current_user": user,
        },
    )


@router.post("/admin/qrcodes")
def create_qrcode(
    name: str = Form(""),
    landing_key: str = Form("rongzi"),
    channel: str = Form("qr"),
    source: str = Form("offline"),
    campaign: str = Form(""),
    sales_id: int = Form(0),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "super_admin")),
):
    if sales_id:
        sales_user = db.get(User, sales_id)
        if not sales_user or not sales_user.is_active or sales_user.role != "sales":
            raise HTTPException(status_code=400, detail="请选择有效销售账号")
    try:
        create_promotion_qrcode(
            db,
            name=name,
            landing_key=landing_key,
            channel=channel,
            source=source,
            campaign=campaign,
            sales_id=sales_id or None,
            created_by=user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(url="/admin/qrcodes", status_code=303)


@router.get("/admin/qrcodes/{qrcode_id}/image")
def preview_qrcode(
    qrcode_id: int,
    download: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*READ_ROLES)),
):
    record = _qrcode_or_404(db, qrcode_id)
    _assert_qrcode_access(record, user)
    image_file = qrcode_image_file(record)
    if not image_file.is_file():
        raise HTTPException(status_code=404, detail="二维码图片不存在")
    return FileResponse(
        path=image_file,
        media_type="image/png",
        filename=Path(image_file).name if download else None,
    )
