import json

from sqlalchemy.orm import Session

from ai.ai_client import AIClient
from ai.financing_agent import FinancingAgent
from ai.risk_agent import RiskAgent
from ai.strategy_agent import StrategyAgent
from core.bank_approval_engine import simulate_bank_approval
from core.bank_product_matcher import match_bank_products
from core.capital_health_report import build_capital_health_report, report_entitlements
from core.config import settings
from core.pricing_engine import PRODUCT_RANK
from ai.pipelines.report_pipeline import ReportPipeline
from db.models import AIGenerationLog, Assessment, Order, Report, ReportVersion
from services.settings_service import get_bool_setting
from services.event_service import track_event
from utils.report_display_mapper import (
    build_customer_report_display,
    display_value,
    enrich_report_display_fields,
)
from utils.report_formatters import normalize_report_action_steps
from utils.report_render_formatter import format_report_for_render
from utils.logger import logger


def _assessment_data(item: Assessment) -> dict:
    fields = [
        "company_name", "industry", "years", "employee_count", "annual_revenue",
        "net_profit", "monthly_cashflow", "debt_total", "short_debt",
        "receivable_days", "funding_need", "funding_purpose", "has_collateral",
        "tax_status", "credit_status", "knows_cashflow", "has_budget",
        "leverage_attitude", "asset_efficiency", "fund_usage_plan",
    ]
    return {field: getattr(item, field) for field in fields}


def _money(value: float) -> str:
    return f"{value / 10000:,.0f}万元"


def _chapter(
    title: str,
    conclusion: str,
    key_issues: list[str],
    bank_view: str,
    owner_actions: list[str],
    next_actions: list[str],
    details: dict | None = None,
) -> dict:
    return {
        "title": title,
        "conclusion": conclusion,
        "key_issues": key_issues,
        "bank_view": bank_view,
        "owner_actions": owner_actions,
        "next_actions": next_actions,
        "details": details or {},
    }


