"""现金流风险规则：只基于已填写资料，缺失资料不推断为正常。"""

RISK_LABELS = {"red": "严重风险", "orange": "较高风险", "yellow": "需关注", "green": "正常"}


def build_risk_signals(data: dict, metrics: dict) -> list[dict]:
    signals: list[dict] = []
    def add(level: str, title: str, detail: str):
        signals.append({"level": level, "label": RISK_LABELS[level], "title": title, "detail": detail})
    negative_months = data.get("negative_operating_cf_months")
    if negative_months is not None and negative_months >= 3: add("red", "经营现金流持续为负", "已连续3个月及以上经营现金流为负。")
    coverage = metrics.get("short_debt_cash_coverage")
    if coverage is not None and coverage < .3: add("red", "现金覆盖短期债务不足30%", "短期偿债缓冲不足。")
    if (data.get("dso_yoy") or 0) > 20: add("orange", "应收回款周期明显拉长", "DSO同比增加超过20%。")
    if (data.get("dio_yoy") or 0) > 30: add("orange", "库存周转恶化", "DIO同比增加超过30%。")
    if data.get("dpo_yoy") is not None and data["dpo_yoy"] < -10: add("yellow", "付款账期缩短", "DPO下降，供应商资金占用空间收窄。")
    if data.get("gross_margin_declining"): add("yellow", "毛利率持续下降", "需要复核订单结构与成本控制。")
    utilization = metrics.get("credit_utilization")
    if utilization is not None and utilization > .8: add("orange", "授信使用率偏高", "已用授信超过80%，新增融资弹性有限。")
    for key, title in [("loan_overdue", "贷款逾期"), ("credit_withdrawal", "存在抽贷压贷"), ("major_lawsuit", "存在重大诉讼"), ("tax_arrears", "存在欠税")]:
        if data.get(key): add("red", title, "请提供相关资料供顾问核验并制定处置方案。")
    for key, title in [("financing_cost_rising", "融资成本上升"), ("bridge_funding_high", "过桥资金比例偏高"), ("supplier_customer_risk", "客户或供应商存在风险"), ("payroll_social_security_delayed", "工资或社保存在延期")]:
        if data.get(key): add("orange", title, "建议纳入近期资金安排与风险处置清单。")
    return signals or [{"level": "green", "label": "正常", "title": "暂未识别显著风险", "detail": "仅基于已填写资料；缺失项目仍需补充核验。"}]
