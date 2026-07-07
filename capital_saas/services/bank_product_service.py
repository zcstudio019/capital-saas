from sqlalchemy.orm import Session

from db.models import BankProduct


DEFAULT_BANK_PRODUCTS = [
    ("模拟城商行", "城商行", "城商行经营贷", "经营贷", "通用", 1_000_000, 2, True, True, False, 5_000_000, "年化4.5%-8.0%", "12-36个月", "经营稳定、纳税与流水可核验", "额度与利率以实际审批为准"),
    ("模拟股份制银行", "股份制银行", "税票贷", "信用贷", "通用", 1_500_000, 2, True, True, False, 3_000_000, "年化4.8%-9.0%", "12-24个月", "连续纳税开票、征信正常", "税票波动会影响额度"),
    ("模拟国有银行", "国有大行", "抵押经营贷", "抵押贷", "通用", 2_000_000, 2, True, True, True, 20_000_000, "年化3.5%-6.5%", "36-120个月", "产权清晰、经营用途真实", "需评估抵押率和还款覆盖"),
    ("模拟供应链机构", "供应链金融", "供应链应收账款融资", "应收账款融资", "制造/贸易/企业服务", 2_000_000, 2, False, True, False, 8_000_000, "年化6.0%-12.0%", "3-18个月", "核心买方可核验、应收账款可确权", "依赖买方资质与确权"),
    ("模拟租赁机构", "融资租赁", "设备融资租赁", "融资租赁", "制造/生产", 1_000_000, 1, False, True, False, 10_000_000, "综合成本以方案为准", "24-60个月", "设备权属与现金流可核验", "设备残值和用途影响方案"),
    ("模拟小微专营机构", "农商行", "小微企业信用贷", "信用贷", "通用", 500_000, 1, True, True, False, 1_000_000, "年化5.5%-12.0%", "12-24个月", "经营真实、流水稳定、无重大负面", "额度相对有限"),
]


def ensure_default_bank_products(db: Session) -> None:
    if db.query(BankProduct).count():
        return
    for item in DEFAULT_BANK_PRODUCTS:
        db.add(BankProduct(
            bank_name=item[0], bank_type=item[1], product_name=item[2],
            product_type=item[3], suitable_industry=item[4], min_revenue=item[5],
            min_years=item[6], requires_tax_normal=item[7],
            requires_credit_normal=item[8], requires_collateral=item[9],
            max_amount=item[10], interest_rate_range=item[11], loan_term=item[12],
            application_requirements=item[13], risk_notes=item[14],
        ))
    db.commit()
