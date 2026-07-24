from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy.orm import Session

from core.bank_product_matcher import match_bank_products
from db.models import Assessment, Order
from services.settings_service import get_bool_setting, get_setting


DIMENSION_DEFINITIONS = [
    ("企业基本面", 15, "核验企业经营基础、持续经营能力与业务稳定性"),
    ("征信状况", 20, "识别企业及法人的信用瑕疵与查询风险"),
    ("流水质量", 15, "判断经营回款真实性、稳定性与还款来源"),
    ("负债情况", 15, "判断杠杆水平、期限错配与偿债压力"),
    ("司法风险", 10, "排查诉讼、执行、处罚及资产受限风险"),
    ("税务合规", 10, "判断纳税连续性、发票规范与税务融资基础"),
    ("资产状况", 5, "盘点可用于抵押、增信或盘活的核心资产"),
    ("融资能力", 10, "综合判断新增融资空间、可用渠道与申请时机"),
]

REPORT_BODY_PRODUCTS = {
    "299_report",
    "699_bank_match",
    "980_capital_health_report",
    "1999_structure_plan",
    "one_on_one_consulting",
    "high_ticket_consulting",
}
BANK_MATCH_PRODUCTS = {
    "699_bank_match",
    "1999_structure_plan",
    "one_on_one_consulting",
    "high_ticket_consulting",
}
STRUCTURE_PLAN_PRODUCTS = {
    "1999_structure_plan",
    "one_on_one_consulting",
    "high_ticket_consulting",
}


def _clamp(value: float, low: float = 1.0, high: float = 5.0) -> float:
    return round(max(low, min(high, value)), 1)


def _money(value: float | int | None) -> str:
    number = float(value or 0)
    if number >= 10_000:
        return f"{number / 10_000:,.1f}万元"
    return f"{number:,.0f}元"


def _percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def _yes_no(value: bool, yes: str = "符合", no: str = "需改善") -> str:
    return yes if value else no


def _status(raw_score: float) -> str:
    if raw_score >= 4:
        return "绿灯"
    if raw_score >= 3:
        return "黄灯"
    if raw_score >= 2:
        return "橙灯"
    return "红灯"


def _grade(total: int) -> str:
    if total >= 80:
        return "A"
    if total >= 70:
        return "B+"
    if total >= 60:
        return "B"
    if total >= 50:
        return "C"
    return "D"


def _risk_level(total: int) -> str:
    if total >= 80:
        return "健康"
    if total >= 60:
        return "亚健康"
    if total >= 40:
        return "高风险"
    return "危急"


def _item(name: str, result: str, basis: str, score: float) -> dict[str, Any]:
    return {
        "check_item": name,
        "check_result": result,
        "scoring_basis": basis,
        "score": _clamp(score),
    }


