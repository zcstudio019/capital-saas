"""检查最近一份企业资本健康体检报告的结构、权限与客户可见文本。"""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from core.capital_health_report import build_capital_health_report
from db.database import SessionLocal
from db.models import Report
from main import app


FORBIDDEN = [
    r"\{\s*['\"]", r"\[\s*\{", r"\bmedium\b", r"\bhigh\b", r"\blow\b",
    r"\bproduct_code\b", r"\bmatch_score\b", r"\bowner\b", r"\bactions\b",
    r"\boutcome\b", r"\bNone\b", r"\bnull\b", r"\bundefined\b",
    r"填写说明", r"内部使用说明", r"定价策略", r"转化路径",
]


def run() -> None:
    with SessionLocal() as db:
        latest = db.query(Report).order_by(Report.id.desc()).first()
        if not latest:
            raise SystemExit("未找到可检查的报告")
        payload = build_capital_health_report(db, latest.assessment, admin_override=True)
        assert payload["title"] == "企业资本健康体检报告"
        assert len(payload["dimensions"]) == 8
        assert payload["warnings"]
        assert all(dimension["items"] for dimension in payload["dimensions"])
        assert {"body_unlocked", "structure_unlocked"} <= payload["entitlements"].keys()
        assessment_id = latest.assessment_id

    with TestClient(app) as client:
        login = client.post(
            "/login",
            data={"username": "admin", "password": "admin123", "next_url": "/admin"},
            follow_redirects=False,
        )
        if login.status_code != 303:
            raise SystemExit("无法使用管理员账号渲染最近报告")
        pages = [
            client.get(f"/report/{assessment_id}"),
            client.get(f"/report/{assessment_id}/print"),
        ]
        for page in pages:
            assert page.status_code == 200
            visible = re.sub(r"<(style|script)\b[^>]*>.*?</\1>", " ", page.text, flags=re.I | re.S)
            text = re.sub(r"<[^>]+>", " ", visible)
            for expected in ("企业资本健康体检报告", "八维雷达评分概览", "风险预警", "分项检查"):
                assert expected in text
            for pattern in FORBIDDEN:
                assert not re.search(pattern, text, re.I), pattern
    print("CAPITAL_HEALTH_REPORT_OK")


if __name__ == "__main__":
    run()
