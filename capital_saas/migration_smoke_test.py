"""验证 Phase 1 SQLite 旧表可自动补齐 Phase 2 字段。"""

import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
database_file = ROOT / "legacy_migration_test.db"
if database_file.exists():
    database_file.unlink()

connection = sqlite3.connect(database_file)
connection.executescript(
    """
    CREATE TABLE assessments (
        id INTEGER PRIMARY KEY,
        company_name VARCHAR(200)
    );
    CREATE TABLE leads (
        id INTEGER PRIMARY KEY,
        assessment_id INTEGER,
        company_name VARCHAR(200),
        phone VARCHAR(30),
        lead_grade VARCHAR(10),
        conversion_status VARCHAR(30),
        recommended_product VARCHAR(200),
        created_at DATETIME
    );
    CREATE TABLE orders (
        id INTEGER PRIMARY KEY,
        assessment_id INTEGER,
        product_name VARCHAR(200),
        amount FLOAT,
        status VARCHAR(20),
        paid_at DATETIME,
        created_at DATETIME
    );
    CREATE TABLE reports (
        id INTEGER PRIMARY KEY,
        assessment_id INTEGER,
        free_summary_json TEXT,
        full_report_json TEXT,
        html_content TEXT,
        is_unlocked BOOLEAN,
        created_at DATETIME
    );
    CREATE TABLE uploaded_documents (
        id INTEGER PRIMARY KEY,
        lead_id INTEGER,
        assessment_id INTEGER,
        file_name VARCHAR(300),
        file_path VARCHAR(500),
        file_type VARCHAR(30),
        document_category VARCHAR(100),
        uploaded_by INTEGER,
        created_at DATETIME
    );
    """
)
connection.close()

os.environ["DATABASE_URL"] = "sqlite:///./legacy_migration_test.db"

from db.migrations import migrate_database  # noqa: E402
from db.database import Base, engine  # noqa: E402
from db import models  # noqa: E402,F401

Base.metadata.create_all(bind=engine)
changed = migrate_database()
connection = sqlite3.connect(database_file)
assessment_columns = {row[1] for row in connection.execute("PRAGMA table_info(assessments)")}
lead_columns = {row[1] for row in connection.execute("PRAGMA table_info(leads)")}
order_columns = {row[1] for row in connection.execute("PRAGMA table_info(orders)")}
tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
report_columns = {row[1] for row in connection.execute("PRAGMA table_info(reports)")} if "reports" in tables else set()
uploaded_columns = {row[1] for row in connection.execute("PRAGMA table_info(uploaded_documents)")} if "uploaded_documents" in tables else set()
user_columns = {row[1] for row in connection.execute("PRAGMA table_info(users)")}
case_columns = {row[1] for row in connection.execute("PRAGMA table_info(consulting_cases)")}
project_columns = {row[1] for row in connection.execute("PRAGMA table_info(financing_projects)")}
application_columns = {row[1] for row in connection.execute("PRAGMA table_info(funding_applications)")}
connection.close()

assert {"contact_name", "phone", "wechat_id", "city"} <= assessment_columns
assert {
    "source_channel", "source_campaign", "source_keyword", "source_landing_page",
    "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term",
} <= assessment_columns
assert {
    "contact_name",
    "wechat_id",
    "city",
    "lead_score",
    "follow_status",
    "next_follow_time",
    "last_follow_note",
    "assigned_sales",
    "sales_script",
    "updated_at",
    "assigned_sales_id", "source_channel", "source_campaign", "source_keyword",
    "source_landing_page", "utm_source", "utm_medium", "utm_campaign",
    "utm_content", "utm_term",
} <= lead_columns
assert {"org_id", "owner_user_id", "owner_org_id", "source_partner_id"} <= lead_columns
assert {"product_code", "pay_channel", "transaction_id", "buyer_contact", "refund_at",
        "org_id", "owner_user_id", "owner_org_id", "source_partner_id"} <= order_columns
assert {"org_id"} <= user_columns
assert {"last_login_at","last_login_ip","failed_login_count","locked_until","password_changed_at",
        "force_password_change","two_factor_enabled","two_factor_secret_mock","session_version"} <= user_columns
assert {"org_id", "owner_user_id", "owner_org_id", "consultant_user_id"} <= case_columns
assert {"org_id", "owner_user_id", "owner_org_id", "consultant_user_id"} <= project_columns
assert {"org_id", "institution_contact_id"} <= application_columns
assert {"public_token", "token_expired_at"} <= report_columns
assert {
    "review_status", "reviewed_by", "reviewed_at", "review_note", "current_version_id"
} <= report_columns
assert {
    "follow_tasks", "events", "users", "system_settings", "ab_experiments",
    "ab_assignments", "lead_follow_logs", "sales_script_templates", "tags", "lead_tags",
    "report_versions", "bank_products", "consulting_cases", "uploaded_documents",
    "ai_generation_logs",
    "document_parse_tasks", "due_diligence_reports", "financing_application_packages",
    "financing_projects", "funding_applications", "project_timeline_events",
    "project_tasks", "project_reviews", "success_cases", "rejection_reason_library",
    "organizations", "channel_partners", "institution_contacts", "commission_rules", "commission_records",
    "customer_accounts", "customer_access_tokens", "customer_tasks", "customer_messages", "customer_confirmations",
    "notification_templates", "notification_jobs", "notification_logs", "notification_preferences", "internal_notifications",
    "audit_logs", "legal_documents", "legal_acceptances", "worker_runs",
} <= tables
assert {"parse_status", "verify_status", "parsed_json", "parse_error", "file_size", "file_hash",
        "note", "verified_by", "verified_at", "customer_id", "uploaded_source"} <= uploaded_columns
assert {"customer_id"} <= order_columns
assert {"show_consultant_contact"} <= case_columns
assert {"deleted_at","deleted_by","delete_reason"} <= lead_columns
print({"migration_fields_added": changed})
print("LEGACY_MIGRATION_OK")
engine.dispose()
database_file.unlink()
