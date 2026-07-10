from pathlib import Path
from types import SimpleNamespace
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.bank_product_matcher import match_bank_products
from db.database import Base
from db.models import BankProduct


def product(
    name,
    product_type,
    min_revenue,
    min_years,
    min_amount,
    max_amount,
    *,
    requires_tax=False,
    requires_credit=True,
    requires_collateral=False,
    source="imported",
    industry="通用",
    city="全国",
    risk_notes="",
):
    return BankProduct(
        product_code=name.upper().replace(" ", "_"),
        bank_name="测试银行",
        bank_type="银行",
        product_name=name,
        product_type=product_type,
        city=city,
        suitable_industry=industry,
        min_revenue=min_revenue,
        min_years=min_years,
        min_amount=min_amount,
        max_amount=max_amount,
        requires_tax_normal=requires_tax,
        requires_credit_normal=requires_credit,
        requires_collateral=requires_collateral,
        interest_rate_range="年化3.5%-8.0%",
        loan_term="12-36个月",
        required_documents_json='["营业执照","近12个月纳税记录","近6个月银行流水"]',
        risk_notes=risk_notes,
        data_source=source,
        is_active=True,
    )


def customer(**kwargs):
    base = dict(
        company_name="测试企业",
        industry="科技",
        city="上海",
        annual_revenue=20_000_000,
        funding_need=3_000_000,
        years=4,
        tax_status=True,
        invoice_status=True,
        credit_status=True,
        has_collateral=False,
        debt_total=4_000_000,
        monthly_cashflow=500_000,
        query_count=2,
        funding_purpose="经营周转",
        document_completeness=0.75,
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def names(result):
    return [item["product_name"] for item in result["matched_products"]]


def main():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as db:
        db.add_all(
            [
                product("税票信用贷", "税贷", 1_000_000, 2, 100_000, 5_000_000, requires_tax=True),
                product("线上经营信用贷", "信用贷", 800_000, 1, 50_000, 3_000_000),
                product("抵押经营贷", "抵押贷", 2_000_000, 2, 1_000_000, 20_000_000, requires_collateral=True),
                product("大额经营贷", "经营贷", 10_000_000, 5, 5_000_000, 30_000_000, requires_collateral=True),
                product("弱资质担保贷", "担保贷", 300_000, 1, 50_000, 1_500_000, requires_credit=False, risk_notes="适合征信轻微瑕疵客户"),
                product("模拟固定产品", "信用贷", 0, 1, 10_000, 9_999_999, source="mock"),
            ]
        )
        db.commit()

        customer_a = customer(company_name="高营收信用客户", funding_need=3_000_000, has_collateral=False)
        customer_b = customer(
            company_name="大额抵押客户",
            annual_revenue=80_000_000,
            funding_need=15_000_000,
            years=10,
            has_collateral=True,
            tax_status=True,
            credit_status=True,
            debt_total=20_000_000,
        )
        customer_c = customer(
            company_name="弱资质客户",
            annual_revenue=800_000,
            funding_need=800_000,
            years=1,
            tax_status=False,
            invoice_status=False,
            credit_status=False,
            has_collateral=False,
            query_count=12,
            debt_total=900_000,
            document_completeness=0.25,
        )

        result_a = match_bank_products(db, customer_a, include_debug=True)
        result_b = match_bank_products(db, customer_b, include_debug=True)
        result_c = match_bank_products(db, customer_c, include_debug=True)

        assert names(result_a)[0] in {"税票信用贷", "线上经营信用贷"}
        assert names(result_b)[0] in {"抵押经营贷", "大额经营贷"}
        assert names(result_a) != names(result_b)
        assert names(result_c) != names(result_a)
        assert all(item["product_name"] != "模拟固定产品" for item in result_a["matched_products"])

        scores = [item["match_score"] for item in result_a["matched_products"] + result_b["matched_products"] + result_c["matched_products"]]
        assert len(set(scores)) > 3
        assert any(score != 90 for score in scores)
        assert max(item["match_score"] for item in result_c["matched_products"]) < max(item["match_score"] for item in result_a["matched_products"])
        assert result_a["matched_products"][0]["recommendation_reason"] != result_b["matched_products"][0]["recommendation_reason"]
        assert result_a["matched_products"][0]["matched_points"]
        assert result_c["matched_products"][0]["risk_points"]

        db.query(BankProduct).filter(BankProduct.data_source.in_(("imported", "manual"))).delete(synchronize_session=False)
        db.commit()
        fallback = match_bank_products(db, customer_a)
        assert fallback["fallback_notice"]
        assert fallback["matched_products"][0]["product_name"] == "模拟固定产品"

    print("PHASE_BANK_MATCHER_OK")


if __name__ == "__main__":
    main()
