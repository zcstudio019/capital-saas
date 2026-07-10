"""Fail when a customer-facing report contains internal English enum values."""

from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path


FORBIDDEN_REPORT_ENUMS = (
    "medium", "high", "low", "pending", "approved", "rejected", "strong", "weak",
    "normal", "excellent", "unknown", "good", "poor", "pass", "fail", "up", "down",
    "stable", "critical",
)
_ENUM_PATTERN = re.compile(
    r"(?<![A-Za-z])(" + "|".join(FORBIDDEN_REPORT_ENUMS) + r")(?![A-Za-z])",
    re.IGNORECASE,
)
_NON_VISIBLE_BLOCK = re.compile(r"<(?:style|script)\b[^>]*>.*?</(?:style|script)>", re.IGNORECASE | re.DOTALL)
_TAG_PATTERN = re.compile(r"<[^>]+>")


def extract_report_text(path: str | Path) -> str:
    """Extract customer-visible text from an HTML or PDF report."""
    report_path = Path(path)
    if report_path.suffix.lower() == ".pdf":
        from pypdf import PdfReader

        return "\n".join(page.extract_text() or "" for page in PdfReader(str(report_path)).pages)

    content = report_path.read_text(encoding="utf-8")
    return visible_report_text(content)


def visible_report_text(text: str) -> str:
    return html.unescape(_TAG_PATTERN.sub(" ", _NON_VISIBLE_BLOCK.sub(" ", text)))


def find_forbidden_enums(text: str) -> list[str]:
    return sorted({match.group(1).lower() for match in _ENUM_PATTERN.finditer(text)})


def assert_report_chinese_only(text: str) -> None:
    forbidden = find_forbidden_enums(visible_report_text(text))
    if forbidden:
        raise AssertionError(f"report contains internal English enums: {', '.join(forbidden)}")


def _report_files(paths: list[str]) -> list[Path]:
    files: list[Path] = []
    for raw_path in paths:
        path = Path(raw_path)
        if path.is_dir():
            files.extend(item for item in path.rglob("*") if item.suffix.lower() in {".html", ".pdf"})
        else:
            files.append(path)
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description="检查客户报告是否包含英文内部枚举")
    parser.add_argument("paths", nargs="+", help="待扫描的报告 HTML/PDF 文件或目录")
    args = parser.parse_args()

    failures: list[str] = []
    for report_path in _report_files(args.paths):
        if not report_path.exists():
            failures.append(f"{report_path}: file not found")
            continue
        forbidden = find_forbidden_enums(extract_report_text(report_path))
        if forbidden:
            failures.append(f"{report_path}: {', '.join(forbidden)}")
    if failures:
        print("REPORT_CHINESE_ONLY_FAILED")
        print("\n".join(failures))
        return 1

    print("REPORT_CHINESE_ONLY_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
