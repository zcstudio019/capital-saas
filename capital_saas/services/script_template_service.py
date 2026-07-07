from sqlalchemy.orm import Session

from db.models import SalesScriptTemplate


DEFAULT_SCRIPTS = [
    ("初次加微信", "first_wechat", "", "", "您好，我是沪上银企业融资顾问。已看到您的测评结果，我先把银行最关注的风险点和下一步资料清单发您。"),
    ("免费测评后未支付", "free_unpaid", "", "299_report", "您的免费结果只展示了表层评分，完整报告会说明银行可能压额度的原因和修复顺序。"),
    ("推299", "push_299", "C", "299_report", "当前不建议直接申请银行，先用299完整诊断把影响通过率的问题看清。"),
    ("推699", "push_699", "B", "699_bank_match", "不同银行准入差异很大，699银行匹配报告会给出额度区间和申请顺序。"),
    ("推1999", "push_1999", "A", "1999_structure_plan", "您具备融资基础，接下来关键是额度、成本、期限和银行顺序的结构设计。"),
    ("高客单顾问服务", "high_ticket", "S", "high_ticket_consulting", "您的重点不是能不能贷，而是怎样把额度和成本做到更优，建议安排1对1顾问预诊断。"),
    ("24小时未回复", "no_reply_24h", "", "", "昨天的诊断您看过了吗？如果方便，我可以用三句话说明当前最影响银行审批的点。"),
    ("7天重新激活", "reactivate_7d", "", "", "近期融资计划是否有变化？如果您愿意，我可以重新帮您核一下当前银行申请窗口。"),
    ("已支付感谢", "paid_thanks", "", "", "感谢信任，报告已解锁。建议先看银行视角和行动建议两章，有问题可以直接回复我。"),
    ("升级服务推荐", "upsell", "", "", "基础报告解决看清问题，下一阶段可以进一步做银行匹配或融资结构优化。"),
]


def ensure_default_scripts(db: Session) -> None:
    existing = {x.scenario for x in db.query(SalesScriptTemplate).all()}
    for name, scenario, grade, product, content in DEFAULT_SCRIPTS:
        if scenario not in existing:
            db.add(SalesScriptTemplate(
                name=name, scenario=scenario, lead_grade=grade,
                product_code=product, content=content, is_active=True
            ))
    db.commit()


def matched_scripts(db: Session, lead) -> list[SalesScriptTemplate]:
    return db.query(SalesScriptTemplate).filter(
        SalesScriptTemplate.is_active.is_(True),
        ((SalesScriptTemplate.lead_grade == "") | (SalesScriptTemplate.lead_grade == lead.lead_grade)),
        ((SalesScriptTemplate.product_code == "") | (SalesScriptTemplate.product_code == lead.recommended_product)),
    ).order_by(SalesScriptTemplate.id).all()
