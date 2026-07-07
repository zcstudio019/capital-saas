from sqlalchemy.orm import Session

from db.models import Assessment, ConsultingCase


def ensure_consulting_case(db: Session, assessment: Assessment, product_code: str) -> ConsultingCase | None:
    if product_code != "1999_structure_plan":
        return None
    existing = db.query(ConsultingCase).filter(
        ConsultingCase.assessment_id == assessment.id,
        ConsultingCase.product_code == product_code,
        ConsultingCase.case_status != "cancelled",
    ).first()
    if existing:
        return existing
    case = ConsultingCase(
        lead_id=assessment.lead.id if assessment.lead else None,
        assessment_id=assessment.id,
        report_id=assessment.report.id if assessment.report else None,
        product_code=product_code,
        case_status="pending",
        case_summary=f"{assessment.company_name}已购买融资结构优化方案，企业评分{assessment.score}分。",
        service_goal=f"围绕{assessment.funding_need / 10000:,.0f}万元融资需求设计额度、成本、期限和申请顺序。",
        org_id=assessment.lead.org_id if assessment.lead else None,
        owner_org_id=assessment.lead.owner_org_id if assessment.lead else None,
        owner_user_id=assessment.lead.owner_user_id if assessment.lead else None,
    )
    db.add(case)
    db.flush()
    return case
