FUNNEL_STAGES = [
    ("landing_view", "访问落地页"),
    ("assessment_submitted", "提交测评"),
    ("free_result_viewed", "查看免费结果"),
    ("checkout_viewed", "进入支付页"),
    ("payment_success", "支付成功"),
    ("report_viewed", "查看报告"),
    ("document_uploaded", "上传资料"),
    ("consulting_case_created", "进入顾问服务"),
    ("financing_project_created", "融资项目立项"),
]


def analyze_dropoff(counts: dict) -> dict:
    largest_stage = ""
    largest_rate = 0.0
    for idx in range(len(FUNNEL_STAGES) - 1):
        current_key, current_name = FUNNEL_STAGES[idx]
        next_key, next_name = FUNNEL_STAGES[idx + 1]
        current = max(int(counts.get(current_key, 0) or 0), 0)
        nxt = max(int(counts.get(next_key, 0) or 0), 0)
        if current <= 0:
            continue
        rate = (current - nxt) / current
        if rate > largest_rate:
            largest_rate = rate
            largest_stage = f"{current_name} → {next_name}"
    reasons = {
        "查看免费结果 → 进入支付页": ["免费结果价值感不足", "CTA不够明确", "用户对完整报告信任不足"],
        "进入支付页 → 支付成功": ["价格异议", "支付方式不适合", "销售跟进不及时"],
        "支付成功 → 查看报告": ["报告审核/生成等待过长", "客户不知道入口", "通知触达不足"],
        "查看报告 → 上传资料": ["补资料清单不够清楚", "顾问未及时解释资料用途", "客户担心资料安全"],
    }
    actions = {
        "查看免费结果 → 进入支付页": ["强化银行视角差距提示", "增加案例和报告样例", "销售24小时内跟进B级以上线索"],
        "进入支付页 → 支付成功": ["增加manual_transfer说明", "对未支付订单30分钟提醒", "销售发送付款价值话术"],
        "支付成功 → 查看报告": ["报告通过后自动通知", "客户门户首页突出报告入口", "顾问主动发链接"],
        "查看报告 → 上传资料": ["生成一页式资料清单", "客户门户展示缺失资料", "顾问发送补资料话术"],
    }
    return {
        "largest_dropoff_stage": largest_stage or "暂无明显掉点",
        "dropoff_rate": f"{largest_rate:.0%}",
        "possible_reasons": reasons.get(largest_stage, ["样本量不足，建议继续观察"]),
        "recommended_actions": actions.get(largest_stage, ["持续补充真实客户样本", "每日复盘客户卡点"]),
    }
