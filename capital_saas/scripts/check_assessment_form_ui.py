"""企业资本健康测评表 UI 结构专项检查。"""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "templates" / "assessment_form.html"
FIELDS = ROOT / "templates" / "components" / "assessment_form_fields.html"
CSS = ROOT / "static" / "css" / "assessment-form.css"
JS = ROOT / "static" / "js" / "assessment-form.js"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run() -> None:
    page = PAGE.read_text(encoding="utf-8")
    fields = FIELDS.read_text(encoding="utf-8")
    css = CSS.read_text(encoding="utf-8")
    script = JS.read_text(encoding="utf-8")
    markup = f"{page}\n{fields}"

    require("assessment-form.css" in page, "测评页未加载独立样式文件")
    require("assessment-form.js" in page, "测评页未加载独立交互脚本")
    require('class="assessment-form"' in page, "缺少 assessment-form 根组件")
    require('class="assessment-section"' in fields, "缺少 assessment-section 区块")
    require("assessment-section-header" in fields, "缺少统一的区块标题组件")
    require("assessment-grid" in fields, "缺少统一字段网格")
    require("form-field" in fields and "form-control" in fields, "字段未使用统一组件")

    labels_with_units = [
        "经营年限（年）",
        "当前员工人数（人）",
        "近12个月营业收入（元）",
        "近12个月净利润率（%）",
        "近6个月月均经营性现金流入（元）",
        "当前有息负债总额（元）",
        "一年内到期的短期负债（元）",
        "平均应收账款回款周期（天）",
        "本次计划融资金额（元）",
    ]
    for label in labels_with_units:
        require(label in fields, f"关键字段单位未并入标题：{label}")
    require("field-unit" not in markup, "仍存在单位单独占行的 field-unit 节点")

    require('data-checkbox-group="funding-purpose"' in fields, "融资用途未使用统一复选组件")
    require('data-checkbox-group="collateral"' in fields, "抵押物未使用统一复选组件")
    require(fields.count('class="checkbox-item"') >= 3, "复选项未使用 checkbox-item")
    require("assessment-dual-groups" in fields, "两个大复选模块未使用双列容器")
    require('value="暂无抵押物"' not in fields or "data-collateral-option" in fields, "抵押物互斥选项缺少交互标记")
    require('input.value === "暂无抵押物"' in script, "缺少“暂无抵押物”互斥逻辑")
    require("is-selected" in script, "缺少复选项兼容选中态")

    require("@media (max-width: 1024px)" in css, "缺少平板端媒体查询")
    require("@media (max-width: 680px)" in css, "缺少手机端媒体查询")
    require("grid-template-columns: 1fr" in css, "手机端未切换为单列")
    require("overflow-x: clip" in css or "overflow-x: hidden" in css, "缺少页面横向溢出防护")
    require(".checkbox-group {" in css, "未重置 fieldset 组件")
    checkbox_css = css.split(".checkbox-group {", 1)[1].split("}", 1)[0]
    for property_name in ("margin:", "padding:", "border:", "min-width:"):
        require(property_name in checkbox_css, f"fieldset 重置缺少 {property_name}")

    fieldsets = re.findall(r"<fieldset\b([^>]*)>", fields)
    require(fieldsets, "未找到复选字段组")
    require(all("checkbox-group" in attrs for attrs in fieldsets), "存在未使用统一样式的原生 fieldset")
    require("novalidate" in page, "未启用统一中文错误提示")
    require("form-error" in fields and "has-error" in css, "错误状态组件不完整")
    require("font-size: 16px" in css, "移动端输入字号不足，可能触发页面缩放")

    controls = re.findall(r"<(?:input|select|textarea)\b([^>]*)>", fields)
    named_controls = [attrs for attrs in controls if re.search(r"\bname=", attrs) and "type=\"checkbox\"" not in attrs]
    require(all(re.search(r"\bid=", attrs) for attrs in named_controls), "存在没有 id 的普通表单控件")

    print("ASSESSMENT_FORM_UI_CHECK_OK")


if __name__ == "__main__":
    run()
