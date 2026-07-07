"""Validate DeepSeek/OpenAI runtime configuration without making an API request."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config import settings


def main() -> int:
    checks = {
        "AI_MODE=openai": settings.ai_mode == "openai",
        "OPENAI_BASE_URL=https://api.deepseek.com": (
            settings.openai_base_url == "https://api.deepseek.com"
        ),
        "OPENAI_MODEL=deepseek-v4-flash": (
            settings.openai_model == "deepseek-v4-flash"
        ),
        "OPENAI_API_KEY 已从环境配置": bool(settings.openai_api_key),
    }
    print(f"ai_mode={settings.ai_mode}")
    print(f"openai_model={settings.openai_model}")
    print(f"openai_base_url_configured={bool(settings.openai_base_url)}")
    print(f"openai_api_key_configured={bool(settings.openai_api_key)}")
    for label, passed in checks.items():
        print(f"[{'PASS' if passed else 'FAIL'}] {label}")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())