def _build_items(assessment: Assessment) -> dict[str, list[dict[str, Any]]]:
    revenue = max(float(assessment.annual_revenue or 0), 0)
    profit = float(assessment.net_profit or 0)
    monthly_flow = max(float(assessment.monthly_cashflow or 0), 0)
    debt = max(float(assessment.debt_total or 0), 0)
    short_debt = max(float(assessment.short_debt or 0), 0)
    years = max(int(assessment.years or 0), 0)
    employees = max(int(assessment.employee_count or 0), 0)
    debt_ratio = debt / revenue if revenue else 1
    short_ratio = short_debt / debt if debt else 0
    profit_margin = profit / revenue if revenue else 0
    flow_coverage = monthly_flow * 12 / revenue if revenue else 0
    receivable_days = max(int(assessment.receivable_days or 0), 0)
    funding_need = max(float(assessment.funding_need or 0), 0)
    financing_space = max(revenue * 0.35 - debt, 0)

    return {
        "企业基本面": [
            _item("企业名称", assessment.company_name, "企业主体信息完整", 5),
            _item("成立时间", f"持续经营{years}年", "经营3年以上较稳定", 5 if years >= 5 else 4 if years >= 3 else 2.5),
            _item("行业类型", assessment.industry or "待补充", "行业信息用于判断准入政策", 4 if assessment.industry else 2),
            _item("注册资本", "本次测评未采集", "建议补充工商登记信息", 3),
            _item("员工人数", f"{employees}人", "人员规模用于佐证经营稳定性", 4 if employees >= 20 else 3 if employees >= 5 else 2.5),
            _item("年营收", _money(revenue), "营收规模越稳定，授信基础越好", 5 if revenue >= 10_000_000 else 4 if revenue >= 3_000_000 else 3),
            _item("年净利润", _money(profit), "持续盈利有利于证明偿债来源", 5 if profit_margin >= .12 else 4 if profit > 0 else 2),
            _item("营收增长率", "本次测评未采集", "建议补充近三年营收数据", 3),
            _item("主营业务", assessment.industry or "待补充主营业务说明", "业务口径应与合同、开票和流水一致", 3.5),
            _item("上下游稳定性", "需结合合同与流水复核", "集中度越低、合作越稳定越有利", 3),
        ],
        "征信状况": [
            _item("企业征信状态", _yes_no(assessment.credit_status, "正常", "存在需核验事项"), "无逾期和不良记录为优", 4.5 if assessment.credit_status else 1.8),
            _item("企业贷款笔数", "需调取征信报告核验", "机构数与借款笔数过多会影响审批", 3),
            _item("企业逾期记录", _yes_no(assessment.credit_status, "未发现异常", "需核验逾期情况"), "当前逾期将显著影响准入", 4.5 if assessment.credit_status else 1.5),
            _item("企业关注或不良类", _yes_no(assessment.credit_status, "未发现异常", "需重点核验"), "关注及不良分类需先处理", 4.5 if assessment.credit_status else 1.5),
            _item("企业担保情况", "需补充对外担保明细", "或有负债会占用融资空间", 3),
            _item("法人逾期记录", _yes_no(assessment.credit_status, "未发现异常", "需调取法人征信"), "法人信用通常纳入企业授信审查", 4.5 if assessment.credit_status else 2),
            _item("近6月查询次数", "需调取征信报告核验", "建议控制机构查询频率", 3),
            _item("信用卡使用率", "需调取法人征信核验", "建议控制在合理区间", 3),
            _item("个人贷款余额", "需调取法人征信核验", "个人负债会影响担保能力", 3),
            _item("对外担保", "需补充担保明细", "高额担保可能形成代偿风险", 3),
            _item("多头借贷", "需结合征信明细核验", "机构数量过多会降低审批评价", 3),
        ],
        "流水质量": [
            _item("月均对公流入", _money(monthly_flow), "稳定经营流入是主要还款来源", 5 if monthly_flow >= revenue / 15 else 4 if monthly_flow > 0 else 1.5),
            _item("月均对公流出", "需补充完整对公流水", "流入流出应与业务规模匹配", 3),
            _item("经营流水占比", _percent(min(flow_coverage, 1)), "经营流水应覆盖主要营收", 5 if flow_coverage >= .8 else 4 if flow_coverage >= .5 else 2.5),
            _item("交易对手集中度", "需按流水明细测算", "单一客户占比过高会增加波动", 3),
            _item("流水稳定性", "较稳定" if monthly_flow > 0 else "需改善", "连续稳定流入优于临时大额入账", 4 if monthly_flow > 0 else 1.5),
            _item("内部转账占比", "需按流水明细识别", "内部循环流水不能作为有效经营收入", 3),
            _item("快进快出识别", "需按流水明细识别", "高频快进快出会削弱流水质量", 3),
            _item("月均个人流入", "需补充个人经营流水", "个人经营流水仅作辅助佐证", 3),
            _item("公私往来占比", "需补充账户明细", "建议公私分离、回款归集对公账户", 2.8),
            _item("日均余额", "需按流水明细测算", "稳定日均余额有利于偿债评估", 3),
        ],
        "负债情况": [
            _item("负债与营收比", _percent(debt_ratio), "建议控制整体杠杆水平", 5 if debt_ratio <= .3 else 4 if debt_ratio <= .6 else 2),
            _item("月供与月营收比", "需补充月供明细", "月供压力应与经营现金流匹配", 3),
            _item("高息资金占比", "需补充借款成本明细", "优先置换高成本短期资金", 3),
            _item("短贷长用情况", _percent(short_ratio) + "为短期负债占比", "短期资金用于长期投入会形成期限错配", 5 if short_ratio <= .35 else 3.5 if short_ratio <= .65 else 2),
            _item("多头借贷情况", "需结合征信核验", "控制融资机构数量与查询频率", 3),
            _item("隐性负债排查", "需补充担保及民间借款明细", "隐性负债必须纳入统一偿债测算", 3),
        ],
        "司法风险": [
            _item("民事诉讼作为被告", "需通过公开数据复核", "重大未决诉讼可能影响授信", 3.5),
            _item("民事诉讼作为原告", "需通过公开数据复核", "关注应收款回收及诉讼周期", 3.5),
            _item("被执行记录", "需通过公开数据复核", "被执行记录属于重点风险信号", 3.5),
            _item("失信被执行人", "需通过公开数据复核", "失信状态通常影响银行准入", 3.5),
            _item("行政处罚", "需通过公开数据复核", "重大处罚需准备情况说明", 3.5),
            _item("限制高消费", "需通过公开数据复核", "限制高消费属于重大融资障碍", 3.5),
            _item("股权冻结", "需通过公开数据复核", "股权冻结可能影响治理与增信", 3.5),
        ],
        "税务合规": [
            _item("纳税信用等级", _yes_no(assessment.tax_status, "纳税状态正常", "需核验异常"), "连续正常纳税有利于税票类融资", 4.5 if assessment.tax_status else 1.8),
            _item("年纳税总额", "需补充完税证明", "纳税额可用于交叉验证经营规模", 3),
            _item("纳税及时性", _yes_no(assessment.tax_status, "正常", "需改善"), "逾期申报和欠税会影响准入", 4.5 if assessment.tax_status else 1.8),
            _item("发票合规性", "需补充开票明细", "发票应与合同、流水和收入一致", 3.2),
            _item("关联交易定价", "需补充关联交易说明", "异常定价会影响收入真实性判断", 3),
            _item("社保公积金缴纳", "需补充缴纳记录", "连续缴纳可佐证真实经营与用工", 3),
        ],
        "资产状况": [
            _item("不动产", _yes_no(assessment.has_collateral, "具备可评估抵押物", "暂未提供"), "权属清晰的抵押物可增强授信", 4.5 if assessment.has_collateral else 2),
            _item("车辆", "需补充车辆清单", "经营车辆可作为资产佐证", 3),
            _item("知识产权", "需补充证书及权属资料", "有效知识产权可用于增信或质押", 3),
            _item("应收账款", f"平均回款周期{receivable_days}天", "账期越短、付款方越优质越有利", 5 if receivable_days <= 45 else 3.5 if receivable_days <= 90 else 2),
            _item("存货", "需补充存货明细", "关注变现能力与跌价风险", 3),
            _item("对外投资", "需补充投资明细", "核验资金占用及投资收益稳定性", 3),
        ],
        "融资能力": [
            _item("当前负债总额", _money(debt), "结合营收判断杠杆与偿债压力", 5 if debt_ratio <= .3 else 4 if debt_ratio <= .6 else 2),
            _item("可新增融资空间", _money(financing_space), "按营收与现有负债进行审慎测算", 5 if financing_space >= funding_need else 3.5 if financing_space > 0 else 1.5),
            _item("净可用融资额", _money(min(financing_space, funding_need or financing_space)), "以需求额与审慎空间孰低估算", 4 if financing_space > 0 else 1.5),
            _item("融资后总负债率", _percent((debt + min(financing_space, funding_need)) / revenue) if revenue else "无法测算", "融资后杠杆应保持可持续", 4 if revenue and (debt + min(financing_space, funding_need)) / revenue <= .65 else 2),
            _item("可操作渠道", "银行信用、抵押或经营场景融资", "最终以产品准入和金融机构审批为准", 4 if assessment.credit_status or assessment.has_collateral else 2),
            _item("推荐融资路径", "直接申请型" if assessment.score >= 80 else "优化后申请型", "先处理高优先级异常项再确定申请顺序", 4.5 if assessment.score >= 70 else 2.5),
        ],
    }


