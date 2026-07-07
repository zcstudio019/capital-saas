def lead_grade(score: int, funding_need: float) -> str:
    if score >= 75 and funding_need >= 1_000_000:
        return "A"
    if score >= 60 or funding_need >= 500_000:
        return "B"
    return "C"


def recommended_product(score: int) -> str:
    if score >= 75:
        return "融资结构优化方案"
    if score >= 60:
        return "融资能力提升辅导"
    return "财务与现金流基础治理"

