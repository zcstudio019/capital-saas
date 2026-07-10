"""后台展示层标签：只转换显示文案，不修改数据库原始 code。"""

import json
import re

NAV_LABELS = {
    "admin_dashboard": "总览", "dashboard": "总览", "delivery_dashboard": "交付看板",
    "financing_projects": "融资项目", "sales_workbench": "销售工作台", "leads": "线索管理",
    "follow_tasks": "跟进任务", "reports": "报告管理", "bank_products": "银行产品",
    "consulting_cases": "顾问案件", "advisor_bookings": "顾问预约", "orders": "订单管理", "growth": "增长看板",
    "hq_dashboard": "总部总览", "city_dashboard": "城市经营", "team_performance": "团队业绩",
    "organizations": "组织管理", "channel_partners": "渠道伙伴", "institution_contacts": "机构联系人",
    "commissions": "提成结算", "script_templates": "话术库", "backup": "数据备份",
    "settings": "系统设置", "users": "用户管理", "audit_logs": "审计日志",
    "notifications": "通知中心", "notification_templates": "通知模板", "notification_jobs": "通知任务",
    "system_health": "系统健康", "production_checklist": "上线检查", "setup_wizard": "初始化向导",
    "launch_dashboard": "试运营看板", "pilot_batches": "试运营批次", "pilot_dashboard": "试运营作战台",
    "feedback": "客户反馈", "issues": "问题池", "daily_reports": "运营日报",
    "weekly_reports": "运营周报", "client_portals": "客户门户", "legal_documents": "法律文档",
    "release_notes": "发布说明",
}

ROLE_LABELS = {
    "super_admin": "超级管理员", "admin": "管理员", "city_manager": "城市负责人",
    "sales_manager": "销售主管", "sales": "销售", "consultant_manager": "顾问主管",
    "consultant": "融资顾问", "finance": "财务", "viewer": "只读账号", "partner": "渠道伙伴",
}

INSTITUTION_TYPE_LABELS = {
    "bank": "银行",
    "guarantee": "担保公司",
    "factoring": "保理公司",
    "leasing": "融资租赁公司",
    "fund": "资金方",
    "microloan": "小贷公司",
    "trust": "信托机构",
    "asset_management": "资管机构",
    "other": "其他机构",
}


def get_nav_label(code):
    value = "" if code is None else str(code).strip().lower()
    return NAV_LABELS.get(value, "系统模块")


def get_role_label(role):
    value = "" if role is None else str(role).strip().lower()
    return ROLE_LABELS.get(value, "系统账号")


def get_institution_type_label(code):
    value = "" if code is None else str(code).strip().lower()
    return INSTITUTION_TYPE_LABELS.get(value, "其他机构")


def get_user_display_name(user):
    if user is None:
        return "系统用户"
    username = str(getattr(user, "username", "") or "").strip()
    if username.lower() == "admin":
        return "系统管理员"
    role_label = get_role_label(getattr(user, "role", ""))
    return f"{username}（{role_label}）" if username else role_label

