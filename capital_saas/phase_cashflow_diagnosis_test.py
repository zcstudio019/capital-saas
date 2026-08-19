"""现金流诊断专项回归：使用内存库，不影响已有客户及旧报告。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.database import Base
from db.models import CustomerAccount, CashflowActionItem, CashflowForecast, CashflowMetricResult, CashflowReport, CashflowRiskSignal
from services.cashflow_service import create_diagnosis, report_content

engine = create_engine("sqlite:///:memory:")
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
db = Session()
customer = CustomerAccount(company_name="测试企业", login_phone="13800138000", name="张三")
db.add(customer); db.commit()
data = {
    "company_name":"测试企业", "phone":"13800138000", "current_assets":100, "current_liabilities":200,
    "inventory":20, "cash":20, "monthly_operating_expense":50, "revenue":1000, "net_profit":100,
    "operating_cashflow":-30, "cash_received_sales":800, "capex":10, "total_assets":500,
    "total_debt":350, "interest_bearing_debt":250, "short_interest_debt":100, "interest_expense":20,
    "ebit":30, "dso":120, "dso_yoy":25, "dio":100, "dio_yoy":35, "dpo":30, "dpo_yoy":-15,
    "credit_limit":100, "credit_used":90, "negative_operating_cf_months":3, "loan_overdue":True,
    "compressible_expense":15, "forecast_in_1":10, "forecast_out_1":50,
}
assessment, report, content = create_diagnosis(db, data, customer)
assert assessment.customer_id == customer.id
assert db.query(CashflowMetricResult).filter_by(assessment_id=assessment.id).count() >= 8
assert next(x for x in content["metrics"] if x["key"] == "ccc")["value"] == 190
assert db.query(CashflowRiskSignal).filter_by(assessment_id=assessment.id).count() >= 1
assert {x.priority for x in db.query(CashflowActionItem).filter_by(assessment_id=assessment.id)} >= {"P0", "P1", "P3", "P4"}
assert db.query(CashflowForecast).filter_by(assessment_id=assessment.id).count() == 6
assert assessment.cash_gap_week == 1 and assessment.cash_gap_amount == 20
assert db.get(CashflowReport, report.id).customer_id == customer.id
assert report_content(report)["title"] == "企业现金流健康诊断报告"
assert "None" not in report.content_json and "{'" not in report.content_json
partial, partial_report, partial_content = create_diagnosis(db, {"company_name":"资料不全企业"})
assert partial.health_score is None and partial.risk_level == "待补充资料核验"
assert partial_content["metrics"][0]["status"] == "待补充资料核验"
print("CASHFLOW_DIAGNOSIS_OK")
