"""公共前台桌面/手机导航布局专项回归。"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEST_DB = ROOT / "phase_navigation_layout_test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
os.environ["AI_MODE"] = "mock"
os.environ["APP_ENV"] = "development"
if TEST_DB.exists():
    TEST_DB.unlink()
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from main import app


def run() -> None:
    with TestClient(app) as client:
        response = client.get("/assessment")
        assert response.status_code == 200
        html = response.text

        assert html.count('class="public-header"') == 1
        assert html.count('class="public-desktop-nav"') == 1
        assert html.count('class="public-mobile-toggle"') == 1
        assert html.count('class="public-mobile-nav"') == 1
        assert html.count('{% include "components/public_header.html" %}') == 0

        desktop_match = re.search(
            r'<nav class="public-desktop-nav"[^>]*>(.*?)</nav>', html, re.S,
        )
        assert desktop_match
        desktop = desktop_match.group(1)
        for label in ("免费测评", "产品服务", "客户登录", "管理后台"):
            assert desktop.count(label) == 1
        assert "员工入口" not in desktop
        assert 'href="/client/login"' in desktop
        assert 'href="/admin/login"' in desktop

        mobile_match = re.search(
            r'<nav id="public-mobile-navigation"[^>]*>(.*?)</nav>', html, re.S,
        )
        assert mobile_match
        mobile = mobile_match.group(1)
        assert all(label in mobile for label in ("免费测评", "产品服务", "客户登录"))
        assert "管理后台" not in mobile and "员工入口" not in mobile

    css = (ROOT / "static/css/style.css").read_text(encoding="utf-8")
    base = (ROOT / "templates/base.html").read_text(encoding="utf-8")
    assessment = (ROOT / "templates/assessment_form.html").read_text(encoding="utf-8")

    assert base.count('include "components/public_header.html"') == 1
    assert "public-nav-layout" in base
    assert "public_header.html" not in assessment
    assert "@media(max-width:768px)" in css
    assert "@media(min-width:769px)" in css
    assert ".public-desktop-nav{display:none!important}" in css
    assert ".public-mobile-toggle{display:inline-flex!important}" in css
    assert ".public-mobile-toggle,\n  .public-mobile-nav{display:none!important}" in css
    assert ".public-header{height:74px}" in css
    assert ".public-header-inner" in css and "align-items:center" in css
    assert ".assessment-page-hero{padding:54px 0 48px}" in css
    print("PUBLIC_NAV_LAYOUT_OK")


if __name__ == "__main__":
    run()
