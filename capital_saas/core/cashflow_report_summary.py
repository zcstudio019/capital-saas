"""现金流报告管理层摘要：只使用已填、已关联或已上传的数据。"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from sqlalchemy import or_

from core.bank_approval_engine import simulate_bank_approval
from core.bank_product_matcher import match_bank_products
from db.models import Assessment, CustomerAccount, Lead, UploadedDocument


PRIORITY_LABELS = {
    "P0": "P0 · 立即处理", "P1": "P1 · 短期改善", "P2": "P2 · 中期优化",
    "P3": "P3 · 中长期盘活", "P4": "P4 · 长期机制",
}
def _money(value: Any) -> str:
    if value is None:
        return "待补充资料核验"
    number = float(value)
    if abs(number) >= 10_000:
        return f"{number / 10_000:,.1f}万元"
    return f"{number:,.0f}元"


def _number(value: Any) -> float | None:
    try:
        return None if value is None or value == "" else float(value)
    except (TypeError, ValueError):
        return None


def _health_level(score: Any) -> str:
    value = _number(score)
    if value is None:
        return "待补充资料核验"
    if value >= 85:
        return "健康"
    if value >= 70:
        return "基本健康"
    if value >= 55:
        return "亚健康"
    if value >= 40:
        return "高风险"
    return "严重风险"


def _current_assessment(db, cashflow) -> Assessment | None:
    if cashflow.lead_id:
        lead = db.get(Lead, cashflow.lead_id)
        linked = db.get(Assessment, lead.assessment_id) if lead and lead.assessment_id else None
        if linked:
            return linked
    if cashflow.customer_id:
        customer = db.get(CustomerAccount, cashflow.customer_id)
        if customer and customer.assessment_id:
            linked = db.get(Assessment, customer.assessment_id)
            if linked:
                return linked
        return db.query(Assessment).filter(
            Assessment.customer_id == cashflow.customer_id
        ).order_by(Assessment.created_at.desc()).first()
    return None


def _problem(code: str, rank: int, name: str, level: str, current: str,
             reason: str, impact: str) -> dict[str, Any]:
    return {"code": code, "rank": rank, "name": name, "risk_level": level,
            "current_value": current, "reason": reason, "impact": impact}


def build_core_problems(data: dict, metrics: dict, forecasts: list[dict], risks: list[dict]) -> list[dict]:
    items: list[dict] = []
    current_cash = _number(data.get("cash"))
    if current_cash is not None and current_cash < 0:
        items.append(_problem("current_gap", 1, "当前已经出现现金缺口", "严重",
            f"当前现金余额{_money(current_cash)}", "当前可用现金余额已经低于零。",
            "企业已处于资金缺口状态，应立即安排回款、支出压降和过渡资金。"))
    gap_week = data.get("cash_gap_week")
    if gap_week:
        label = next((row.get("period_label") for row in forecasts if row.get("period_no") == gap_week), f"第{gap_week}期")
        items.append(_problem("forecast_gap", 2, "未来现金余额预计转负", "严重",
            f"预计{label}出现{_money(data.get('cash_gap_amount'))}现金缺口",
            "13周滚动预测中的期末现金余额低于零。", "若不提前筹资或压降支出，刚性付款可能无法按期完成。"))
    if data.get("loan_overdue"):
        items.append(_problem("loan_overdue", 3, "贷款已经逾期", "严重", "已勾选贷款逾期",
            "企业已确认存在贷款逾期事项。", "可能影响征信、续贷和其他银行授信稳定性。"))
    if data.get("credit_withdrawal"):
        items.append(_problem("credit_withdrawal", 3, "存在抽贷或压贷", "严重", "已发生抽贷或压贷",
            "现有授信稳定性已经受到影响。", "可用资金可能快速下降并放大短期偿付压力。"))
    short_ratio = metrics.get("short_debt_ratio")
    short_coverage = metrics.get("short_debt_cash_coverage")
    if (short_ratio is not None and short_ratio > 70) or (short_coverage is not None and short_coverage < .3):
        items.append(_problem("short_debt", 4, "短期偿债压力偏高", "高",
            f"短期有息负债{_money(data.get('short_interest_debt'))}，占有息负债{short_ratio:.1f}%" if short_ratio is not None else f"现金仅覆盖短期债务{short_coverage * 100:.1f}%",
            "短期债务占比较高或现金覆盖率不足30%。", "未来6—12个月可能面临集中偿付与续贷压力。"))
    negative_months = _number(data.get("negative_operating_cf_months"))
    operating_cashflow = _number(data.get("operating_cashflow"))
    if (negative_months is not None and negative_months >= 3) or (operating_cashflow is not None and operating_cashflow < 0):
        items.append(_problem("negative_operating_cashflow", 5, "经营活动现金流偏弱", "严重" if negative_months and negative_months >= 3 else "高",
            f"连续{int(negative_months)}个月为负" if negative_months else f"经营活动现金流净额{_money(operating_cashflow)}",
            "主营经营活动未能持续形成正向现金净流入。", "企业需要依赖存量现金或新增融资维持日常经营。"))
    dso, dso_yoy = _number(data.get("dso")), _number(data.get("dso_yoy"))
    if (dso is not None and dso > 90) or (dso_yoy is not None and dso_yoy > 20):
        items.append(_problem("receivables", 6, "应收账款占用资金较多", "高",
            f"应收账款周转天数{dso:.0f}天" if dso is not None else f"周转天数同比增加{dso_yoy:.1f}%",
            "回款周期超过90天或同比拉长超过20%。", "销售收入不能及时转化为现金，挤占采购与偿债资金。"))
    dio, dio_yoy = _number(data.get("dio")), _number(data.get("dio_yoy"))
    stagnant = _number(data.get("inventory_stagnant_ratio"))
    if (dio is not None and dio > 120) or (dio_yoy is not None and dio_yoy > 30) or (stagnant is not None and stagnant > .2):
        items.append(_problem("inventory", 7, "存货资金占用偏高", "高",
            f"存货周转天数{dio:.0f}天" if dio is not None else f"滞销库存占比{stagnant * 100:.1f}%",
            "库存周转偏慢、同比恶化或滞销占比较高。", "采购资金沉淀在库存中，降低可用现金和资产变现能力。"))
    utilization = metrics.get("credit_utilization")
    if utilization is not None and utilization > .8:
        items.append(_problem("credit_utilization", 8, "授信额度使用率偏高", "高",
            f"已使用授信{utilization * 100:.1f}%", "授信使用率超过80%。", "备用融资空间较小，突发缺口缺少缓冲。"))
    if data.get("financing_cost_rising") or data.get("bridge_funding_high"):
        items.append(_problem("financing_cost", 9, "融资成本与稳定性承压", "高",
            "融资成本上升或过桥资金占比较高", "高成本短期资金使用增加。", "利息及续作压力会持续消耗经营现金。"))
    compressible = _number(data.get("compressible_expense"))
    if data.get("capex_deferrable") or (compressible is not None and compressible > 0):
        items.append(_problem("expense", 10, "支出结构存在优化空间", "需关注",
            f"可压缩或延后支出{_money((compressible or 0) + (_number(data.get('capex')) or 0 if data.get('capex_deferrable') else 0))}",
            "存在非刚性支出或可延后的资本性项目。", "若不主动安排，将占用短期现金储备。"))
    coverage = metrics.get("cash_coverage")
    if coverage is not None and coverage < 3:
        items.append(_problem("cash_reserve", 11, "现金储备周期偏短",
            "严重" if coverage < 1 else "高", f"按当前支出仅可维持{coverage:.1f}个月",
            "现金保障倍数低于3个月。", "应对收入波动、集中付款和授信变化的能力不足。"))
    items.sort(key=lambda item: (item["rank"], item["name"]))
    if not items:
        return [_problem("data_verification", 99, "关键资料仍需持续核验", "需关注",
            "暂未识别显著异常", "当前结论仅基于客户已填写资料。", "资料缺失可能使部分风险尚未被识别。")]
    return items[:5]


def _document_flags(db, cashflow) -> dict[str, bool]:
    filters = []
    if cashflow.customer_id:
        filters.append(UploadedDocument.customer_id == cashflow.customer_id)
    if cashflow.lead_id:
        filters.append(UploadedDocument.lead_id == cashflow.lead_id)
    docs = db.query(UploadedDocument).filter(or_(*filters), UploadedDocument.deleted_at.is_(None)).all() if filters else []
    text = " ".join(f"{item.document_category} {item.file_name}" for item in docs)
    return {"银行流水": "流水" in text, "企业征信": "征信" in text,
            "纳税记录": any(word in text for word in ("纳税", "税务", "税票")),
            "财务报表": any(word in text for word in ("财务", "报表", "资产负债", "利润表"))}


def build_financing_capacity(db, cashflow, data: dict, score: int | None) -> dict[str, Any]:
    linked = _current_assessment(db, cashflow)
    docs = _document_flags(db, cashflow)
    revenue = _number(data.get("revenue"))
    operating = _number(data.get("operating_cashflow"))
    debt = _number(data.get("interest_bearing_debt"))
    if debt is None:
        debt = _number(data.get("total_debt"))
    short_debt = _number(data.get("short_interest_debt"))
    total_assets = _number(data.get("total_assets"))
    credit_known = "credit_status" in data or bool(linked and linked.enterprise_credit_status != "unknown") or docs["企业征信"]
    tax_known = "tax_status" in data or bool(linked and (
        linked.tax_status or linked.tax_paid_12m > 0 or linked.tax_credit_grade != "unknown"
        or linked.tax_arrears_status != "unknown"
    )) or docs["纳税记录"]
    financial_known = all(value is not None for value in (revenue, operating, debt, short_debt, total_assets)) or docs["财务报表"]
    missing = []
    if not docs["银行流水"] and not (linked and (linked.public_inflow_monthly or linked.monthly_cashflow)):
        missing.append("银行流水")
    if not credit_known:
        missing.append("企业征信")
    if not tax_known:
        missing.append("纳税记录")
    if not financial_known:
        missing.append("财务报表")
    if (revenue is None or revenue <= 0 or operating is None or debt is None or short_debt is None
            or score is None or not credit_known or not tax_known or not financial_known or "银行流水" in missing):
        return {"status": "待补充资料后评估", "theoretical_range": "待补充资料后评估",
                "recommended_amount": "待补充资料后评估", "optimized_range": "待补充资料后评估",
                "missing_documents": missing or ["关键经营及负债数据"], "basis": [],
                "financing_structure": [], "matched_product_count": 0, "matched_products": [],
                "product_notice": "补充资料后可进一步测算真实融资空间。"}

    credit_ok = bool(data.get("credit_status", linked.credit_status if linked else False))
    tax_ok = bool(data.get("tax_status", linked.tax_status if linked else False))
    collateral = bool(data.get("has_collateral", linked.has_collateral if linked else False))
    receivables = _number(data.get("receivables_balance")) or 0
    profit = _number(data.get("net_profit"))
    total_debt = _number(data.get("total_debt")) or debt
    credit_limit = _number(data.get("credit_limit")) or 0
    credit_used = _number(data.get("credit_used")) or 0
    target = linked.funding_need if linked and linked.funding_need else max(revenue * .3, 100_000)
    approval_input = {"annual_revenue": revenue, "monthly_cashflow": operating / 12,
        "debt_total": debt, "short_debt": short_debt, "receivable_days": _number(data.get("dso")) or 0,
        "funding_need": target, "has_collateral": collateral, "tax_status": tax_ok, "credit_status": credit_ok}
    approval = simulate_bank_approval(approval_input, int(score))
    adjustment = 1.0
    calculation_notes = ["沿用现有银行审批模拟器的营收、经营现金流、负债与评分规则"]
    if profit is not None and profit <= 0:
        adjustment *= .75; calculation_notes.append("净利润非正，融资空间按75%审慎调整")
    if total_assets and total_debt / total_assets > .7:
        adjustment *= .75; calculation_notes.append("资产负债率较高，融资空间按75%审慎调整")
    utilization = credit_used / credit_limit if credit_limit > 0 else 0
    if utilization > .8:
        adjustment *= .8; calculation_notes.append("授信使用率超过80%，融资空间按80%审慎调整")
    if data.get("loan_overdue"):
        adjustment *= .65; calculation_notes.append("存在贷款逾期，融资空间按65%审慎调整")
    unused_credit = max(credit_limit - credit_used, 0)
    theoretical_high = max(50_000, approval.estimated_credit_high * adjustment + unused_credit)
    theoretical_low = max(50_000, min(theoretical_high, approval.estimated_credit_low * adjustment))
    practical = theoretical_high * .8
    optimized_high = max(theoretical_high, min(revenue * .4,
        theoretical_high * 1.3 + receivables * .25))
    optimized_low = max(theoretical_low, optimized_high * .6)

    profile = SimpleNamespace(company_name=cashflow.company_name, industry=cashflow.industry,
        city=getattr(linked, "city", "") if linked else "", annual_revenue=revenue,
        financing_amount=practical, business_years=int(cashflow.years or (linked.years if linked else 0) or 0),
        tax_status=tax_ok, invoice_status=tax_ok, credit_status=credit_ok,
        bank_flow_status="good" if operating > 0 else "weak", debt_level=debt / max(revenue, 1),
        query_count=getattr(linked, "credit_query_count_6m", 0) if linked else 0,
        has_collateral=collateral, funding_purpose=getattr(linked, "funding_purpose", "补充经营流动资金") if linked else "补充经营流动资金",
        company_type=cashflow.company_type, legal_person_credit=bool(getattr(linked, "legal_credit_status", "unknown") == "no_overdue") if linked else credit_ok,
        document_completeness=max(0.4, sum(docs.values()) / 4))
    matches = match_bank_products(db, profile, limit=3, real_only=True)
    products = matches.get("matched_products", [])
    short_part = min(practical * .4, max((_number(data.get("monthly_operating_expense")) or 0) * 3, 0))
    receivable_part = min(receivables * .7, practical * .3)
    medium_part = max(practical - short_part - receivable_part, 0)
    structure = []
    if short_part > 0:
        structure.append({"name": "短期流动资金", "amount": _money(short_part), "purpose": "覆盖近期经营周转"})
    if medium_part > 0:
        structure.append({"name": "中期经营贷款", "amount": _money(medium_part), "purpose": "优化债务期限结构"})
    if receivable_part > 0:
        structure.append({"name": "应收账款融资", "amount": _money(receivable_part), "purpose": "盘活真实贸易应收"})
    if collateral:
        structure.append({"name": "抵押经营融资", "amount": "视抵押物评估后确定", "purpose": "补充中长期低成本额度"})
    return {"status": "已测算", "theoretical_range": f"{theoretical_low / 10_000:,.0f}万—{theoretical_high / 10_000:,.0f}万元",
            "recommended_amount": f"{practical / 10_000:,.0f}万元以内",
            "optimized_range": f"{optimized_low / 10_000:,.0f}万—{optimized_high / 10_000:,.0f}万元",
            "missing_documents": missing, "basis": ["营业收入", "经营活动现金流", "有息负债",
                "短期负债", "净利润", "企业资产", "征信与纳税情况", "现有授信"],
            "calculation_notes": calculation_notes,
            "financing_structure": structure, "matched_product_count": len(products),
            "matched_products": [item["product_name"] for item in products],
            "product_notice": matches.get("fallback_notice") or "具体产品详情按当前报告权限展示。"}


def build_improvement_plan(problems: list[dict], actions: list[dict]) -> dict[str, list[dict]]:
    plan = {"immediate": [], "days_30": [], "days_90": [], "months_6": []}
    mapping = {
        "forecast_gap": [("immediate", "冻结非必要支出并逐日校准未来13周收支", "财务负责人", "本周", "避免预测缺口进一步扩大"),
                         ("days_30", "落实缺口对应的回款、展期和备用授信方案", "总经理与财务负责人", "30天", "覆盖预测现金缺口")],
        "current_gap": [("immediate", "立即建立每日资金调度表并锁定刚性付款顺序", "总经理与财务负责人", "24小时", "停止现金缺口扩大"),
                        ("days_30", "落实专项回款、债务展期和过渡授信", "总经理", "30天", "恢复正向现金余额")],
        "cash_reserve": [("immediate", "暂停非必要资本性支出并提高最低现金余额", "总经理", "本周", "保留刚性付款资金"),
                         ("days_90", "建立最低现金储备红线和备用授信", "财务负责人", "90天", "形成现金缓冲")],
        "loan_overdue": [("immediate", "立即与债权银行确认逾期处置和还款安排", "总经理", "48小时", "防止征信风险扩大")],
        "credit_withdrawal": [("immediate", "核对授信条件并准备替代资金来源", "总经理与财务负责人", "本周", "降低抽贷冲击")],
        "short_debt": [("immediate", "梳理未来6个月债务到期日历并启动展期沟通", "财务负责人", "本周", "避免集中兑付"),
                       ("days_90", "用中长期经营贷款置换部分高成本短期债务", "总经理", "90天", "延长融资期限")],
        "negative_operating_cashflow": [("days_30", "逐项复盘毛利、回款和刚性支出，形成经营现金改善清单", "经营负责人", "30天", "恢复经营现金净流入")],
        "receivables": [("immediate", "对前十大应收逐户明确回款日期和责任人", "销售负责人", "本周", "加快重点回款"),
                        ("days_30", "执行催收、早付款折扣并评估保理", "销售与财务负责人", "30天", "缩短回款周期"),
                        ("days_90", "建立客户信用额度和账期审批制度", "财务负责人", "90天", "控制新增应收")],
        "inventory": [("days_30", "清理滞销库存并降低非必要采购", "供应链负责人", "30天", "释放库存占用"),
                      ("days_90", "设置安全库存、库龄和采购预警线", "供应链负责人", "90天", "提高库存周转")],
        "credit_utilization": [("days_30", "提前准备续授信资料并补充备用额度", "财务负责人", "30天", "恢复融资缓冲"),
                               ("days_90", "建立分银行、分期限授信额度池", "财务负责人", "90天", "降低单一银行依赖")],
        "financing_cost": [("immediate", "停止新增高成本过桥和短期资金", "总经理", "本周", "控制财务费用"),
                           ("days_90", "比较银行产品并置换高成本融资", "财务负责人", "90天", "降低综合融资成本")],
        "expense": [("immediate", "暂停非必要资本支出并锁定可压缩费用", "总经理", "本周", "直接减少现金流出"),
                    ("days_30", "按部门落实费用压降目标", "各部门负责人", "30天", "兑现可压缩空间")],
        "data_verification": [("days_30", "补齐流水、征信、纳税和财务报表并统一口径", "财务负责人", "30天", "提高诊断和融资测算可靠性")],
    }
    expected_by_task = [(str(row.get("task", "")), row.get("expected_cash")) for row in actions]
    seen = set()
    for problem in problems:
        for bucket, action, owner, deadline, outcome in mapping.get(problem["code"], []):
            key = (bucket, action)
            if key in seen:
                continue
            expected = next((value for text, value in expected_by_task if value is not None and any(word in text for word in action.split("并")[:1])), None)
            plan[bucket].append({"action": action, "owner": owner, "deadline": deadline,
                                 "expected_cash": _money(expected) if expected is not None else "待执行后测算",
                                 "solves_problem": problem["name"], "target": outcome})
            seen.add(key)
    primary_problem = problems[0]["name"] if problems else "现金流管理"
    fallbacks = {
        "immediate": ("明确最高风险事项的责任人、资金影响和本周处置节点", "总经理与财务负责人", "本周", "先控制风险继续扩大"),
        "days_30": ("完成最高风险事项的专项复盘并量化改善结果", "财务负责人", "30天", "验证改善动作是否释放现金"),
        "days_90": ("把最高风险事项的控制要求纳入预算和经营考核", "总经理与财务负责人", "90天", "防止同类问题重复发生"),
    }
    for bucket, (action, owner, deadline, target) in fallbacks.items():
        if not plan[bucket]:
            plan[bucket].append({"action": action, "owner": owner, "deadline": deadline,
                "expected_cash": "待执行后测算", "solves_problem": primary_problem, "target": target})
    mechanisms = [
        ("建立13周滚动现金流预测和每周复盘机制", "财务负责人", "持续提前识别缺口"),
        ("建立月度资金预算、债务到期日历和现金预警阈值", "财务负责人", "形成长期现金流治理机制"),
        ("建立多银行授信组合并定期评估额度、成本和期限", "总经理与财务负责人", "提高融资稳定性"),
    ]
    for action, owner, target in mechanisms:
        plan["months_6"].append({"action": action, "owner": owner, "deadline": "6个月",
            "expected_cash": "机制建设，不单独估算", "solves_problem": "现金流管理机制", "target": target})
    return plan


def enrich_cashflow_report(db, cashflow, content: dict) -> dict:
    data = dict(content.get("working_capital") or {})
    try:
        original = __import__("json").loads(cashflow.input_json or "{}")
        if isinstance(original, dict):
            original.update({key: value for key, value in data.items() if value is not None})
            data = original
    except (TypeError, ValueError):
        pass
    metrics = {row.get("key"): row.get("value") for row in content.get("metrics", [])}
    overview = content.get("overview") or {}
    score = _number(overview.get("score"))
    actions = content.get("actions") or []
    priorities = sorted({row.get("priority") for row in actions if row.get("priority")})
    highest = priorities[0] if priorities else "P4"
    problems = build_core_problems(data, metrics, content.get("forecasts") or [], content.get("risks") or [])
    content["executive_summary"] = {
        "current_score": int(score) if score is not None else "待补充资料核验",
        "health_level": _health_level(score), "risk_level": overview.get("risk_level") or "待补充资料核验",
        "cash_runway": overview.get("runway"), "cash_gap_week": overview.get("gap_week"),
        "cash_gap_amount": overview.get("gap_amount"), "highest_priority": highest,
        "cash_gap_label": next((row.get("period_label") for row in content.get("forecasts", [])
                                if row.get("period_no") == overview.get("gap_week")), "待补充资料核验"),
        "highest_priority_label": PRIORITY_LABELS.get(highest, "待判断"),
    }
    content["core_problems"] = problems
    content["financing_capacity"] = build_financing_capacity(db, cashflow, data, int(score) if score is not None else None)
    content["improvement_plan"] = build_improvement_plan(problems, actions)
    return content
