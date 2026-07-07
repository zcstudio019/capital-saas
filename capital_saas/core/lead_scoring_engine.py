from dataclasses import asdict, dataclass


@dataclass
class LeadScoreResult:
    lead_score: int
    lead_grade: str
    recommended_product: str
    priority: str
    next_action: str

    def to_dict(self) -> dict:
        return asdict(self)


def calculate_lead_score(data: dict, assessment_score: int) -> LeadScoreResult:
    funding_need = float(data.get("funding_need", 0))
    if funding_need >= 5_000_000:
        funding_points = 25
    elif funding_need >= 2_000_000:
        funding_points = 20
    elif funding_need >= 500_000:
        funding_points = 15
    else:
        funding_points = 8

    if assessment_score >= 85:
        assessment_points = 25
    elif assessment_score >= 75:
        assessment_points = 20
    elif assessment_score >= 60:
        assessment_points = 15
    else:
        assessment_points = 8

    healthy_items = int(bool(data.get("credit_status"))) + int(bool(data.get("tax_status")))
    compliance_points = {2: 20, 1: 10, 0: 3}[healthy_items]
    collateral_points = 15 if data.get("has_collateral") else 5

    monthly_cashflow = float(data.get("monthly_cashflow", 0))
    monthly_revenue = float(data.get("annual_revenue", 0)) / 12
    cashflow_ratio = monthly_cashflow / monthly_revenue if monthly_revenue > 0 else 0
    if monthly_cashflow > 0 and cashflow_ratio >= 0.5:
        cashflow_points = 15
    elif monthly_cashflow > 0 and cashflow_ratio >= 0.15:
        cashflow_points = 10
    else:
        cashflow_points = 5

    total = funding_points + assessment_points + compliance_points + collateral_points + cashflow_points
    if total >= 85:
        grade = "S"
    elif total >= 70:
        grade = "A"
    elif total >= 55:
        grade = "B"
    elif total >= 40:
        grade = "C"
    else:
        grade = "D"

    product_map = {
        "S": "high_ticket_consulting",
        "A": "1999_structure_plan",
        "B": "699_bank_match",
        "C": "299_report",
        "D": "free_nurture",
    }
    priority = "high" if grade in {"S", "A"} else "medium" if grade in {"B", "C"} else "low"
    action_map = {
        "S": "2小时内联系，安排融资结构预诊断与顾问沟通。",
        "A": "当日联系，讲解申请顺序与1999元结构优化方案。",
        "B": "24小时内联系，推荐699元银行匹配与额度预测报告。",
        "C": "发送299元完整诊断报告价值说明，先诊断再申请。",
        "D": "进入长期培育，先发送基础条件改善清单。",
    }
    return LeadScoreResult(total, grade, product_map[grade], priority, action_map[grade])

