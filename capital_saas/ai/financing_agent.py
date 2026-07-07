class FinancingAgent:
    def generate(self, data: dict, score: dict) -> dict:
        revenue = data["annual_revenue"]
        need = data["funding_need"]
        high = max(min(revenue * 0.3, need * 1.2), need * 0.6)
        low = max(min(revenue * 0.1, need * 0.6), 100_000)
        collateral = data["has_collateral"]
        return {
            "feasibility": score["funding_probability"],
            "loan_range": f"{low / 10000:.0f}万—{high / 10000:.0f}万元",
            "bank_pass_rate": "较高" if score["total"] >= 75 else "中等" if score["total"] >= 60 else "偏低",
            "short_term": "优先整理近12个月流水、纳税与应收账款资料，匹配经营性信用贷。"
            if score["total"] >= 60
            else "先修复现金流与征信/纳税资料，再进行预授信测算。",
            "medium_term": "建立授信银行组合，并将短期高成本负债置换为期限匹配的经营贷。",
            "long_term": "以规范财务数据和持续增长记录为基础，逐步引入产业资本或股权融资。",
            "portfolio": (
                "抵押贷40% + 信用贷30% + 供应链金融30%"
                if collateral
                else "信用贷40% + 供应链金融40% + 股东资金/股权融资20%"
            ),
        }