def _build_dimensions(assessment: Assessment) -> list[dict[str, Any]]:
    item_groups = _build_items(assessment)
    dimensions: list[dict[str, Any]] = []
    for name, weight, purpose in DIMENSION_DEFINITIONS:
        items = item_groups[name]
        raw_score = _clamp(sum(item["score"] for item in items) / len(items))
        weighted_score = round(raw_score * weight / 5, 1)
        abnormal = [
            {
                "check_item": item["check_item"],
                "description": item["check_result"],
                "suggestion": item["scoring_basis"],
            }
            for item in items
            if item["score"] < 3
        ]
        dimensions.append(
            {
                "dimension_name": name,
                "weight": weight,
                "raw_score": raw_score,
                "weighted_score": weighted_score,
                "status_light": _status(raw_score),
                "purpose": purpose,
                "items": items,
                "summary": f"{name}得分{raw_score:.1f}分，当前为{_status(raw_score)}状态。",
                "abnormal_items": abnormal,
            }
        )
    return dimensions


def _build_warnings(dimensions: list[dict[str, Any]]) -> list[dict[str, str]]:
    warnings: list[dict[str, str]] = []
    for dimension in dimensions:
        abnormal = dimension["abnormal_items"]
        if abnormal:
            level = "红灯" if dimension["raw_score"] < 2 else "黄灯"
            first = abnormal[0]
            warnings.append(
                {
                    "warning_level": level,
                    "warning_item": f"{dimension['dimension_name']}：{first['check_item']}",
                    "description": first["description"],
                    "urgency": "必须立即处理，否则影响融资" if level == "红灯" else "需要规划改善",
                    "suggestion": first["suggestion"],
                    "deadline": "30天内" if level == "红灯" else "3个月内",
                }
            )
        else:
            warnings.append(
                {
                    "warning_level": "绿灯",
                    "warning_item": dimension["dimension_name"],
                    "description": dimension["summary"],
                    "urgency": "目前安全但需持续关注",
                    "suggestion": "保持数据连续性，每月复核一次。",
                    "deadline": "持续跟踪",
                }
            )
    order = {"红灯": 0, "黄灯": 1, "绿灯": 2}
    return sorted(warnings, key=lambda item: order[item["warning_level"]])


