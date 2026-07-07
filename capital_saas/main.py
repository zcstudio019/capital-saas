from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from utils.rate_limiter import RateLimitMiddleware
from core.template_filters import patch_jinja_templates

patch_jinja_templates()
from api import admin, advisor, assessment, auth, client_portal, delivery, diligence, events, growth, notifications, organization, payment, pilot, release, report, sales, security
from core.config import BASE_DIR, settings
from db import models  # noqa: F401
from db.database import Base, SessionLocal, engine
from db.migrations import migrate_database
from services.auth_service import ensure_default_admin
from services.settings_service import ensure_default_settings
from services.settings_service import get_setting
from services.ab_test_service import ensure_default_experiment
from services.script_template_service import ensure_default_scripts
from services.tag_service import ensure_default_tags
from services.bank_product_service import ensure_default_bank_products
from services.organization_service import ensure_default_organization
from services.notification_service import ensure_default_notification_templates
from services.legal_service import ensure_default_legal_documents
from utils.logger import logger


templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    changed = migrate_database()
    with SessionLocal() as db:
        admin_user = ensure_default_admin(db)
        ensure_default_settings(db)
        ensure_default_experiment(db)
        ensure_default_scripts(db)
        ensure_default_tags(db)
        ensure_default_bank_products(db)
        ensure_default_organization(db, admin_user)
        ensure_default_notification_templates(db)
        ensure_default_legal_documents(db)
        admin_username = admin_user.username
    if settings.secret_key == "change-me-in-production":
        logger.warning("SECRET_KEY仍为默认值，生产上线前必须修改。")
    if settings.app_env == "production":
        if settings.payment_mode == "mock":
            logger.warning("生产环境仍使用 mock 支付，请确认是否仅用于灰度试运营。")
        if not settings.rate_limit_enabled:
            logger.warning("生产环境未开启限流。")
        if not settings.security_audit_enabled:
            logger.warning("生产环境未开启安全审计。")
        if settings.admin_default_password == "admin123":
            logger.warning("生产环境默认管理员密码配置仍为 admin123。")
    logger.info(
        "AI配置 mode=%s model=%s base_url_configured=%s",
        settings.ai_mode,
        settings.openai_model,
        bool(settings.openai_base_url),
    )
    logger.info(
        "应用启动 env=%s database=%s admin=%s migrated=%s",
        settings.app_env,
        settings.database_url,
        admin_username,
        ",".join(changed) if changed else "none",
    )
    yield


app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)
app.state.started_at = datetime.now()
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    session_cookie="capital_saas_session",
    same_site="lax",
    https_only=settings.app_env == "production",
    max_age=60 * 60 * 12,
)
app.add_middleware(RateLimitMiddleware)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.middleware("http")
async def runtime_settings_middleware(request: Request, call_next):
    request.state.site_name = settings.app_name
    request.state.company_name = "沪上银"
    request.state.unread_notifications = 0
    request.state.force_password_change = False
    try:
        with SessionLocal() as db:
            request.state.site_name = get_setting(db, "site_name", settings.app_name)
            request.state.company_name = get_setting(db, "company_name", "沪上银")
            user_id=request.session.get("user_id")
            if user_id:
                from db.models import InternalNotification,User
                active_user=db.get(User,int(user_id));request.state.force_password_change=bool(active_user and active_user.force_password_change)
                request.state.unread_notifications=db.query(InternalNotification).filter(
                    InternalNotification.user_id==int(user_id),InternalNotification.status=="unread").count()
    except Exception:
        pass
    response=await call_next(request)
    session=request.scope.get("session",{});actor_user_id=session.get("user_id");actor_customer_id=session.get("customer_id")
    if settings.security_audit_enabled and request.method in {"POST","PUT","PATCH","DELETE"} and response.status_code<400:
        path=request.url.path
        should_audit=(path.startswith("/admin/") and path not in {"/admin/notifications/read-all"}) or path.startswith("/client/confirmations/")
        if should_audit:
            try:
                from services.audit_service import write_audit_log
                ids=[int(x) for x in path.split("/") if x.isdigit()]
                high=any(x in path for x in ["order","payment","refund","cancel","delete","backup","users","settings","approve","reject","assign"])
                with SessionLocal() as db:write_audit_log(db,f"http_{request.method.lower()}",path.split("/")[2] if len(path.split("/"))>2 else "route",ids[0] if ids else None,user_id=int(actor_user_id) if actor_user_id else None,customer_id=int(actor_customer_id) if actor_customer_id else None,actor_type="admin_user" if actor_user_id else "customer",request=request,risk_level="high" if high else "medium",commit=True)
            except Exception:logger.exception("通用审计日志写入失败 path=%s",path)
    return response

app.include_router(auth.router)
app.include_router(assessment.router)
app.include_router(payment.router)
app.include_router(report.router)
app.include_router(admin.router)
app.include_router(events.router)
app.include_router(growth.router)
app.include_router(sales.router)
app.include_router(advisor.router)
app.include_router(diligence.router)
app.include_router(delivery.router)
app.include_router(organization.router)
app.include_router(client_portal.router)
app.include_router(notifications.router)
app.include_router(security.router)
app.include_router(release.router)
app.include_router(pilot.router)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code == 401:
        if request.url.path.startswith("/admin"):
            target = quote(request.url.path, safe="/")
            return RedirectResponse(url=f"/login?next={target}", status_code=303)
        if request.url.path.startswith("/client"):
            return templates.TemplateResponse(request=request,name="client_notice.html",
                context={"customer":None,"title":"客户门户登录已失效","message":str(exc.detail)},status_code=401)
        return templates.TemplateResponse(
            request=request,
            name="unauthorized.html",
            context={"message": str(exc.detail)},
            status_code=401,
        )
    if exc.status_code == 403:
        if request.url.path.startswith("/client"):
            return templates.TemplateResponse(request=request,name="client_notice.html",
                context={"customer":None,"title":"无法访问","message":str(exc.detail)},status_code=403)
        return templates.TemplateResponse(
            request=request,
            name="error_403.html",
            context={"message": str(exc.detail)},
            status_code=403,
        )
    if exc.status_code == 429:
        return templates.TemplateResponse(request=request,name="error_429.html",context={"message":str(exc.detail)},status_code=429)
    if exc.status_code == 404:
        return templates.TemplateResponse(
            request=request,
            name="error_404.html",
            context={"message": str(exc.detail)},
            status_code=404,
        )
    return templates.TemplateResponse(
        request=request,
        name="error_500.html",
        context={"message": str(exc.detail)},
        status_code=exc.status_code,
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    request_id=uuid.uuid4().hex
    logger.exception("未处理异常 request_id=%s path=%s",request_id, request.url.path)
    try:
        from services.event_service import track_event
        with SessionLocal() as db:track_event(db,"unhandled_exception",data={"request_id":request_id,"path":request.url.path,"error":type(exc).__name__})
    except Exception:pass
    return templates.TemplateResponse(
        request=request,
        name="error_500.html",
        context={"message": "系统暂时无法处理该请求，请稍后重试。", "request_id":request_id},
        status_code=500,
    )


@app.get("/health")
def health_check():
    from api.security import health_payload
    with SessionLocal() as db:return health_payload(db)

@app.get("/healthz")
def healthz():return health_check()

@app.get("/ready")
def ready():return health_check()
