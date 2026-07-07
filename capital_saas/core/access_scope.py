from dataclasses import asdict, dataclass

from sqlalchemy.orm import Session

from db.models import ChannelPartner, Organization, User


@dataclass
class AccessScope:
    can_view_all: bool
    allowed_org_ids: list[int]
    allowed_user_ids: list[int]
    allowed_partner_ids: list[int]
    role: str

    def to_dict(self): return asdict(self)


def effective_role(user: User) -> str:
    return "super_admin" if user.role == "admin" else user.role


def _descendant_org_ids(db: Session, org_id: int | None) -> list[int]:
    if not org_id: return []
    result, frontier = [org_id], [org_id]
    while frontier:
        children = [row[0] for row in db.query(Organization.id).filter(Organization.parent_id.in_(frontier)).all()]
        result.extend(x for x in children if x not in result); frontier = children
    return result


def get_access_scope(db: Session, user: User) -> AccessScope:
    role = effective_role(user)
    if role == "super_admin":
        return AccessScope(True, [x[0] for x in db.query(Organization.id).all()],
                           [x[0] for x in db.query(User.id).all()],
                           [x[0] for x in db.query(ChannelPartner.id).all()], role)
    org_ids = _descendant_org_ids(db, user.org_id)
    org_users = [x[0] for x in db.query(User.id).filter(User.org_id.in_(org_ids or [-1])).all()]
    if role in {"sales", "consultant"}: org_users = [user.id]
    partners = [x[0] for x in db.query(ChannelPartner.id).filter(ChannelPartner.org_id.in_(org_ids or [-1])).all()]
    if role == "partner":
        partner = db.query(ChannelPartner).filter(ChannelPartner.org_id == user.org_id).first()
        partners = [partner.id] if partner else []
    return AccessScope(False, org_ids, org_users, partners, role)


def apply_org_scope(query, model, scope: AccessScope):
    if scope.can_view_all: return query
    org_column = getattr(model, "owner_org_id", None)
    if org_column is None: org_column = getattr(model, "org_id", None)
    return query.filter(org_column.in_(scope.allowed_org_ids or [-1])) if org_column is not None else query
