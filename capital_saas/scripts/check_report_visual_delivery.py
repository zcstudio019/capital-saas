"""静态检查商业级报告交付组件、权限边界与客户模板安全性。"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(path: str, fragments: tuple[str, ...]) -> None:
    target = ROOT / path
    assert target.exists(), f"缺少文件：{path}"
    text = target.read_text(encoding="utf-8")
    for fragment in fragments:
        assert fragment in text, f"{path} 缺少：{fragment}"


def run() -> None:
    require("static/css/capital_health_report.css", (
        "--report-navy", ".report-document", "@media print", "@page", "break-inside: avoid",
    ))
    require("templates/components/report_cover.html", ("企业资本健康体检报告", "报告编号", "免责声明"))
    require("templates/components/report_toc.html", ("体检总评", "后续服务建议"))
    require("templates/components/report_capital_health_body.html", (
        "body_unlocked", "structure_unlocked", "report_upgrade_gate.html",
    ))
    require("templates/components/report_bank_product_cards.html", (
        "bank_name", "match_level", "core_documents", "查看产品详情",
    ))
    require("templates/components/report_action_timeline.html", ("未来", "6个月融资落地节奏"))
    require("templates/result_capital_health_free.html", (
        "score-ring", "核心发现", "完整企业资本健康体检报告已生成",
    ))
    customer_templates = [
        ROOT / "templates/report_capital_health_full.html",
        ROOT / "templates/report_capital_health_print.html",
        ROOT / "templates/client_report_capital_health.html",
        ROOT / "templates/result_capital_health_free.html",
    ]
    forbidden = ("填写说明", "内部使用说明", "定价策略内部", "转化路径内部", "|tojson", "json.loads")
    combined = "\n".join(item.read_text(encoding="utf-8") for item in customer_templates)
    for term in forbidden:
        assert term not in combined, f"客户模板包含内部或原始结构化内容：{term}"
    print("REPORT_VISUAL_DELIVERY_CHECK_OK")


if __name__ == "__main__":
    run()
