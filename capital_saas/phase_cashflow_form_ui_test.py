"""现金流诊断表中文文案、复选框 DOM 与响应式样式专项检查。"""
from html.parser import HTMLParser
from pathlib import Path
from types import SimpleNamespace
from jinja2 import Environment, FileSystemLoader
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from api.cashflow import _data
template = (ROOT / "templates" / "cashflow_assessment.html").read_text(encoding="utf-8")
styles = (ROOT / "static" / "css" / "style.css").read_text(encoding="utf-8")

for text in (
    "税息前利润（EBIT）", "应收账款周转天数（DSO）",
    "存货周转天数（DIO）", "应付账款周转天数（DPO）",
    "非刚性支出可压缩金额", "闲置资产可变现金额", "可延后项目",
):
    assert text in template
for naked in (">EBIT<", ">DSO（天）<", ">DIO（天）<", ">DPO（天）<"):
    assert naked not in template

class CheckboxStructureParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.stack=[]; self.checkbox_count=0; self.valid_count=0
    def handle_starttag(self, tag, attrs):
        values=dict(attrs); self.stack.append((tag, values.get("class", "")))
        if tag == "input" and values.get("type") == "checkbox":
            self.checkbox_count += 1
            tags=[item[0] for item in self.stack[:-1]]
            classes=" ".join(item[1] for item in self.stack[:-1])
            if "label" in tags and "checkbox-item" in classes: self.valid_count += 1
    def handle_endtag(self, tag):
        for index in range(len(self.stack)-1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]; break

environment=Environment(loader=FileSystemLoader(ROOT / "templates"))
environment.globals["url_for"] = lambda name, **kwargs: kwargs.get("path", "/")
class TestURL:
    path="/cashflow-assessment"
    def __str__(self): return "http://test/cashflow-assessment"
request=SimpleNamespace(url=TestURL(), url_path_for=lambda *a, **k: "/",
    session={}, state=SimpleNamespace(company_name="沪上银", site_name="企业资本健康管理"))
rendered=environment.get_template("cashflow_assessment.html").render(
    request=request, form_values={}, submit_error="")
parser=CheckboxStructureParser(); parser.feed(rendered)
assert parser.checkbox_count == parser.valid_count == 10
assert rendered.count("data-other-select") == 3
assert all(text in rendered for text in ("请选择行业", "请选择主营业务", "请选择企业性质"))
assert all(text in rendered for text in ("制造业", "产品生产制造", "民营企业"))

# 非枚举历史值回显为“其他”，原文字进入补充输入框且不丢失。
legacy_rendered=environment.get_template("cashflow_assessment.html").render(
    request=request, form_values={"industry":"化工设备制造", "business_scope":"特种泵阀生产",
        "company_type":"地方混合所有制企业"}, submit_error="")
for value in ("化工设备制造", "特种泵阀生产", "地方混合所有制企业"):
    assert f'value="{value}"' in legacy_rendered
assert legacy_rendered.count('<option value="其他" selected>') == 3
merged=_data({"industry":"其他", "industry_other":"化工设备制造",
    "business_scope":"其他", "business_scope_other":"泵阀设备生产制造",
    "company_type":"其他", "company_type_other":"民营科技企业"})
assert merged["industry"] == "化工设备制造"
assert merged["business_scope"] == "泵阀设备生产制造"
assert merged["company_type"] == "民营科技企业"
assert ".cashflow-form .checkbox-item label{display:flex;flex-direction:row;align-items:center" in styles
assert ".cashflow-form .checkbox-group{display:grid;grid-template-columns:repeat(2" in styles
assert "@media(max-width:768px)" in styles
assert ".cashflow-form .form-grid-3,.cashflow-form .checkbox-group,.company-profile-grid{grid-template-columns:1fr}" in styles
assert ".cashflow-form .form-field select{appearance:none" in styles
print("CASHFLOW_FORM_UI_OK")
