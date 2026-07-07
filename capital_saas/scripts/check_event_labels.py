"""Validate that technical event codes are safe for business-facing display."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.display_labels import EVENT_LABELS, get_event_label

EXPECTED = {
    "landing_page_viewed": "落地页已查看",
    "ab_assigned": "A/B测试已分组",
    "notification_job_created": "通知任务已创建",
    "sales_workbench_viewed": "销售工作台已查看",
    "notification_template_deleted": "通知模板已删除",
    "customer_logged_in": "客户已登录",
    "unknown_event_test": "系统事件",
}
DIRECT_EVENT_OUTPUT = re.compile(r"{{\s*(?!filters\.)\w+\.event_type\s*}}")


def main() -> int:
    failures = []
    for code, expected in EXPECTED.items():
        actual = get_event_label(code)
        if actual != expected:
            failures.append(f"{code}: expected={expected!r}, actual={actual!r}")
        if "_" in actual:
            failures.append(f"{code}: label contains underscore: {actual!r}")

    for code in EVENT_LABELS:
        label = get_event_label(code)
        if "_" in label:
            failures.append(f"{code}: mapped label contains underscore: {label!r}")

    for template in (ROOT / "templates").rglob("*.html"):
        text = template.read_text(encoding="utf-8")
        if DIRECT_EVENT_OUTPUT.search(text):
            failures.append(f"{template.relative_to(ROOT)}: event_type is rendered without event_label")

    if failures:
        print("\n".join(failures))
        return 1
    print("EVENT_LABELS_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
