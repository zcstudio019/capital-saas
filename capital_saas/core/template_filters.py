from fastapi.templating import Jinja2Templates
from utils.display_labels import (
    get_ab_variant_label, get_boolean_label, get_booking_status_label, get_channel_label,
    get_commission_trigger_label, get_commission_type_label, get_commission_value_label,
    get_data_source_label, get_display_company_name, get_document_category_label,
    get_document_parse_status_label, get_document_verify_status_label, get_event_label,
    get_event_target_label, get_follow_status_label, get_funding_application_status_label,
    get_institution_type_label, get_internal_notification_type_label, get_landing_page_label, get_lead_grade_label, get_nav_label, get_notification_channel_label,
    get_notification_status_label, get_order_status_label, get_payment_channel_label,
    get_notification_template_label, get_payment_status_label, get_product_label, get_project_status_label, get_role_label,
    get_role_type_label, get_report_generation_status_label, get_report_review_status_label, get_script_scenario_label, get_service_type_label,
    get_settlement_status_label, get_source_channel_label, get_status_label,
    get_task_priority_label, get_task_status_label, get_task_type_label,
    get_urgency_level_label, get_user_display_name, safe_display_label,
)


ZH_MAP = {
    "admin": "管理员", "super_admin": "总部超级管理员", "city_manager": "城市负责人",
    "sales_manager": "销售主管", "sales": "销售", "consultant_manager": "顾问主管",
    "consultant": "融资顾问", "finance": "财务", "viewer": "只读", "partner": "渠道伙伴",
    "customer": "客户",
    "mock": "模拟通道", "openai": "OpenAI", "manual_transfer": "人工转账", "wechat_pay": "微信支付",
    "alipay": "支付宝", "in_app": "站内信", "email": "邮件", "sms": "短信", "wecom_webhook": "企业微信机器人",
    "pending": "待处理", "queued": "待发送", "sending": "发送中", "success": "成功",
    "failed": "失败", "cancelled": "已取消", "skipped": "已跳过", "paid": "已支付",
    "refunded": "已退款", "done": "已完成", "open": "待处理", "in_progress": "处理中",
    "resolved": "已解决", "closed": "已关闭", "won't_fix": "暂不处理",
    "new": "新反馈", "reviewing": "处理中", "ignored": "已忽略",
    "draft": "草稿", "pending_review": "待审核", "approved": "已通过", "rejected": "已拒绝",
    "planning": "筹备中", "running": "运行中", "paused": "已暂停", "completed": "已完成", "archived": "已归档",
    "ready": "已就绪", "submitted": "已提交", "returned": "已退回",
    "complete": "完整", "partial": "部分完整", "weak": "较弱",
    "high": "高", "medium": "中", "low": "低", "critical": "严重",
    "bug": "Bug问题", "feature_request": "需求建议", "data_issue": "数据问题",
    "payment_issue": "支付问题", "report_issue": "报告问题", "operation_issue": "运营问题",
    "customer_feedback": "客户反馈", "admin_created": "后台创建", "system_detected": "系统发现",
    "sales_feedback": "销售反馈", "consultant_feedback": "顾问反馈",
    "report_quality": "报告质量", "payment": "支付问题", "document_upload": "资料上传",
    "project_progress": "项目进度", "advisor_service": "顾问服务", "usability": "使用体验", "other": "其他",
    "invited": "已邀请", "assessed": "已测评", "report_viewed": "已看报告",
    "documents_uploaded": "已上传资料", "consulting_started": "已进入顾问服务",
    "project_created": "已立项", "dropped": "已流失",
    "call": "电话跟进", "wechat": "微信跟进", "send_report": "发送报告",
    "payment_follow": "支付跟进", "upsell": "升级跟进", "revisit": "回访",
    "collect_documents": "收集资料", "verify_documents": "核验资料", "client_clarification": "客户澄清",
    "advisor": "顾问消息", "document_request": "补资料提醒", "project_update": "项目进度", "reminder": "提醒",
    "upload_document": "上传资料", "confirm_info": "确认信息", "review_report": "查看报告",
    "provide_feedback": "提交反馈", "sign_confirmation": "签署确认",
    "application_submit_authorized": "授权提交申请", "financing_plan_confirmed": "确认融资方案",
    "document_list_confirmed": "确认资料清单", "disclaimer_confirmed": "确认免责声明",
    "service_completed": "确认服务完成",
    "ai": "智能", "AI": "智能", "A/B": "A/B测试",
    "variant_a": "风险提示版", "variant_b": "机会收益版",
    "free_result_conversion": "免费结果页转化实验",
    "299_report": "299元基础诊断报告", "699_bank_match": "699元银行匹配报告",
    "1999_structure_plan": "1999元融资结构方案", "high_ticket_consulting": "一对一融资顾问服务",
    "free_nurture": "免费培育", "direct": "直接访问",
    "headquarters": "总部", "branch": "分公司", "team": "团队", "active": "启用", "inactive": "停用",
    "per_lead": "按线索结算", "per_paid_order": "按付费订单结算",
    "per_disbursed_amount": "按放款金额结算", "manual": "人工结算",
    "fixed_amount": "固定金额", "percentage": "比例提成", "confirmed": "已确认",
    "preparing": "资料准备中", "bank_review": "金融机构审核中", "supplement_required": "需补充资料",
    "disbursed": "已放款", "withdrawn": "已撤回", "partial_success": "部分成功",
    "planned": "计划申请", "reviewed": "已审核", "cancelled": "已取消",
    "bank": "银行", "guarantee": "担保机构", "factoring": "保理机构", "leasing": "融资租赁",
    "microloan": "小额贷款", "private_fund": "私募资金", "system": "系统消息",
    "service": "服务通知", "marketing": "营销通知", "production": "生产环境",
    "development": "开发环境", "staging": "预发布环境", "unknown": "未知",
    "pending_parse": "待解析", "parsed": "已解析", "parse_failed": "解析失败",
    "verified": "已核验", "unverified": "待核验", "needs_more_documents": "需补充资料",
    "portal_login": "客户门户登录", "report_access": "报告访问", "document_upload": "资料上传",
    "project_view": "项目查看", "read": "已读", "unread": "未读", "worker": "后台任务",
    "excellent": "优秀", "good": "良好", "average": "一般", "poor": "较差",
    "assessment_submitted": "已提交测评", "free_result_viewed": "已查看免费结果",
    "checkout_viewed": "已进入结算页", "payment_success": "支付成功", "report_viewed": "已查看报告",
    "landing_page_viewed": "已访问落地页", "client_dashboard_viewed": "客户已查看服务概览",
}