def _build_professional_report(db: Session, assessment: Assessment) -> dict:
    data = _assessment_data(assessment)
    score = {
        "total": assessment.score,
        "grade": assessment.grade,
        "risk_level": assessment.risk_level,
        "funding_probability": assessment.funding_probability,
    }
    strategy = StrategyAgent().generate(data, score)
    financing = FinancingAgent().generate(data, score)
    risk = RiskAgent().generate(data, score)
    bank = simulate_bank_approval(data, assessment.score).to_dict()
    company_grade_display = display_value("company_grade", assessment.grade)
    finance_feasibility_display = display_value(
        "finance_feasibility", assessment.funding_probability
    )
    risk_level_display = display_value("risk_level", assessment.risk_level)

    revenue = max(assessment.annual_revenue, 1)
    monthly_revenue = revenue / 12
    profit_margin = assessment.net_profit / revenue
    debt_ratio = assessment.debt_total / revenue
    short_ratio = assessment.short_debt / max(assessment.debt_total, 1)
    cash_ratio = assessment.monthly_cashflow / monthly_revenue
    funding_ratio = assessment.funding_need / revenue
    strong = assessment.grade in {"S", "A"}
    weak = assessment.grade in {"C", "D"}

    overall_conclusion = (
        f"企业评分{assessment.score}分（评级{company_grade_display}），具备融资基础。当前重点不是简单判断“能否贷款”，"
        f"而是围绕预计{bank['estimated_credit_limit']}的授信空间，优化成本、期限与申请顺序。"
        if strong
        else f"企业评分{assessment.score}分（评级{company_grade_display}），融资可行性为{finance_feasibility_display}。"
        f"当前不宜盲目多头申请，应先处理影响审批的硬指标，再进入银行预审。"
    )

    financial_issues = [
        f"年营收{_money(assessment.annual_revenue)}，净利润{_money(assessment.net_profit)}，净利率约{profit_margin * 100:.1f}%。",
        f"总负债{_money(assessment.debt_total)}，占年营收约{debt_ratio * 100:.1f}%；其中短债占总负债约{short_ratio * 100:.1f}%。",
        f"月均现金流{_money(assessment.monthly_cashflow)}，相当于月均收入的{cash_ratio * 100:.1f}%。",
        f"应收账款周期{assessment.receivable_days}天，直接影响银行对回款稳定性和第一还款来源的判断。",
    ]
    if weak:
        financial_issues.append("企业评级尚未达到良好水平，银行更可能要求增信、降低额度或暂缓审批。")

    allocation = [
        {"name": "主营业务周转与订单交付", "percent": 45 if funding_ratio < 0.35 else 40},
        {"name": "高回报增长项目", "percent": 25 if assessment.net_profit > 0 else 15},
        {"name": "短债置换与结构优化", "percent": 20 if short_ratio > 0.55 else 10},
        {"name": "偿债与风险准备金", "percent": 15 if cash_ratio < 0.25 else 10},
    ]
    total_percent = sum(item["percent"] for item in allocation)
    allocation[0]["percent"] += 100 - total_percent

    chapters = [
        _chapter(
            "企业整体评分",
            overall_conclusion,
            [
                f"融资需求{_money(assessment.funding_need)}，约占年营收的{funding_ratio * 100:.1f}%。",
                *bank["likely_rejection_reasons"][:3],
            ],
            f"模拟审批通过概率约{bank['approval_probability'] * 100:.0f}%，预计可贷额度区间为{bank['estimated_credit_limit']}。"
            f"银行风险等级为{risk_level_display}。",
            [
                "先确定融资用途、提款节奏和还款来源，再决定申请产品。",
                "把流水、纳税、合同、发票、财务报表统一到同一经营口径。",
            ],
            bank["improvement_actions"][:3],
            {
                "score": assessment.score,
                "grade": assessment.grade,
                "risk_level": assessment.risk_level,
                "funding_probability": assessment.funding_probability,
                "bank_approval": bank,
            },
        ),
        _chapter(
            "商业模式诊断",
            f"{assessment.company_name}已经营{assessment.years}年，商业模式能否获得授信，核心取决于收入是否可验证、客户是否稳定、回款是否可预测。",
            [
                f"所属行业为{assessment.industry}，当前员工{assessment.employee_count}人，需证明人员规模与收入产出匹配。",
                f"应收周期{assessment.receivable_days}天，说明价值交付到现金回收之间存在{assessment.receivable_days}天资金占用。",
                "商业模式需要从“有收入”升级为“收入可持续、订单可验证、现金可回收”。",
            ],
            "银行不会只听商业故事，更关注合同、发票、流水和纳税能否相互验证，以及核心客户集中度是否可控。",
            [
                "梳理前十大客户收入、毛利、账期与复购情况。",
                "把融资用途绑定到可验证订单、采购合同或产能释放计划。",
            ],
            [
                "30天内形成客户结构与收入质量表。",
                "将长账期客户改为分阶段回款或引入保理。",
            ],
            {
                "business_canvas": strategy["business_canvas"],
                "ansoff": strategy["ansoff"],
                "value_chain": strategy["value_chain"],
                "core_competence": strategy["core_competence"],
            },
        ),
        _chapter(
            "财务健康体检",
            f"企业净利率约{profit_margin * 100:.1f}%，负债/营收约{debt_ratio * 100:.1f}%，短债占比约{short_ratio * 100:.1f}%。"
            + ("财务结构总体可融资，但仍需控制新增负债成本。" if strong else "财务结构对新增授信形成约束，需要先改善现金覆盖和短债结构。"),
            financial_issues,
            f"银行会重点核验经营现金流能否覆盖本息。当前月均现金流为{_money(assessment.monthly_cashflow)}，"
            f"{'可作为还款来源证明，但需保持稳定。' if assessment.monthly_cashflow > 0 else '不足以支持新增债务，应先修复。'}",
            [
                "每月同时看利润表和现金流表，避免只看利润不看回款。",
                "设置债务到期台账，提前6个月安排续贷或置换。",
            ],
            [
                "建立13周滚动现金流预测。",
                "将应收账款、存货和短债列为周度经营会议指标。",
                "测算新增融资后的月度本息覆盖倍数。",
            ],
            {
                "profit_margin": round(profit_margin, 4),
                "debt_ratio": round(debt_ratio, 4),
                "short_debt_ratio": round(short_ratio, 4),
                "cashflow_to_monthly_revenue": round(cash_ratio, 4),
            },
        ),
        _chapter(
            "SWOT综合研判",
            "企业的融资优势来自既有经营基础与真实业务场景，主要短板集中在财务精细度、回款效率和资本结构匹配。",
            [
                *strategy["swot"]["weaknesses"],
                *strategy["swot"]["threats"],
            ],
            "银行会把优势转化为授信依据，把劣势转化为额度折扣、增信要求或审批条件。",
            [
                "将优势整理成可验证材料，而不是口头描述。",
                "对每项劣势明确责任人、修复指标和完成日期。",
            ],
            strategy["tows"],
            {"swot": strategy["swot"], "tows": strategy["tows"]},
        ),
        _chapter(
            "融资策略",
            f"建议融资需求{_money(assessment.funding_need)}分层解决，不宜一次性依赖单一银行。"
            + ("优先锁定低成本核心额度，再补充流动性工具。" if strong else "先修复硬指标并小范围预审，再逐步扩大申请。"),
            [
                f"预计银行授信区间{bank['estimated_credit_limit']}，与需求{_money(assessment.funding_need)}之间可能存在缺口。",
                f"抵押物状态：{'有，可优先用于锁定长期低成本额度' if assessment.has_collateral else '无，需要依赖纳税、流水、订单和担保增信'}。",
                *bank["likely_rejection_reasons"][:2],
            ],
            f"优先银行/产品方向：{'；'.join(bank['bank_preference'])}。审批概率约{bank['approval_probability'] * 100:.0f}%。",
            [
                "不要在短期内同时向多家银行无序申请，避免征信查询过多。",
                "先申请最确定的核心额度，再安排补充授信。",
            ],
            bank["application_order"],
            {
                "portfolio": financing["portfolio"],
                "short_term": financing["short_term"],
                "medium_term": financing["medium_term"],
                "long_term": financing["long_term"],
                "bank_approval": bank,
            },
        ),
        _chapter(
            "资金投放策略",
            f"融资资金必须与用途“{assessment.funding_purpose}”绑定，并设置预算、里程碑和回款验证，避免贷款进入低效资产或填补长期亏损。",
            [
                "融资需求与业务回报之间需要建立可量化关系。",
                "资金投放周期必须短于贷款期限，避免期限错配。",
                f"当前净利润为{_money(assessment.net_profit)}，新增投入不能只追求收入增长而忽视利润和现金回收。",
            ],
            "贷后检查会关注资金真实用途、合同发票、支付路径及经营指标变化，资金挪用会影响续贷。",
            [
                "设置融资专户或独立资金台账。",
                "每笔资金绑定负责人、预算、ROI目标与退出节点。",
            ],
            [
                "30天完成资金投放预算表。",
                "90天复盘订单、毛利和现金回收。",
                "未达到里程碑的项目暂停追加投入。",
            ],
            {
                "allocation": allocation,
                "target_roi": "目标年化ROI应高于综合融资成本至少8个百分点",
                "payback": "建议投资回收期控制在贷款期限的60%以内",
            },
        ),
        _chapter(
            "贷后管理",
            "贷后管理的目标不是按时还款这么简单，而是持续保持银行愿意续贷、增额和降价的经营状态。",
            [risk["cashflow_risk"], risk["debt_risk"], "资料口径、资金用途和实际经营变化需要持续一致。"],
            "银行贷后通常关注流水下降、纳税异常、负债新增、涉诉、征信逾期和资金用途偏离。",
            [
                "建立月度银企数据包，固定输出流水、纳税、应收、负债和本息覆盖情况。",
                "任何新增借款、担保或大额支出先评估对现有授信的影响。",
            ],
            risk["post_loan"],
            {"warning_level": risk["warning"]},
        ),
        _chapter(
            "长期资本路径",
            "未来资本路径应从单次借款升级为“经营现金流 + 银行授信 + 供应链工具 + 股权资本”的组合。",
            [
                f"现有总负债{_money(assessment.debt_total)}，需要管理到期分布而非只管理总额。",
                "续贷、增额和债务置换应至少提前6个月规划。",
                "股权融资只有在商业模式可复制、数据规范和增长可验证时才具备议价能力。",
            ],
            "银行偏好负债透明、到期分散、无过度对外担保且长期经营记录稳定的企业。",
            [
                "建立未来12个月融资到期日历。",
                "逐步降低短期高成本资金占比。",
            ],
            [
                "6个月内完成存量债务成本与期限盘点。",
                "12个月内形成至少两类稳定融资渠道。",
                "具备增长条件时再评估产业资本或股权融资。",
            ],
            {
                "refinancing": "提前6个月启动续贷和新增授信准备",
                "debt_swap": "用长期低成本资金置换短期高成本负债",
                "equity": "以规范数据和增长证据换取股权融资议价权",
                "capitalization": "完善财务、税务、合同和治理基础",
            },
        ),
        _chapter(
            "财商诊断",
            f"老板当前杠杆态度为“{assessment.leverage_attitude}”，资产效率自评为“{assessment.asset_efficiency}”。"
            f"{'已有预算和资金计划基础。' if assessment.has_budget and assessment.fund_usage_plan else '现金流预算或资金使用闭环仍不完整。'}",
            [
                "利润不等于现金，可融资不等于应该融资。",
                "融资决策应同时测算成本、期限、用途、回报和最坏情形。",
                "老板资金思维需要从“缺口驱动”转向“资本结构驱动”。",
            ],
            "银行更信任能解释资金用途、还款来源和风险预案的经营者，而不是只强调业务前景。",
            [
                "每月复盘现金、利润、资产周转和负债四张表。",
                "任何新增融资都设置最低回报率和止损线。",
            ],
            [
                "补齐年度现金流预算。",
                "建立融资成本台账。",
                "将闲置资产、低效存货和长期应收纳入资金盘活计划。",
            ],
            {
                "knows_cashflow": assessment.knows_cashflow,
                "has_budget": assessment.has_budget,
                "fund_usage_plan": assessment.fund_usage_plan,
                "leverage_attitude": assessment.leverage_attitude,
                "asset_efficiency": assessment.asset_efficiency,
            },
        ),
        _chapter(
            "行动建议",
            ("企业应立即进入融资结构设计与银行预匹配阶段。" if strong else "企业应先完成关键指标修复，再进入正式银行申请。"),
            bank["likely_rejection_reasons"],
            f"当前模拟通过概率{bank['approval_probability'] * 100:.0f}%，预计额度{bank['estimated_credit_limit']}。"
            f"{'可重点优化申请顺序和融资成本。' if strong else '批量申请可能放大征信查询与拒贷风险。'}",
            [
                "指定一名负责人统一融资资料和银行沟通口径。",
                "所有申请动作围绕通过率、额度、成本和期限四个目标决策。",
            ],
            [
                "未来30天：" + "；".join(bank["improvement_actions"][:2]),
                "未来90天：" + ("完成2—3家银行预匹配并锁定核心额度" if assessment.score >= 60 else "修复现金流、征信/纳税和短债结构后重新测评"),
                "未来12个月：完成债务结构复盘，建立多元融资渠道与年度资本计划",
            ],
            {
                "30_days": bank["improvement_actions"][:3],
                "90_days": bank["application_order"],
                "12_months": ["完成年度资本规划", "形成多元融资渠道", "评估再融资、债务置换或股权路径"],
                "bank_approval": bank,
            },
        ),
    ]

    return enrich_report_display_fields({
        "schema_version": 3,
        "generated_by": {
            "provider": (
                "openai"
                if AIClient(db).mode == "openai" and AIClient(db).api_key
                else "mock"
            ),
            "model": AIClient(db).model,
        },
        "company_snapshot": {
            "company_name": assessment.company_name,
            "industry": assessment.industry,
            "annual_revenue": assessment.annual_revenue,
            "net_profit": assessment.net_profit,
            "monthly_cashflow": assessment.monthly_cashflow,
            "debt_total": assessment.debt_total,
            "short_debt": assessment.short_debt,
            "receivable_days": assessment.receivable_days,
            "funding_need": assessment.funding_need,
        },
        "bank_approval": bank,
        "chapters": chapters,
    })


