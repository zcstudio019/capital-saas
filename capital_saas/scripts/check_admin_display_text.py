"""Advisory scan for technical codes rendered by admin templates."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
OUTPUT_RE = re.compile(r"{{\s*(.*?)\s*}}")
TECH_FIELDS = (
    "current_user.username", "current_user.role", "user.role", "event.event_type",
    "product_code", "nav.key", "module.key", "route.name", "task.status", "task.priority",
)
SAFE_FILTERS = {
    "current_user.role": ("role_label", "user_display_name", "zh"),
    "user.role": ("role_label", "user_display_name", "zh"),
    "event.event_type": ("event_label",),
    "product_code": ("product_label",),
    "nav.key": ("nav_label",),
    "module.key": ("nav_label",),
    "route.name": ("nav_label",),
    "task.status": ("task_status_label", "zh"),
    "task.priority": ("task_priority_label", "zh"),
}
ROLE_CODES = ("super_admin", "city_manager", "sales_manager", "consultant_manager")
PRODUCT_CODES = ("high_ticket_consulting", "299_report", "699_bank_match", "1999_structure_plan")


def _is_internal_value(line: str, expression: str) -> bool:
    if ("task.status" in expression or "task.priority" in expression) and (
        "==" in expression or "!=" in expression or "class=" in line
    ):
        return True
    if "product_code" in expression and re.search(
        r'<(?:input|select)[^>]*name=["\'](?:target_)?product_code["\']', line
    ):
        return True
    return False


def main() -> int:
    findings: list[str] = []
    paths = sorted(TEMPLATES.glob("admin*.html"))
    sales = TEMPLATES / "sales_workbench.html"
    if sales.exists():
        paths.append(sales)

    for path in paths:
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for expression in OUTPUT_RE.findall(line):
                for field in TECH_FIELDS:
                    if field not in expression:
                        continue
                    if field == "current_user.username" and "user_display_name" in expression:
                        continue
                    if _is_internal_value(line, expression):
                        continue
                    allowed = SAFE_FILTERS.get(field, ())
                    if not any(filter_name in expression for filter_name in allowed):
                        findings.append(f"{path.relative_to(ROOT)}:{line_no}: {{ {expression} }}")
                if any(code in expression for code in ROLE_CODES + PRODUCT_CODES):
                    if not any(name in expression for name in ("role_label", "product_label", "zh")):
                        findings.append(f"{path.relative_to(ROOT)}:{line_no}: {{ {expression} }}")

    if findings:
        print("发现可能直出的技术字段：")
        print("\n".join(dict.fromkeys(findings)))
    else:
        print("ADMIN_DISPLAY_SCAN_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())