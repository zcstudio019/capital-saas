import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values, load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent

_root_env = dotenv_values(BASE_DIR / ".env")
_app_env = os.getenv("APP_ENV") or _root_env.get("APP_ENV") or "development"
load_dotenv(BASE_DIR / "config" / f"{_app_env}.env", override=False)
load_dotenv(BASE_DIR / ".env", override=True)


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "AI企业资本战略诊断SaaS系统")
    app_env: str = os.getenv("APP_ENV", _app_env)
    secret_key: str = os.getenv("SECRET_KEY", "change-me-in-production")
    database_url: str = os.getenv(
        "DATABASE_URL", f"sqlite:///{(BASE_DIR / 'capital_saas.db').as_posix()}"
    )
    report_price: int = int(os.getenv("REPORT_PRICE", "299"))
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "").strip()
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    ai_mode: str = os.getenv("AI_MODE", "mock").lower()
    payment_mode: str = os.getenv("PAYMENT_MODE", "mock").lower()
    admin_default_username: str = os.getenv("ADMIN_DEFAULT_USERNAME", "admin")
    admin_default_password: str = os.getenv("ADMIN_DEFAULT_PASSWORD", "admin123")
    site_base_url: str = os.getenv("SITE_BASE_URL", "http://127.0.0.1:8001")
    wechat_pay_mch_id: str = os.getenv("WECHAT_PAY_MCH_ID", "")
    wechat_pay_api_key: str = os.getenv("WECHAT_PAY_API_KEY", "")
    alipay_app_id: str = os.getenv("ALIPAY_APP_ID", "")
    report_review_required: bool = os.getenv(
        "REPORT_REVIEW_REQUIRED",
        "true" if os.getenv("APP_ENV", "development") == "production" else "false",
    ).lower() in {"1", "true", "yes", "on"}
    upload_max_mb: int = int(os.getenv("MAX_UPLOAD_MB", os.getenv("UPLOAD_MAX_MB", "20")))
    notification_mode: str = os.getenv("NOTIFICATION_MODE", "mock")
    email_enabled: bool = os.getenv("EMAIL_ENABLED", "false").lower() in {"1","true","yes","on"}
    sms_enabled: bool = os.getenv("SMS_ENABLED", "false").lower() in {"1","true","yes","on"}
    wecom_webhook_enabled: bool = os.getenv("WECOM_WEBHOOK_ENABLED", "false").lower() in {"1","true","yes","on"}
    notification_max_retries: int = int(os.getenv("NOTIFICATION_MAX_RETRIES", "3"))
    payment_pending_remind_minutes: int = int(os.getenv("PAYMENT_PENDING_REMIND_MINUTES", "30"))
    upgrade_remind_hours: int = int(os.getenv("UPGRADE_REMIND_HOURS", "24"))
    app_version: str = os.getenv("APP_VERSION", "13.0.0")
    rate_limit_enabled: bool = os.getenv("RATE_LIMIT_ENABLED", "true" if os.getenv("APP_ENV","development")=="production" else "false").lower() in {"1","true","yes","on"}
    rate_limit_per_minute: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))
    login_rate_limit_per_minute: int = int(os.getenv("LOGIN_RATE_LIMIT_PER_MINUTE", "10"))
    max_lead_upload_mb: int = int(os.getenv("MAX_LEAD_UPLOAD_MB", "500"))
    backup_retention_days: int = int(os.getenv("BACKUP_RETENTION_DAYS", "30"))
    force_password_change: bool = os.getenv("FORCE_PASSWORD_CHANGE", "true").lower() in {"1","true","yes","on"}
    security_audit_enabled: bool = os.getenv("SECURITY_AUDIT_ENABLED", "true").lower() in {"1","true","yes","on"}
    data_masking_enabled: bool = os.getenv("DATA_MASKING_ENABLED", "true").lower() in {"1","true","yes","on"}
    trial_mode: bool = os.getenv("TRIAL_MODE", "false").lower() in {"1","true","yes","on"}
    trial_allowed_ips: str = os.getenv("TRIAL_ALLOWED_IPS", "")
    trial_access_code: str = os.getenv("TRIAL_ACCESS_CODE", "")


settings = Settings()
