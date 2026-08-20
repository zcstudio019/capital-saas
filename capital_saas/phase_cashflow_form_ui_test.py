"""现金流诊断表中文文案、复选框 DOM 与响应式样式专项检查。"""
from html.parser import HTMLParser
from pathlib import Path
from types import SimpleNamespace
from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parent
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
assert ".cashflow-form .checkbox-item label{display:flex;flex-direction:row;align-items:center" in styles
assert ".cashflow-form .checkbox-group{display:grid;grid-template-columns:repeat(2" in styles
assert "@media(max-width:768px)" in styles
assert ".cashflow-form .form-grid-3,.cashflow-form .checkbox-group{grid-template-columns:1fr}" in styles
print("CASHFLOW_FORM_UI_OK")
