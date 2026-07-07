def generate_document_request_script(company_name: str, contact_name: str, missing: list[str]) -> dict:
    items = list(dict.fromkeys(missing))
    display = "、".join(items) if items else "暂无需补充的核心资料"
    short = (
        f"{contact_name or '您好'}，我们正在整理{company_name}的融资预审资料，"
        f"目前还需要补充：{display}。您方便时发我即可，我会按银行审查口径统一整理。"
    )
    detailed = (
        f"{contact_name or '您好'}，为了避免正式申请后因资料口径不一致被退回，我们已完成第一轮资料核对。\n"
        f"本轮建议补充：{display}。\n"
        "资料尽量提供清晰完整版本；涉及账户、身份证号等敏感信息可通过双方确认的安全方式传输。"
        "收到后我们会继续核验经营、流水、纳税和还款来源的一致性，再给出申请顺序建议。"
    )
    return {
        "short_message": short,
        "detailed_message": detailed,
        "document_list": items,
        "friendly_reminder": "不用一次准备得很完美，可先发已有资料，我们会标记缺口并分批推进。",
    }