PRODUCT_LABELS = {
    "299_report": "基础诊断报告（299元）", "699_bank_match": "银行匹配报告（699元）",
    "1999_structure_plan": "融资结构优化方案（1999元）", "high_ticket_consulting": "高客单顾问服务", "free_nurture": "免费培育",
    "manual_consulting": "人工顾问服务", "structure_plan": "融资结构方案",
}
ORDER_STATUS_LABELS = {"pending": "待支付", "paid": "已支付", "refunded": "已退款", "cancelled": "已取消", "failed": "支付失败", "closed": "已关闭"}
PAYMENT_CHANNEL_LABELS = {
    "mock": "模拟支付", "manual_transfer": "人工转账", "wechat": "微信支付", "wechat_pay": "微信支付",
    "alipay": "支付宝", "alipay_pay": "支付宝", "bank_transfer": "银行转账", "local": "本地模拟通道",
}
PAYMENT_STATUS_LABELS = ORDER_STATUS_LABELS.copy()
LANDING_PAGE_LABELS = {
    "/": "官网首页", "/assessment": "免费测评页", "/lp/rongzi": "企业融资测评页",
    "/lp/cashflow": "现金流风险测评页", "/lp/bank": "银行贷款通过率测评页",
    "/lp/boss": "老板财商诊断页", "/products": "产品服务页",
    "/checkout": "支付解锁页", "/result": "免费结果页",
}
COMMISSION_TRIGGER_LABELS = {
    "paid_order": "订单支付成功", "consulting_case_created": "顾问案件创建",
    "project_approved": "融资项目批复", "project_disbursed": "融资项目放款",
    "funding_application_approved": "资金申请批复",
    "funding_application_disbursed": "资金申请放款",
}
COMMISSION_TYPE_LABELS = {
    "fixed_amount": "固定金额", "percentage": "按比例",
    "tiered_percentage": "阶梯比例", "manual": "手动结算",
}
SCRIPT_SCENARIO_LABELS = {
    "first_wechat": "初次加微信", "after_free_assessment": "免费测评后未支付",
    "free_unpaid": "免费测评后未支付", "push_299": "推荐基础诊断报告",
    "push_699": "推荐银行匹配报告", "push_1999": "推荐融资结构优化方案",
    "high_ticket_consulting": "推荐高客单顾问服务", "high_ticket": "推荐高客单顾问服务",
    "no_reply_24h": "24小时未回复", "reactivate_7d": "7天重新激活",
    "paid_thanks": "已支付感谢", "upsell_recommend": "升级服务推荐", "upsell": "升级服务推荐",
    "document_request": "补资料提醒", "report_ready": "报告生成提醒",
    "project_update": "项目进度通知", "payment_follow": "付款跟进",
    "renewal_reminder": "续贷提醒",
}
STATUS_LABELS = {
    "pending": "待处理", "confirmed": "已确认", "paid": "已支付", "cancelled": "已取消",
    "active": "已启用", "inactive": "已停用", "success": "成功", "failed": "失败",
    "draft": "草稿", "ready": "已就绪", "submitted": "已提交", "returned": "已退回",
    "archived": "已归档", "planning": "筹备中", "running": "进行中", "completed": "已完成",
}
SETTLEMENT_STATUS_LABELS = {
    "pending": "待处理", "confirmed": "已确认", "paid": "已支付", "cancelled": "已取消",
}
SOURCE_CHANNEL_LABELS = {
    "": "直接访问", "direct": "直接访问", "organic": "自然访问", "douyin": "抖音",
    "xiaohongshu": "小红书", "wechat": "微信私域", "partner": "渠道伙伴",
    "sales_call": "电销客户", "wx_private": "微信私域", "partner_caishui": "财税渠道",
}
LEAD_GRADE_LABELS = {"S": "S级线索", "A": "A级线索", "B": "B级线索", "C": "C级线索", "D": "D级线索"}
FOLLOW_STATUS_LABELS = {
    "uncontacted": "未联系", "contacted": "已联系", "wechat_added": "已加微信", "report_sent": "已发报告",
    "paid": "已付费", "documents_uploaded": "已上传资料", "advisor_booked": "已预约顾问",
    "project_created": "已进入项目", "dropped": "已流失",
}
BOOKING_STATUS_LABELS = {
    "submitted": "已提交", "assigned": "已分配", "contacted": "已联系", "scheduled": "已安排",
    "completed": "已完成", "cancelled": "已取消", "invalid": "无效预约",
}
SERVICE_TYPE_LABELS = {
    "financing_structure_consulting": "融资结构设计", "bank_product_matching": "银行产品匹配",
    "document_review": "资料准备与尽调", "project_delivery": "融资项目推进",
    "high_ticket_consulting": "高客单顾问服务",
}
URGENCY_LEVEL_LABELS = {"normal": "普通", "urgent": "比较急", "very_urgent": "非常急"}
AB_VARIANT_LABELS = {
    "variant_a": "风险提示版", "variant_b": "机会收益版",
    "free_result_conversion": "免费结果页转化实验", "ab_assigned": "A/B测试已分组",
}
DATA_SOURCE_LABELS = {"mock": "模拟数据", "imported": "导入数据", "manual": "手动维护", "system": "系统生成"}
DOCUMENT_CATEGORY_LABELS = {
    "营业执照/工商资料": "营业执照/工商资料", "企业基础资料": "企业基础资料", "财务报表": "财务报表",
    "银行流水": "银行流水", "纳税资料": "纳税资料", "征信资料": "征信资料", "经营合同": "经营合同",
    "应收账款资料": "应收账款资料", "抵押物资料": "抵押物资料", "法人/股东资料": "法人/股东资料",
    "其他资料": "其他资料",
}
DOCUMENT_PARSE_STATUS_LABELS = {"pending_parse": "待解析", "parsed": "已解析", "parse_failed": "解析失败", "pending": "待处理"}
DOCUMENT_VERIFY_STATUS_LABELS = {"verified": "已核验", "rejected": "已驳回", "unverified": "待核验", "pending": "待处理"}
PROJECT_STATUS_LABELS = {
    "draft": "草稿", "preparing": "准备资料", "submitted": "已提交", "bank_review": "银行审核中",
    "supplement_required": "需补充资料", "approved": "已批复", "rejected": "未通过",
    "disbursed": "已放款", "cancelled": "已取消", "archived": "已归档",
}
FUNDING_APPLICATION_STATUS_LABELS = {
    "planned": "计划申请", "submitted": "已提交", "reviewing": "审核中", "supplement_required": "需补资料",
    "approved": "已批复", "rejected": "未通过", "disbursed": "已放款", "withdrawn": "已撤回",
}
NOTIFICATION_STATUS_LABELS = {"queued": "待发送", "sending": "发送中", "success": "发送成功", "failed": "发送失败", "cancelled": "已取消", "skipped": "已跳过", "unread": "未读", "read": "已读", "archived": "已归档"}
NOTIFICATION_CHANNEL_LABELS = {"in_app": "站内通知", "email": "邮件", "sms": "短信", "wecom_webhook": "企业微信机器人", "mock": "模拟通道"}
NOTIFICATION_TEMPLATE_LABELS = {
    "upgrade_recommend_customer": "升级推荐客户通知",
    "payment_success_customer": "支付成功客户通知",
    "payment_success_internal": "支付成功内部通知",
    "new_lead_admin": "新线索管理员通知",
    "lead_assigned_sales": "线索分配销售通知",
    "advisor_booking_submitted_customer": "顾问预约客户通知",
    "advisor_booking_submitted_internal": "顾问预约内部通知",
}
INTERNAL_NOTIFICATION_TYPE_LABELS = {"new_lead": "新线索", "lead_assigned": "线索分配", "advisor_booking": "顾问预约", "document_uploaded": "资料上传", "task_due": "任务到期", "task_overdue": "任务逾期", "payment_success": "支付成功", "report_ready": "报告完成", "system": "系统通知"}


