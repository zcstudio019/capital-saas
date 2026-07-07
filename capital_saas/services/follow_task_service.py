from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from db.models import FollowTask, Lead


TASK_PLANS = {
    "S": [
        ("call", "立即电话联系", "确认融资需求、时间节点和决策人，预约结构预诊断。", "high", 0),
        ("wechat", "添加微信并发送诊断摘要", "发送核心评分与银行视角风险摘要，建立持续沟通。", "high", 2),
        ("upsell", "推荐1999方案或顾问服务", "重点沟通额度、成本与融资结构，不建议直接盲目申请。", "high", 6),
        ("revisit", "24小时内二次跟进", "确认客户反馈并推动顾问沟通或结构方案成交。", "high", 24),
    ],
    "A": [
        ("wechat", "添加微信并发送诊断摘要", "说明企业具备融资基础，但申请路径和顺序需要优化。", "high", 2),
        ("upsell", "推荐1999融资结构方案", "讲解结构优化、银行顺序与期限成本设计价值。", "high", 8),
        ("revisit", "24小时内跟进", "跟进方案阅读情况和融资时间窗口。", "high", 24),
    ],
    "B": [
        ("send_report", "推荐699银行匹配报告", "说明盲目选银行可能被拒或压额度，先做产品匹配。", "medium", 4),
        ("payment_follow", "48小时内跟进", "跟进银行匹配报告购买意向与当前申请进度。", "medium", 48),
    ],
    "C": [
        ("send_report", "推荐299完整诊断报告", "当前条件需要先诊断，不建议直接批量申请银行。", "medium", 8),
        ("payment_follow", "72小时内跟进", "确认客户是否理解核心问题与修复顺序。", "medium", 72),
    ],
    "D": [
        ("wechat", "加入长期养熟池", "发送基础条件改善清单，不强推付费。", "low", 24),
        ("revisit", "7天后回访", "确认征信、纳税、现金流等基础条件改善进度。", "low", 168),
    ],
}


def create_default_tasks(db: Session, lead: Lead, commit: bool = False) -> list[FollowTask]:
    now = datetime.now()
    tasks = []
    for task_type, title, content, priority, hours in TASK_PLANS.get(lead.lead_grade, TASK_PLANS["D"]):
        task = FollowTask(
            lead_id=lead.id,
            assessment_id=lead.assessment_id,
            task_type=task_type,
            task_title=title,
            task_content=content,
            priority=priority,
            due_time=now + timedelta(hours=hours),
            status="pending",
        )
        db.add(task)
        tasks.append(task)
    if commit:
        db.commit()
    return tasks


def create_manual_task(
    db: Session,
    lead: Lead,
    task_type: str,
    task_title: str,
    task_content: str,
    priority: str,
    due_time: datetime,
) -> FollowTask:
    task = FollowTask(
        lead_id=lead.id,
        assessment_id=lead.assessment_id,
        task_type=task_type,
        task_title=task_title,
        task_content=task_content,
        priority=priority,
        due_time=due_time,
        status="pending",
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task

