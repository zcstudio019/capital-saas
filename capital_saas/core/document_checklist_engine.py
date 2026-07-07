from typing import Any


def generate_document_checklist(assessment: Any, product_code: str) -> dict:
    required = [
        {"category": "企业基础资料", "items": ["营业执照", "公司章程", "法人及股东身份证明"]},
        {"category": "财务资料", "items": ["近2年财务报表", "最近一期科目余额表", "主要负债明细"]},
        {"category": "银行流水", "items": ["企业近12个月银行流水", "主要回款账户说明"]},
        {"category": "经营证明", "items": ["前十大客户合同", "采购合同", "场地或经营证明"]},
    ]
    optional = []
    missing_risk = []
    if assessment.tax_status:
        required.append({"category": "纳税资料", "items": ["近12个月纳税申报表", "完税证明", "开票明细"]})
    else:
        missing_risk.append("纳税状态异常或资料不完整会显著降低税贷、信用贷准入率")
    if assessment.has_collateral:
        required.append({"category": "抵押物资料", "items": ["产权证", "评估资料", "权属人与婚姻/股东决议材料"]})
    else:
        optional.append({"category": "增信资料", "items": ["可提供的担保主体说明", "设备或其他可盘活资产清单"]})
    if assessment.receivable_days >= 60:
        required.append({"category": "应收账款/合同资料", "items": ["应收账龄表", "核心买方合同", "发票与回款记录", "确权材料"]})
    if not assessment.credit_status:
        missing_risk.append("征信异常需先准备说明、结清证明或修复证据，不宜直接多头申请")
    if assessment.monthly_cashflow <= 0:
        missing_risk.append("经营现金流不足，需补充未来13周现金流预测与还款来源证明")

    if product_code == "299_report":
        return {
            "required_documents": [item["category"] for item in required],
            "optional_documents": ["高级版本提供逐项资料清单与准备顺序"],
            "missing_risk": missing_risk[:2],
            "preparation_priority": ["先统一流水、纳税、合同、发票的经营口径"],
            "detail_level": "direction",
        }
    if product_code == "699_bank_match":
        required = required[:5]
        detail_level = "brief"
    else:
        detail_level = "full"
        optional.append({"category": "其他补充资料", "items": ["融资用途预算", "30/90/180天执行计划", "贷后监控指标表"]})
    return {
        "required_documents": required,
        "optional_documents": optional,
        "missing_risk": missing_risk,
        "preparation_priority": [
            "P0：征信、纳税、营业执照与银行流水",
            "P1：财务报表、负债明细、合同发票",
            "P2：抵押物、应收账款确权及融资用途证明",
        ],
        "detail_level": detail_level,
    }