def get_landing_page_label(path):
    value = "" if path is None else str(path).strip()
    clean_path = value.split("?", 1)[0].rstrip("/") or "/"
    return LANDING_PAGE_LABELS.get(clean_path, "其他落地页")


def get_commission_trigger_label(code):
    return COMMISSION_TRIGGER_LABELS.get(str(code or "").strip().lower(), "其他业务触发")


def get_commission_type_label(code):
    return COMMISSION_TYPE_LABELS.get(str(code or "").strip().lower(), "其他结算方式")


def get_commission_value_label(rule):
    code = str(getattr(rule, "commission_type", "") or "").strip().lower()
    value = getattr(rule, "commission_value", 0)
    unit = "元" if code == "fixed_amount" else "%" if code in {"percentage", "tiered_percentage"} else ""
    return f"{get_commission_type_label(code)}：{value}{unit}"


def get_role_type_label(code):
    return get_role_label(code)


def get_script_scenario_label(code):
    return SCRIPT_SCENARIO_LABELS.get(str(code or "").strip().lower(), "通用跟进场景")


def get_status_label(code):
    return STATUS_LABELS.get(str(code or "").strip().lower(), "状态未知")


def get_boolean_label(value):
    if isinstance(value, str):
        enabled = value.strip().lower() in {"1", "true", "yes", "on", "active"}
    else:
        enabled = bool(value)
    return "是" if enabled else "否"


