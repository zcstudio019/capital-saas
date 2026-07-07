import json

from sqlalchemy.orm import Session

from db.models import Assessment, Event
from services.attribution_service import ATTRIBUTION_FIELDS


def track_event(
    db: Session,
    event_type: str,
    assessment_id: int | None = None,
    lead_id: int | None = None,
    data: dict | None = None,
    attribution: dict | None = None,
    commit: bool = True,
) -> Event:
    source = attribution or {}
    if assessment_id and not source:
        assessment = db.get(Assessment, assessment_id)
        if assessment:
            source = {key: getattr(assessment, key, "") for key in ATTRIBUTION_FIELDS}
    event = Event(
        assessment_id=assessment_id,
        lead_id=lead_id,
        event_type=event_type,
        event_data_json=json.dumps(data or {}, ensure_ascii=False),
        **{key: source.get(key, "") for key in ATTRIBUTION_FIELDS},
    )
    db.add(event)
    if commit:
        db.commit()
        db.refresh(event)
    return event
