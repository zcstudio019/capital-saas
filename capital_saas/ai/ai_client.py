import json
from typing import Any

from core.config import settings
from utils.logger import logger


class AIClient:
    """统一 AI 调用入口。默认 Mock，OpenAI 调用失败时自动降级。"""

    def __init__(self, db=None):
        self.api_key = settings.openai_api_key
        self.base_url = settings.openai_base_url
        self.model = settings.openai_model
        self.mode = settings.ai_mode


    def generate_json(self, prompt: str, data: dict) -> dict[str, Any]:
        fallback = self._mock_result(prompt, data)
        if self.mode != "openai" or not self.api_key:
            return fallback
        try:
            from openai import OpenAI

            client_kwargs = {"api_key": self.api_key}
            if self.base_url:
                client_kwargs["base_url"] = self.base_url
            client = OpenAI(**client_kwargs)
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "你是严谨的中国中小企业融资顾问。只返回合法JSON，不承诺贷款必然获批。",
                    },
                    {
                        "role": "user",
                        "content": f"{prompt}\n\n企业数据：{json.dumps(data, ensure_ascii=False)}",
                    },
                ],
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content or "{}"
            payload = json.loads(content)
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