def get_settlement_status_label(code):
    return SETTLEMENT_STATUS_LABELS.get(str(code or "").strip().lower(), "状态未知")


def get_lead_grade_label(code):
    value = str(code or "").strip().upper()
    return LEAD_GRADE_LABELS.get(value, "全部线索" if not value else "其他等级线索")


def get_source_channel_label(code):
    return SOURCE_CHANNEL_LABELS.get(str(code or "").strip().lower(), "其他渠道")

def get_channel_label(code): return get_source_channel_label(code)
def get_order_status_label(code): return ORDER_STATUS_LABELS.get(str(code or "").strip().lower(), "未知订单状态")
def get_payment_channel_label(code): return PAYMENT_CHANNEL_LABELS.get(str(code or "").strip().lower(), "其他支付渠道")
def get_payment_status_label(code): return PAYMENT_STATUS_LABELS.get(str(code or "").strip().lower(), "未知支付状态")
def get_follow_status_label(code):
    value = "" if code is None else str(code).strip()
    if re.search(r"[\u4e00-\u9fff]", value):
        return value
    return FOLLOW_STATUS_LABELS.get(value.lower(), "未知跟进状态")
def get_booking_status_label(code): return BOOKING_STATUS_LABELS.get(str(code or "").strip().lower(), "未知预约状态")
def get_service_type_label(code): return SERVICE_TYPE_LABELS.get(str(code or "").strip().lower(), "其他顾问服务")
def get_urgency_level_label(code): return URGENCY_LEVEL_LABELS.get(str(code or "").strip().lower(), "普通")
def get_ab_variant_label(code): return AB_VARIANT_LABELS.get(str(code or "").strip().lower(), "实验版本")
def get_data_source_label(code): return DATA_SOURCE_LABELS.get(str(code or "").strip().lower(), "其他来源")
def get_document_category_label(code):
    value = "" if code is None else str(code).strip()
    return DOCUMENT_CATEGORY_LABELS.get(value, "其他资料")
def get_document_parse_status_label(code): return DOCUMENT_PARSE_STATUS_LABELS.get(str(code or "").strip().lower(), "未知解析状态")
def get_document_verify_status_label(code): return DOCUMENT_VERIFY_STATUS_LABELS.get(str(code or "").strip().lower(), "未知核验状态")
def get_project_status_label(code): return PROJECT_STATUS_LABELS.get(str(code or "").strip().lower(), "未知项目状态")
def get_funding_application_status_label(code): return FUNDING_APPLICATION_STATUS_LABELS.get(str(code or "").strip().lower(), "未知申请状态")
def get_notification_status_label(code): return NOTIFICATION_STATUS_LABELS.get(str(code or "").strip().lower(), "未知通知状态")
def get_notification_channel_label(code): return NOTIFICATION_CHANNEL_LABELS.get(str(code or "").strip().lower(), "其他通知渠道")
def get_notification_template_label(code): return NOTIFICATION_TEMPLATE_LABELS.get(str(code or "").strip().lower(), "客户通知")
def get_internal_notification_type_label(code): return INTERNAL_NOTIFICATION_TYPE_LABELS.get(str(code or "").strip().lower(), "系统通知")

