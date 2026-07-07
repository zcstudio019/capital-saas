def generate_sales_script(
    lead_grade: str,
    company_name: str,
    contact_name: str,
    assessment_score: int,
    funding_need: float,
    risk_point: str,
) -> dict:
    name = contact_name or "老板"
    need_text = f"{funding_need / 10000:.0f}万元"
    common_opening = (
        f"{name}您好，我是沪上银企业融资顾问。我们刚完成了{company_name}的测评，"
        f"企业评分为{assessment_score}分，融资需求约{need_text}。"
    )
    scripts = {
        "S": {
            "pain": "您现在的重点已经不是能不能贷，而是如何把额度、成本和期限结构做到更优。",
            "offer": "建议先做融资结构设计，再决定银行和申请顺序，适合安排1对1顾问预诊断。",
            "follow": "我可以先用15分钟把可优化的额度空间和当前结构风险给您梳理一遍。",
            "upgrade": "下一步重点推荐融资结构优化与1对1顾问服务。",
        },
        "A": {
            "pain": "企业具备融资基础，但申请路径和银行顺序会直接影响额度与审批结果。",
            "offer": "建议采用1999元企业融资结构优化方案，先设计顺序、期限和工具组合。",
            "follow": "我可以先说明为什么同样的资料，先申请不同银行结果可能完全不同。",
            "upgrade": "完成结构方案后，再进入银行匹配与申请辅导。",
        },
        "B": {
            "pain": "目前最大的风险是不清楚哪家银行更匹配，盲目申请容易留下查询记录并被压额度。",
            "offer": "建议先做699元银行匹配与额度预测报告，明确产品、额度区间和申请顺序。",
            "follow": "我可以先结合您的行业和流水，说明银行匹配报告会解决哪些问题。",
            "upgrade": "条件改善后可升级1999元融资结构优化方案。",
        },
        "C": {
            "pain": "当前融资条件存在明显限制，核心问题需要先诊断，不建议直接提交银行申请。",
            "offer": "建议先解锁299元完整报告，确认影响通过率的关键指标和修复顺序。",
            "follow": "先把问题看清，再决定是否申请，可以减少无效征信查询和试错成本。",
            "upgrade": "完成基础修复后，再评估银行匹配服务。",
        },
        "D": {
            "pain": "当前基础条件还不足以支持直接融资，现阶段强行申请的价值不高。",
            "offer": "暂不强推付费，建议先补齐纳税、征信、现金流和财务资料。",
            "follow": "我可以先发送一份基础条件改善清单，后续条件成熟再重新测评。",
            "upgrade": "进入免费培育，条件改善后再规划融资。",
        },
    }
    selected = scripts.get(lead_grade, scripts["D"])
    return {
        "opening_script": common_opening,
        "pain_point_script": f"{selected['pain']} 当前重点风险是：{risk_point}",
        "offer_script": selected["offer"],
        "follow_up_script": selected["follow"],
        "upgrade_script": selected["upgrade"],
    }
