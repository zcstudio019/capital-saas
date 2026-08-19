import json
from datetime import datetime

from core.cashflow_priority_engine import build_actions
from core.cashflow_risk_engine import build_risk_signals
from db.models import (CashflowActionItem, CashflowAssessment, CashflowDebtAnalysis,
    CashflowExpenseAnalysis, CashflowForecast, CashflowMetricResult, CashflowReport,
    CashflowReportVersion, CashflowRiskSignal, CashflowWorkingCapital)

METRICS = [
    ("current_ratio", "流动比率", "倍", lambda d: ratio(d.get("current_assets"), d.get("current_liabilities")), (1.5, 1.0)),
    ("quick_ratio", "速动比率", "倍", lambda d: ratio(sub(d.get("current_assets"), d.get("inventory")), d.get("current_liabilities")), (1.0, .7)),
    ("cash_ratio", "现金比率", "倍", lambda d: ratio(d.get("cash"), d.get("current_liabilities")), (.5, .2)),
    ("cash_coverage", "现金保障倍数", "月", lambda d: ratio(d.get("cash"), d.get("monthly_operating_expense")), (3, 1)),
    ("operating_cf_profit", "经营现金流利润比", "倍", lambda d: ratio(d.get("operating_cashflow"), d.get("net_profit")), (.8, .3)),
    ("cash_collection_rate", "销售收现率", "%", lambda d: pct(ratio(d.get("cash_received_sales"), d.get("revenue"))), (90, 70)),
    ("free_cashflow", "自由现金流", "元", lambda d: sub(d.get("operating_cashflow"), d.get("capex")), (0, None)),
    ("ccc", "现金转换周期 CCC", "天", lambda d: ccc(d), (90, 150)),
    ("debt_ratio", "资产负债率", "%", lambda d: pct(ratio(d.get("total_debt"), d.get("total_assets"))), (60, 75)),
    ("interest_debt_ratio", "有息负债率", "%", lambda d: pct(ratio(d.get("interest_bearing_debt"), d.get("total_assets"))), (40, 60)),
    ("short_debt_ratio", "短期负债占比", "%", lambda d: pct(ratio(d.get("short_interest_debt"), d.get("interest_bearing_debt"))), (50, 70)),
    ("interest_coverage", "利息保障倍数", "倍", lambda d: ratio(d.get("ebit"), d.get("interest_expense")), (3, 1)),
    ("short_debt_cash_coverage", "现金覆盖短期债务", "%", lambda d: ratio(d.get("cash"), d.get("short_interest_debt")), (.5, .3)),
    ("credit_utilization", "授信使用率", "%", lambda d: ratio(d.get("credit_used"), d.get("credit_limit")), (.7, .8)),
]

def ratio(a, b): return None if a is None or b is None or b == 0 else a / b
def sub(a, b): return None if a is None or b is None else a - b
def pct(v): return None if v is None else v * 100
def ccc(d):
    values = (d.get("dio"), d.get("dso"), d.get("dpo"))
    return None if any(v is None for v in values) else values[0] + values[1] - values[2]

def metric_rows(data):
    rows, values = [], {}
    for key, name, unit, func, thresholds in METRICS:
        value = func(data); values[key] = value
        if value is None: status = "待补充资料核验"
        elif thresholds[1] is not None and value < thresholds[1]: status = "危险"
        elif thresholds[0] is not None and value < thresholds[0]: status = "关注"
        else: status = "正常"
        rows.append({"key":key,"name":name,"value":value,"unit":unit,"status":status})
    return rows, values

def forecast_rows(data):
    opening = data.get("cash")
    result = []
    for index, label in enumerate(["第1周","第2周","第3周","第4周","第5-8周","第9-13周"], 1):
        incoming, outgoing = data.get(f"forecast_in_{index}"), data.get(f"forecast_out_{index}")
        net = sub(incoming, outgoing)
        ending = None if opening is None or net is None else opening + net
        result.append({"period_no":index,"period_label":label,"cash_in":incoming,"cash_out":outgoing,"net_cashflow":net,"ending_cash":ending})
        opening = ending
    gaps = [x for x in result if x["ending_cash"] is not None and x["ending_cash"] < 0]
    return result, (gaps[0] if gaps else None)