EVENT_LABELS = {
    "audit_log_created": "审计日志已创建", "unhandled_exception": "系统异常", "assessment_page_viewed": "测评页面被访问",
    "assessment_submitted": "已提交测评", "free_result_viewed": "已查看免费结果", "checkout_viewed": "已进入支付页",
    "payment_success": "支付成功", "report_viewed": "报告已查看", "client_report_viewed": "客户查看报告",
    "client_document_uploaded": "客户已上传资料", "customer_logged_in": "客户已登录", "notification_sent": "通知已发送",
    "notification_failed": "通知发送失败", "login_success": "登录成功", "login_failed": "登录失败",
    "financing_project_created": "已创建融资项目", "funding_application_created": "已创建资金申请",
    "funding_application_approved": "资金申请已批复", "funding_application_rejected": "资金申请未通过",
    "funding_application_disbursed": "已放款", "daily_report_generated": "已生成日报", "weekly_report_generated": "已生成周报",
    "customer_feedback_submitted": "客户已提交反馈", "operation_issue_created": "已创建运营问题", "operation_issue_resolved": "运营问题已解决",
    "launch_dashboard_viewed": "试运营看板已查看", "setup_wizard_viewed": "初始化向导已查看",
    "setup_step_completed": "初始化步骤已完成", "release_notes_viewed": "发布说明已查看",
    "production_checklist_viewed": "生产检查清单已查看", "preflight_check_run": "上线前检查已执行",
    "route_manifest_generated": "路由清单已生成", "demo_data_created": "演示数据已创建",
    "demo_data_cleared": "演示数据已清理", "load_test_run": "基础压测已执行",
    "trial_gate_passed": "试运营访问已通过", "trial_gate_blocked": "试运营访问被拦截",
    "public_legal_page_viewed": "法律页面已查看", "sitemap_viewed": "站点地图已查看", "robots_viewed": "搜索引擎规则文件已查看",
    "pilot_batch_created": "试运营批次已创建", "pilot_batch_started": "试运营批次已启动",
    "pilot_batch_completed": "试运营批次已完成", "lead_assigned_to_pilot": "线索已加入试运营",
    "pilot_invite_code_created": "试运营邀请码已创建", "pilot_invite_used": "试运营邀请码已使用",
    "feedback_converted_to_issue": "反馈已转为问题", "dropoff_analysis_generated": "掉点分析已生成",
    "pilot_sop_viewed": "试运营标准流程已查看", "customer_journey_viewed": "客户旅程已查看",
    "pilot_export_downloaded": "试运营数据已导出",
    "sales_workbench_viewed": "销售工作台已查看", "growth_dashboard_viewed": "增长看板已查看",
    "delivery_dashboard_viewed": "融资交付看板已查看", "city_dashboard_viewed": "城市经营看板已查看",
    "team_performance_viewed": "团队业绩看板已查看", "hq_dashboard_viewed": "总部经营总览已查看",
    "notification_dashboard_viewed": "通知看板已查看", "system_health_viewed": "系统健康页已查看",
    "pilot_dashboard_viewed": "试运营看板已查看", "audit_logs_viewed": "审计日志已查看",
}

