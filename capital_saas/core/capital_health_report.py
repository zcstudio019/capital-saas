from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from core.bank_product_matcher import match_bank_products
from core.pricing_engine import get_product
from db.models import AdvisorBooking, Assessment, Order, ReportVersion, UploadedDocument
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


def _item(name: str, result: str, basis: str, score: float | None) -> dict[str, Any]:
    return {
        "check_item": name,
        "check_result": result,
        "scoring_basis": basis,
        "score": _clamp(score) if score is not None else None,
        "needs_verification": score is None,
    }


def _missing_item(name: str) -> dict[str, Any]:
    return _item(
        name,
        "待补充资料核验",
        "当前资料不足，暂按保守口径评估",
        None,
    )


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
            _missing_item("注册资本"),
            _item("员工人数", f"{employees}人", "人员规模用于佐证经营稳定性", 4 if employees >= 20 else 3 if employees >= 5 else 2.5),
            _item("年营收", _money(revenue), "营收规模越稳定，授信基础越好", 5 if revenue >= 10_000_000 else 4 if revenue >= 3_000_000 else 3),
            _item("年净利润", _money(profit), "持续盈利有利于证明偿债来源", 5 if profit_margin >= .12 else 4 if profit > 0 else 2),
            _missing_item("营收增长率"),
            _item("主营业务", assessment.industry or "待补充主营业务说明", "业务口径应与合同、开票和流水一致", 3.5),
            _missing_item("上下游稳定性"),
        ],
        "征信状况": [
            _item("企业征信状态", _yes_no(assessment.credit_status, "正常", "存在需核验事项"), "无逾期和不良记录为优", 4.5 if assessment.credit_status else 1.8),
            _missing_item("企业贷款笔数"),
            _item("企业逾期记录", _yes_no(assessment.credit_status, "未发现异常", "需核验逾期情况"), "当前逾期将显著影响准入", 4.5 if assessment.credit_status else 1.5),
            _item("企业关注或不良类", _yes_no(assessment.credit_status, "未发现异常", "需重点核验"), "关注及不良分类需先处理", 4.5 if assessment.credit_status else 1.5),
            _missing_item("企业担保情况"),
            _item("法人逾期记录", _yes_no(assessment.credit_status, "未发现异常", "需调取法人征信"), "法人信用通常纳入企业授信审查", 4.5 if assessment.credit_status else 2),
            _missing_item("近6月查询次数"),
            _missing_item("信用卡使用率"),
            _missing_item("个人贷款余额"),
            _missing_item("对外担保"),
            _missing_item("多头借贷"),
        ],
        "流水质量": [
            _item("月均对公流入", _money(monthly_flow), "稳定经营流入是主要还款来源", 5 if monthly_flow >= revenue / 15 else 4 if monthly_flow > 0 else 1.5),
            _missing_item("月均对公流出"),
            _item("经营流水占比", _percent(min(flow_coverage, 1)), "经营流水应覆盖主要营收", 5 if flow_coverage >= .8 else 4 if flow_coverage >= .5 else 2.5),
            _missing_item("交易对手集中度"),
            _item("流水稳定性", "较稳定" if monthly_flow > 0 else "需改善", "连续稳定流入优于临时大额入账", 4 if monthly_flow > 0 else 1.5),
            _missing_item("内部转账占比"),
            _missing_item("快进快出识别"),
            _missing_item("月均个人流入"),
            _item("公私往来占比", "需补充账户明细", "建议公私分离、回款归集对公账户", 2.8),
            _missing_item("日均余额"),
        ],
        "负债情况": [
            _item("负债与营收比", _percent(debt_ratio), "建议控制整体杠杆水平", 5 if debt_ratio <= .3 else 4 if debt_ratio <= .6 else 2),
            _missing_item("月供与月营收比"),
            _missing_item("高息资金占比"),
            _item("短贷长用情况", _percent(short_ratio) + "为短期负债占比", "短期资金用于长期投入会形成期限错配", 5 if short_ratio <= .35 else 3.5 if short_ratio <= .65 else 2),
            _missing_item("多头借贷情况"),
            _missing_item("隐性负债排查"),
        ],
        "司法风险": [
            _missing_item("民事诉讼作为被告"),
            _missing_item("民事诉讼作为原告"),
            _missing_item("被执行记录"),
            _missing_item("失信被执行人"),
            _missing_item("行政处罚"),
            _missing_item("限制高消费"),
            _missing_item("股权冻结"),
        ],
        "税务合规": [
            _item("纳税信用等级", _yes_no(assessment.tax_status, "纳税状态正常", "需核验异常"), "连续正常纳税有利于税票类融资", 4.5 if assessment.tax_status else 1.8),
            _missing_item("年纳税总额"),
            _item("纳税及时性", _yes_no(assessment.tax_status, "正常", "需改善"), "逾期申报和欠税会影响准入", 4.5 if assessment.tax_status else 1.8),
            _item("发票合规性", "需补充开票明细", "发票应与合同、流水和收入一致", 3.2),
            _missing_item("关联交易定价"),
            _missing_item("社保公积金缴纳"),
        ],
        "资产状况": [
            _item("不动产", _yes_no(assessment.has_collateral, "具备可评估抵押物", "暂未提供"), "权属清晰的抵押物可增强授信", 4.5 if assessment.has_collateral else 2),
            _missing_item("车辆"),
            _missing_item("知识产权"),
            _item("应收账款", f"平均回款周期{receivable_days}天", "账期越短、付款方越优质越有利", 5 if receivable_days <= 45 else 3.5 if receivable_days <= 90 else 2),
            _missing_item("存货"),
            _missing_item("对外投资"),
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
        scored_items = [item for item in items if item["score"] is not None]
        raw_score = _clamp(
            sum(item["score"] for item in scored_items) / len(scored_items)
            if scored_items else 3.0
        )
        weighted_score = round(raw_score * weight / 5, 1)
        abnormal = [
            {
                "check_item": item["check_item"],
                "description": item["check_result"],
                "suggestion": item["scoring_basis"],
            }
            for item in items
            if item["score"] is not None and item["score"] < 3
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
                "status_description": {
                    "企业基本面": "经营基础与持续经营能力综合表现",
                    "征信状况": "信用基础明确，明细仍待征信报告核验",
                    "流水质量": "经营回款稳定性及账户规范程度",
                    "负债情况": "杠杆水平与期限结构的承压程度",
                    "司法风险": "公开司法信息尚待正式数据复核",
                    "税务合规": "纳税连续性与税务融资基础",
                    "资产状况": "可抵押、增信及盘活资产基础",
                    "融资能力": "当前申请条件与新增融资准备度",
                }[name],
                "summary": f"{name}当前得分{raw_score:.1f}分，已识别信息显示为{_status(raw_score)}状态；未采集项目将在资料核验后更新。",
                "abnormal_items": abnormal,
                "missing_count": len(items) - len(scored_items),
                "improvement_direction": {
                    "企业基本面": "补齐近三年经营数据并验证上下游稳定性。",
                    "征信状况": "调取企业及法人征信，统一核验查询、贷款和担保明细。",
                    "流水质量": "归集完整流水并验证经营回款、日均余额和交易对手结构。",
                    "负债情况": "建立负债台账，补齐月供、成本、期限和融资机构信息。",
                    "司法风险": "以最新公开司法数据及企业说明完成复核。",
                    "税务合规": "补齐完税、开票与社保记录，核对业务口径一致性。",
                    "资产状况": "形成权属清晰的资产清单及证明材料。",
                    "融资能力": "先完成资料核验和问题修复，再锁定申请路径。",
                }[name],
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


def _document_plan(db: Session, assessment: Assessment) -> list[dict[str, Any]]:
    uploaded = db.query(UploadedDocument).filter(
        UploadedDocument.assessment_id == assessment.id,
        UploadedDocument.deleted_at.is_(None),
    ).all()
    uploaded_text = " ".join(f"{item.document_category} {item.file_name}" for item in uploaded)
    definitions = [
        ("企业主体资料", "确认主体、股权和实际控制人", "高", "立即准备", ["营业执照", "公司章程", "法人及实控人身份证明"]),
        ("财务与经营数据", "判断盈利、偿债和经营稳定性", "高", "立即准备", ["近两年财务报表", "科目余额表", "应收应付明细"]),
        ("银行流水", "验证收入真实性和还款来源", "高", "立即准备", ["近12个月对公流水", "主要经营账户流水", "大额交易说明"]),
        ("纳税与开票", "验证税务合规和经营规模", "高", "预审前准备", ["纳税申报表", "完税证明", "开票明细"]),
        ("征信资料", "核验贷款、查询、逾期和担保", "高", "预审前准备", ["企业征信报告", "法人征信报告", "存量贷款明细"]),
        ("资金用途证明", "说明融资用途和还款闭环", "中", "预审前准备", ["资金用途说明", "采购或项目预算", "还款来源说明"]),
        ("抵押或增信资料", "评估抵押、担保及增信条件", "中", "银行要求后补充", ["产权证明", "现有抵押情况", "评估资料"]),
        ("产品专项材料", "满足目标产品个性化准入要求", "中", "银行要求后补充", ["产品申请表", "专项经营证明", "银行补充材料"]),
    ]
    groups: list[dict[str, Any]] = []
    for category, purpose, priority, batch, names in definitions:
        applicable = not (category == "抵押或增信资料" and not assessment.has_collateral)
        items = []
        for name in names:
            keywords = [name[:2], category[:2]]
            matching_docs = [
                item for item in uploaded
                if any(word and word in f"{item.document_category} {item.file_name}" for word in keywords)
            ]
            if not applicable:
                status = "暂不适用"
            elif matching_docs:
                status = "已具备" if any(item.verify_status == "verified" for item in matching_docs) else "待核验"
            else:
                status = "待上传" if priority == "高" else "建议补充"
            items.append({"name": name, "status": status})
        groups.append({"category": category, "purpose": purpose, "priority": priority, "batch": batch, "items": items})
    return groups


def _action_plans(assessment: Assessment, warnings: list[dict[str, str]]) -> list[dict[str, Any]]:
    first_risk = next((item["warning_item"] for item in warnings if item["warning_level"] != "绿灯"), "资料完整性")
    credit_action = (
        "调取并核验企业及法人征信，停止非必要查询"
        if not assessment.credit_status
        else "保持按时履约并控制新增征信查询"
    )
    debt_action = (
        f"围绕{_money(assessment.debt_total)}存量负债建立成本与到期台账"
        if assessment.debt_total
        else "确认企业无隐性负债及对外担保"
    )
    collateral_action = (
        "整理抵押物权属、现有抵押和评估资料"
        if assessment.has_collateral
        else "评估信用、税票和经营场景融资路径"
    )
    return [
        {
            "period": "未来30天行动计划",
            "goal": "完成风险止损与基础资料归集",
            "actions": [credit_action, debt_action, f"优先核验当前核心风险：{first_risk}", "归集流水、纳税、合同与发票"],
            "responsible": "企业负责人、财务负责人",
            "deliverable": "风险核验表、基础资料包、融资需求说明",
            "completion_standard": "核心资料完成归档，存量负债和待核验风险均有责任人。",
            "deadline": "第30天",
        },
        {
            "period": "未来90天行动计划",
            "goal": "完成关键指标优化并形成可申请材料包",
            "actions": [credit_action, "提升对公回款占比并核对合同、开票、流水口径", collateral_action, "针对目标产品补齐准入材料"],
            "responsible": "财务负责人、业务负责人、融资顾问",
            "deliverable": "问题修复记录、目标产品材料包、申请顺序表",
            "completion_standard": "至少完成一次目标产品预审，核心风险形成可验证改善记录。",
            "deadline": "第90天",
        },
        {
            "period": "未来180天行动计划",
            "goal": "完成核心融资申请并优化存量结构",
            "actions": ["按顺序推进银行预审", "锁定主授信与备用渠道", "置换高成本短期负债", "建立月度贷后监测机制"],
            "responsible": "企业负责人、融资顾问",
            "deliverable": "授信申请进度表、负债置换方案、贷后监测表",
            "completion_standard": "形成主申请和备选路径，完成放款条件或明确下一轮修复事项。",
            "deadline": "第180天",
        },
        {
            "period": "6个月融资落地节奏",
            "goal": "形成准备、预审、申请、审批和贷后管理闭环",
            "actions": ["第1月停止无序申请、完成资料盘点", f"第2月围绕{first_risk}完成重点优化", "第3月完成银行预匹配与预审", "第4月提交核心申请", "第5月补件、审批和额度确认", "第6月放款、债务置换和项目复盘"],
            "responsible": "企业融资项目组",
            "deliverable": "融资落地闭环及下一周期资本计划",
            "completion_standard": "每月保留检查记录、交付材料和融资推进结论。",
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


def _legacy_report_entitlements(db: Session, assessment_id: int, admin_override: bool = False) -> dict[str, Any]:
    codes = paid_product_codes(db, assessment_id)
    if admin_override:
        return {"paid_products": codes, "body_unlocked": True, "bank_match_unlocked": True, "structure_unlocked": True}
    return {
        "paid_products": sorted(codes),
        "body_unlocked": bool(codes & REPORT_BODY_PRODUCTS),
        "bank_match_unlocked": bool(codes & BANK_MATCH_PRODUCTS),
        "structure_unlocked": bool(codes & STRUCTURE_PLAN_PRODUCTS),
    }


def _legacy_build_capital_health_report(
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


# 商业交付版权益和快照。保留上方旧构建器仅用于历史代码兼容，
# 对外调用由下面的同名函数接管。
def report_entitlements(db: Session, assessment_id: int, admin_override: bool = False) -> dict[str, Any]:
    codes = paid_product_codes(db, assessment_id)
    legacy_policy = get_setting(db, "legacy_299_upgrade_policy", "keep_legacy_rights")
    legacy_299_grants_report = "299_report" in codes and legacy_policy == "grant_980_rights"
    body_unlocked = bool(codes & REPORT_BODY_PRODUCTS) or legacy_299_grants_report
    structure_unlocked = bool(codes & STRUCTURE_PLAN_PRODUCTS)
    if admin_override:
        body_unlocked = True
        structure_unlocked = True
    if structure_unlocked:
        access_level = "advisor_delivery" if codes & {"one_on_one_consulting", "high_ticket_consulting"} else "structure_plan"
    elif body_unlocked:
        access_level = "capital_health_report"
    else:
        access_level = "free"
    return {
        "paid_products": sorted(codes),
        "body_unlocked": body_unlocked,
        "bank_match_unlocked": True if admin_override else bool(codes & BANK_MATCH_PRODUCTS),
        "structure_unlocked": structure_unlocked,
        "legacy_report_unlocked": bool(codes & {"299_report", "699_bank_match"}),
        "legacy_299_grants_report": legacy_299_grants_report,
        "access_level": access_level,
    }


def _delivery_product_cards(matches: dict[str, Any], assessment: Assessment) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for source in matches.get("matched_products", []):
        item = deepcopy(source)
        reasons = list(item.get("matched_points") or [])
        if len(reasons) < 2:
            reasons.append(f"与{assessment.industry or '企业当前行业'}及经营阶段具备初步适配性")
        if len(reasons) < 2:
            reasons.append("融资需求与该产品基础申请场景相符")
        risks = list(item.get("risk_points") or [])
        if not risks:
            risks = ["基础条件较匹配，仍以银行实际审批为准"]
        documents = list(item.get("missing_requirements") or [])
        documents.extend(["营业执照及公司章程", "近两年财务报表", "近12个月银行流水"])
        item.update(
            matched_points=reasons[:6],
            risk_points=risks[:6],
            core_documents=list(dict.fromkeys(documents))[:5],
        )
        cards.append(item)
    return cards


def _delivery_advisor_cta(db: Session, assessment: Assessment) -> dict[str, str]:
    booking = (
        db.query(AdvisorBooking)
        .filter(AdvisorBooking.assessment_id == assessment.id)
        .order_by(AdvisorBooking.created_at.desc())
        .first()
    )
    if booking and (booking.consultant_user_id or booking.booking_status in {"accepted", "assigned", "processing"}):
        status, text = "assigned", "顾问已受理，请留意联系"
    elif booking:
        status, text = "submitted", "顾问预约已提交"
    else:
        status, text = "not_booked", "预约1对1融资顾问服务"
    return {
        "status": status,
        "button_text": text,
        "booking_url": f"/advisor/book/{assessment.report.id}" if assessment.report else "",
    }


def _delivery_remediation_plans(assessment: Assessment, warnings: list[dict[str, str]]) -> list[dict[str, Any]]:
    plans = deepcopy(_remediation_plans(assessment))
    first_risk = next((item["warning_item"] for item in warnings if item["warning_level"] != "绿灯"), "资料完整性")
    for plan in plans:
        if plan["title"] == "征信修复方案" and assessment.credit_status:
            plan["title"] = "征信维护方案"
        owner = "财务负责人"
        if "资产" in plan["title"]:
            owner = "企业负责人、财务负责人"
        elif "征信" in plan["title"]:
            owner = "企业负责人、融资顾问"
        plan["rows"] = [
            row + [owner, f"{row[2]}达到并形成可核验记录"]
            for row in plan["rows"]
        ]
        plan["risk_note"] = f"当前优先关联风险：{first_risk}。"
        plan["expected_improvement"] = "改善融资准入口径、资料一致性和银行预审可解释性。"
        plan["implementation_note"] = "所有改善动作均需保留合同、流水、凭证或台账作为完成依据。"
    return plans


def build_capital_health_report(
    db: Session,
    assessment: Assessment,
    admin_override: bool = False,
    include_extended: bool = True,
) -> dict[str, Any]:
    dimensions = _build_dimensions(assessment)
    total = int(round(sum(item["weighted_score"] for item in dimensions)))
    warnings = _build_warnings(dimensions)
    entitlements = report_entitlements(db, assessment.id, admin_override)
    generated_at = assessment.report.created_at if assessment.report else assessment.created_at
    validity_days = int(get_setting(db, "capital_health_report_validity_days", "90"))
    matches = (
        match_bank_products(db, assessment, limit=5, real_only=True)
        if include_extended and entitlements["structure_unlocked"]
        else {"matched_products": [], "best_application_order": []}
    )
    products = _delivery_product_cards(matches, assessment)
    debt = max(float(assessment.debt_total or 0), 0)
    need = max(float(assessment.funding_need or 0), 0)
    first_risk = next((item for item in warnings if item["warning_level"] != "绿灯"), warnings[0])
    strengths: list[str] = []
    if assessment.annual_revenue:
        strengths.append(f"年营收约{_money(assessment.annual_revenue)}")
    if assessment.tax_status:
        strengths.append("纳税状态正常")
    if assessment.credit_status:
        strengths.append("企业征信状态正常")
    if not strengths:
        strengths.append(f"企业已持续经营{assessment.business_years or 0}年")
    weaknesses = [first_risk["warning_item"]]
    if assessment.receivable_days:
        weaknesses.append(f"平均回款周期{assessment.receivable_days}天")
    financing_path = "直接申请型" if total >= 80 else "优化型融资"
    _, structure_product = get_product("1999_structure_plan", db, assessment.id)
    institution = get_setting(db, "capital_health_institution", "沪上银 · 企业资本健康管理中心")
    financing_advice = (
        "当前具备较好融资基础，建议完成资料核验后按产品适配度安排申请顺序。"
        if total >= 80
        else "建议先处理核心异常并完成资料核验，再启动银行预审。"
    )
    return {
        "title": "企业资本健康体检报告",
        "subtitle": "Enterprise Capital Health Check Report",
        "show_subtitle": get_bool_setting(db, "capital_health_show_english_subtitle", True),
        "report_no": f"CHCR-{generated_at.year}-{assessment.report.id if assessment.report else assessment.id:06d}",
        "report_date": generated_at.strftime("%Y年%m月%d日"),
        "valid_until": (generated_at + timedelta(days=validity_days)).strftime("%Y年%m月%d日"),
        "company_name": assessment.company_name,
        "check_type": "融资前资本健康度全项检查",
        "institution": institution,
        "disclaimer": "本报告基于企业提供资料及截至报告日期可获取的公开数据编制，旨在为企业融资决策提供参考依据，不构成任何形式的融资承诺或担保。实际融资结果取决于金融机构审批政策、企业资质变化等不可控因素。",
        "score": total,
        "grade": _grade(total),
        "risk_level": _risk_level(total),
        "financing_advice": financing_advice,
        "conclusions": [
            f"资本健康度为{total}分，综合评级为{_grade(total)}，当前处于{_risk_level(total)}状态。",
            f"优先关注{first_risk['warning_item']}，建议在{first_risk['deadline']}完成核验或改善。",
            financing_advice,
        ],
        "executive_summary": [
            {"label": "优势基础", "title": "企业优势", "content": "；".join(strengths[:2]) + "，构成当前融资评估的正向基础。"},
            {"label": "关键问题", "title": "核心短板", "content": "；".join(weaknesses[:2]) + "，将影响准入判断或融资条件。"},
            {"label": "融资出路", "title": "推荐路径", "content": f"建议采用{financing_path}，先完成风险处理与资料核验，再按真实产品匹配结果安排申请。"},
        ],
        "dimensions": dimensions,
        "warnings": warnings,
        "top_risks": [item for item in warnings if item["warning_level"] != "绿灯"][:3] or warnings[:3],
        "initial_suggestion": first_risk["suggestion"],
        "remediation_plans": _delivery_remediation_plans(assessment, warnings),
        "financing_capacity": {
            "current_state": f"{_grade(total)}类（{_risk_level(total)}）",
            "path": financing_path,
            "advice": "可启动产品预匹配并控制申请顺序" if total >= 80 else "先优化3个月，再启动正式融资",
            "metrics": [
                ["当前负债总额", _money(debt)],
                ["当前融资需求", _money(need) if need else "待资料核验"],
                ["当前可行额度区间", "待资料核验"],
                ["优化后额度区间", "待资料核验"],
                ["预计综合成本", "待产品预审"],
                ["建议期限结构", "待产品匹配"],
            ],
            "transition": [
                ["负债结构", "期限与成本明细待统一", "成本、期限和机构数可控", "建立负债台账并优先置换高成本短债", "3—6个月"],
                ["流水质量", "对公流水需进一步核验", "经营回款稳定且公私分离", "统一回款账户并管理日均余额", "1—3个月"],
                ["融资资料", "资料分散、口径待复核", "形成目标银行可提交材料包", "按真实产品准入要求补齐资料", "1—3个月"],
            ],
            "path_comparison": [
                ["信用融资", "待预审", "经营稳定、征信和流水可验证", "征信查询与负债结构可能影响准入", "完成资料核验后优先预审"],
                ["抵押融资", "可评估" if assessment.has_collateral else "暂不适用", "具备权属清晰的抵押物", "估值、权属与现有抵押需核验", "先完成抵押物资料盘点"],
                ["组合融资", "可评估", "融资需求较大或期限需要分层", "多机构申请可能增加查询记录", "由顾问统一安排申请顺序"],
            ],
            "bank_products": products,
            "application_order": matches.get("best_application_order", []),
        },
        "document_plan": _document_plan(db, assessment),
        "document_checklist": _document_plan(db, assessment),
        "action_plans": _action_plans(assessment, warnings),
        "advisor_cta": _delivery_advisor_cta(db, assessment),
        "entitlements": entitlements,
        "prices": {
            "report": get_setting(db, "capital_health_report_price", "980"),
            "structure": structure_product["price"],
            "structure_original": structure_product.get("original_price", structure_product["price"]),
            "structure_deduction": structure_product.get("deduction", 0),
            "structure_upgrade_mode": structure_product.get("upgrade_mode", "full_price"),
            "consulting": get_setting(db, "one_on_one_consulting_price", "9800"),
        },
    }


def ensure_capital_health_snapshot(
    db: Session,
    assessment: Assessment,
    admin_override: bool = False,
    refresh: bool = False,
) -> dict[str, Any]:
    """Read or persist a delivery snapshot; opening a report does not rerun matching."""
    report = assessment.report
    content: dict[str, Any] = {}
    if report and report.full_report_json:
        try:
            content = json.loads(report.full_report_json)
        except (TypeError, ValueError):
            content = {}
    entitlements = report_entitlements(db, assessment.id, admin_override)
    snapshot = content.get("capital_health_snapshot")
    rank = {"free": 0, "capital_health_report": 1, "structure_plan": 2, "advisor_delivery": 3}
    if (
        not refresh
        and isinstance(snapshot, dict)
        and rank.get(snapshot.get("access_level", "free"), 0)
        >= rank.get(entitlements["access_level"], 0)
    ):
        result = deepcopy(snapshot)
        result["entitlements"] = entitlements
        result["advisor_cta"] = _delivery_advisor_cta(db, assessment)
        return result

    snapshot = build_capital_health_report(
        db,
        assessment,
        admin_override=admin_override,
        include_extended=entitlements["structure_unlocked"],
    )
    snapshot["access_level"] = entitlements["access_level"]
    snapshot["snapshot_created_at"] = datetime.now().isoformat(timespec="seconds")
    if report:
        content["capital_health_snapshot"] = snapshot
        report.full_report_json = json.dumps(content, ensure_ascii=False)
        version = (
            db.query(ReportVersion).filter(ReportVersion.id == report.current_version_id).first()
            if report.current_version_id
            else None
        )
        if version:
            try:
                version_content = json.loads(version.report_json)
            except (TypeError, ValueError):
                version_content = {}
            version_content["capital_health_snapshot"] = snapshot
            version.report_json = json.dumps(version_content, ensure_ascii=False)
        db.commit()
    return snapshot
