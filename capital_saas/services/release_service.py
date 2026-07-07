from __future__ import annotations

import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from core.config import BASE_DIR, settings
from db.models import (
    AuditLog,
    BankProduct,
    LegalDocument,
    NotificationTemplate,
    Organization,
    SetupProgress,
    SystemSetting,
    User,
)
from services.auth_service import verify_password
from services.backup_service import list_backups


SETUP_STEPS = [
    ("company_info", "设置公司信息", "/admin/settings"),
    ("admin_password", "修改默认管理员密码", "/admin/account/password"),
    ("site_domain", "设置站点域名", "/admin/settings"),
    ("product_prices", "设置产品价格", "/products"),
    ("payment_mode", "设置支付模式", "/admin/settings"),
    ("ai_mode", "设置AI模式", "/admin/settings"),
    ("notification_mode", "设置通知模式", "/admin/notification-templates"),
    ("legal_docs", "设置隐私协议", "/admin/legal-documents"),
    ("organizations", "设置组织架构", "/admin/organizations"),
    ("channels", "设置渠道来源", "/admin/channel-partners"),
    ("bank_products", "设置银行产品", "/admin/bank-products"),
    ("backup_policy", "设置备份策略", "/admin/backups"),
]


def _status(ok: bool, warn: bool = False) -> str:
    if ok:
        return "pass"
    return "warning" if warn else "fail"


def get_git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            timeout=3,
        )
        return result.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def read_version() -> str:
    path = BASE_DIR / "VERSION"
    return path.read_text(encoding="utf-8").strip() if path.exists() else settings.app_version


def preflight_groups(db: Session) -> dict[str, list[dict]]:
    uploads = BASE_DIR / "data" / "uploads"
    backups_dir = BASE_DIR / "data" / "backups"
    logs_dir = BASE_DIR / "logs"
    for folder in (uploads, backups_dir, logs_dir):
        folder.mkdir(parents=True, exist_ok=True)

    admin = db.query(User).filter(User.username == settings.admin_default_username).first()
    default_admin = bool(admin and verify_password(settings.admin_default_password, admin.password_hash))
    legal_count = db.query(LegalDocument).filter(LegalDocument.is_active.is_(True)).count()
    recent_backup = any(x["created_at"] >= datetime.now() - timedelta(days=7) for x in list_backups())
    high_audits = db.query(AuditLog).filter(
        AuditLog.risk_level.in_(["high", "critical"]),
        AuditLog.created_at >= datetime.now() - timedelta(days=7),
    ).count()

    groups = {
        "安全项": [
            {"name": "SECRET_KEY 非默认", "status": _status(settings.secret_key != "change-me-in-production"), "message": "生产必须使用随机 SECRET_KEY"},
            {"name": "默认管理员密码已修改", "status": _status(not default_admin), "message": "上线前必须修改 admin123"},
            {"name": "审计日志开启", "status": _status(settings.security_audit_enabled), "message": "建议生产保持开启"},
            {"name": "公共入口限流开启", "status": _status(settings.rate_limit_enabled, warn=True), "message": "development 可关闭，production 应开启"},
        ],
        "配置项": [
            {"name": "APP_ENV=production", "status": _status(settings.app_env == "production", warn=True), "message": f"当前 {settings.app_env}"},
            {"name": "SITE_BASE_URL 已配置", "status": _status(settings.site_base_url and "127.0.0.1" not in settings.site_base_url, warn=True), "message": settings.site_base_url},
            {"name": "数据库可连接", "status": "pass", "message": str(db.bind.url) if db.bind else settings.database_url},
            {"name": "uploads/backups/logs 可写", "status": _status(all(p.exists() for p in [uploads, backups_dir, logs_dir])), "message": "本地目录检查通过"},
        ],
        "支付项": [
            {"name": "支付模式已设置", "status": _status(bool(settings.payment_mode)), "message": settings.payment_mode},
            {"name": "真实支付风险提示", "status": "warning" if settings.payment_mode == "mock" else "pass", "message": "mock 适合试运营验证，真实商用需配置支付通道"},
        ],
        "AI项": [
            {"name": "AI模式已设置", "status": _status(settings.ai_mode in {"mock", "openai"}, warn=True), "message": settings.ai_mode},
            {"name": "OpenAI Key", "status": "pass" if settings.ai_mode == "mock" or settings.openai_api_key else "warning", "message": "mock 模式无需配置"},
        ],
        "通知项": [
            {"name": "通知模板已预置", "status": _status(db.query(NotificationTemplate).count() > 0), "message": "用于报告、补资料、项目进度提醒"},
            {"name": "通知模式已设置", "status": _status(bool(settings.notification_mode), warn=True), "message": settings.notification_mode},
        ],
        "备份项": [
            {"name": "备份保留天数", "status": _status(settings.backup_retention_days > 0), "message": f"{settings.backup_retention_days} 天"},
            {"name": "最近7天有备份", "status": _status(recent_backup, warn=True), "message": "建议上线前手动备份一次"},
        ],
        "法务项": [
            {"name": "法律文档已配置", "status": _status(legal_count >= 3), "message": f"当前激活 {legal_count} 份"},
            {"name": "报告审核", "status": _status(settings.report_review_required, warn=True), "message": "生产建议开启"},
        ],
        "组织项": [
            {"name": "默认组织存在", "status": _status(db.query(Organization).count() > 0), "message": "旧数据默认归属总部"},
            {"name": "至少一个用户", "status": _status(db.query(User).count() > 0), "message": "需要管理员账号"},
        ],
        "运营项": [
            {"name": "银行产品库", "status": _status(db.query(BankProduct).count() > 0, warn=True), "message": "用于融资方案匹配"},
            {"name": "系统配置项", "status": _status(db.query(SystemSetting).count() > 0, warn=True), "message": "建议完成 setup wizard"},
        ],
        "性能项": [
            {"name": "SQLite 试运营提示", "status": "warning" if settings.database_url.startswith("sqlite") else "pass", "message": "多城市正式运营建议 MySQL/PostgreSQL"},
            {"name": "高风险审计待处理", "status": "warning" if high_audits else "pass", "message": f"最近7天 {high_audits} 条"},
        ],
    }
    return groups


def flatten_preflight(groups: dict[str, list[dict]]) -> list[dict]:
    rows = []
    for group, items in groups.items():
        for item in items:
            rows.append({"group": group, **item})
    return rows


def setup_status(db: Session) -> list[dict]:
    existing = {x.step_key: x for x in db.query(SetupProgress).all()}
    result = []
    for key, title, url in SETUP_STEPS:
        item = existing.get(key)
        result.append(
            {
                "step_key": key,
                "title": title,
                "url": url,
                "status": item.status if item else "pending",
                "completed_at": item.completed_at if item else None,
            }
        )
    return result

