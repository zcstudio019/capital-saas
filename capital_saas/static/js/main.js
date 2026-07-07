document.querySelectorAll("[data-loading-form]").forEach((form) => {
  form.addEventListener("submit", () => {
    const button = form.querySelector("button[type='submit']");
    if (button) {
      button.disabled = true;
      button.dataset.originalText = button.textContent;
      button.textContent = "正在处理，请稍候…";
    }
  });
});

document.querySelectorAll("[data-consult]").forEach((button) => {
  button.addEventListener("click", () => {
    alert("请联系融资顾问预约1对1服务。");
  });
});

document.querySelectorAll(".copy-script").forEach((button) => {
  button.addEventListener("click", async () => {
    const text = button.dataset.copyText || "";
    try {
      await navigator.clipboard.writeText(text);
      const original = button.textContent;
      button.textContent = "已复制";
      setTimeout(() => { button.textContent = original; }, 1200);
    } catch {
      window.prompt("复制以下话术：", text);
    }
    if (button.dataset.leadId || button.dataset.projectId) {
      const body = new URLSearchParams({
        lead_id: button.dataset.leadId || "0",
        template_id: button.dataset.templateId || "0",
      });
      const endpoint = button.dataset.projectScript ? "/api/events/project-message-copied" : (button.dataset.documentScript ? "/api/events/document-request-script-copied" : "/api/events/script-copied");
      if (button.dataset.projectId) body.set("project_id", button.dataset.projectId);
      fetch(endpoint, {
        method: "POST",
        headers: {"Content-Type": "application/x-www-form-urlencoded"},
        body,
      }).catch(() => {});
    }
  });
});

// 后台展示层中文化：仅替换可见文本，不改动表单 value、接口参数和数据库枚举值。
if (location.pathname.startsWith("/admin") || location.pathname.startsWith("/sales")) {
  const labels = {
    admin: "管理员", super_admin: "总部超级管理员", city_manager: "城市负责人",
    sales_manager: "销售主管", sales: "销售", consultant_manager: "顾问主管", consultant: "融资顾问",
    finance: "财务", viewer: "只读", partner: "渠道伙伴", customer: "客户",
    pending: "待处理", queued: "待发送", sending: "发送中", success: "成功", failed: "失败",
    cancelled: "已取消", skipped: "已跳过", paid: "已支付", refunded: "已退款", done: "已完成",
    open: "待处理", in_progress: "处理中", resolved: "已解决", closed: "已关闭", "won't_fix": "暂不处理",
    draft: "草稿", pending_review: "待审核", approved: "已通过", rejected: "已拒绝",
    planning: "筹备中", running: "运行中", paused: "已暂停", completed: "已完成", archived: "已归档",
    ready: "已就绪", submitted: "已提交", returned: "已退回", high: "高", medium: "中", low: "低", critical: "严重",
    mock: "模拟通道", manual_transfer: "人工转账", wechat_pay: "微信支付", alipay: "支付宝",
    in_app: "站内信", email: "邮件", sms: "短信", wecom_webhook: "企业微信机器人",
    service: "服务通知", marketing: "营销通知", direct: "直接访问", active: "启用", inactive: "停用",
    headquarters: "总部", branch: "分公司", team: "团队", per_lead: "按线索结算",
    per_paid_order: "按付费订单结算", per_disbursed_amount: "按放款金额结算", manual: "人工结算",
    preparing: "资料准备中", bank_review: "金融机构审核中", supplement_required: "需补充资料",
    disbursed: "已放款", withdrawn: "已撤回", planned: "计划申请", complete: "完整", partial: "部分完整", weak: "较弱",
    pending_parse: "待解析", parsed: "已解析", parse_failed: "解析失败", verified: "已核验", unverified: "待核验",
    "299_report": "299元基础诊断报告", "699_bank_match": "699元银行匹配报告",
    "1999_structure_plan": "1999元融资结构方案", free_nurture: "免费培育",
    bug: "程序问题", feature_request: "需求建议", data_issue: "数据问题", payment_issue: "支付问题",
    report_issue: "报告问题", operation_issue: "运营问题", new: "新反馈", reviewing: "处理中", ignored: "已忽略"
  };
  const terms = {
    "??客户资料": "客户资料中心", "A/B??": "对照测试", "已启用（??）": "已启用（模拟）",
    "PRODUCTS": "产品服务", "ORDERS": "订单管理", "ORDER": "订单", "PROJECT": "融资项目",
    "ORGANIZATION": "组织机构", "VERSION": "版本", "CHANGELOG": "更新记录",
    "AI": "智能系统", "A/B": "对照测试", "Prompt": "生成指令", "prompt": "生成指令",
    "ID": "编号", "IP": "网络地址", "CSV": "表格文件", "ZIP": "压缩包",
    "SQLite": "本地数据库", "SHA-256": "文件校验值", "SECRET_KEY": "系统安全密钥",
    "Webhook": "消息回调", "OCR": "图片文字识别", "MB": "兆字节", "SOP": "标准服务流程",
    "Mock": "模拟", "mock": "模拟", "OpenAI": "智能模型", "email": "邮件", "sms": "短信"
  };
  const exactOrTokens = (source) => {
    const trimmed = source.trim();
    if (labels[trimmed]) return source.replace(trimmed, labels[trimmed]);
    let output = source;
    Object.entries(terms).forEach(([from, to]) => {
      output = output.replace(new RegExp(`\\b${from.replace(/[.*+?^${}()|[\\]\\]/g, "\\$&")}\\b`, "g"), to);
    });
    Object.entries(labels).forEach(([from, to]) => {
      output = output.replace(new RegExp(`(^|[\\s/·#：:])${from.replace(/[.*+?^${}()|[\\]\\]/g, "\\$&")}(?=$|[\\s/·#：:])`, "gi"), `$1${to}`);
    });
    return output;
  };
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  nodes.forEach((node) => {
    if (["SCRIPT", "STYLE", "TEXTAREA"].includes(node.parentElement?.tagName)) return;
    node.nodeValue = exactOrTokens(node.nodeValue);
  });
}