def _current_product(db: Session, assessment_id: int) -> str:
    paid = db.query(Order).filter(
        Order.assessment_id == assessment_id,
        Order.status == "paid",
    ).all()
    return max(
        (item.product_code or "299_report" for item in paid),
        key=lambda code: PRODUCT_RANK.get(code, 0),
        default="299_report",
    )


def _apply_product_depth(content: dict, product_code: str) -> dict:
    matches = content.get("bank_product_matches", {})
    all_matches = matches.get("matched_products", [])
    if product_code in {"299_report", "980_capital_health_report"}:
        matches["matched_products"] = all_matches[:1]
        matches["preview_only"] = True
        content["delivery_scope"] = {
            "level": "基础融资诊断",
            "included": ["基础融资诊断", "风险提示", "银行视角简版", "基础行动建议"],
            "locked": ["完整银行产品匹配", "申请顺序与额度预测", "三阶段融资结构优化方案"],
        }
    elif product_code == "699_bank_match":
        matches["matched_products"] = all_matches[:5]
        content["delivery_scope"] = {
            "level": "银行匹配与额度预测",
            "included": [
                "基础融资诊断", "银行产品匹配", "银行申请顺序",
                "预计额度区间", "被拒原因清单", "提升通过率动作",
            ],
            "locked": ["三阶段融资结构优化方案", "完整资料准备清单", "30/90/180天执行计划"],
        }
    else:
        content["delivery_scope"] = {
            "level": "融资结构优化方案",
            "included": [
                "银行产品匹配", "三阶段融资结构优化方案", "资金用途拆分",
                "现金流修复计划", "完整资料准备清单", "30/90/180天执行计划",
                "老板财商提升建议", "高客单顾问服务判断",
            ],
            "locked": [],
        }
        content["structure_plan"] = {
            "stage_1_30_days": ["统一融资资料口径", "修复征信/纳税/现金流硬伤", "完成银行预匹配"],
            "stage_2_90_days": ["按优先顺序提交核心授信", "锁定低成本主额度", "建立13周现金流预测"],
            "stage_3_180_days": ["置换高成本短债", "形成两类以上融资渠道", "复盘融资成本与贷后指标"],
            "funding_use_split": ["主营业务周转", "高成本短债置换", "增长项目里程碑投放", "风险准备金"],
        }
    content["bank_product_matches"] = matches
    return content


