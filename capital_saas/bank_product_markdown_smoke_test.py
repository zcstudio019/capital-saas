import sys
import os
import tempfile
from pathlib import Path
ROUTE_DB = Path(tempfile.gettempdir()) / "capital_saas_markdown_import_test.db"
if ROUTE_DB.exists(): ROUTE_DB.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{ROUTE_DB.as_posix()}"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from db.database import Base
from db.models import BankProduct
from parsers.markdown_bank_product_parser import parse_amount, parse_markdown_bank_products, parse_rate, parse_term
from services.bank_product_import_service import import_bank_products

CONTENT = """
# 产品库

| 银行/机构 | 产品名称 | 产品类型 | 城市 | 额度 | 利率 | 期限 | 准入条件 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 建设银行 | 税贷 | 信用贷 | 上海 | 10-300万 | 3.8%-6.0% | 12个月 | 纳税正常、征信正常 |

## 工商银行｜经营快贷
产品类型：信用贷
城市：上海
额度：最高500万
利率：年化3.8起
期限：1-3年
需抵押：是
所需资料：营业执照、银行流水

### 无法拆分的产品
产品类型：经营贷
城市：杭州
额度：300万元以内
利率：4.5%左右
期限：最长5年
"""

rows = parse_markdown_bank_products(CONTENT)
assert len(rows) == 3, rows
assert rows[0]["min_amount"] == 10 and rows[0]["max_amount"] == 300
assert rows[0]["min_rate"] == 3.8 and rows[0]["max_rate"] == 6.0
assert rows[0]["min_term_months"] == rows[0]["max_term_months"] == 12
assert rows[1]["bank_name"] == "工商银行" and rows[1]["requires_collateral"] is True
assert rows[1]["min_term_months"] == 12 and rows[1]["max_term_months"] == 36
assert rows[2]["bank_name"] == "待补充机构" and rows[2]["max_term_months"] == 60
assert parse_amount("50万起") == (50, None)
assert parse_rate("4.5%左右") == (4.5, 4.5)
assert parse_term("最长5年") == (None, 60)

engine = create_engine("sqlite:///:memory:")
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
with Session() as db:
    result = import_bank_products(db, rows)
    assert result == {"parsed": 3, "success": 3, "failed": 0, "errors": []}, result
    products = db.query(BankProduct).all()
    assert all(item.data_source == "imported" for item in products)
    assert products[0].max_amount == 3_000_000
    again = import_bank_products(db, rows)
    assert again["success"] == 3 and db.query(BankProduct).count() == 3
from fastapi.testclient import TestClient
from main import app
from db.database import SessionLocal, engine as app_engine
with TestClient(app) as client:
    login = client.post("/login", data={"username": "admin", "password": "admin123", "next_url": "/admin"}, follow_redirects=False)
    assert login.status_code == 303
    page = client.get("/admin/bank-products/import")
    assert page.status_code == 200 and "CSV / Excel / Markdown" in page.text
    response = client.post("/admin/bank-products/import", files={"upload": ("products.md", CONTENT.encode("utf-8"), "text/markdown")})
    assert response.status_code == 200, response.text
    assert "成功导入" in response.text and ">3<" in response.text
with SessionLocal() as db:
    imported = db.query(BankProduct).filter_by(data_source="imported").count()
    assert imported == 3, imported
app_engine.dispose()
if ROUTE_DB.exists(): ROUTE_DB.unlink()
print("MARKDOWN_BANK_PRODUCT_IMPORT_OK")