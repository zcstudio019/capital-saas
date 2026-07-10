"""Business-facing formatting for customer journey timeline events."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from utils.display_labels import (
    get_event_label,
    get_notification_channel_label,
    get_notification_template_label,
    get_payment_channel_label,
    get_product_label,
    get_user_display_name,
)


OPERATOR_LABELS = {"admin": "系统管理员", "mock": "模拟操作", "system": "系统"}


def _payload(event: Any) -> tuple[dict[str, Any], bool]:
    for field in ("event_data", "event_data_json", "payload", "metadata", "detail_json"):
        raw = getattr(event, field, None)
        if raw in (None, "", {}, []):
            continue
        if isinstance(raw, dict):
            return raw, False
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
            except (TypeError, ValueError, json.JSONDecodeError):
                return {}, True
            return parsed if isinstance(parsed, dict) else {}, not isinstance(parsed, dict)
    return {}, False


def _money(value: Any) -> str:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return ""
    return f"{amount:,.0f}元" if amount == int(amount) else f"{amount:,.2f}元"


def _time(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    return str(value or "")[:16]


def _detail(label: str, value: Any) -> dict[str, str] | None:
    text = str(value or "").strip()
    return {"label": label, "value": text} if text else None


def _operator(value: Any, users_by_id: dict[int, Any]) -> str:
    if isinstance(value, int) or (isinstance(value, str) and value.isdigit()):
        user = users_by_id.get(int(value))
        return get_user_display_name(user) if user else "系统用户"
    code = str(value or "").strip().lower()
    if code in OPERATOR_LABELS:
        return OPERATOR_LABELS[code]
    user = next((item for item in users_by_id.values() if getattr(item, "username", "") == code), None)
    return get_user_display_name(user) if user else "系统"


def _payment_channel(value: Any) -> str:
    text = str(value or "").strip()
    if text in {"模拟", "模拟支付"}:
        return "模拟支付"
    return get_payment_channel_label(text)


def _next_action(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    product_label = get_product_label(text)
    return f"升级{product_label}" if product_label != "其他业务产品" else text


def format_journey_event(
    event: Any,
    users_by_id: dict[int, Any] | None = None,
    orders_by_id: dict[int, Any] | None = None,
    lead: Any = None,
) -> dict[str, Any]:
    """Convert an event payload into a safe Chinese timeline record."""
    users_by_id = users_by_id or {}
    orders_by_id = orders_by_id or {}
    payload, parse_failed = _payload(event)
    event_type = str(getattr(event, "event_type", "") or "")
    title = get_event_label(event_type)
    details: list[dict[str, str]] = []
    summary = f"系统已记录{title}。"

    if event_type == "customer_journey_viewed":
        summary = "有用户查看了该客户的完整旅程。"
        operator = _operator(payload.get("user_id") or payload.get("operator"), users_by_id)
        if item := _detail("操作人", operator): details.append(item)
    elif event_type == "payment_success":
        order_id = payload.get("order_id")
        order = orders_by_id.get(int(order_id)) if str(order_id or "").isdigit() else None
        product_code = payload.get("product_code") or getattr(order, "product_code", "")
        amount = payload.get("amount") or getattr(order, "amount", 0)
        product = get_product_label(product_code)
        amount_text = _money(amount)
        summary = f"客户已完成{product}支付{('，金额' + amount_text) if amount_text else ''}。"
        for label, value in [
            ("订单编号", f"#{order_id}" if order_id else ""),
            ("购买产品", product),
            ("支付金额", amount_text),
            ("支付渠道", _payment_channel(payload.get("channel"))),
            ("操作方式", _operator(payload.get("operator"), users_by_id)),
        ]:
            if item := _detail(label, value): details.append(item)
    elif event_type == "notification_job_created":
        summary = "系统已创建一条客户通知任务。"
        for label, value in [
            ("通知编号", f"#{payload.get('job_id')}" if payload.get("job_id") else ""),
            ("通知模板", get_notification_template_label(payload.get("template_key"))),
            ("通知渠道", get_notification_channel_label(payload.get("channel"))),
        ]:
            if item := _detail(label, value): details.append(item)
    elif event_type in {"sales_next_action", "next_best_action", "next_best_action_viewed"}:
        title = "销售建议已生成"
        action = _next_action(payload.get("next_action"))
        summary = f"系统建议下一步推进客户{action or '融资服务跟进'}。"
        for label, value in [("下一步动作", action), ("操作人", _operator(payload.get("operator"), users_by_id))]:
            if item := _detail(label, value): details.append(item)
    elif event_type == "assessment_submitted":
        summary = "客户已提交企业融资测评。"
        subject = lead or getattr(event, "lead", None)
        for label, value in [
            ("企业名称", getattr(subject, "company_name", "")),
            ("联系人", getattr(subject, "contact_name", "")),
            ("评分", f"{payload.get('score')}分" if payload.get("score") is not None else ""),
            ("评级", payload.get("grade")),
        ]:
            if item := _detail(label, value): details.append(item)
    elif event_type == "free_result_viewed":
        summary = "客户查看了免费测评结果。"
    elif event_type in {"report_viewed", "client_report_viewed"}:
        summary = "客户或内部人员查看了完整报告。"
    elif event_type == "lead_sales_assigned":
        summary = "管理员已将该客户分配给销售跟进。"
        for label, value in [
            ("负责销售", _operator(payload.get("sales_user_id"), users_by_id)),
            ("操作人", _operator(payload.get("operator"), users_by_id)),
        ]:
            if item := _detail(label, value): details.append(item)
    elif event_type in {"advisor_booking_submitted", "advisor_booking_created"}:
        summary = "客户提交了1对1融资顾问服务预约。"
    elif event_type in {"document_uploaded", "client_document_uploaded"}:
        summary = "客户上传了新的融资资料。"
        for label, value in [
            ("资料类型", payload.get("document_category") or payload.get("category")),
            ("文件名称", payload.get("file_name") or payload.get("document_name")),
            ("上传人", _operator(payload.get("uploaded_by") or payload.get("operator"), users_by_id)),
        ]:
            if item := _detail(label, value): details.append(item)

    if parse_failed or (payload and not details and event_type not in {"free_result_viewed", "report_viewed", "client_report_viewed"}):
        details = [{"label": "补充信息", "value": "系统已记录该操作。"}]

    category = (
        "支付" if event_type == "payment_success" else "通知" if event_type.startswith("notification_")
        else "销售" if "action" in event_type or "sales" in event_type else "测评" if "assessment" in event_type or "result" in event_type
        else "报告" if "report" in event_type else "资料" if "document" in event_type else "顾问" if "advisor" in event_type else "客户"
    )
    return {"title": title, "summary": summary, "details": details, "time": _time(getattr(event, "created_at", None)), "category": category}
