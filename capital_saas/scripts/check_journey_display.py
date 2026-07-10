"""Detect technical payload output in rendered customer journey HTML."""

from __future__ import annotations

import argparse
import html
import re
from pathlib import Path


FORBIDDEN_VISIBLE_TOKENS = (
    "user_id", "order_id", "product_code", "template_key", "operator", "channel",
    "notification_job", "in_app", "299_report",
)
_NON_VISIBLE_BLOCK = re.compile(r"<(?:style|script)\b[^>]*>.*?</(?:style|script)>", re.IGNORECASE | re.DOTALL)
_TAG = re.compile(r"<[^>]+>")


def visible_text(value: str) -> str:
    return html.unescape(_TAG.sub(" ", _NON_VISIBLE_BLOCK.sub(" ", value)))


def find_journey_display_issues(value: str) -> list[str]:
    text = visible_text(value)
    lowered = text.lower()
    issues = [token for token in FORBIDDEN_VISIBLE_TOKENS if token in lowered]
    if "{" in text or "}" in text:
        issues.append("raw_json_structure")
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="检查客户旅程页面是否泄漏技术字段")
    parser.add_argument("paths", nargs="+", help="渲染后的客户旅程 HTML 文件")
    args = parser.parse_args()
    failures: list[str] = []
    for raw_path in args.paths:
        path = Path(raw_path)
        if not path.exists():
            failures.append(f"{path}: file not found")
            continue
        issues = find_journey_display_issues(path.read_text(encoding="utf-8"))
        if issues:
            failures.append(f"{path}: {', '.join(issues)}")
    if failures:
        print("JOURNEY_DISPLAY_CHECK_FAILED")
        print("\n".join(failures))
        return 1
    print("JOURNEY_DISPLAY_CHECK_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
