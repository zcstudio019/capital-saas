from typing import Any


FULL_REQUIRED_DOCUMENTS = [
    {
        "category": "企业基础资料",
        "purpose": "用于确认企业主体、经营资质、股权结构和实际控制人信息。",
        "priority": "高",
        "items": ["营业执照", "公司章程", "法人身份证", "股东/实控人信息", "开户许可证或基本户信息", "企业工商变更记录"],
        "missing_risk": "如果缺少该类资料，可能影响银行对企业主体真实性、控制权和基础准入的判断。",
    },
    {
        "category": "财务资料",
        "purpose": "用于判断企业盈利能力、资产负债结构、偿债压力和财务稳定性。",
        "priority": "高",
        "items": ["最近一年财务报表", "最近6个月科目余额表", "应收账款明细", "应付账款明细", "主要资产负债明细", "利润表/现金流相关资料"],
        "missing_risk": "如果缺少该类资料，银行难以判断真实经营规模和偿债能力，可能压低额度或要求补充材料。",
    },
    {
        "category": "银行流水",
        "purpose": "用于判断企业现金流质量、经营稳定性、回款能力和还款来源。",
        "priority": "高",
        "items": ["最近6-12个月对公流水", "最近6-12个月个人经营流水", "主要收款账户流水", "主要付款账户流水", "大额进出账说明"],
        "missing_risk": "如果缺少该类资料，可能影响银行对收入真实性、现金流连续性和还款能力的判断。",
    },
    {
        "category": "纳税资料",
        "purpose": "用于判断企业纳税连续性、开票稳定性和税务合规情况。",
        "priority": "高",
        "items": ["近12个月纳税申报表", "完税证明", "增值税申报记录", "企业所得税申报记录", "开票明细"],
        "missing_risk": "如果缺少该类资料，税贷、信用贷和线上化产品可能无法准确核额，甚至无法准入。",
    },
    {
        "category": "经营证明",
        "purpose": "用于证明企业真实经营、上下游交易关系和订单履约能力。",
        "priority": "中",
        "items": ["主要销售合同", "采购合同", "订单记录", "发票", "场地租赁合同", "经营照片或经营场所证明"],
        "missing_risk": "如果缺少该类资料，银行可能认为经营真实性不足，要求补充核验或现场尽调。",
    },
    {
        "category": "资金用途资料",
        "purpose": "用于说明贷款资金用途、资金安排和后续还款来源。",
        "priority": "中",
        "items": ["采购计划", "备货计划", "工资/租金/货款支付计划", "项目投入预算", "还款来源说明"],
        "missing_risk": "如果缺少该类资料，银行可能无法确认资金闭环，影响审批通过率和放款节奏。",
    },
    {
        "category": "抵押物资料（如适用）",
        "purpose": "用于评估可抵押资产价值、权属清晰度和增信能力。",
        "priority": "中",
        "items": ["房产证或不动产权证", "抵押物评估资料", "权属人身份证明", "共有权人同意材料", "房贷/抵押情况说明"],
        "missing_risk": "如果融资方案需要抵押增信但资料不完整，可能导致评估延迟、额度下降或无法办理抵押。",
    },
    {
        "category": "补充资料",
        "purpose": "用于补充说明征信、司法、股东和银行个性化审查要求。",
        "priority": "低",
        "items": ["企业征信", "法人征信", "股东征信", "诉讼/执行情况说明", "其他银行要求补充材料"],
        "missing_risk": "如果存在征信、诉讼或执行瑕疵但没有说明材料，可能影响银行风险判断和审批结论。",
    },
]


def generate_document_checklist(assessment: Any, product_code: str) -> dict:
    missing_risk = []
    if not getattr(assessment, "tax_status", True):
        missing_risk.append("纳税状态异常或资料不完整会降低税贷、信用贷准入概率。")
    if not getattr(assessment, "credit_status", True):
        missing_risk.append("征信异常需先准备说明、结清证明或修复证据，不宜直接多头申请。")
    if getattr(assessment, "monthly_cashflow", 0) <= 0:
        missing_risk.append("经营现金流不足时，需补充未来现金流预测与还款来源证明。")

    return {
        "required_documents": FULL_REQUIRED_DOCUMENTS,
        "optional_documents": [
            {"category": "银行申请材料包", "items": ["授信申请表", "企业授权书", "实控人授权书", "银行个性化补充资料"]},
        ],
        "missing_risk": missing_risk,
        "preparation_priority": [
            "P0：先补齐营业执照、征信、纳税、银行流水等硬准入资料。",
            "P1：整理财务报表、应收应付、合同、发票等经营真实性材料。",
            "P2：根据目标银行补充抵押物、资金用途和执行计划材料。",
        ],
        "detail_level": "full" if product_code == "1999_structure_plan" else "preview",
    }
