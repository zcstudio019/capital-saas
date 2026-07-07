from typing import Any


STABILITY = {"bank": 15, "guarantee": 12, "factoring": 11, "leasing": 11,
             "microloan": 7, "private_fund": 6, "other": 8}


def _get(item: Any, key: str, default=0):
    return item.get(key, default) if isinstance(item, dict) else getattr(item, key, default)


def compare_financing_offers(applications: list[Any]) -> dict:
    ranking = []
    approved = [item for item in applications if _get(item, "application_status") in {"approved", "disbursed"}]
    for item in approved:
        apply_amount = max(float(_get(item, "apply_amount", 0)), 1)
        amount = float(_get(item, "final_amount", 0) or _get(item, "approved_amount", 0))
        rate = float(_get(item, "approved_rate", 0) or _get(item, "expected_rate", 0) or 20)
        term = int(_get(item, "loan_term", 12) or 12)
        amount_score = min(30, amount / apply_amount * 30)
        rate_score = max(0, min(25, 25 - max(rate - 3, 0) * 2.2))
        term_score = min(15, term / 24 * 15)
        stability_score = STABILITY.get(_get(item, "institution_type", "other"), 8)
        supplement_score = 3 if _get(item, "supplement_required", False) else 10
        renewal_score = 5 if _get(item, "institution_type") == "bank" else 3
        score = round(amount_score + rate_score + term_score + stability_score + supplement_score + renewal_score)
        pros, cons = [], []
        pros.append(f"批复额度覆盖申请的{amount / apply_amount * 100:.0f}%")
        if rate <= 6: pros.append("综合利率相对可控")
        else: cons.append("融资成本偏高")
        if term >= 24: pros.append("期限较长，月度现金流压力较低")
        else: cons.append("期限偏短，需要提前规划续贷或置换")
        if _get(item, "supplement_required", False): cons.append("附加资料或审批条件较多")
        ranking.append({"application_id": _get(item, "id"), "score": score,
                        "reason": f"额度、成本、期限及审批稳定性综合得分{score}", "pros": pros, "cons": cons})
    ranking.sort(key=lambda row: row["score"], reverse=True)
    return {"best_offer_id": ranking[0]["application_id"] if ranking else None,
            "ranking": ranking,
            "recommendation": "优先选择综合得分最高且提款条件可满足的方案，不应只比较名义利率。" if ranking else "暂无已批复方案可供比选。",
            "boss_decision_tip": "签约前同时核对担保、服务费、提前还款、续贷条件和资金用途限制。"}
