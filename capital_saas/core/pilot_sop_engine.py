def pilot_sop_recommendation(
    pilot_stage: str = "",
    lead_grade: str = "",
    paid_product: str = "",
    document_completeness: int = 0,
    feedback_rating: int = 0,
    last_activity_at=None,
) -> dict:
    stage = pilot_stage or "invited"
    if stage == "assessed":
        return {
            "next_action": "销售在24小时内跟进，解释完整报告价值并推进支付",
            "owner_role": "sales",
            "priority": "high" if lead_grade in {"S", "A", "B"} else "medium",
            "suggested_message": "王总，测评结果已经出来了。现在关键不是能不能贷，而是银行会怎么看额度、成本和结构，我建议先把完整报告解锁看清楚。",
            "risk": "客户看完免费结果后如果无人跟进，容易流失。",
        }
    if stage == "paid":
        return {
            "next_action": "顾问发送补资料清单，引导客户上传核心材料",
            "owner_role": "consultant",
            "priority": "high",
            "suggested_message": "报告已解锁，下一步建议补充营业执照、流水、纳税和财务资料，我们会据此做银行视角尽调。",
            "risk": "付费后未进入交付，会影响信任和升级转化。",
        }
    if stage == "documents_uploaded":
        return {
            "next_action": "顾问生成尽调底稿并判断是否立项",
            "owner_role": "consultant",
            "priority": "high" if document_completeness >= 60 else "medium",
            "suggested_message": "资料已收到，我们会先核对完整度，再给您一个适合申请的银行路径和资料补充建议。",
            "risk": "资料解析/尽调延迟会造成服务体验下降。",
        }
    if stage == "report_viewed":
        return {
            "next_action": "根据已购产品推荐699/1999升级或顾问服务",
            "owner_role": "sales",
            "priority": "medium",
            "suggested_message": "报告里已经看到核心问题，下一步如果要真正推进申请，建议做银行匹配和融资结构设计。",
            "risk": "只看报告不推进，容易停留在诊断层。",
        }
    if stage == "project_created":
        return {
            "next_action": "进入融资交付SOP，跟踪银行申请节点",
            "owner_role": "consultant",
            "priority": "high",
            "suggested_message": "项目已立项，接下来我们会按资料准备、提交、审批、批复节点同步进度。",
            "risk": "项目交付节点需要透明同步，避免客户焦虑。",
        }
    if stage == "dropped":
        return {
            "next_action": "记录流失原因，7天后做一次轻触达复盘",
            "owner_role": "sales",
            "priority": "low",
            "suggested_message": "后续如果您还想了解银行额度或资料准备，我们可以再帮您做一次简短复盘。",
            "risk": "不要强推，保留养熟关系。",
        }
    return {
        "next_action": "确认客户是否完成测评并建立首次联系",
        "owner_role": "sales",
        "priority": "medium",
        "suggested_message": "我们这次试运营主要帮企业老板提前看清银行视角，您可以先完成3分钟测评。",
        "risk": "未进入测评前无法判断真实意向。",
    }
