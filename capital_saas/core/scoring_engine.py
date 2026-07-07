from dataclasses import dataclass


@dataclass
class ScoreResult:
    total: int
    grade: str
    grade_text: str
    funding_probability: str
    risk_level: str
    dimensions: dict[str, int]
    core_risk: str
    financial_literacy_gap: str
    finance_now: str


def _ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator > 0 else 0


def calculate_score(data: dict) -> ScoreResult:
    revenue = max(float(data.get("annual_revenue", 0)), 0)
    profit = float(data.get("net_profit", 0))
    cashflow = float(data.get("monthly_cashflow", 0))
    debt = max(float(data.get("debt_total", 0)), 0)
    short_debt = max(float(data.get("short_debt", 0)), 0)
    funding_need = max(float(data.get("funding_need", 0)), 0)
    years = int(data.get("years", 0))
    receivable_days = int(data.get("receivable_days", 0))

    business = 4
    business += 4 if years >= 5 else 3 if years >= 3 else 1
    business += 4 if revenue >= 10_000_000 else 3 if revenue >= 3_000_000 else 1
    business += {"高": 3, "中": 2, "低": 0}.get(data.get("asset_efficiency"), 1)

    profit_margin = _ratio(profit, revenue)
    financial = 3
    financial += 6 if profit_margin >= 0.15 else 4 if profit_margin >= 0.08 else 2 if profit > 0 else 0
    debt_ratio = _ratio(debt, revenue)
    financial += 6 if debt_ratio <= 0.3 else 4 if debt_ratio <= 0.6 else 1
    financial += 5 if revenue >= 5_000_000 else 3 if revenue >= 1_000_000 else 1

    cash = 2
    cash += 8 if cashflow >= revenue / 18 else 6 if cashflow > 0 else 0
    cash += 6 if receivable_days <= 45 else 4 if receivable_days <= 90 else 1
    cash += 4 if data.get("has_budget") else 0

    debt_structure = 3
    short_ratio = _ratio(short_debt, debt)
    debt_structure += 6 if debt == 0 or short_ratio <= 0.4 else 4 if short_ratio <= 0.7 else 1
    debt_structure += 6 if debt_ratio <= 0.4 else 3 if debt_ratio <= 0.7 else 0

    financing = 1
    financing += 4 if data.get("tax_status") else 0
    financing += 4 if data.get("credit_status") else 0
    financing += 3 if data.get("has_collateral") else 0
    financing += 3 if funding_need <= max(revenue * 0.3, 1) else 1

    literacy = 1
    literacy += 4 if data.get("knows_cashflow") else 0
    literacy += 4 if data.get("has_budget") else 0
    literacy += 3 if data.get("fund_usage_plan") else 0
    literacy += {"适中": 3, "保守": 2, "激进": 0}.get(data.get("leverage_attitude"), 1)

    dimensions = {
        "商业模式": min(business, 15),
        "财务健康": min(financial, 20),
        "现金流质量": min(cash, 20),
        "负债结构": min(debt_structure, 15),
        "融资条件": min(financing, 15),
        "财商能力": min(literacy, 15),
    }
    total = max(0, min(sum(dimensions.values()), 100))

    if total >= 90:
        grade, grade_text = "S", "可融资且结构优秀"
    elif total >= 75:
        grade, grade_text = "A", "可融资但需优化"
    elif total >= 60:
        grade, grade_text = "B", "融资受限，需要调整"
    elif total >= 45:
        grade, grade_text = "C", "高风险，直接融资难度大"
    else:
        grade, grade_text = "D", "暂不建议直接融资"

    funding_probability = "high" if total >= 75 else "medium" if total >= 60 else "low"
    risk_level = "low" if total >= 75 else "medium" if total >= 60 else "high"

    weakest = min(dimensions, key=dimensions.get)
    risk_map = {
        "商业模式": "经营稳定性与商业模式证明不足，银行可能下调授信预期。",
        "财务健康": "盈利与偿债指标偏弱，可能影响银行对还款来源的判断。",
        "现金流质量": "经营现金流承压，应收账款周期可能形成资金缺口。",
        "负债结构": "短期债务占比偏高，存在期限错配和集中偿付压力。",
        "融资条件": "税务、征信或增信条件存在短板，申请前需要先行修复。",
        "财商能力": "资金规划与预算管理不足，融资后资金使用风险较高。",
    }
    literacy_gap = (
        "当前缺少清晰的现金流预算和资金使用闭环。"
        if not data.get("has_budget") or not data.get("fund_usage_plan")
        else "需要进一步建立融资成本、回报率与风险的量化决策机制。"
    )
    finance_now = (
        "建议马上进入融资方案设计"
        if total >= 75
        else "建议优化关键指标后再申请"
        if total >= 60
        else "暂不建议盲目申请融资"
    )
    return ScoreResult(
        total=total,
        grade=grade,
        grade_text=grade_text,
        funding_probability=funding_probability,
        risk_level=risk_level,
        dimensions=dimensions,
        core_risk=risk_map[weakest],
        financial_literacy_gap=literacy_gap,
        finance_now=finance_now,
    )