def zh_label(value):
    if value is None:
        return ""
    text = str(value)
    return ZH_MAP.get(text, ZH_MAP.get(text.lower(), safe_display_label(text)))


def install_chinese_filters(templates: Jinja2Templates) -> Jinja2Templates:
    templates.env.filters["zh"] = zh_label
    templates.env.filters["product_label"] = get_product_label
    templates.env.filters["order_status_label"] = get_order_status_label
    templates.env.filters["report_generation_status_label"] = get_report_generation_status_label
    templates.env.filters["report_review_status_label"] = get_report_review_status_label
    templates.env.filters["payment_channel_label"] = get_payment_channel_label
    templates.env.filters["payment_status_label"] = get_payment_status_label
    templates.env.filters["landing_page_label"] = get_landing_page_label
    templates.env.filters["commission_trigger_label"] = get_commission_trigger_label
    templates.env.filters["commission_type_label"] = get_commission_type_label
    templates.env.filters["commission_value_label"] = get_commission_value_label
    templates.env.filters["role_type_label"] = get_role_type_label
    templates.env.filters["script_scenario_label"] = get_script_scenario_label
    templates.env.filters["status_label"] = get_status_label
    templates.env.filters["boolean_label"] = get_boolean_label
    templates.env.filters["settlement_status_label"] = get_settlement_status_label
    templates.env.filters["lead_grade_label"] = get_lead_grade_label
    templates.env.filters["source_channel_label"] = get_source_channel_label
    templates.env.filters["channel_label"] = get_channel_label
    templates.env.filters["follow_status_label"] = get_follow_status_label
    templates.env.filters["booking_status_label"] = get_booking_status_label
    templates.env.filters["service_type_label"] = get_service_type_label
    templates.env.filters["urgency_level_label"] = get_urgency_level_label
    templates.env.filters["ab_variant_label"] = get_ab_variant_label
    templates.env.filters["data_source_label"] = get_data_source_label
    templates.env.filters["document_category_label"] = get_document_category_label
    templates.env.filters["document_parse_status_label"] = get_document_parse_status_label
    templates.env.filters["document_verify_status_label"] = get_document_verify_status_label
    templates.env.filters["project_status_label"] = get_project_status_label
    templates.env.filters["funding_application_status_label"] = get_funding_application_status_label
    templates.env.filters["notification_status_label"] = get_notification_status_label
    templates.env.filters["notification_channel_label"] = get_notification_channel_label
    templates.env.filters["notification_template_label"] = get_notification_template_label
    templates.env.filters["internal_notification_type_label"] = get_internal_notification_type_label
    templates.env.filters["institution_type_label"] = get_institution_type_label
    templates.env.filters["safe_display_label"] = safe_display_label
    templates.env.filters["nav_label"] = get_nav_label
    templates.env.filters["role_label"] = get_role_label
    templates.env.filters["user_display_name"] = get_user_display_name
    templates.env.filters["event_label"] = get_event_label
    templates.env.filters["task_status_label"] = get_task_status_label
    templates.env.filters["task_priority_label"] = get_task_priority_label
    templates.env.filters["task_type_label"] = get_task_type_label
    templates.env.filters["display_company_name"] = get_display_company_name
    templates.env.filters["event_target_label"] = get_event_target_label
    for name, func in {
        "get_product_label": get_product_label,
        "get_order_status_label": get_order_status_label,
        "get_report_generation_status_label": get_report_generation_status_label,
        "get_report_review_status_label": get_report_review_status_label,
        "get_payment_channel_label": get_payment_channel_label,
        "get_payment_status_label": get_payment_status_label,
        "get_event_label": get_event_label,
        "get_event_target_label": get_event_target_label,
        "get_role_label": get_role_label,
        "get_user_display_name": get_user_display_name,
        "get_nav_label": get_nav_label,
        "get_task_status_label": get_task_status_label,
        "get_task_priority_label": get_task_priority_label,
        "get_task_type_label": get_task_type_label,
        "get_lead_grade_label": get_lead_grade_label,
        "get_follow_status_label": get_follow_status_label,
        "get_booking_status_label": get_booking_status_label,
        "get_service_type_label": get_service_type_label,
        "get_urgency_level_label": get_urgency_level_label,
        "get_commission_trigger_label": get_commission_trigger_label,
        "get_commission_type_label": get_commission_type_label,
        "get_settlement_status_label": get_settlement_status_label,
        "get_landing_page_label": get_landing_page_label,
        "get_channel_label": get_channel_label,
        "get_ab_variant_label": get_ab_variant_label,
        "get_data_source_label": get_data_source_label,
        "get_document_category_label": get_document_category_label,
        "get_document_parse_status_label": get_document_parse_status_label,
        "get_document_verify_status_label": get_document_verify_status_label,
        "get_project_status_label": get_project_status_label,
        "get_funding_application_status_label": get_funding_application_status_label,
        "get_notification_status_label": get_notification_status_label,
        "get_notification_channel_label": get_notification_channel_label,
        "get_notification_template_label": get_notification_template_label,
        "get_internal_notification_type_label": get_internal_notification_type_label,
        "get_institution_type_label": get_institution_type_label,
        "get_boolean_label": get_boolean_label,
        "get_display_company_name": get_display_company_name,
        "safe_display_label": safe_display_label,
    }.items():
        templates.env.globals[name] = func
    templates.env.globals["zh_labels"] = ZH_MAP
    return templates