EVENT_LABELS.update({
    "landing_page_viewed": "落地页已查看", "ab_assigned": "A/B测试已分组",
    "notification_job_created": "通知任务已创建", "notification_job_sent": "通知任务已发送",
    "notification_job_failed": "通知任务发送失败", "notification_job_cancelled": "通知任务已取消",
    "notification_template_created": "通知模板已创建", "notification_template_updated": "通知模板已更新",
    "notification_sent": "通知已发送", "notification_failed": "通知发送失败",
    "notification_retried": "通知已重试", "notification_cancelled": "通知已取消",
    "reminder_scan_run": "提醒扫描已执行", "notification_worker_run": "通知任务Worker已执行",
    "audit_log_created": "审计日志已创建", "assessment_page_viewed": "测评页面已查看",
    "assessment_submitted": "测评已提交", "free_result_viewed": "免费结果已查看",
    "checkout_viewed": "支付页已查看", "payment_success": "支付成功", "payment_failed": "支付失败",
    "report_viewed": "报告已查看", "client_report_viewed": "客户已查看报告",
    "client_document_uploaded": "客户已上传资料", "customer_logged_in": "客户已登录",
    "sales_workbench_viewed": "销售工作台已查看", "launch_dashboard_viewed": "试运营看板已查看",
    "pilot_dashboard_viewed": "试运营看板已查看", "growth_dashboard_viewed": "增长看板已查看",
    "system_health_viewed": "系统健康页已查看", "production_checklist_viewed": "生产检查清单已查看",
    "customer_journey_viewed": "客户旅程已查看", "financing_project_created": "融资项目已创建",
    "funding_application_created": "资金申请已创建", "funding_application_approved": "资金申请已批复",
    "funding_application_rejected": "资金申请未通过", "funding_application_disbursed": "已放款",
    "customer_feedback_submitted": "客户反馈已提交", "operation_issue_created": "运营问题已创建",
    "daily_report_generated": "运营日报已生成", "weekly_report_generated": "运营周报已生成",
    "advisor_booking_submitted": "顾问预约已提交", "advisor_booking_updated": "顾问预约已更新",
    "advisor_booking_followed": "顾问预约已跟进", "lead_sales_assigned": "线索已分配销售",
    "order_refunded": "订单已退款",
})
EVENT_SUBJECT_LABELS = {
    "sales_workbench": "销售工作台", "launch_dashboard": "试运营看板", "pilot_dashboard": "试运营看板",
    "growth_dashboard": "增长看板", "delivery_dashboard": "融资交付看板", "city_dashboard": "城市经营看板",
    "team_performance": "团队业绩", "hq_dashboard": "总部经营总览", "notification_dashboard": "通知看板",
    "customer_journey": "客户旅程", "assessment_page": "测评页面", "free_result": "免费结果", "checkout": "支付页",
    "report": "报告", "payment": "支付", "document": "资料", "customer": "客户", "lead": "线索", "order": "订单",
    "audit_log": "审计日志", "notification": "通知", "financing_project": "融资项目", "funding_application": "资金申请",
    "daily_report": "运营日报", "weekly_report": "运营周报", "operation_issue": "运营问题", "customer_feedback": "客户反馈",
}
EVENT_SUBJECT_LABELS.update({
    "landing_page": "落地页", "ab": "A/B测试", "ab_test": "A/B测试",
    "notification_job": "通知任务", "notification_template": "通知模板", "notification": "通知",
    "reminder_scan": "提醒扫描", "notification_worker": "通知Worker", "audit_log": "审计日志",
    "assessment_page": "测评页面", "assessment": "测评", "free_result": "免费结果", "checkout": "支付页",
    "payment": "支付", "report": "报告", "client_report": "客户报告", "client_document": "客户资料",
    "customer": "客户", "lead": "线索", "order": "订单", "sales_workbench": "销售工作台",
    "launch_dashboard": "试运营看板", "pilot_dashboard": "试运营看板", "growth_dashboard": "增长看板",
    "system_health": "系统健康页", "production_checklist": "生产检查清单", "customer_journey": "客户旅程",
    "financing_project": "融资项目", "funding_application": "资金申请", "customer_feedback": "客户反馈",
    "operation_issue": "运营问题", "daily_report": "运营日报", "weekly_report": "运营周报",
})
EVENT_ACTION_LABELS = {
    "viewed": "已查看", "created": "已创建", "updated": "已更新", "deleted": "已删除", "submitted": "已提交",
    "generated": "已生成", "uploaded": "已上传", "downloaded": "已下载", "failed": "失败", "success": "成功",
    "approved": "已批复", "rejected": "未通过", "disbursed": "已放款", "completed": "已完成", "cancelled": "已取消",
}
EVENT_ACTION_LABELS.update({
    "viewed": "已查看", "created": "已创建", "updated": "已更新", "deleted": "已删除",
    "submitted": "已提交", "assigned": "已分配", "generated": "已生成", "uploaded": "已上传",
    "downloaded": "已下载", "sent": "已发送", "failed": "失败", "success": "成功",
    "approved": "已批复", "rejected": "未通过", "disbursed": "已放款", "completed": "已完成",
    "cancelled": "已取消", "retried": "已重试", "run": "已执行", "read": "已读", "logged_in": "已登录",
})
TASK_STATUS_LABELS = {"pending": "待跟进", "done": "已完成", "cancelled": "已取消", "overdue": "已逾期"}
TASK_PRIORITY_LABELS = {"high": "高优先级", "medium": "中优先级", "low": "低优先级"}
TASK_TYPE_LABELS = {
    "call": "电话联系", "wechat": "微信跟进", "send_report": "发送报告", "payment_follow": "付款跟进",
    "upsell": "升级跟进", "revisit": "回访", "collect_documents": "补充资料", "verify_documents": "资料核验",
    "client_clarification": "客户补充说明", "repayment_reminder": "还款提醒", "post_loan_check": "贷后检查",
    "renewal_prepare": "续贷准备", "cashflow_review": "现金流复查", "advisor_booking_follow": "顾问预约跟进",
}

