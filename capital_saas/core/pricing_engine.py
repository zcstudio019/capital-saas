products = {
    "299_report": {
        "name": "AI企业融资+财商诊断完整报告",
        "price": 299,
        "description": "解锁10章企业融资、财务健康与资本路径诊断。",
    },
    "699_bank_match": {
        "name": "银行匹配与额度预测报告",
        "price": 699,
        "description": "进一步获得银行产品匹配、申请顺序与额度预测。",
    },
    "1999_structure_plan": {
        "name": "企业融资结构优化方案",
        "price": 1999,
        "description": "围绕额度、成本、期限与工具组合设计融资结构。",
    },
}

REPORT_PRODUCT_NAME = products["299_report"]["name"]
PRODUCT_RANK = {"299_report": 1, "699_bank_match": 2, "1999_structure_plan": 3}
recommended_product_labels = {
    "299_report": "299元完整诊断报告",
    "699_bank_match": "699元银行匹配报告",
    "1999_structure_plan": "1999元融资结构优化方案",
    "high_ticket_consulting": "高客单1对1融资顾问",
    "free_nurture": "免费长期培育",
}


def report_price() -> int:
    return products["299_report"]["price"]


def get_product(product_code: str | None, db=None) -> tuple[str, dict]:
    code = product_code if product_code in products else "299_report"
    product = dict(products[code])
    if db is not None:
        from services.settings_service import get_setting

        price_key = {
            "299_report": "report_price_299",
            "699_bank_match": "report_price_699",
            "1999_structure_plan": "report_price_1999",
        }[code]
        try:
            product["price"] = float(get_setting(db, price_key, str(product["price"])))
        except ValueError:
            pass
    return code, product


def product_label(product_code: str) -> str:
    return products.get(product_code, {}).get("name", product_code)
