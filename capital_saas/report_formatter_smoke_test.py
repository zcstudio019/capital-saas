"""Regression checks for safe action-plan formatting."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.report_formatters import format_action_steps, normalize_report_action_steps


SAMPLE = {
    "30_days": {"负责人": "财务负责人", "动作": "统一资料口径", "目标": "完成授信准备"},
    "90_days": {"owner": "融资负责人", "action": "完成银行匹配", "goal": "形成申请包"},
    "180_days": {"负责人": "老板", "动作": "优化负债结构", "注意事项": "控制新增短债"},
    "365_days": {"owner": "老板", "action": "建立年度资本计划", "note": "每季度复盘"},
}


def assert_safe(steps):
    assert isinstance(steps, list) and steps
    for step in steps:
        assert set(step) == {"period", "owner", "action", "goal", "note"}
        assert not any(isinstance(value, (dict, list)) for value in step.values())
        rendered = "".join(step.values())
        assert "{'" not in rendered and "_days" not in rendered


def run():
    dict_steps = format_action_steps(SAMPLE)
    assert [step["period"] for step in dict_steps] == [
        "30天行动计划", "90天行动计划", "180天行动计划", "365天行动计划"
    ]
    assert dict_steps[0]["owner"] == "财务负责人"
    assert dict_steps[2]["note"] == "控制新增短债"
    assert_safe(dict_steps)

    list_steps = format_action_steps([
        {"period": "30天", "owner": "财务负责人", "action": "补充资料", "goal": "完成预审"}
    ])
    assert list_steps[0]["period"] == "30天行动计划"
    assert_safe(list_steps)

    json_steps = format_action_steps(
        '{"90_days":{"负责人":"融资负责人","动作":"提交申请","目标":"获得反馈"}}'
    )
    assert json_steps[0]["period"] == "90天行动计划"
    assert_safe(json_steps)

    python_repr_steps = format_action_steps(str(SAMPLE))
    assert len(python_repr_steps) == 4
    assert_safe(python_repr_steps)

    text_steps = format_action_steps("建议先补充资料，再申请银行授信")
    assert text_steps[0]["period"] == "行动建议"
    assert text_steps[0]["action"] == "建议先补充资料，再申请银行授信"
    assert_safe(text_steps)

    malformed_steps = format_action_steps("{'30_days': invalid}")
    assert malformed_steps[0]["action"] == "行动建议内容暂无法解析，请联系顾问核验。"
    assert_safe(malformed_steps)

    report = {"chapters": [{} for _ in range(9)] + [{"title": "行动建议", "action_plan": SAMPLE}]}
    normalize_report_action_steps(report)
    assert report["chapters"][9]["formatted_action_steps"] == dict_steps
    print("REPORT_FORMATTER_SMOKE_OK")


if __name__ == "__main__":
    run()