def create_diagnosis(db, data, customer=None, lead=None):
    metrics, values = metric_rows(data); forecasts, gap = forecast_rows(data)
    data["cash_gap_week"] = gap["period_no"] if gap else None
    data["cash_gap_amount"] = abs(gap["ending_cash"]) if gap else None
    data["cash_runway_months"] = values.get("cash_coverage")
    risks = build_risk_signals(data, values); actions = build_actions(data, values, risks)
    severe = sum(x["level"] == "red" for x in risks); high = sum(x["level"] == "orange" for x in risks)
    core_filled = sum(data.get(key) is not None for key in ("cash", "monthly_operating_expense", "current_assets", "current_liabilities", "revenue", "operating_cashflow"))
    score = max(0, 100 - severe * 25 - high * 12 - sum(x["status"] == "危险" for x in metrics) * 6 - sum(x["status"] == "关注" for x in metrics) * 2) if core_filled >= 4 else None
    risk_level = "待补充资料核验" if score is None else ("严重风险" if severe else "较高风险" if high else "需关注" if any(x["status"] != "正常" for x in metrics) else "正常")
    assessment = CashflowAssessment(customer_id=customer.id if customer else None, lead_id=lead.id if lead else None,
        organization_id=getattr(lead, "org_id", None), company_name=data.get("company_name") or "待补充资料核验",
        phone=data.get("phone") or "", industry=data.get("industry") or "", business_scope=data.get("business_scope") or "",
        years=data.get("years"), company_type=data.get("company_type") or "", controller=data.get("controller") or "",
        employee_count=data.get("employee_count"), finance_contact=data.get("finance_contact") or "", credit_code=data.get("credit_code") or "",
        input_json=json.dumps(data, ensure_ascii=False), health_score=score, risk_level=risk_level,
        cash_gap_week=data["cash_gap_week"], cash_gap_amount=data["cash_gap_amount"], cash_runway_months=data["cash_runway_months"])
    db.add(assessment); db.flush()
    for row in metrics: db.add(CashflowMetricResult(assessment_id=assessment.id, metric_key=row["key"], metric_name=row["name"], value=row["value"], unit=row["unit"], status=row["status"]))
    db.add(CashflowWorkingCapital(assessment_id=assessment.id, receivables_balance=data.get("receivables_balance"), dso=data.get("dso"), dso_yoy=data.get("dso_yoy"), inventory_balance=data.get("inventory"), dio=data.get("dio"), dio_yoy=data.get("dio_yoy"), payables_balance=data.get("payables_balance"), dpo=data.get("dpo"), dpo_yoy=data.get("dpo_yoy"), details_json="{}"))
    db.add(CashflowDebtAnalysis(assessment_id=assessment.id, details_json=json.dumps({k:data.get(k) for k in ("credit_limit","credit_used","factoring","lease_finance","shareholder_loan","government_loan")}, ensure_ascii=False)))
    db.add(CashflowExpenseAnalysis(assessment_id=assessment.id, details_json=json.dumps({k:data.get(k) for k in ("capex","compressible_expense","idle_assets_cash")}, ensure_ascii=False)))
    for row in forecasts: db.add(CashflowForecast(assessment_id=assessment.id, **row))
    for row in risks: db.add(CashflowRiskSignal(assessment_id=assessment.id, level=row["level"], title=row["title"], detail=row["detail"]))
    for row in actions: db.add(CashflowActionItem(assessment_id=assessment.id, **row))
    content = {"title":"企业现金流健康诊断报告","generated_at":datetime.now().strftime("%Y-%m-%d"),"overview":{"score":score if score is not None else "待补充资料核验","risk_level":risk_level,"runway":data["cash_runway_months"],"gap_week":data["cash_gap_week"],"gap_amount":data["cash_gap_amount"]},"metrics":metrics,"working_capital":data,"forecasts":forecasts,"risks":risks,"actions":actions,"advisor_note":"建议预约顾问，结合已上传财务资料进行核验与落地辅导。"}
    report = CashflowReport(assessment_id=assessment.id, customer_id=assessment.customer_id, content_json=json.dumps(content, ensure_ascii=False))
    db.add(report); db.flush(); version = CashflowReportVersion(report_id=report.id, version_no=1, content_json=report.content_json); db.add(version); db.flush(); report.current_version_id=version.id
    db.commit(); return assessment, report, content

def report_content(report):
    try: return json.loads(report.content_json)
    except (TypeError, ValueError): return {}
