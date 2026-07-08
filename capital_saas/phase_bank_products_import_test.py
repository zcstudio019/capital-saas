import sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from db.database import Base
from db.models import BankProduct
from core.bank_product_matcher import match_bank_products
from parsers.markdown_bank_product_parser import parse_markdown_bank_products
from services.bank_product_import_service import disable_mock_products, import_bank_products

SAMPLE = """# 企业信用类产品库
## 1. 【BOCOM-001】 普惠e贷1.0
- 机构：交通银行（交行）
- 原章节：第 1 章 国有大行
- 原分组：▶ 线上化产品（企业客户）
| 字段 | 内容 |
|---|---|
| 贷款类型 | 信用贷 |
| 利率 | 标准：3.25%；科技型：可议价 |
| 最高额度 | 普通企业：300万；制造业：400万；科技型企业：2000万 |
| 期限 | 新客户：6个月；老客户：12个月 |
## 2. 【CCB-003】 建设银行善营贷
- 机构：中国建设银行
- 原章节：第 1 章 国有大行
- 原分组：线上经营贷
| 字段 | 内容 |
|---|---|
| 贷款类型 | 经营信用贷 |
| 利率 | 年化3.15%-9.45% |
| 最高额度 | 50万-100万 |
| 贷款期限 | 最长3年 |
"""

def main():
    rows = parse_markdown_bank_products(SAMPLE)
    assert len(rows) == 2
    assert rows[0]["product_code"] == "BOCOM-001" and rows[0]["bank_name"] == "交通银行（交行）"
    assert rows[0]["product_name"] == "普惠e贷1.0" and rows[0]["product_type"] == "信用贷"
    assert rows[0]["max_amount"] == 2000 and (rows[0]["min_rate"], rows[0]["max_rate"]) == (3.25, 3.25)
    assert (rows[0]["min_term_months"], rows[0]["max_term_months"]) == (6, 12)
    engine = create_engine("sqlite:///:memory:"); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as db:
        db.add(BankProduct(bank_name="模拟国有银行", bank_type="银行", product_name="模拟产品", product_type="信用贷", data_source="mock", is_active=True)); db.commit()
        result = import_bank_products(db, rows, "企业信用类产品库.md")
        assert result["success"] == 2 and result["created"] == 2
        assert disable_mock_products(db) == 1
        a = SimpleNamespace(annual_revenue=10_000_000, years=3, tax_status=True, credit_status=True, has_collateral=False, receivable_days=0, industry="科技", funding_need=1_000_000)
        matched = match_bank_products(db, a)
        assert matched["matched_products"] and not matched["fallback_notice"]
        assert all(x["bank_name"] != "模拟国有银行" for x in matched["matched_products"])
    print("PHASE_BANK_PRODUCTS_IMPORT_OK")

if __name__ == "__main__": main()