def _remediation_plans(assessment: Assessment) -> list[dict[str, Any]]:
    debt = max(float(assessment.debt_total or 0), 0)
    short = max(float(assessment.short_debt or 0), 0)
    return [
        {
            "title": "征信修复方案",
            "rows": [
                ["征信查询次数", "需核验", "近6个月合理控制", "集中选择目标机构，避免短期多头申请", "3个月"],
                ["信用卡使用率", "需核验", "控制在合理区间", "优先归还循环额度并保留正常使用记录", "1—3个月"],
                ["小贷记录", "需核验", "压降低额高频借款", "结清高成本小额借款并保留结清证明", "1—3个月"],
                ["征信静养期", "尚未安排", "形成稳定信用窗口", "停止非必要查询，保持按时还款", "3—6个月"],
            ],
        },
        {
            "title": "负债结构优化方案",
            "rows": [
                ["高息负债占比", "需补充成本明细", "优先降至可控水平", "按利率从高到低制定置换顺序", "1—3个月"],
                ["综合融资成本", "需统一测算", "逐步降低", "用银行中长期资金置换短期高成本资金", "3—6个月"],
                ["短贷长用", _percent(short / debt) if debt else "无存量负债", "降低期限错配", "将长期投入匹配中长期融资", "3—6个月"],
                ["负债机构数", "需核验", "保留核心合作机构", "归并零散授信，避免多头管理", "3—6个月"],
            ],
        },
        {
            "title": "流水规范方案",
            "rows": [
                ["公私分离", "需改善", "经营回款主要进入对公账户", "统一收款账户并减少无业务背景往来", "30天"],
                ["对公流水占比", "需复核", "覆盖主要经营收入", "合同、开票、回款使用一致的企业主体", "1—3个月"],
                ["日均余额", "需测算", "形成稳定资金沉淀", "设置最低运营资金线并管理付款节奏", "1—3个月"],
                ["客户回款节奏", f"平均账期{assessment.receivable_days}天", "缩短并稳定回款周期", "按客户建立应收账款催收表", "1—3个月"],
            ],
        },
        {
            "title": "资产增值方案",
            "rows": [
                ["知识产权", "需盘点", "形成权属清晰的资产清单", "整理证书、研发投入和应用证明", "1—3个月"],
                ["应收账款", f"平均账期{assessment.receivable_days}天", "提高确权与可融资性", "形成合同、发票、验收、回款闭环", "30—90天"],
                ["抵押物", _yes_no(assessment.has_collateral, "已具备", "暂未提供"), "完成权属与价值核验", "准备权证、估值和现有抵押情况说明", "30—60天"],
                ["核心资产证明", "资料分散", "形成统一资产包", "建立资产台账并按季度更新证明", "30天"],
            ],
        },
    ]


