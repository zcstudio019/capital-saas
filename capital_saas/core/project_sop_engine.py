from datetime import datetime, timedelta


SOP = {
    "preparing": [
        ("document_check", "核对资料完整性", "依据尽调缺失清单逐项核验", 1, "high"),
        ("amount_confirm", "确认目标融资金额", "确认最低可接受额度与分批提款方案", 1, "high"),
        ("rate_confirm", "确认客户可接受利率", "记录综合成本上限及担保条件", 2, "medium"),
        ("package_prepare", "准备申请材料包", "统一合同、流水、纳税和财务口径", 2, "high"),
    ],
    "submitted": [
        ("receipt_confirm", "确认银行收件", "确认资料已进入银行审批流程", 1, "high"),
        ("manager_record", "记录客户经理", "补齐机构联系人和联系方式", 1, "medium"),
        ("feedback_time", "记录预计反馈时间", "与机构约定首轮反馈节点", 2, "medium"),
    ],
    "bank_review": [
        ("review_follow", "跟进审批进度", "核验当前审批节点和待决条件", 2, "high"),
        ("supplement_prepare", "准备补充材料", "提前准备流水、合同和用途说明", 2, "medium"),
        ("cashflow_stable", "提醒客户保持流水稳定", "避免审批期新增高成本负债或异常转账", 3, "high"),
    ],
    "supplement_required": [
        ("collect_documents", "完成银行补资料", "按机构清单收集并统一提交", 1, "high"),
        ("client_clarification", "发送客户补资料说明", "说明资料用途、截止时间和风险", 1, "high"),
    ],
    "approved": [
        ("approval_check", "核对批复条件", "确认额度、利率、期限、担保和提款条件", 1, "high"),
        ("offer_compare", "比较额度、利率与期限", "完成多方案成本与现金流压力比选", 1, "high"),
        ("signing_notice", "提醒客户签约注意事项", "核对合同、费用、提前还款和违约条款", 2, "medium"),
    ],
    "disbursed": [
        ("repayment_reminder", "首月还款提醒", "确认首期还款日与扣款账户余额", 25, "high"),
        ("repayment_reminder", "每月还款计划维护", "建立月度还款日历", 30, "medium"),
        ("post_loan_check", "贷后资料留存提醒", "留存合同、提款、支付及用途凭证", 7, "medium"),
        ("renewal_prepare", "续贷前90天准备", "提前复盘流水、负债和续贷资料", 275, "medium"),
        ("post_loan_check", "资金用途合规提醒", "按合同约定用途使用并保存凭证", 3, "high"),
        ("cashflow_review", "现金流风险复查", "复查13周现金流和本息覆盖", 30, "high"),
    ],
}


def project_sop_tasks(status: str, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now()
    return [{"task_type": task_type, "task_title": title, "task_content": content,
             "due_time": now + timedelta(days=days), "priority": priority}
            for task_type, title, content, days, priority in SOP.get(status, [])]
