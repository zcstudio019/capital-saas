class StrategyAgent:
    def generate(self, data: dict, score: dict) -> dict:
        industry = data["industry"]
        years = data["years"]
        return {
            "business_canvas": {
                "客户": f"聚焦{industry}领域的高价值核心客户",
                "价值主张": "以稳定交付、专业服务和资金效率形成差异化",
                "渠道": "老客复购、行业合作与数字化获客并行",
                "收入": "主营业务收入为主，逐步增加高毛利服务收入",
            },
            "ansoff": "优先做市场渗透与产品升级，待现金流稳定后再进入新市场。",
            "value_chain": "重点优化获客成本、交付周期、回款节点和供应商账期。",
            "core_competence": f"企业经营{years}年，核心竞争力应沉淀为客户复购、交付能力与行业资源。",
            "swot": {
                "strengths": ["已有业务基础与客户场景", "具备明确融资需求与发展意愿"],
                "weaknesses": ["财务数据精细度仍需提升", "资金结构与业务周期匹配不足"],
                "opportunities": ["数字化经营提升效率", "政策性与普惠金融工具增加"],
                "threats": ["行业竞争加剧", "回款放缓与融资成本波动"],
            },
            "tows": [
                "SO：用既有客户与交付能力扩大高质量订单",
                "WO：以数字化预算和融资工具补足资金短板",
                "ST：提高产品差异化和回款约束以对冲竞争",
                "WT：控制固定成本，避免激进扩张和期限错配",
            ],
        }

