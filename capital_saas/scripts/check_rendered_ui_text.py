"""Render core pages and report visible technical English codes.

Uses FastAPI TestClient instead of a browser so it is safe for CI and local
smoke runs. The check strips tags, scripts, styles, URLs, and attributes before
matching visible text.
"""

from __future__ import annotations

import re
import sys
from html import unescape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from db.database import SessionLocal  # noqa: E402
from db.models import User  # noqa: E402
from main import app  # noqa: E402
from services.auth_service import hash_password  # noqa: E402

ADMIN_PAGES = [
    "/admin", "/admin/leads", "/admin/orders", "/admin/growth",
    "/admin/commissions", "/admin/commission-rules", "/admin/script-templates",
    "/admin/advisor-bookings",
]
SALES_PAGES = ["/sales/workbench"]
FORBIDDEN = [
    "paid_order", "project_disbursed", "fixed_amount", "percentage",
    "299_report", "699_bank_match", "1999_structure_plan",
    "landing_page_viewed", "notification_job_created", "Advisor Bookings",
    "super_admin", "sales_manager",
]


def ensure_sales_user() -> None:
    with SessionLocal() as db:
        user = db.query(User).filter(User.username == "ui_text_sales").first()
        if not user:
            user = User(
                username="ui_text_sales",
                password_hash=hash_password("ui_text_sales123"),
                display_name="销售展示检查",
                role="sales",
                is_active=True,
                session_version=1,
            )
            db.add(user)
        else:
            user.role = "sales"
            user.is_active = True
        db.commit()


def visible_text(html: str) -> str:
    html = re.sub(r"<(script|style)\b.*?</\1>", " ", html, flags=re.I | re.S)
    html = re.sub(r"https?://\S+|/[a-z0-9_./?=&%-]+", " ", html, flags=re.I)
    html = re.sub(r"<[^>]+>", " ", html)
    html = unescape(html)
    return re.sub(r"\s+", " ", html)


def login(client: TestClient, username: str, password: str) -> None:
    response = client.post(
        "/login",
        data={"username": username, "password": password, "next_url": "/admin"},
        follow_redirects=False,
    )
    if response.status_code != 303:
        raise RuntimeError(f"登录失败：{username}")


def scan_pages(client: TestClient, pages: list[str], label: str) -> list[str]:
    findings: list[str] = []
    for path in pages:
        response = client.get(path)
        if response.status_code >= 400:
            findings.append(f"{label} {path}: HTTP {response.status_code}")
            continue
        text = visible_text(response.text)
        for token in FORBIDDEN:
            if token in text:
                findings.append(f"{label} {path}: {token}")
    return findings


def main() -> None:
    ensure_sales_user()
    findings: list[str] = []
    with TestClient(app) as client:
        login(client, "admin", "admin123")
        findings.extend(scan_pages(client, ADMIN_PAGES, "admin"))
    with TestClient(app) as client:
        login(client, "ui_text_sales", "ui_text_sales123")
        findings.extend(scan_pages(client, SALES_PAGES, "sales"))

    if findings:
        for item in findings:
            print(item)
        return
    print("RENDERED_UI_TEXT_CHECK_OK")


if __name__ == "__main__":
    main()
