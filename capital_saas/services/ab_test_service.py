import random

from sqlalchemy import func
from sqlalchemy.orm import Session

from db.models import ABAssignment, ABExperiment, Order
from services.event_service import track_event


EXPERIMENT_KEY = "free_result_conversion"


def ensure_default_experiment(db: Session) -> None:
    existing = db.query(ABExperiment).filter(
        ABExperiment.experiment_key == EXPERIMENT_KEY
    ).count()
    if existing:
        return
    db.add_all([
        ABExperiment(experiment_key=EXPERIMENT_KEY, variant="variant_a", description="风险提示型"),
        ABExperiment(experiment_key=EXPERIMENT_KEY, variant="variant_b", description="机会收益型"),
    ])
    db.commit()


def assign_variant(db: Session, session_id: str, assessment_id: int, lead_id: int | None) -> str:
    assignment = db.query(ABAssignment).filter(
        ABAssignment.session_id == session_id,
        ABAssignment.experiment_key == EXPERIMENT_KEY,
    ).first()
    if assignment:
        if not assignment.assessment_id:
            assignment.assessment_id = assessment_id
            assignment.lead_id = lead_id
            db.commit()
        return assignment.variant
    variants = [
        row.variant for row in db.query(ABExperiment).filter(
            ABExperiment.experiment_key == EXPERIMENT_KEY,
            ABExperiment.is_active.is_(True),
        ).all()
    ] or ["variant_a", "variant_b"]
    variant = random.choice(variants)
    assignment = ABAssignment(
        session_id=session_id,
        experiment_key=EXPERIMENT_KEY,
        variant=variant,
        assessment_id=assessment_id,
        lead_id=lead_id,
    )
    db.add(assignment)
    db.flush()
    track_event(
        db, "ab_assigned", assessment_id=assessment_id, lead_id=lead_id,
        data={"experiment_key": EXPERIMENT_KEY, "variant": variant}, commit=False
    )
    db.commit()
    return variant


def ab_metrics(db: Session) -> list[dict]:
    rows = []
    variants = db.query(ABExperiment).filter(
        ABExperiment.experiment_key == EXPERIMENT_KEY
    ).all()
    for experiment in variants:
        assignments = db.query(ABAssignment).filter(
            ABAssignment.experiment_key == EXPERIMENT_KEY,
            ABAssignment.variant == experiment.variant,
        ).all()
        assessment_ids = [x.assessment_id for x in assignments if x.assessment_id]
        paid_orders = db.query(Order).filter(
            Order.status == "paid", Order.assessment_id.in_(assessment_ids or [-1])
        ).all()
        paid_assessment_ids = {x.assessment_id for x in paid_orders}
        count = len(assignments)
        rows.append({
            "experiment_key": experiment.experiment_key,
            "variant": experiment.variant,
            "description": experiment.description,
            "assigned": count,
            "paid": len(paid_assessment_ids),
            "conversion_rate": round(len(paid_assessment_ids) / count * 100, 1) if count else 0,
            "revenue": sum(x.amount for x in paid_orders),
        })
    return rows

