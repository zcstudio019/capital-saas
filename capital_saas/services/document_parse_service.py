import json
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from core.config import BASE_DIR
from db.models import DocumentParseTask, FollowTask, UploadedDocument
from parsers.parser_router import parse_document, parser_for
from services.event_service import track_event


def classify_document(file_name: str, selected_category: str = "") -> str:
    if selected_category and selected_category != "自动识别":
        return selected_category
    name = file_name.lower()
    rules = [
        (["营业执照", "工商"], "营业执照/工商资料"),
        (["资产负债", "利润表", "财务", "科目余额"], "财务报表"),
        (["流水", "bank"], "银行流水"), (["纳税", "完税", "发票"], "纳税资料"),
        (["征信"], "征信资料"), (["合同"], "经营合同"),
        (["应收", "账龄"], "应收账款资料"), (["房产", "产权", "抵押"], "抵押物资料"),
        (["法人", "股东", "身份证"], "法人/股东资料"),
    ]
    for keywords, category in rules:
        if any(keyword in name for keyword in keywords):
            return category
    return "其他资料"


def create_parse_task(db: Session, document: UploadedDocument) -> DocumentParseTask:
    try:
        parser_type = parser_for(BASE_DIR / document.file_path).parser_type
    except ValueError:
        parser_type = "unknown"
    task = DocumentParseTask(
        document_id=document.id, lead_id=document.lead_id,
        assessment_id=document.assessment_id, task_status="queued", parser_type=parser_type,
    )
    db.add(task)
    db.flush()
    return task


def _manual_verify_task(db: Session, document: UploadedDocument) -> None:
    title = f"人工核验资料：{document.file_name}"
    exists = db.query(FollowTask).filter(
        FollowTask.lead_id == document.lead_id, FollowTask.task_title == title,
        FollowTask.status == "pending",
    ).first()
    if not exists:
        db.add(FollowTask(
            lead_id=document.lead_id, assessment_id=document.assessment_id,
            task_type="verify_documents", task_title=title,
            task_content=document.parse_error or "资料自动解析失败，请人工打开并核验。",
            priority="high", due_time=datetime.now() + timedelta(days=1), status="pending",
        ))


def run_parse_task(db: Session, document: UploadedDocument, reparse: bool = False) -> DocumentParseTask:
    task = create_parse_task(db, document)
    task.task_status = "running"
    task.started_at = datetime.now()
    document.parse_status = "pending_parse"
    track_event(db, "document_parse_started", document.assessment_id, document.lead_id,
                {"document_id": document.id, "task_id": task.id, "reparse": reparse}, commit=False)
    try:
        result = parse_document(BASE_DIR / document.file_path)
        payload = json.dumps(result, ensure_ascii=False)
        task.task_status = "success"
        task.result_json = payload
        document.parsed_json = payload
        document.parse_status = "parsed"
        document.parse_error = ""
        track_event(db, "document_parse_success", document.assessment_id, document.lead_id,
                    {"document_id": document.id, "task_id": task.id, "parser": task.parser_type,
                     "result_status": result.get("status")}, commit=False)
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"
        task.task_status = "failed"
        task.error_message = message
        document.parse_status = "parse_failed"
        document.parse_error = message
        _manual_verify_task(db, document)
        track_event(db, "document_parse_failed", document.assessment_id, document.lead_id,
                    {"document_id": document.id, "task_id": task.id, "error": message}, commit=False)
    task.finished_at = datetime.now()
    db.commit()
    db.refresh(task)
    return task