def _refresh_bank_product_matches(db: Session, assessment: Assessment, content: dict, product_code: str) -> dict:
    matches = match_bank_products(db, assessment)
    content["bank_product_matches"] = matches
    if len(content.get("chapters") or []) >= 5:
        details = content["chapters"][4].setdefault("details", {})
        details["bank_product_matches"] = matches
        details["best_application_order"] = matches.get("best_application_order", [])
    return format_report_for_render(
        enrich_report_display_fields(_apply_product_depth(content, product_code))
    )


def _save_version(
    db: Session,
    report: Report,
    content: dict,
    product_code: str,
    quality_score: int,
    created_by: str,
) -> ReportVersion:
    latest = db.query(ReportVersion).filter(
        ReportVersion.report_id == report.id
    ).order_by(ReportVersion.version_no.desc()).first()
    version = ReportVersion(
        report_id=report.id,
        assessment_id=report.assessment_id,
        version_no=(latest.version_no + 1) if latest else 1,
        product_code=product_code,
        generator_mode=(content.get("generated_by") or {}).get("provider", "mock"),
        quality_score=quality_score,
        report_json=json.dumps(content, ensure_ascii=False),
        html_content="",
        created_by=created_by,
    )
    db.add(version)
    db.flush()
    report.current_version_id = version.id
    return version


