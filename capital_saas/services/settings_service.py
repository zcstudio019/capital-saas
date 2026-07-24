from datetime import datetime

from sqlalchemy.orm import Session

from core.config import settings
from db.models import SystemSetting


SETTING_DEFINITIONS = {
    "site_name": (settings.app_name, "网站显示名称"),
    "company_name": ("沪上银", "运营主体名称"),
    "contact_phone": ("", "客户联系电话"),
    "contact_wechat": ("", "客户联系微信"),
    "report_price_299": ("299", "基础诊断报告价格"),
    "report_price_699": ("699", "银行匹配报告价格"),
    "report_price_1999": ("1999", "融资结构优化方案价格"),
    "capital_health_report_price": ("980", "企业资本健康体检报告价格"),
    "capital_structure_plan_price": ("1999", "融资结构优化方案价格"),
    "one_on_one_consulting_price": ("9800", "1对1融资顾问服务起价"),
    "capital_health_institution": ("沪上银 · 企业资本健康管理中心", "资本健康体检机构名称"),
    "capital_health_report_validity_days": ("90", "资本健康报告有效期天数"),
    "capital_health_show_english_subtitle": ("true", "资本健康报告是否显示英文副标题"),
    "structure_plan_upgrade_mode": ("deduct_report_price", "结构优化方案升级计价：full_price/deduct_report_price"),
    "legacy_299_upgrade_policy": ("keep_legacy_rights", "旧299权益：keep_legacy_rights/grant_980_rights"),
    "capital_health_report_review_required": ("false", "980体检报告交付前是否必须人工审核"),
    "structure_plan_review_required": ("true", "1999结构优化方案交付前是否必须人工审核"),
    "980_report_review_required": ("false", "980元企业资本健康体检报告是否必须人工审核"),
    "1999_plan_review_required": ("true", "1999元融资结构优化方案是否必须人工审核"),
    "ai_mode": (settings.ai_mode, "AI运行模式：mock/openai"),
    "openai_model": (settings.openai_model, "OpenAI模型"),
    "payment_mode": (settings.payment_mode, "支付模式"),
    "enable_registration": ("false", "是否开放用户注册"),
    "report_review_required": (
        str(settings.report_review_required).lower(),
        "客户查看完整报告前是否必须人工审核",
    ),
    "upload_max_mb": (str(settings.upload_max_mb), "单个客户资料最大上传MB"),
    "notification_mode": (settings.notification_mode, "通知模式：mock/production"),
    "email_enabled": (str(settings.email_enabled).lower(), "启用邮件通知"),
    "smtp_host": ("", "SMTP服务器"), "smtp_port": ("587", "SMTP端口"),
    "smtp_username": ("", "SMTP账号"), "smtp_password": ("", "SMTP密码（建议仅使用环境变量）"),
    "sms_enabled": (str(settings.sms_enabled).lower(), "启用短信通知"),
    "sms_provider": ("", "短信供应商"), "sms_api_key": ("", "短信API密钥（建议仅使用环境变量）"),
    "wecom_webhook_enabled": (str(settings.wecom_webhook_enabled).lower(), "启用企业微信Webhook"),
    "wecom_webhook_url": ("", "企业微信机器人Webhook"),
    "notification_max_retries": (str(settings.notification_max_retries), "通知最大重试次数"),
    "payment_pending_remind_minutes": (str(settings.payment_pending_remind_minutes), "待支付提醒延迟分钟"),
    "upgrade_remind_hours": (str(settings.upgrade_remind_hours), "升级提醒延迟小时"),
    "rate_limit_enabled": (str(settings.rate_limit_enabled).lower(), "启用公共入口限流"),
    "rate_limit_per_minute": (str(settings.rate_limit_per_minute), "普通入口每分钟IP限额"),
    "login_rate_limit_per_minute": (str(settings.login_rate_limit_per_minute), "登录入口每分钟IP限额"),
    "max_lead_upload_mb": (str(settings.max_lead_upload_mb), "单线索资料总容量MB"),
    "backup_retention_days": (str(settings.backup_retention_days), "备份保留天数"),
    "force_password_change": (str(settings.force_password_change).lower(), "默认账号强制改密"),
    "security_audit_enabled": (str(settings.security_audit_enabled).lower(), "启用安全审计"),
    "data_masking_enabled": (str(settings.data_masking_enabled).lower(), "启用数据脱敏"),
}


def ensure_default_settings(db: Session) -> None:
    current_settings = db.query(SystemSetting).all()
    existing = {item.key for item in current_settings}
    # 产品首档统一为 299 元，兼容更新旧库中的历史测试价格。
    for item in current_settings:
        if item.key == "report_price_299" and item.value in {"199", "199.0", "333", "333.0"}:
            item.value = "299"
            item.updated_at = datetime.now()
    for key, (value, description) in SETTING_DEFINITIONS.items():
        if key not in existing:
            db.add(SystemSetting(key=key, value=value, description=description))
    db.commit()


def get_setting(db: Session, key: str, fallback: str | None = None) -> str:
    item = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if item:
        return item.value
    if fallback is not None:
        return fallback
    return SETTING_DEFINITIONS.get(key, ("", ""))[0]


def get_bool_setting(db: Session, key: str, fallback: bool = False) -> bool:
    value = get_setting(db, key, str(fallback).lower())
    return value.strip().lower() in {"1", "true", "yes", "on"}


def save_settings(db: Session, values: dict[str, str]) -> None:
    for key, value in values.items():
        if key not in SETTING_DEFINITIONS:
            continue
        item = db.query(SystemSetting).filter(SystemSetting.key == key).first()
        if not item:
            item = SystemSetting(
                key=key,
                value=value,
                description=SETTING_DEFINITIONS[key][1],
            )
            db.add(item)
        else:
            item.value = value
            item.updated_at = datetime.now()
    db.commit()


def settings_dict(db: Session) -> dict[str, str]:
    return {
        key: get_setting(db, key, default)
        for key, (default, _) in SETTING_DEFINITIONS.items()
    }
