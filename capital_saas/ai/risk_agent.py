class RiskAgent:
    def generate(self, data: dict, score: dict) -> dict:
        revenue = max(data["annual_revenue"], 1)
        debt_ratio = data["debt_total"] / revenue
        short_ratio = data["short_debt"] / max(data["debt_total"], 1)
        return {
            "cashflow_risk": (
                "应收周期偏长，需设置回款红线与滚动现金流预测。"
                if data["receivable_days"] > 60
                else "应收周期处于可控区间，仍需维持周度现金流监控。"
            ),
            "debt_risk": (
                "负债压力较高，应暂停新增高成本短债并推进债务置换。"
                if debt_ratio > 0.6 or short_ratio > 0.7
                else "负债结构总体可控，新增融资需与资产和订单周期匹配。"
            ),
            "post_loan": [
                "每周更新13周现金流预测",
                "月度监控资产负债率、利息保障倍数与应收账款周转",
                "设置偿债备付金，覆盖至少3个月本息",
                "融资用途专户管理，保留合同、发票和支付凭证",
            ],
            "warning": score["risk_level"],
        }

