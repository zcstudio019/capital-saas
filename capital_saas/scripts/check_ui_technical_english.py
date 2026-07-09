"""Scan likely user-visible UI text for raw technical English codes.

This is a reporting helper. It does not fail the process; it prints suspicious
locations so templates can be reviewed without changing API values or routes.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN_DIRS = [ROOT / "templates", ROOT / "static", ROOT / "api", ROOT / "services"]

SNAKE_RE = re.compile(r"\b[a-z]+_[a-z0-9_]+\b")
CODE_RE = re.compile(
    r"\b(299_report|699_bank_match|1999_structure_plan|paid_order|project_disbursed|"
    r"fixed_amount|percentage|super_admin|sales_manager|consultant_manager|"
    r"notification_job(?:_created)?|landing_page(?:_viewed)?|ab_assigned|advisor_bookings|"
    r"mock|imported|manual|pending|submitted|cancelled|refunded)\b"
)
TITLE_RE = re.compile(
    r"\b(Advisor Bookings|Sales Workbench|Growth Dashboard|Delivery Dashboard|"
    r"Client Portal|System Health|Production Checklist)\b"
)

ALLOW_LINE_PATTERNS = [
    re.compile(r"\b(def|class|from|import|return|if|elif|for|while)\b"),
    re.compile(r"@router\.|Depends\(|\.filter\(|\.query\(|mapped_column|ForeignKey"),
    re.compile(r"\b(name|value|class|id|href|action|src|data-[\w-]+)="),
    re.compile(r"\{\%|\{\#|type=\"hidden\"|input type=\"hidden\""),
    re.compile(r"templates\.|TemplateResponse|RedirectResponse|HTTPException"),
    re.compile(r"^[\s\w.]+="),
]


def looks_user_visible(line: str, path: Path) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if path.suffix == ".py":
        # API/service modules mostly contain internal keys, route handlers, and
        # data contracts. Only flag obvious HTML fragments returned from Python.
        if not re.search(r"</?[a-zA-Z][\w:-]*(?:\s|>|/>)", stripped):
            return False
    if path.suffix == ".js":
        # Ignore implementation code and label dictionaries; they are not raw
        # visible text. Literal DOM text is still scanned below.
        js_code_prefixes = (
            "const ",
            "let ",
            "var ",
            "if ",
            "for ",
            "while ",
            "fetch(",
            "document.",
            "window.",
            "button.",
            "body.",
            "Object.",
            "nodes.",
            "return ",
            "try ",
            "catch ",
            "setTimeout",
        )
        if stripped.startswith(js_code_prefixes) or ":" in stripped and re.search(r"^[\"']?[\w-]+[\"']?\s*:", stripped):
            return False
    if "{{" in stripped and not re.search(r">\s*(?:[a-z]+_[a-z0-9_]+|299_report|699_bank_match|1999_structure_plan|mock|imported|manual|pending|submitted|cancelled|refunded)\s*<", stripped):
        return False
    if any(pattern.search(stripped) for pattern in ALLOW_LINE_PATTERNS):
        # A line that also has a literal option body is still visible.
        return bool(re.search(r">\s*[a-z0-9_./-]+\s*<", stripped))
    if stripped.startswith(("#", "//", "/*", "*")):
        return False
    return True


def main() -> None:
    findings: list[tuple[Path, int, str]] = []
    for folder in SCAN_DIRS:
        for path in folder.rglob("*"):
            if path.suffix not in {".html", ".js", ".py"}:
                continue
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except UnicodeDecodeError:
                continue
            for lineno, line in enumerate(lines, 1):
                if not looks_user_visible(line, path):
                    continue
                if SNAKE_RE.search(line) or CODE_RE.search(line) or TITLE_RE.search(line):
                    findings.append((path.relative_to(ROOT), lineno, line.strip()))

    if not findings:
        print("UI_TECHNICAL_ENGLISH_SCAN_OK")
        return
    for path, lineno, text in findings:
        print(f"{path}:{lineno}: {text[:220]}")


if __name__ == "__main__":
    main()
