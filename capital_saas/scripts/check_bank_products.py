"""Post-import integrity check for bank_products."""
from _bootstrap import ROOT  # noqa: F401
from db.database import SessionLocal
from db.models import BankProduct

def main() -> int:
    with SessionLocal() as db:
        total = db.query(BankProduct).count()
        active = db.query(BankProduct).filter(BankProduct.is_active.is_(True)).count()
        counts = {s: db.query(BankProduct).filter(BankProduct.data_source == s).count() for s in ("imported", "manual", "mock")}
        active_mock = db.query(BankProduct).filter(BankProduct.data_source == "mock", BankProduct.is_active.is_(True)).count()
        missing_code = db.query(BankProduct).filter((BankProduct.product_code == "") | BankProduct.product_code.is_(None)).count()
        missing_names = db.query(BankProduct).filter((BankProduct.bank_name == "") | (BankProduct.product_name == "")).count()
        real = db.query(BankProduct).filter(BankProduct.data_source.in_(("imported", "manual")), BankProduct.is_active.is_(True)).limit(10).all()
        print(f"产品总数: {total}\n启用产品数: {active}\nimported/manual/mock: {counts['imported']}/{counts['manual']}/{counts['mock']}")
        print(f"启用中的 mock: {active_mock}\nproduct_code 缺失: {missing_code}\n银行或产品名缺失: {missing_names}")
        for item in real: print(f"{item.product_code}\t{item.bank_name}\t{item.product_name}")
        ok = counts["imported"] > 0 and missing_names == 0 and active_mock == 0
        print("BANK_PRODUCTS_CHECK_OK" if ok else "BANK_PRODUCTS_CHECK_FAILED")
        return 0 if ok else 1

if __name__ == "__main__": raise SystemExit(main())