def _document_checklist() -> list[dict[str, Any]]:
    return [
        {"category": "企业基础资料", "items": ["营业执照", "公司章程", "法人及实际控制人身份证明", "工商变更记录"]},
        {"category": "财务资料", "items": ["近两年财务报表", "近期科目余额表", "应收应付明细", "存量负债明细"]},
        {"category": "银行流水", "items": ["近12个月对公流水", "主要经营账户流水", "大额交易说明", "日均余额统计"]},
        {"category": "纳税资料", "items": ["纳税申报表", "完税证明", "开票明细", "纳税信用等级证明"]},
        {"category": "经营证明", "items": ["主要合同与订单", "发票及验收材料", "经营场地证明", "上下游合作证明"]},
        {"category": "资金用途资料", "items": ["资金用途说明", "采购或项目预算", "付款计划", "还款来源说明"]},
        {"category": "抵押物资料（如适用）", "items": ["产权证明", "评估资料", "现有抵押情况", "共有权人同意材料"]},
        {"category": "补充资料", "items": ["企业及法人征信", "涉诉情况说明", "对外担保明细", "金融机构要求的其他材料"]},
    ]


def _action_plans() -> list[dict[str, Any]]:
    return [
        {
            "period": "未来30天行动计划",
            "goal": "完成风险止损与基础资料归集",
            "actions": ["核验企业及法人征信", "建立全部负债和融资成本台账", "归集流水、纳税、合同与发票", "明确本轮融资用途和还款来源"],
            "responsible": "企业负责人、财务负责人",
            "deliverable": "风险核验表、基础资料包、融资需求说明",
            "deadline": "第30天",
        },
        {
            "period": "未来90天行动计划",
            "goal": "完成关键指标优化并形成可申请材料包",
            "actions": ["执行征信静养与高息负债压降", "提升对公回款占比", "修复财税与业务口径差异", "针对目标产品补齐准入材料"],
            "responsible": "财务负责人、业务负责人、融资顾问",
            "deliverable": "问题修复记录、目标产品材料包、申请顺序表",
            "deadline": "第90天",
        },
        {
            "period": "未来180天行动计划",
            "goal": "完成核心融资申请并优化存量结构",
            "actions": ["按顺序推进银行预审", "锁定主授信与备用渠道", "置换高成本短期负债", "建立月度贷后监测机制"],
            "responsible": "企业负责人、融资顾问",
            "deliverable": "授信申请进度表、负债置换方案、贷后监测表",
            "deadline": "第180天",
        },
        {
            "period": "6个月融资落地节奏",
            "goal": "形成准备、预审、申请、审批和贷后管理闭环",
            "actions": ["第1月完成体检与资料盘点", "第2—3月完成指标优化和产品预匹配", "第4月提交首批申请", "第5月补件与审批沟通", "第6月完成放款或备选方案切换"],
            "responsible": "企业融资项目组",
            "deliverable": "融资落地闭环及下一周期资本计划",
            "deadline": "6个月",
        },
    ]


def paid_product_codes(db: Session, assessment_id: int) -> set[str]:
    return {
        item.product_code
        for item in db.query(Order).filter(
            Order.assessment_id == assessment_id,
            Order.status == "paid",
        )
        if item.product_code
    }


def report_entitlements(db: Session, assessment_id: int, admin_override: bool = False) -> dict[str, Any]:
    codes = paid_product_codes(db, assessment_id)
    if admin_override:
        return {"paid_products": codes, "body_unlocked": True, "bank_match_unlocked": True, "structure_unlocked": True}
    return {
        "paid_products": codes,
        "body_unlocked": bool(codes & REPORT_BODY_PRODUCTS),
        "bank_match_unlocked": bool(codes & BANK_MATCH_PRODUCTS),
        "structure_unlocked": bool(codes & STRUCTURE_PLAN_PRODUCTS),
    }