def _label(mapping, code):
    if code is None:
        return ""
    value = str(code)
    return mapping.get(value, value)

def get_product_label(code):
    value = "" if code is None else str(code).strip()
    return PRODUCT_LABELS.get(value, "全部产品" if not value else "其他业务产品")
def get_event_label(code):
    value = "" if code is None else str(code).strip().lower()
    if value in EVENT_LABELS:
        return EVENT_LABELS[value]
    for suffix in sorted(EVENT_ACTION_LABELS, key=len, reverse=True):
        marker = f"_{suffix}"
        if not value.endswith(marker):
            continue
        subject_label = EVENT_SUBJECT_LABELS.get(value[:-len(marker)])
        return f"{subject_label}{EVENT_ACTION_LABELS[suffix]}" if subject_label else "系统事件"
    return "系统事件"
def get_task_status_label(code): return _label(TASK_STATUS_LABELS, code)
def get_task_priority_label(code): return _label(TASK_PRIORITY_LABELS, code)
def get_task_type_label(code): return _label(TASK_TYPE_LABELS, code)


SAFE_CATEGORY_FALLBACKS = {
    "product": "其他业务产品", "order_status": "未知订单状态", "payment_channel": "其他支付渠道",
    "event": "系统事件", "role": "系统账号", "status": "未知状态", "task_status": "未知任务状态",
    "task_type": "其他任务", "booking_status": "未知预约状态", "service_type": "其他顾问服务",
    "commission_trigger": "其他业务触发", "commission_type": "其他结算方式", "landing_page": "其他落地页",
    "channel": "其他渠道", "data_source": "其他来源", "notification": "系统通知",
}


