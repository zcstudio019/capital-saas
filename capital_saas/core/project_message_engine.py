MESSAGES = {
 "draft": ("融资项目已立项", "我们已建立融资项目档案，下一步将确认目标额度、成本和资料范围。", "当前尚未进入机构审批，不代表授信承诺。", "确认项目目标与负责人"),
 "preparing": ("融资资料正在准备", "我们正在按银行审查口径核对资料和申请材料包。", "请保持流水、纳税和征信状态稳定。", "补齐缺失资料并完成预审"),
 "submitted": ("资料已提交机构", "申请资料已经提交，正在等待机构确认收件和首轮反馈。", "审批期间不建议多头无序申请。", "记录客户经理和预计反馈时间"),
 "bank_review": ("银行正在审核", "项目已进入审批阶段，我们会持续跟踪节点并提前准备补充资料。", "请避免新增高成本负债和异常资金流。", "跟进审批进度"),
 "supplement_required": ("银行需要补充资料", "机构提出补充资料要求，请按清单准备，我们会统一口径后提交。", "逾期或资料矛盾可能影响审批。", "按截止时间补齐资料"),
 "approved": ("融资方案已获批复", "机构已给出批复，请重点核对额度、利率、期限、担保及提款条件。", "批复不等于已放款，签约前请看清全部费用和限制。", "完成方案比选与合同核验"),
 "rejected": ("本次申请未获通过", "本次申请被拒，我们会拆解原因并调整资料、产品或申请顺序。", "不建议立即向多家机构重复申请。", "完成拒绝原因复盘与修复"),
 "disbursed": ("融资已完成放款", "资金已经到账，请严格按合同用途使用并建立还款日历。", "用途偏离、逾期或流水异常会影响续贷。", "完成贷后资料留存和现金流复查"),
}


def generate_project_message(status: str, missing_documents: list[str] | None = None) -> dict:
    short, detail, risk, action = MESSAGES.get(status, MESSAGES["draft"])
    if status == "supplement_required" and missing_documents:
        detail += " 当前待补：" + "、".join(missing_documents)
    return {"short_message": short, "detailed_message": detail, "risk_reminder": risk, "next_action": action}
