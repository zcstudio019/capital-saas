from pathlib import Path
from urllib.parse import urlencode

import qrcode
from sqlalchemy.orm import Session

from core.config import BASE_DIR, settings
from db.models import PromotionQRCode


LANDING_PAGE_OPTIONS = {
    "rongzi": {"path": "/lp/rongzi", "label": "企业融资测评页"},
    "cashflow": {"path": "/lp/cashflow", "label": "现金流风险测评页"},
    "bank": {"path": "/lp/bank", "label": "银行贷款通过率测评页"},
    "boss": {"path": "/lp/boss", "label": "老板财商诊断页"},
    "assessment": {"path": "/assessment", "label": "通用免费测评页"},
}
QR_UPLOAD_DIR = BASE_DIR / "static" / "uploads" / "qrcodes"


def build_promotion_url(landing_key: str, channel: str, source: str, campaign: str, sales_id: int | None, qr_id: int) -> str:
    option = LANDING_PAGE_OPTIONS.get(landing_key)
    if not option:
        raise ValueError("不支持的客户入口")
    params = {"channel": channel or "qr", "source": source or "offline", "qr_id": qr_id}
    if campaign:
        params["campaign"] = campaign
    if sales_id:
        params["sales_id"] = sales_id
    return f"{settings.promotion_qr_base_url.rstrip('/')}{option['path']}?{urlencode(params)}"


def create_promotion_qrcode(
    db: Session,
    *,
    name: str,
    landing_key: str,
    channel: str,
    source: str,
    campaign: str,
    sales_id: int | None,
    created_by: int | None,
) -> PromotionQRCode:
    option = LANDING_PAGE_OPTIONS.get(landing_key)
    if not option:
        raise ValueError("不支持的客户入口")
    record = PromotionQRCode(
        name=(name or f"{option['label']}推广二维码").strip()[:200],
        landing_page=option["path"],
        channel=(channel or "qr").strip()[:100],
        source=(source or "offline").strip()[:100],
        campaign=(campaign or "").strip()[:200],
        sales_id=sales_id,
        created_by=created_by,
    )
    db.add(record)
    db.flush()
    record.full_url = build_promotion_url(landing_key, record.channel, record.source, record.campaign, record.sales_id, record.id)
    QR_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    source_part = "".join(char for char in record.source if char.isalnum() or char in {"-", "_"}) or "offline"
    sales_part = f"sales_{record.sales_id}" if record.sales_id else source_part
    filename = f"qr_{landing_key}_{sales_part}_{record.id}.png"
    image_path = QR_UPLOAD_DIR / filename
    qrcode.make(record.full_url).save(image_path)
    record.qr_image_path = f"/static/uploads/qrcodes/{filename}"
    db.commit()
    db.refresh(record)
    return record


def qrcode_image_file(record: PromotionQRCode) -> Path:
    return QR_UPLOAD_DIR / Path(record.qr_image_path or "").name