def generate_full_report(
    db: Session,
    assessment: Assessment,
    force: bool = False,
    created_by: str = "system",
) -> Report:
    report = assessment.report
    if report is None:
        raise ValueError("评估记录缺少报告")
    desired_product = _current_product(db, assessment.id)
    if report.full_report_json and not force:
        try:
            current = json.loads(report.full_report_json)
            current_product = current.get("product_code", "299_report")
            if (
                current.get("schema_version") == 3
                and current.get("chapters")
                and PRODUCT_RANK.get(current_product, 0) >= PRODUCT_RANK.get(desired_product, 0)
            ):
                if not db.query(ReportVersion).filter(ReportVersion.report_id == report.id).first():
                    quality = (current.get("quality") or {}).get("quality_score", 0)
                    _save_version(
                        db, report, current, current.get("product_code", _current_product(db, assessment.id)),
                        quality, "legacy-import",
                    )
                    db.commit()
                return report
        except (json.JSONDecodeError, AttributeError):
            pass
    product_code = desired_product
    fallback = _build_professional_report(db, assessment)
    content, quality = ReportPipeline(db, report).run(assessment, product_code, fallback)
    content = format_report_for_render(
        enrich_report_display_fields(_apply_product_depth(content, product_code))
    )
    normalize_report_action_steps(content)
    entitlements = report_entitlements(db, assessment.id)
    snapshot = build_capital_health_report(
        db,
        assessment,
        include_extended=entitlements["structure_unlocked"],
    )
    snapshot["access_level"] = entitlements["access_level"]
    content["capital_health_snapshot"] = snapshot
    report.full_report_json = json.dumps(content, ensure_ascii=False)
    report.html_content = ""
    report.is_unlocked = True
    delivery_quality = quality.get("delivery_quality") or {}
    delivery_issues = delivery_quality.get("issues") or []
    delivery_failed = not delivery_quality.get("valid", True)
    review_required = get_bool_setting(db, "report_review_required", False)
    if product_code in {"1999_structure_plan", "one_on_one_consulting", "high_ticket_consulting"}:
        review_required = get_bool_setting(db, "1999_plan_review_required", True)
    elif product_code == "980_capital_health_report":
        review_required = get_bool_setting(db, "980_report_review_required", False)
    if delivery_failed:
        logger.error("report delivery quality failed report_id=%s issues=%s", report.id, delivery_issues)
        track_event(
            db,
            "report_quality_failed",
            assessment_id=assessment.id,
            lead_id=assessment.lead.id if assessment.lead else None,
            data={"report_id": report.id, "issues": delivery_issues},
            commit=False,
        )
        db.add(AIGenerationLog(
            assessment_id=assessment.id,
            report_id=report.id,
            section_name="报告交付质量检查",
            ai_mode="system",
            model_name="",
            prompt_name="report_delivery_quality",
            status="failed",
            error_message="；".join(delivery_issues),
            token_usage_json=json.dumps({}, ensure_ascii=False),
            quality_score=quality["quality_score"],
        ))
    if delivery_failed and settings.app_env == "production":
        report.review_status = "quality_failed"
        report.review_note = "报告正在重新整理，请稍后查看。"
    else:
        report.review_status = "pending_review" if review_required else "approved"
    if not review_required and not delivery_failed:
        report.review_note = "系统配置为无需人工审核，生成后自动通过。"
    content["report_meta"] = {
        "access_level": entitlements["access_level"],
        "created_at": report.created_at.isoformat(),
        "created_by": created_by,
        "review_status": report.review_status,
        "reviewer": "",
        "change_summary": "重新生成报告" if force else "首次生成报告",
    }
    report.full_report_json = json.dumps(content, ensure_ascii=False)
    _save_version(
        db, report, content, product_code, quality["quality_score"], created_by
    )
    db.query(AIGenerationLog).filter(
        AIGenerationLog.report_id == report.id,
        AIGenerationLog.quality_score == 0,
    ).update({"quality_score": quality["quality_score"]}, synchronize_session=False)
    db.commit()
    db.refresh(report)
    return report


def parse_report(report: Report) -> tuple[dict, dict | None]:
    free = json.loads(report.free_summary_json)
    full = json.loads(report.full_report_json) if report.full_report_json else None
    normalize_report_action_steps(full)
    return free, full


def parse_customer_report(report: Report) -> dict | None:
    """Read a customer-safe report payload with internal fields removed."""
    _, full = parse_report(report)
    return format_report_for_render(build_customer_report_display(format_report_for_render(full)))


def parse_customer_free_summary(report: Report) -> dict:
    free, _ = parse_report(report)
    return build_customer_report_display(free) or {}
