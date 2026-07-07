from datetime import datetime, timedelta


def calculate_next_best_action(lead, orders: list, tasks: list) -> dict:
    paid_products = {x.product_code for x in orders if x.status == "paid"}
    last_activity = lead.updated_at or lead.created_at
    if "1999_structure_plan" in paid_products:
        return {"next_action": "预约1对1融资顾问服务", "priority": "high", "reason": "客户已购买结构优化方案，适合进入顾问交付与高客单服务。", "suggested_script": "方案已经解决结构设计，下一步建议安排顾问沟通推动执行落地。", "recommended_product": "high_ticket_consulting"}
    if "699_bank_match" in paid_products:
        return {"next_action": "升级1999融资结构优化", "priority": "high", "reason": "客户已明确银行匹配方向，需要把额度、成本和期限落成结构方案。", "suggested_script": "银行匹配解决选哪家，结构方案解决怎么申请、申请多少和如何降低成本。", "recommended_product": "1999_structure_plan"}
    if "299_report" in paid_products:
        return {"next_action": "升级699银行匹配报告", "priority": "medium", "reason": "客户已认可诊断价值，可进一步明确银行、额度和申请顺序。", "suggested_script": "完整报告已经看清问题，下一步可以匹配更适合的银行与额度。", "recommended_product": "699_bank_match"}
    if datetime.now() - last_activity >= timedelta(days=7):
        return {"next_action": "重新激活客户", "priority": "medium", "reason": "超过7天无有效动作。", "suggested_script": "近期融资计划是否有变化？我可以重新帮您核一下当前申请窗口。", "recommended_product": lead.recommended_product}
    if lead.lead_grade == "S" and lead.follow_status == "待联系":
        return {"next_action": "立即电话联系并推顾问服务", "priority": "high", "reason": "S级高价值线索尚未触达。", "suggested_script": "您现在的重点不是能不能贷，而是额度、成本和结构，建议先做融资结构设计。", "recommended_product": "high_ticket_consulting"}
    if lead.lead_grade == "A":
        return {"next_action": "发送银行视角价值话术", "priority": "high", "reason": "具备融资基础但尚未付款。", "suggested_script": "申请顺序会直接影响额度，建议先把结构和银行路径设计好。", "recommended_product": "1999_structure_plan"}
    if lead.lead_grade == "B":
        return {"next_action": "推荐699银行匹配报告", "priority": "medium", "reason": "融资受限，最需要避免选错银行。", "suggested_script": "先看匹配银行和额度预测，可以减少拒贷与无效查询。", "recommended_product": "699_bank_match"}
    if lead.lead_grade == "C":
        return {"next_action": "推荐299基础诊断报告", "priority": "medium", "reason": "当前问题应先诊断后申请。", "suggested_script": "不建议直接申请，先把影响通过率的问题和修复顺序看清。", "recommended_product": "299_report"}
    return {"next_action": "进入养熟与定期回访", "priority": "low", "reason": "当前付费与融资条件不足。", "suggested_script": "先补齐基础条件，条件改善后再重新评估融资。", "recommended_product": "free_nurture"}
