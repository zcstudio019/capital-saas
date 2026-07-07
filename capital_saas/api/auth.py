from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from db.database import get_db
from services.auth_service import authenticate_user


router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = "/admin"):
    if request.session.get("user_id"):
        return RedirectResponse(url=next if next.startswith("/") else "/admin", status_code=303)
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
    user = authenticate_user(db, username.strip(), password, request)
    if not user:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"next_url": next_url, "error": "用户名或密码错误"},
            status_code=400,
        )
    request.session.clear()
    request.session["user_id"] = user.id
    request.session["username"] = user.username
    request.session["role"] = user.role
    request.session["session_version"] = user.session_version or 1
    destination = next_url if next_url.startswith("/") else "/admin"
    return RedirectResponse(url=destination, status_code=303)


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)
