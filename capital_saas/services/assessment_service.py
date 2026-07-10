import json

from sqlalchemy.orm import Session

from core.lead_scoring_engine import calculate_lead_score
from core.sales_script_engine import generate_sales_script
from core.scoring_engine import calculate_score
from db.models import Assessment, ChannelPartner, Lead, Organization, Report
from services.attribution_service import ATTRIBUTION_FIELDS
from services.event_service import track_event
from services.follow_task_service import create_default_tasks
from services.customer_portal_service import ensure_customer_account
from services.notification_service import notify_new_lead
from services.pilot_service import bind_by_invite_code, set_pilot_stage


def create_assessment(db: Session, form_data: dict) -> Assessment:
    form_data = dict(form_data)
    partner_code = form_data.pop("partner_source_code", "")
    pilot_invite_code = form_data.pop("pilot_invite_code", "")
    partner = db.query(ChannelPartner).filter(
        ChannelPartner.source_code == partner_code, ChannelPartner.status == "active"
    ).first() if partner_code else None
    hq = db.query(Organization).filter(Organization.org_type == "headquarters").first()
    org_id = partner.org_id if partner else (hq.id if hq else None)
    score = calculate_score(form_data)
    assessment = Assessment(
        **form_data,
        score=score.total,
        grade=score.grade,
        risk_level=score.risk_level,
        funding_probability=score.funding_probability,
    )
    db.add(assessment)
    db.flush()

    free_summary = {
        "score": score.total,
        "grade": score.grade,
        "grade_text": score.grade_text,
        "risk_level": score.risk_level,
        "funding_probability": score.funding_probability,
        "core_risk": score.core_risk,
        "financial_literacy_gap": score.financial_literacy_gap,
        "finance_now": score.finance_now,
        "dimensions": score.dimensions,
    }
    lead_result = calculate_lead_score(form_data, score.total)
    sales_script = generate_sales_script(
        lead_grade=lead_result.lead_grade,
        company_name=assessment.company_name,
        contact_name=assessment.contact_name,
        assessment_score=score.total,
        funding_need=assessment.funding_need,
        risk_point=score.core_risk,
    )
    db.add(
        Report(
            assessment_id=assessment.id,
            free_summary_json=json.dumps(free_summary, ensure_ascii=False),
            is_unlocked=False,
        )
    )
    lead = Lead(
            assessment_id=assessment.id,
            company_name=assessment.company_name,
            contact_name=assessment.contact_name,
            phone=assessment.phone,
            wechat_id=assessment.wechat_id,
            city=assessment.city,
            lead_grade=lead_result.lead_grade,
            lead_score=lead_result.lead_score,
            recommended_product=lead_result.recommended_product,
            follow_status="待联系",
            conversion_status="未成交",
            sales_script=json.dumps(sales_script, ensure_ascii=False),
            org_id=org_id, owner_org_id=org_id,
            source_partner_id=partner.id if partner else None,
            **{key: getattr(assessment, key, "") for key in ATTRIBUTION_FIELDS},
        )
    db.add(lead)
    db.flush()
    ensure_customer_account(db, lead, commit=False)
    if pilot_invite_code:
        bind_by_invite_code(db, lead, pilot_invite_code, commit=False)
    set_pilot_stage(db, lead, "assessed", commit=False)
    create_default_tasks(db, lead)
    track_event(
        db,
        "assessment_submitted",
        assessment_id=assessment.id,
        lead_id=lead.id,
        data={
            "score": score.total,
            "grade": score.grade,
            "lead_score": lead_result.lead_score,
            "lead_grade": lead_result.lead_grade,
        },
        attribution={key: getattr(assessment, key, "") for key in ATTRIBUTION_FIELDS},
        commit=False,
    )
    if partner:
        track_event(db, "partner_lead_created", assessment.id, lead.id,
                    {"partner_id": partner.id, "source_code": partner.source_code}, commit=False)
    notify_new_lead(db, lead, commit=False)
    db.commit()
    db.refresh(assessment)
    return assessment


def get_assessment(db: Session, assessment_id: int) -> Assessment | None:
    return db.get(Assessment, assessment_id)
