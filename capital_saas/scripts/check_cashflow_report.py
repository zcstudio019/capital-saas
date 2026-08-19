"""报告结构检查：确保客户可见文本采用中文且不泄漏技术对象。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from services.cashflow_service import metric_rows, forecast_rows

metrics, _ = metric_rows({"current_assets": None, "current_liabilities": 0})
forecast, _ = forecast_rows({"cash": None})
assert metrics[0]["status"] == "待补充资料核验"
assert metrics[0]["value"] is None and forecast[0]["ending_cash"] is None
assert all("None" not in x["name"] for x in metrics)
print("CASHFLOW_REPORT_CHECK_OK")
