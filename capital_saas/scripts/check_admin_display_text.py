"""Advisory scan for technical codes rendered by admin templates."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
OUTPUT_RE = re.compile(r"{{\s*(.*?)\s*}}")
TECH_FIELDS = {
    "current_user.username": ("user_display_name",),
    "current_user.role": ("role_label", "user_display_name", "zh"),
    "user.role": ("role_label", "user_display_name", "zh"),
    "event.event_type": ("event_label",),
    "product_code": ("product_label",),
    "nav.key": ("nav_label",), "module.key": ("nav_label",), "route.name": ("nav_label",),
    "task.status": ("task_status_label", "zh"), "task.priority": ("task_priority_label", "zh"),
    "trigger_event": ("commission_trigger_label",),
    "commission_type": ("commission_type_label", "commission_value_label"),
    "settlement_status": ("settlement_status_label",),
    ".scenario": ("script_scenario_label",), ".lead_grade": ("lead_grade_label",),
    ".is_active": ("boolean_label",),
    "x.path": ("landing_page_label",), "x.code": ("product_label",),
    "source_channel": ("source_channel_label",),
}
VISIBLE_TECH_CODES = (
    "299_report", "699_bank_match", "1999_structure_plan", "paid_order", "project_disbursed",
    "fixed_amount", "percentage", "sales_manager", "consultant_manager", "high_ticket_consulting",
    "/lp/rongzi", "/lp/cashflow", "/lp/bank", "/lp/boss", "variant_a", "variant_b",
    "free_result_conversion",
)


def _is_internal_value(line: str, expression: str) -> bool:
    if " if " in expression or "==" in expression or "!=" in expression or "|lower" in expression:
        return True
    if ("task.status" in expression or "task.priority" in expression) and (
        "==" in expression or "!=" in expression or "class=" in line
    ):
        return True
    if "product_code" in expression and re.search(
        r'<(?:input|select)[^>]*name=["\'](?:target_)?product_code["\']', line
    ):
        return True
    if any(field in expression for field in ("settlement_status", "is_active")) and (
        "==" in expression or "!=" in expression
    ):
        return True
    return False


def _visible_text(line: str) -> str:
    text = re.sub(r"{%.*?%}", "", line)
    text = re.sub(r"{{.*?}}", "", text)
    return re.sub(r"<[^>]+>", " ", text)


def main() -> int:
    findings: list[str] = []
    paths = sorted(TEMPLATES.glob("admin*.html"))
    sales = TEMPLATES / "sales_workbench.html"
    if sales.exists():
        paths.append(sales)

    for path in paths:
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for expression in OUTPUT_RE.findall(line):
                for field, safe_filters in TECH_FIELDS.items():
                    if field not in expression or _is_internal_value(line, expression):
                        continue
                    if not any(name in expression for name in safe_filters):
                        findings.append(f"{path.relative_to(ROOT)}:{line_no}: {{ {expression} }}")
            visible = _visible_text(line)
            if "?partner=" not in line and "?pilot=" not in line:
                for code in VISIBLE_TECH_CODES:
                    if code in visible:
                        findings.append(f"{path.relative_to(ROOT)}:{line_no}: visible code {code!r}")

    if findings:
        print("发现可能直出的技术字段：")
        print("\n".join(dict.fromkeys(findings)))
    else:
        print("ADMIN_DISPLAY_SCAN_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())