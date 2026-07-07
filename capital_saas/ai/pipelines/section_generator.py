import json
from pathlib import Path
from typing import Any

from ai.ai_client import AIClient
from core.config import BASE_DIR
from db.models import AIGenerationLog


SECTION_PROMPTS = [
    ("企业整体评分", "overall_score_prompt.txt"),
    ("商业模式诊断", "business_model_prompt.txt"),
    ("财务健康体检", "financial_health_prompt.txt"),
    ("SWOT综合研判", "swot_prompt.txt"),
    ("融资策略", "financing_strategy_prompt.txt"),
    ("资金投放策略", "capital_allocation_prompt.txt"),
    ("贷后管理", "post_loan_management_prompt.txt"),
    ("长期资本路径", "long_term_capital_path_prompt.txt"),
    ("财商诊断", "financial_literacy_prompt.txt"),
    ("行动建议", "action_plan_prompt.txt"),
]

REQUIRED_KEYS = (
    "section_title", "conclusion", "key_findings", "bank_view",
    "boss_action", "next_steps", "risk_warning", "upsell_hint",
)


def normalize_section(section: dict[str, Any], title: str) -> dict[str, Any]:
    key_findings = section.get("key_findings") or section.get("key_issues") or []
    boss_action = section.get("boss_action") or section.get("owner_actions") or []
    next_steps = section.get("next_steps") or section.get("next_actions") or []
    normalized = {
        "section_title": section.get("section_title") or section.get("title") or title,
        "conclusion": section.get("conclusion") or "本章需结合企业经营数据进一步核验。",
        "key_findings": key_findings if isinstance(key_findings, list) else [str(key_findings)],
        "bank_view": section.get("bank_view") or "银行将结合流水、纳税、征信与还款来源综合判断。",
        "boss_action": boss_action if isinstance(boss_action, list) else [str(boss_action)],
        "next_steps": next_steps if isinstance(next_steps, list) else [str(next_steps)],
        "risk_warning": section.get("risk_warning") or "本结论不构成授信承诺，实际结果以金融机构审批为准。",
        "upsell_hint": section.get("upsell_hint") or "如需进一步落地，可升级银行匹配或融资结构优化服务。",
        "details": section.get("details") or {},
    }
    # 兼容 Phase 1-5 模板和测试。
    normalized.update({
        "title": normalized["section_title"],
        "key_issues": normalized["key_findings"],
        "owner_actions": normalized["boss_action"],
        "next_actions": normalized["next_steps"],
    })
    return normalized


class SectionGenerator:
    def __init__(self, db, report_id: int, assessment_id: int):
        self.db = db
        self.report_id = report_id
        self.assessment_id = assessment_id
        self.client = AIClient(db)

    def _prompt(self, file_name: str) -> str:
        return (BASE_DIR / "prompts" / "report_sections" / file_name).read_text(encoding="utf-8")

    def generate(
        self,
        context: dict[str, Any],
        baseline_sections: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        generated = []
        for index, (title, prompt_name) in enumerate(SECTION_PROMPTS):
            baseline = baseline_sections[index] if index < len(baseline_sections) else {}
            status = "mock"
            error = ""
            section = normalize_section(baseline, title)
            try:
                if self.client.mode == "openai" and self.client.api_key:
                    payload = self.client.generate_json(
                        self._prompt(prompt_name),
                        {**context, "section_name": title, "baseline_section": section},
                    )
                    if all(payload.get(key) for key in REQUIRED_KEYS):
                        section = normalize_section(payload, title)
                        status = "success" if payload.get("provider") == "openai" else "fallback"
                    else:
                        status = "fallback"
                        error = "AI输出缺少必需结构字段"
            except Exception as exc:  # 主流程必须可降级
                status = "fallback"
                error = f"{type(exc).__name__}: {exc}"
            self.db.add(AIGenerationLog(
                assessment_id=self.assessment_id,
                report_id=self.report_id,
                section_name=title,
                ai_mode=self.client.mode,
                model_name=self.client.model,
                prompt_name=prompt_name,
                status=status,
                error_message=error,
                token_usage_json=json.dumps({}, ensure_ascii=False),
            ))
            generated.append(section)
        self.db.flush()
        return generated
