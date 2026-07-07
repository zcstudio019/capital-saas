from fastapi import APIRouter, Depends, Form
from sqlalchemy.orm import Session

from db.database import get_db
from db.models import Lead
from services.event_service import track_event


router = APIRouter()


@router.post("/api/events/upgrade-click")
def upgrade_click(
    assessment_id: int = Form(...),
    product_code: str = Form(...),
    from_product: str = Form(...),
    target_product: str = Form(...),
    db: Session = Depends(get_db),
):
    lead = db.query(Lead).filter(Lead.assessment_id == assessment_id).first()
    event = track_event(
        db,
        "upgrade_clicked",
        assessment_id=assessment_id,
        lead_id=lead.id if lead else None,
        data={
            "product_code": product_code,
            "from_product": from_product,
            "target_product": target_product,
        },
    )
    return {"ok": True, "event_id": event.id}