def safe_display_label(value, category=None):
    if value is None or value == "":
        return ""
    dispatch = {
        "product": get_product_label, "order_status": get_order_status_label,
        "payment_channel": get_payment_channel_label, "payment_status": get_payment_status_label,
        "event": get_event_label, "role": get_role_label, "nav": get_nav_label,
        "task_status": get_task_status_label, "task_priority": get_task_priority_label,
        "task_type": get_task_type_label, "lead_grade": get_lead_grade_label,
        "follow_status": get_follow_status_label, "booking_status": get_booking_status_label,
        "service_type": get_service_type_label, "urgency": get_urgency_level_label,
        "commission_trigger": get_commission_trigger_label, "commission_type": get_commission_type_label,
        "settlement_status": get_settlement_status_label, "landing_page": get_landing_page_label,
        "channel": get_channel_label, "ab_variant": get_ab_variant_label, "data_source": get_data_source_label,
        "document_category": get_document_category_label, "document_parse_status": get_document_parse_status_label,
        "document_verify_status": get_document_verify_status_label, "project_status": get_project_status_label,
        "funding_status": get_funding_application_status_label, "notification_status": get_notification_status_label,
        "notification_channel": get_notification_channel_label, "boolean": get_boolean_label,
    }
    if category in dispatch:
        return dispatch[category](value)
    text = str(value).strip()
    if re.search(r"[\u4e00-\u9fff]", text) and "_" not in text:
        return text
    known = (
        PRODUCT_LABELS | ORDER_STATUS_LABELS | PAYMENT_CHANNEL_LABELS | ROLE_LABELS | STATUS_LABELS |
        TASK_STATUS_LABELS | TASK_PRIORITY_LABELS | TASK_TYPE_LABELS | BOOKING_STATUS_LABELS |
        SERVICE_TYPE_LABELS | COMMISSION_TRIGGER_LABELS | COMMISSION_TYPE_LABELS | SETTLEMENT_STATUS_LABELS |
        SOURCE_CHANNEL_LABELS | AB_VARIANT_LABELS | DATA_SOURCE_LABELS | PROJECT_STATUS_LABELS |
        FUNDING_APPLICATION_STATUS_LABELS | NOTIFICATION_STATUS_LABELS | NOTIFICATION_CHANNEL_LABELS
        | INTERNAL_NOTIFICATION_TYPE_LABELS
    )
    lowered = text.lower()
    if lowered in known:
        return known[lowered]
    if "_" in text or re.fullmatch(r"[a-z0-9_./-]+", text):
        return SAFE_CATEGORY_FALLBACKS.get(category or "", "系统记录")
    return text


def get_display_company_name(company_name):
    """隐藏历史阶段测试前缀，不改动原始企业名称。"""
    if not company_name:
        return "未命名企业"
    value = str(company_name).strip()
    value = re.sub(r"^Phase(?:[6-9]|1[0-4])(?:[-_\s]*)", "", value, flags=re.IGNORECASE)
    if "测试企业" in value:
        return "测试客户"
    if re.search(r"demo|演示", value, flags=re.IGNORECASE):
        return "演示客户"
    return value.strip() or "测试企业"


DEMO_TEST_KEYWORDS = ("phase", "demo", "测试", "演示", "smoke", "验收", "回归")


def is_demo_or_test_record(value):
    """递归检查企业名称、备注、标签等展示数据，仅用于看板过滤。"""
    if value is None:
        return False
    if isinstance(value, str):
        lowered = value.lower()
        return any(keyword in lowered for keyword in DEMO_TEST_KEYWORDS)
    if isinstance(value, dict):
        return any(is_demo_or_test_record(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(is_demo_or_test_record(item) for item in value)
    for attr in ("company_name", "note", "pilot_note", "task_title", "task_content"):
        if is_demo_or_test_record(getattr(value, attr, None)):
            return True
    return False


def get_event_target_label(event):
    """生成事件所属对象的业务化说明。"""
    if event is None:
        return "系统"
    lead = getattr(event, "lead", None)
    assessment = getattr(event, "assessment", None)
    company_name = getattr(lead, "company_name", "") or getattr(assessment, "company_name", "")
    if not company_name:
        try:
            payload = json.loads(getattr(event, "event_data_json", "{}") or "{}")
            company_name = payload.get("company_name", "")
        except (TypeError, ValueError, json.JSONDecodeError):
            company_name = ""
    if company_name:
        return f"企业：{get_display_company_name(company_name)}"
    assessment_id = getattr(event, "assessment_id", None)
    if assessment_id:
        return f"测评 #{assessment_id}"
    event_type = str(getattr(event, "event_type", "") or "")
    if event_type == "audit_log_created":
        return "系统记录"
    if event_type.startswith(("client_", "customer_")):
        return "客户行为"
    if event_type.endswith("_viewed") or event_type in {"setup_step_completed", "preflight_check_run", "route_manifest_generated", "load_test_run"}:
        return "后台操作"
    return "系统"
