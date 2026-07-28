"""财务字段的新旧口径兼容工具。"""

from __future__ import annotations


def net_profit_margin_fraction(
    net_profit: float | None,
    annual_revenue: float | None,
    net_profit_margin: float | None = None,
) -> float:
    """优先使用新百分比字段；旧记录回退为净利润金额÷营业收入。"""
    if net_profit_margin is not None:
        return float(net_profit_margin) / 100
    revenue = float(annual_revenue or 0)
    return float(net_profit or 0) / revenue if revenue else 0


def net_profit_margin_percent(
    net_profit: float | None,
    annual_revenue: float | None,
    net_profit_margin: float | None = None,
) -> float:
    return net_profit_margin_fraction(net_profit, annual_revenue, net_profit_margin) * 100
