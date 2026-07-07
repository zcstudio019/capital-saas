"""Scan user-facing source files for likely garbled text.

This is an advisory check: findings are printed, but the process exits successfully.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN_DIRS = ("templates", "static", "api", "services", "core")
TEXT_SUFFIXES = {
    ".html", ".htm", ".css", ".js", ".json", ".py", ".txt", ".md", ".svg",
}
LITERAL_MARKERS = ("????", "???", "??", "？？", "�", "Ã", "ä¸", "å", "æ")
EMOJI_RE = re.compile(
    "[\\U0001F300-\\U0001FAFF\\u2600-\\u27BF]"
)


def scan_file(path: Path) -> list[tuple[int, str, str]]:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        return [(exc.start, "非 UTF-8 编码", str(exc))]

    findings: list[tuple[int, str, str]] = []
    for line_no, line in enumerate(text.splitlines(), 1):
        markers: list[str] = []
        for marker in LITERAL_MARKERS:
            if marker in line and not any(marker in longer for longer in markers):
                markers.append(marker)
        emoji = EMOJI_RE.search(line)
        if emoji:
            markers.append(f"emoji {emoji.group(0)!r}")
        if markers:
            findings.append((line_no, ", ".join(markers), line.strip()))
    return findings


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    total = 0
    for directory in SCAN_DIRS:
        base = ROOT / directory
        if not base.exists():
            continue
        for path in sorted(p for p in base.rglob("*") if p.is_file()):
            if path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            for line_no, marker, content in scan_file(path):
                total += 1
                relative = path.relative_to(ROOT)
                print(f"{relative}:{line_no}: [{marker}] {content}")
    print(f"扫描完成：发现 {total} 处可疑内容（仅提示，不影响启动）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())