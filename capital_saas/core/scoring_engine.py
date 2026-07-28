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
    years = float(data.get("years", 0))
    receivable_days = int(data.get("receivable_days", 0))

    margin_input = data.get("net_profit_margin")
    profit_margin = float(margin_input) / 100 if margin_input is not None else _ratio(profit, revenue)
    debt_ratio = _ratio(debt, revenue)
    short_ratio = _ratio(short_debt, debt)
    business = (
        (5 if years >= 5 else 4 if years >= 3 else 2.5)
        + (5 if revenue >= 10_000_000 else 4 if revenue >= 3_000_000 else 3)
        + (5 if profit_margin >= .12 else 4 if profit_margin > 0 else 2)
    ) / 3
    credit = 4.5 if data.get("credit_status") else 1.8
    query_count = max(int(data.get("credit_query_count_6m") or 0), 0)
    card_usage = data.get("credit_card_usage_rate")
    if query_count:
        credit += 0.3 if query_count <= 3 else -0.4 if query_count <= 6 else -1
    if card_usage is not None:
        credit += 0.2 if float(card_usage) <= 50 else -0.4 if float(card_usage) <= 80 else -0.8
    if data.get("online_loan_status") == "active":
        credit -= 0.7
    credit = max(1, min(5, credit))
    cash = (
        (5 if cashflow >= revenue / 15 else 4 if cashflow > 0 else 1.5)
        + (5 if receivable_days <= 45 else 3.5 if receivable_days <= 90 else 2)
        + (4 if data.get("has_budget") else 2.5)
    ) / 3
    operating_flow_ratio = data.get("operating_flow_ratio")
    internal_transfer_ratio = data.get("internal_transfer_ratio")
    if operating_flow_ratio is not None:
        cash += 0.3 if float(operating_flow_ratio) >= 80 else -0.4 if float(operating_flow_ratio) < 50 else 0
    if internal_transfer_ratio is not None and float(internal_transfer_ratio) > 30:
        cash -= 0.4
    if data.get("fast_in_out_status") == "frequent":
        cash -= 0.6
    cash = max(1, min(5, cash))
    liabilities = (
        (5 if debt_ratio <= .3 else 4 if debt_ratio <= .6 else 2)
        + (5 if debt == 0 or short_ratio <= .35 else 3.5 if short_ratio <= .65 else 2)
    ) / 2
    judicial = 3.5  # 公开司法数据需在正式交付前复核，未核验时采用中性分。
    judicial_statuses = [
        data.get("enforcement_status", "unknown"),
        data.get("dishonest_status", "unknown"),
        data.get("consumption_restriction_status", "unknown"),
    ]
    if "current" in judicial_statuses:
        judicial = 1.2
    elif "resolved" in judicial_statuses:
        judicial = 2.8
    if data.get("lawsuit_defendant_status") == "yes":
        judicial -= 0.6
    judicial = max(1, judicial)
    tax_unknown = (
        data.get("tax_arrears_status", "unknown") == "unknown"
        and data.get("tax_credit_grade", "unknown") == "unknown"
    )
    tax = 3.2 if tax_unknown else 4.5 if data.get("tax_status") else 1.8
    if data.get("tax_credit_grade") == "A":
        tax = min(5, tax + 0.4)
    elif data.get("tax_credit_grade") in {"C", "D"}:
        tax = max(1, tax - 1)
    assets = (
        (4.5 if data.get("has_collateral") else 2)
        + (5 if receivable_days <= 45 else 3.5 if receivable_days <= 90 else 2)
        + {"高": 4.5, "中": 3.5, "低": 2.5}.get(data.get("asset_efficiency"), 3)
    ) / 3
    asset_value = sum(float(data.get(key) or 0) for key in (
        "property_value", "factory_value", "land_value", "vehicle_value",
        "equipment_value", "financeable_receivables", "inventory_value",
    ))
    if asset_value > 0:
        assets = min(5, assets + 0.5)
    financing = (
        (4.5 if data.get("credit_status") else 2)
        + (3.2 if tax_unknown else 4.5 if data.get("tax_status") else 2)
        + (4 if funding_need <= max(revenue * .35, 1) else 2)
    ) / 3

    raw_dimensions = {
        "企业基本面": business,
        "征信状况": credit,
        "流水质量": cash,
        "负债情况": liabilities,
        "司法风险": judicial,
        "税务合规": tax,
        "资产状况": assets,
        "融资能力": financing,
    }
    weights = {
        "企业基本面": 15, "征信状况": 20, "流水质量": 15, "负债情况": 15,
        "司法风险": 10, "税务合规": 10, "资产状况": 5, "融资能力": 10,
    }
    dimensions = {name: round(max(1, min(5, score)), 1) for name, score in raw_dimensions.items()}
    total = round(sum(dimensions[name] * weights[name] / 5 for name in dimensions))

    if total >= 80:
        grade, grade_text = "A", "资本健康，具备较好融资基础"
    elif total >= 70:
        grade, grade_text = "B+", "资本亚健康，优化后融资更稳妥"
    elif total >= 60:
        grade, grade_text = "B", "资本亚健康，需要改善关键指标"
    elif total >= 50:
        grade, grade_text = "C", "资本风险较高，应先修复再融资"
    else:
        grade, grade_text = "D", "资本状态危急，暂不建议直接融资"

    funding_probability = "较高" if total >= 80 else "中等" if total >= 60 else "较低"
    risk_level = "健康" if total >= 80 else "亚健康" if total >= 60 else "高风险" if total >= 40 else "危急"

    weakest = min(dimensions, key=dimensions.get)
    risk_map = {
        "企业基本面": "经营规模、盈利或持续经营证明不足，可能影响授信基础。",
        "征信状况": "企业或法人征信存在待核验事项，申请前需要先行修复。",
        "流水质量": "经营流水质量偏弱，应收账款周期可能形成资金缺口。",
        "负债情况": "负债水平或短期债务占比偏高，存在期限错配压力。",
        "司法风险": "司法公开数据尚需复核，重大诉讼或执行会影响准入。",
        "税务合规": "纳税连续性或税务合规存在短板，可能影响税票类融资。",
        "资产状况": "可用于抵押、增信或盘活的资产证明不足。",
        "融资能力": "新增融资空间和准入条件偏弱，应先优化后申请。",
    }
    literacy_gap = (
        "当前缺少清晰的现金流预算和资金使用闭环。"
        if not data.get("has_budget") or not data.get("fund_usage_plan")
        else "需要进一步建立融资成本、回报率与风险的量化决策机制。"
    )
    finance_now = (
        "建议马上进入融资方案设计"
        if total >= 80
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
