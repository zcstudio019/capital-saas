products = {
    "free_assessment": {
        "name": "免费测评",
        "price": 0,
        "description": "查看企业资本健康度评分、风险摘要与初步建议。",
    },
    "980_capital_health_report": {
        "name": "企业资本健康体检报告",
        "price": 980,
        "description": "解锁八维资本体检报告、红旗清单、分项检查和基础融资建议。",
    },
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
        "name": "融资结构优化方案",
        "price": 1999,
        "description": "解锁优化处方、银行产品组合、资料清单、行动计划和融资落地节奏。",
    },
    "one_on_one_consulting": {
        "name": "1对1融资顾问服务",
        "price": 9800,
        "description": "顾问陪跑、资料整理、银行申请路径设计与融资落地跟进。",
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
    "299_report": "299元完整诊断报告",
    "980_capital_health_report": "980元企业资本健康体检报告",
    "699_bank_match": "699元银行匹配报告",
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
        from services.settings_service import get_setting

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
        if code == "1999_structure_plan" and assessment_id:
            from db.models import Order

            mode = get_setting(db, "structure_plan_upgrade_mode", "deduct_report_price")
            paid_report = db.query(Order).filter(
                Order.assessment_id == assessment_id,
                Order.product_code == "980_capital_health_report",
                Order.status == "paid",
            ).first()
            if mode == "deduct_report_price" and paid_report:
                original_price = float(product["price"])
                deduction = min(float(paid_report.amount or 0), original_price)
                product["original_price"] = original_price
                product["deduction"] = deduction
                product["price"] = max(0, original_price - deduction)
                product["upgrade_mode"] = mode
    return code, product


def product_label(product_code: str) -> str:
    return products.get(product_code, {}).get("name", product_code)
