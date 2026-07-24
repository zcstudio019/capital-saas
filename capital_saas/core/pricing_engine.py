products = {
    "free_assessment": {
        "name": "免费测评",
        "price": 0,
        "description": "查看企业资本健康度评分、风险摘要与初步建议。",
        "is_public": True,
        "is_active": True,
        "product_type": "free_entry",
    },
    "980_capital_health_report": {
        "name": "企业资本健康体检报告",
        "price": 980,
        "description": "解锁八维资本体检报告、红旗清单、分项检查和基础融资建议。",
        "is_public": True,
        "is_active": True,
        "product_type": "core_report",
    },
    "299_report": {
        "name": "企业资本健康简版报告",
        "price": 299,
        "description": "查看综合评分、八维摘要、核心风险和基础融资方向。",
        "is_public": False,
        "is_active": True,
        "product_type": "hidden_offer",
    },
    "699_bank_match": {
        "name": "银行产品专项匹配报告",
        "price": 699,
        "description": "针对特定企业提供银行产品匹配、申请顺序与额度参考。",
        "is_public": False,
        "is_active": True,
        "product_type": "specialist_offer",
    },
    "1999_structure_plan": {
        "name": "融资结构优化方案",
        "price": 1999,
        "description": "解锁优化处方、银行产品组合、资料清单、行动计划和融资落地节奏。",
        "is_public": True,
        "is_active": True,
        "product_type": "structure_plan",
    },
    "one_on_one_consulting": {
        "name": "1对1融资顾问服务",
        "price": 9800,
        "description": "顾问陪跑、资料整理、银行申请路径设计与融资落地跟进。",
        "is_public": True,
        "is_active": True,
        "product_type": "advisor_service",
    },
}

PUBLIC_PRODUCT_ORDER = (
    "free_assessment",
    "980_capital_health_report",
    "1999_structure_plan",
    "one_on_one_consulting",
)

PRODUCT_TYPE_LABELS = {
    "free_entry": "免费入口",
    "core_report": "核心报告",
    "hidden_offer": "私域隐藏产品",
    "specialist_offer": "专项服务产品",
    "structure_plan": "结构优化方案",
    "advisor_service": "顾问服务",
}

PRODUCT_DEDUCTION_RULES = {
    "299_report": {
        "980_capital_health_report": 299,
        "1999_structure_plan": 299,
    },
    "699_bank_match": {
        "1999_structure_plan": 699,
    },
    "980_capital_health_report": {
        "1999_structure_plan": 980,
    },
}

REPORT_PRODUCT_NAME = products["980_capital_health_report"]["name"]
PRODUCT_RANK = {
    "free_assessment": 0,
    "299_report": 1,
    "980_capital_health_report": 2,
    "699_bank_match": 2,
    "1999_structure_plan": 3,
    "one_on_one_consulting": 4,
}
recommended_product_labels = {
    "299_report": "299元企业资本健康简版报告",
    "980_capital_health_report": "980元企业资本健康体检报告",
    "699_bank_match": "699元银行产品专项匹配报告",
    "1999_structure_plan": "1999元融资结构优化方案",
    "high_ticket_consulting": "高客单1对1融资顾问",
    "one_on_one_consulting": "1对1融资顾问服务",
    "free_nurture": "免费长期培育",
}


def report_price() -> int:
    return products["980_capital_health_report"]["price"]


def get_product(product_code: str | None, db=None, assessment_id: int | None = None) -> tuple[str, dict]:
    code = product_code if product_code in products else "980_capital_health_report"
    product = dict(products[code])
    if db is not None:
        from services.settings_service import get_bool_setting, get_setting

        price_key = {
            "free_assessment": None,
            "299_report": "report_price_299",
            "980_capital_health_report": "capital_health_report_price",
            "699_bank_match": "report_price_699",
            "1999_structure_plan": "capital_structure_plan_price",
            "one_on_one_consulting": "one_on_one_consulting_price",
        }[code]
        try:
            if price_key:
                product["price"] = float(get_setting(db, price_key, str(product["price"])))
        except ValueError:
            pass
        product["is_public"] = get_bool_setting(
            db, f"product_{code}_is_public", bool(product.get("is_public"))
        )
        product["is_active"] = get_bool_setting(
            db, f"product_{code}_is_active", bool(product.get("is_active", True))
        )
        product["product_type"] = get_setting(
            db, f"product_{code}_type", str(product.get("product_type", ""))
        )
        if assessment_id and code in {"980_capital_health_report", "1999_structure_plan"}:
            from db.models import CustomerAccount
            from services.upgrade_pricing_service import get_upgrade_quote

            customer = db.query(CustomerAccount).filter(
                CustomerAccount.assessment_id == assessment_id,
                CustomerAccount.is_active.is_(True),
            ).first()
            mode = get_setting(db, "structure_plan_upgrade_mode", "deduct_report_price")
            quote = get_upgrade_quote(
                customer.id if customer else None,
                code,
                db,
                assessment_id=assessment_id,
                allow_deduction=mode != "full_price",
                target_price=float(product["price"]),
            )
            product.update(quote)
    return code, product


def public_products(db=None) -> dict[str, dict]:
    catalog: dict[str, dict] = {}
    for code in PUBLIC_PRODUCT_ORDER:
        item = get_product(code, db)[1] if db is not None else dict(products[code])
        if item.get("is_public", True) and item.get("is_active", True):
            catalog[code] = item
    if db is not None:
        for code in products:
            if code in catalog or code in PUBLIC_PRODUCT_ORDER:
                continue
            item = get_product(code, db)[1]
            if item.get("is_public") and item.get("is_active"):
                catalog[code] = item
    return catalog


def product_label(product_code: str) -> str:
    return products.get(product_code, {}).get("name", product_code)
