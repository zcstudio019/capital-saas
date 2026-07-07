import json
from typing import Any

from core.config import settings
from utils.logger import logger


class AIClient:
    """统一 AI 调用入口。默认 Mock，OpenAI 调用失败时自动降级。"""

    def __init__(self, db=None):
        self.api_key = settings.openai_api_key
        self.model = settings.openai_model
        self.mode = settings.ai_mode
        if db is not None:
            from services.settings_service import get_setting

            self.model = get_setting(db, "openai_model", self.model)
            self.mode = get_setting(db, "ai_mode", self.mode).lower()

    def generate_json(self, prompt: str, data: dict) -> dict[str, Any]:
        fallback = self._mock_result(prompt, data)
        if self.mode != "openai" or not self.api_key:
            return fallback
        try:
            from openai import OpenAI

            client = OpenAI(api_key=self.api_key)
            response = client.responses.create(
                model=self.model,
                instructions=(
                    "你是严谨的中国中小企业融资顾问。只返回合法JSON，不承诺贷款必然获批。"
                ),
                input=f"{prompt}\n\n企业数据：{json.dumps(data, ensure_ascii=False)}",
            )
            payload = json.loads(response.output_text)
            if isinstance(payload, dict):
                payload.setdefault("provider", "openai")
                payload.setdefault("model", self.model)
                return payload
        except Exception as exc:
            fallback["fallback_reason"] = type(exc).__name__
            logger.warning("AI调用降级 model=%s reason=%s", self.model, type(exc).__name__)
        return fallback

    def _mock_result(self, prompt: str, data: dict) -> dict[str, Any]:
        return {
            "provider": "mock",
            "model": self.model,
            "prompt_received": bool(prompt),
            "company": data.get("company_name", "企业"),
            "summary": "当前使用确定性规则与顾问模板生成内容。",
        }