def patch_jinja_templates() -> None:
    original_init = Jinja2Templates.__init__
    original_template_response = Jinja2Templates.TemplateResponse
    if getattr(Jinja2Templates, "_capital_saas_zh_patched", False):
        return

    def patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        install_chinese_filters(self)

    def patched_template_response(self, *args, **kwargs):
        context = kwargs.get("context")
        request = kwargs.get("request")
        if context is None and len(args) >= 3 and isinstance(args[2], dict):
            context = args[2]
        if request is None and len(args) >= 1 and hasattr(args[0], "state"):
            request = args[0]
        if isinstance(context, dict):
            count = getattr(getattr(request, "state", None), "notification_unread_count", 0) if request else 0
            if not count and request is not None:
                try:
                    user_id = request.session.get("user_id")
                    if user_id:
                        from db.database import SessionLocal
                        from services.notification_service import get_unread_count
                        with SessionLocal() as db:
                            count = get_unread_count(db, int(user_id))
                        request.state.notification_unread_count = count
                        request.state.unread_notifications = count
                except Exception:
                    count = 0
            context.setdefault("notification_unread_count", count)
        return original_template_response(self, *args, **kwargs)

    Jinja2Templates.__init__ = patched_init
    Jinja2Templates.TemplateResponse = patched_template_response
    Jinja2Templates._capital_saas_zh_patched = True
