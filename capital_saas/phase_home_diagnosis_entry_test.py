"""首页双诊断入口、统一路由与移动导航专项验收。"""
from __future__ import annotations
import os, re, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent
TEST_DB=ROOT / "phase_home_diagnosis_entry_test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
if TEST_DB.exists(): TEST_DB.unlink()
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from main import app

assert str(app.url_path_for("assessment_form")) == "/assessment"
assert str(app.url_path_for("cashflow_assessment_form")) == "/cashflow-assessment"
with TestClient(app) as client:
    response=client.get("/"); assert response.status_code == 200
    html=response.text
    assert "开始免费测评" in html and "企业资本健康测评" in html and "企业现金流诊断" in html
    assert html.count('href="http://testserver/assessment"') >= 3
    assert html.count('href="http://testserver/cashflow-assessment"') >= 2
    mobile=re.search(r'<nav id="public-mobile-navigation".*?</nav>', html, re.S).group(0)
    assert "企业资本健康测评" in mobile and "企业现金流诊断" in mobile
    assert "管理后台" not in mobile and "员工入口" not in mobile

for filename in ("index.html", "components/public_header.html"):
    source=(ROOT / "templates" / filename).read_text(encoding="utf-8")
    assert 'href="/assessment"' not in source and 'href="/cashflow-assessment"' not in source
print("HOME_DIAGNOSIS_ENTRY_OK")
