"""根据实际触发的问题生成差异化现金流行动优先级。"""

def build_actions(data: dict, metrics: dict, risks: list[dict]) -> list[dict]:
    actions: list[dict] = []
    def add(priority, timeframe, task, goal, expected=None):
        actions.append({"priority":priority,"timeframe":timeframe,"task":task,"owner":"财务负责人","due_text":timeframe,"goal":goal,"expected_cash":expected})
    if metrics.get("short_debt_cash_coverage") is not None and metrics["short_debt_cash_coverage"] < .3:
        add("P0","本周行动","梳理未来30天到期债务，立即与债权方协商展期或置换。","避免短期债务挤兑现金。")
    if data.get("cash_gap_week") or any(x["level"] == "red" for x in risks):
        add("P0","本周行动","冻结非紧急资本支出与非刚性支出，建立每日资金台账。","优先守住工资、税费和核心供应商付款。",data.get("compressible_expense"))
    if (data.get("dso_yoy") or 0) > 20 or (data.get("dso") or 0) > 90:
        add("P1","30天行动","对逾期应收逐户催收；新订单设置预付款、早付款折扣或保理方案。","缩短回款周期，释放应收占用。",data.get("receivables_balance"))
    if (data.get("dio_yoy") or 0) > 30 or (data.get("inventory_stagnant_ratio") or 0) > .2:
        add("P1","30天行动","制定滞销库存清理、采购降速和安全库存方案。","降低库存资金占用。",data.get("idle_assets_cash"))
    if (data.get("credit_utilization") or 0) > .8:
        add("P2","90天行动","补齐授信续作资料，比较循环授信、保理与供应链金融成本。","恢复可用融资缓冲。")
    if data.get("capex_deferrable"):
        add("P2","90天行动","评估可延后项目，分期或租赁替代一次性资本开支。","降低未来项目资金压力。")
    add("P3","6个月行动","建立滚动13周现金流预测及月度经营复盘。","提高现金缺口的提前预警能力。")
    add("P4","6个月行动","固化回款、采购账期、资本开支和融资额度管理制度。","形成长期现金流治理机制。")
    return actions