def build_capital_health_report(
    db: Session,
    assessment: Assessment,
    admin_override: bool = False,
) -> dict[str, Any]:
    dimensions = _build_dimensions(assessment)
    total = int(round(sum(item["weighted_score"] for item in dimensions)))
    warnings = _build_warnings(dimensions)
    entitlements = report_entitlements(db, assessment.id, admin_override)
    generated_at = assessment.report.created_at if assessment.report else assessment.created_at
    validity_days = int(get_setting(db, "capital_health_report_validity_days", "90"))
    real_matches = match_bank_products(db, assessment, limit=5, real_only=True)
    bank_products = real_matches.get("matched_products", [])
    revenue = max(float(assessment.annual_revenue or 0), 0)
    debt = max(float(assessment.debt_total or 0), 0)
    need = max(float(assessment.funding_need or 0), 0)
    financing_space = max(revenue * 0.35 - debt, 0)
    usable = min(need or financing_space, financing_space)
    target_total = debt + usable
    return {
        "title": "企业资本健康体检报告",
        "subtitle": "Enterprise Capital Health Check Report",
        "show_subtitle": get_bool_setting(db, "capital_health_show_english_subtitle", True),
        "report_no": f"CHCR-{generated_at.year}-{assessment.report.id if assessment.report else assessment.id:06d}",
        "report_date": generated_at.strftime("%Y年%m月%d日"),
        "valid_until": (generated_at + timedelta(days=validity_days)).strftime("%Y年%m月%d日"),
        "company_name": assessment.company_name,
        "check_type": "融资前资本健康度全项检查",
        "institution": get_setting(db, "capital_health_institution", "沪上银 · 企业资本健康管理中心"),
        "disclaimer": "本报告基于企业提供资料及截至报告日期可获取的公开数据编制，旨在为企业融资决策提供参考依据，不构成任何形式的融资承诺或担保。实际融资结果取决于金融机构审批政策、企业资质变化等不可控因素。",
        "score": total,
        "grade": _grade(total),
        "risk_level": _risk_level(total),
        "financing_advice": "建议按体检异常项先优化、后申请，优先建立稳定的对公流水和清晰的负债结构。" if total < 80 else "当前具备较好融资基础，建议按产品适配度和查询影响安排申请顺序。",
        "conclusions": [
            f"企业资本健康度综合得分为{total}分，综合评级为{_grade(total)}，处于{_risk_level(total)}状态。",
            f"当前优先关注{warnings[0]['warning_item']}，应在{warnings[0]['deadline']}完成核验或改善。",
            "融资申请应以资料口径一致、负债透明和经营现金流可验证为前提。",
        ],
        "dimensions": dimensions,
        "warnings": warnings,
        "top_risks": [item for item in warnings if item["warning_level"] != "绿灯"][:3] or warnings[:3],
        "initial_suggestion": warnings[0]["suggestion"],
        "remediation_plans": _remediation_plans(assessment),
        "financing_capacity": {
            "current_state": f"{_grade(total)}类（{_risk_level(total)}）",
            "path": "直接申请型" if total >= 80 else "优化型",
            "advice": "可启动产品预匹配并控制申请顺序" if total >= 80 else "先优化3个月，再启动正式融资",
            "metrics": [
                ["当前负债总额", _money(debt)],
                ["可新增融资空间", _money(financing_space)],
                ["净可用融资额", _money(usable)],
                ["融资后总负债率", _percent(target_total / revenue) if revenue else "暂无法测算"],
            ],
            "transition": [
                ["负债结构", "期限与成本明细待统一", "成本、期限和机构数可控", "建立负债台账并优先置换高成本短债", "3—6个月"],
                ["流水质量", "对公流水需进一步规范", "经营回款稳定且公私分离", "统一回款账户并管理日均余额", "1—3个月"],
                ["融资资料", "资料分散、口径待复核", "形成目标银行可提交材料包", "按真实产品准入要求补齐资料", "1—3个月"],
            ],
            "bank_products": bank_products,
            "application_order": real_matches.get("best_application_order", []),
        },
        "document_checklist": _document_checklist(),
        "action_plans": _action_plans(),
        "entitlements": entitlements,
        "prices": {
            "report": get_setting(db, "capital_health_report_price", "980"),
            "structure": get_setting(db, "capital_structure_plan_price", "1999"),
            "consulting": get_setting(db, "one_on_one_consulting_price", "9800"),
        },
    }
