from sqlalchemy.orm import Session

from db.models import Lead, LeadTag, Tag


DEFAULT_TAGS = {
    "高融资需求": "#9b6c18", "有抵押物": "#17654d", "征信正常": "#245d91",
    "纳税正常": "#245d91", "现金流紧张": "#b84343", "应收账款长": "#b84343",
    "高客单潜力": "#7a4f00", "需养熟": "#68758a", "已成交": "#238164", "需复购": "#8a4ca8",
    "资料不完整": "#b84343", "财务数据不一致": "#b84343", "现金流弱": "#b84343",
    "短债压力高": "#b84343", "征信待核验": "#9b6c18", "纳税待核验": "#9b6c18",
    "抵押物待核验": "#9b6c18", "应收账款风险": "#b84343", "需人工尽调": "#7a4f00",
}
DEFAULT_TAGS.update({
    "试运营客户": "#c9a45c", "高反馈价值": "#17654d", "付费意向强": "#245d91",
    "卡在支付": "#b84343", "卡在资料上传": "#b84343", "报告已看未升级": "#9b6c18",
    "顾问跟进中": "#7a4f00", "真实融资项目": "#238164", "待复盘": "#8a4ca8",
})


def ensure_default_tags(db: Session) -> None:
    existing = {x.name for x in db.query(Tag).all()}
    for name, color in DEFAULT_TAGS.items():
        if name not in existing:
            db.add(Tag(name=name, color=color))
    db.commit()


def auto_tag_lead(db: Session, lead: Lead, commit: bool = False) -> None:
    assessment = lead.assessment
    names = []
    if assessment.funding_need >= 2_000_000:
        names.append("高融资需求")
    if assessment.has_collateral:
        names.append("有抵押物")
    if assessment.credit_status:
        names.append("征信正常")
    if assessment.tax_status:
        names.append("纳税正常")
    if assessment.monthly_cashflow <= max(assessment.annual_revenue / 36, 1):
        names.append("现金流紧张")
    if assessment.receivable_days > 75:
        names.append("应收账款长")
    if lead.lead_grade in {"S", "A"}:
        names.append("高客单潜力")
    if lead.lead_grade == "D":
        names.append("需养熟")
    for tag in db.query(Tag).filter(Tag.name.in_(names or [""])).all():
        if not db.query(LeadTag).filter(LeadTag.lead_id == lead.id, LeadTag.tag_id == tag.id).first():
            db.add(LeadTag(lead_id=lead.id, tag_id=tag.id))
    if commit:
        db.commit()


def add_named_tag(db: Session, lead: Lead, name: str, commit: bool = False) -> None:
    tag = db.query(Tag).filter(Tag.name == name).first()
    if tag and not db.query(LeadTag).filter(
        LeadTag.lead_id == lead.id, LeadTag.tag_id == tag.id
    ).first():
        db.add(LeadTag(lead_id=lead.id, tag_id=tag.id))
    if commit:
        db.commit()
