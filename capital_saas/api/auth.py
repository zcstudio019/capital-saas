from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from db.database import get_db
from db.models import User
from services.auth_service import authenticate_user, verify_password


router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))
BACKEND_LOGIN_ROLES = {"admin", "super_admin", "sales_manager", "sales", "consultant", "consultant_manager", "viewer"}


def _default_backend_home(role: str | None) -> str:
    return "/sales/workbench" if role == "sales" else "/admin"


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = "/admin"):
    if request.session.get("user_id"):
        return RedirectResponse(url=_default_backend_home(request.session.get("role")), status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"next_url": next, "error": ""},
    )


@router.post("/login", response_class=HTMLResponse)
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next_url: str = Form("/admin"),
    db: Session = Depends(get_db),
):
    candidate = db.query(User).filter(User.username == username.strip()).first()
    if candidate and not candidate.is_active and verify_password(password, candidate.password_hash):
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"next_url": next_url, "error": "账号已停用，请联系管理员"},
            status_code=403,
        )
    user = authenticate_user(db, username.strip(), password, request)
    if not user:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"next_url": next_url, "error": "用户名或密码错误"},
            status_code=400,
        )
    if user.role not in BACKEND_LOGIN_ROLES:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"next_url": next_url, "error": "客户请通过专属客户门户链接访问"},
            status_code=403,
        )
    request.session.clear()
    request.session["user_id"] = user.id
    request.session["username"] = user.username
    request.session["role"] = user.role
    request.session["session_version"] = user.session_version or 1
    destination = _default_backend_home(user.role)
    return RedirectResponse(url=destination, status_code=303)


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)
