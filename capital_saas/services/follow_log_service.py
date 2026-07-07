from sqlalchemy.orm import Session

from db.models import LeadFollowLog, User


def add_follow_log(
    db: Session,
    lead_id: int,
    user: User | None,
    action_type: str,
    content: str = "",
    old_status: str = "",
    new_status: str = "",
    commit: bool = False,
) -> LeadFollowLog:
    item = LeadFollowLog(
        lead_id=lead_id,
        user_id=user.id if user else None,
        action_type=action_type,
        content=content,
        old_status=old_status,
        new_status=new_status,
    )
    db.add(item)
    if commit:
        db.commit()
    return item

