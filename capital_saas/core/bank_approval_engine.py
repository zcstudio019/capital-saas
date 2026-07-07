from dataclasses import asdict, dataclass


@dataclass
class BankApprovalResult:
    approval_probability: float
    estimated_credit_limit: str
    likely_rejection_reasons: list[str]
    bank_preference: list[str]
    application_order: list[str]
    improvement_actions: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


def simulate_bank_approval(data: dict, score: int) -> BankApprovalResult:
    revenue = max(float(data.get("annual_revenue", 0)), 0)
    monthly_cashflow = float(data.get("monthly_cashflow", 0))
    debt = max(float(data.get("debt_total", 0)), 0)
    short_debt = max(float(data.get("short_debt", 0)), 0)
    receivable_days = int(data.get("receivable_days", 0))
    funding_need = max(float(data.get("funding_need", 0)), 0)
    collateral = bool(data.get("has_collateral"))
    tax_ok = bool(data.get("tax_status"))
    credit_ok = bool(data.get("credit_status"))

    probability = 0.18 + score * 0.0055
    probability += 0.08 if credit_ok else -0.22
    probability += 0.07 if tax_ok else -0.16
    probability += 0.10 if collateral else 0
    probability += 0.06 if monthly_cashflow > 0 else -0.14
    short_ratio = short_debt / debt if debt > 0 else 0
    debt_ratio = debt / revenue if revenue > 0 else 1
    if short_ratio > 0.7:
        probability -= 0.12
    if debt_ratio > 0.65:
        probability -= 0.14
    if receivable_days > 120:
        probability -= 0.12
    elif receivable_days > 75:
        probability -= 0.06
    if score < 60:
        probability = min(probability, 0.42)
    probability = round(max(0.05, min(probability, 0.95)), 2)

    operating_capacity = max(monthly_cashflow * 8, revenue * 0.08)
    revenue_capacity = revenue * (0.32 if collateral else 0.18)
    debt_deduction = debt * (0.22 if collateral else 0.32)
    score_factor = 1.0 if score >= 85 else 0.82 if score >= 75 else 0.62 if score >= 60 else 0.35
    high = max(100_000, min(funding_need * 1.15 or revenue_capacity, revenue_capacity + operating_capacity - debt_deduction) * score_factor)
    if collateral:
        high *= 1.2
    low = max(50_000, high * 0.55)
    estimated_credit_limit = f"{low / 10000:.0f}万—{high / 10000:.0f}万元"

    rejection_reasons: list[str] = []
    if not credit_ok:
        rejection_reasons.append("征信存在异常或近期查询记录可能超出银行容忍度")
    if not tax_ok:
        rejection_reasons.append("纳税连续性或申报收入不足，难以证明稳定经营")
    if monthly_cashflow <= 0:
        rejection_reasons.append("经营现金流为负，第一还款来源不足")
    elif monthly_cashflow < max(revenue / 36, 1):
        rejection_reasons.append("月均现金流相对收入偏弱，偿债覆盖能力不足")
    if short_ratio > 0.7:
        rejection_reasons.append("短期负债占比过高，存在集中到期与期限错配")
    if debt_ratio > 0.65:
        rejection_reasons.append("存量负债相对营收偏高，新增授信空间受限")
    if receivable_days > 90:
        rejection_reasons.append(f"应收账款周期达到{receivable_days}天，回款不确定性较高")
    if funding_need > revenue * 0.4 and revenue > 0:
        rejection_reasons.append("融资需求相对年营收偏大，资金用途与还款来源需进一步证明")
    if not rejection_reasons:
        rejection_reasons.append("暂无明显硬伤，主要关注资料一致性、资金用途和申请顺序")

    preference: list[str] = []
    if collateral:
        preference.extend(["城商行经营性抵押贷", "股份制银行抵押经营贷"])
    if tax_ok and credit_ok and revenue >= 1_000_000:
        preference.extend(["城商行税贷/信用贷", "股份制银行经营信用贷"])
    if receivable_days > 60:
        preference.append("供应链金融或应收账款保理")
    if score >= 80:
        preference.append("国有大行普惠经营贷")
    if score < 60:
        preference = ["先做资料与指标修复", "必要时评估担保增信渠道"]

    if score < 60:
        application_order = ["先修复征信、纳税、现金流和负债结构", "完成银行预审测算", "再选择城商行或增信类产品"]
    elif collateral:
        application_order = ["先申请抵押类经营贷锁定核心额度", "再补充城商行/股份制信用贷", "最后评估国有大行低成本授信"]
    elif tax_ok and credit_ok:
        application_order = ["先城商行税贷或经营信用贷", "再股份制银行补充授信", "资料稳定后尝试国有大行普惠产品"]
    else:
        application_order = ["先完成资料修复与预审", "再申请城商行", "最后评估小贷/担保等补充渠道"]

    actions = [
        "统一银行流水、纳税申报、财务报表与合同口径，避免数据相互矛盾",
        "准备未来13周现金流预测，明确新增融资的本息覆盖来源",
    ]
    if receivable_days > 60:
        actions.append("压缩回款周期或提供核心客户应收凭证，评估保理/供应链融资")
    if short_ratio > 0.6:
        actions.append("优先置换短期高成本债务，降低未来6个月集中偿付压力")
    if not collateral:
        actions.append("补充纳税、订单、发票和稳定流水证据，增强纯信用授信依据")
    if score < 60:
        actions.append("当前不建议批量提交银行申请，先完成至少60—90天指标修复")

    return BankApprovalResult(
        approval_probability=probability,
        estimated_credit_limit=estimated_credit_limit,
        likely_rejection_reasons=rejection_reasons,
        bank_preference=list(dict.fromkeys(preference)),
        application_order=application_order,
        improvement_actions=actions,
    )
