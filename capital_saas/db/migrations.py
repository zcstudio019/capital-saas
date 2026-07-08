from sqlalchemy import inspect, text

from db.database import engine


SQLITE_COLUMNS = {
    "assessments": {
        "contact_name": "VARCHAR(100) NOT NULL DEFAULT ''",
        "phone": "VARCHAR(30) NOT NULL DEFAULT ''",
        "wechat_id": "VARCHAR(100) NOT NULL DEFAULT ''",
        "city": "VARCHAR(100) NOT NULL DEFAULT ''",
        "source_channel": "VARCHAR(100) NOT NULL DEFAULT ''",
        "source_campaign": "VARCHAR(200) NOT NULL DEFAULT ''",
        "source_keyword": "VARCHAR(200) NOT NULL DEFAULT ''",
        "source_landing_page": "VARCHAR(200) NOT NULL DEFAULT ''",
        "utm_source": "VARCHAR(100) NOT NULL DEFAULT ''",
        "utm_medium": "VARCHAR(100) NOT NULL DEFAULT ''",
        "utm_campaign": "VARCHAR(200) NOT NULL DEFAULT ''",
        "utm_content": "VARCHAR(200) NOT NULL DEFAULT ''",
        "utm_term": "VARCHAR(200) NOT NULL DEFAULT ''",
        "deleted_at":"DATETIME","deleted_by":"INTEGER","delete_reason":"TEXT NOT NULL DEFAULT ''",
    },
    "leads": {
        "contact_name": "VARCHAR(100) NOT NULL DEFAULT ''",
        "phone": "VARCHAR(30) NOT NULL DEFAULT ''",
        "wechat_id": "VARCHAR(100) NOT NULL DEFAULT ''",
        "city": "VARCHAR(100) NOT NULL DEFAULT ''",
        "lead_score": "INTEGER NOT NULL DEFAULT 0",
        "follow_status": "VARCHAR(30) NOT NULL DEFAULT '待联系'",
        "next_follow_time": "DATETIME",
        "last_follow_note": "TEXT NOT NULL DEFAULT ''",
        "assigned_sales": "VARCHAR(100) NOT NULL DEFAULT ''",
        "sales_script": "TEXT NOT NULL DEFAULT '{}'",
        "updated_at": "DATETIME",
        "assigned_sales_id": "INTEGER",
        "source_channel": "VARCHAR(100) NOT NULL DEFAULT ''",
        "source_campaign": "VARCHAR(200) NOT NULL DEFAULT ''",
        "source_keyword": "VARCHAR(200) NOT NULL DEFAULT ''",
        "source_landing_page": "VARCHAR(200) NOT NULL DEFAULT ''",
        "utm_source": "VARCHAR(100) NOT NULL DEFAULT ''",
        "utm_medium": "VARCHAR(100) NOT NULL DEFAULT ''",
        "utm_campaign": "VARCHAR(200) NOT NULL DEFAULT ''",
        "utm_content": "VARCHAR(200) NOT NULL DEFAULT ''",
        "utm_term": "VARCHAR(200) NOT NULL DEFAULT ''",
        "org_id": "INTEGER", "owner_user_id": "INTEGER", "owner_org_id": "INTEGER",
        "source_partner_id": "INTEGER",
        "pilot_batch_id": "INTEGER",
        "pilot_stage": "VARCHAR(40) NOT NULL DEFAULT ''",
        "pilot_note": "TEXT NOT NULL DEFAULT ''",
        "deleted_at":"DATETIME","deleted_by":"INTEGER","delete_reason":"TEXT NOT NULL DEFAULT ''",
    },
    "orders": {
        "product_code": "VARCHAR(50) NOT NULL DEFAULT '299_report'",
        "pay_channel": "VARCHAR(30) NOT NULL DEFAULT 'mock'",
        "transaction_id": "VARCHAR(100) NOT NULL DEFAULT ''",
        "buyer_contact": "VARCHAR(100) NOT NULL DEFAULT ''",
        "refund_at": "DATETIME",
        "source_channel": "VARCHAR(100) NOT NULL DEFAULT ''",
        "source_campaign": "VARCHAR(200) NOT NULL DEFAULT ''",
        "source_keyword": "VARCHAR(200) NOT NULL DEFAULT ''",
        "source_landing_page": "VARCHAR(200) NOT NULL DEFAULT ''",
        "utm_source": "VARCHAR(100) NOT NULL DEFAULT ''",
        "utm_medium": "VARCHAR(100) NOT NULL DEFAULT ''",
        "utm_campaign": "VARCHAR(200) NOT NULL DEFAULT ''",
        "utm_content": "VARCHAR(200) NOT NULL DEFAULT ''",
        "utm_term": "VARCHAR(200) NOT NULL DEFAULT ''",
        "org_id": "INTEGER", "owner_user_id": "INTEGER", "owner_org_id": "INTEGER",
        "source_partner_id": "INTEGER",
        "customer_id": "INTEGER",
    },
    "reports": {
        "public_token": "VARCHAR(100)",
        "token_expired_at": "DATETIME",
        "review_status": "VARCHAR(30) NOT NULL DEFAULT 'draft'",
        "reviewed_by": "INTEGER",
        "reviewed_at": "DATETIME",
        "review_note": "TEXT NOT NULL DEFAULT ''",
        "current_version_id": "INTEGER",
        "deleted_at":"DATETIME","deleted_by":"INTEGER","delete_reason":"TEXT NOT NULL DEFAULT ''",
    },
    "events": {
        "source_channel": "VARCHAR(100) NOT NULL DEFAULT ''",
        "source_campaign": "VARCHAR(200) NOT NULL DEFAULT ''",
        "source_keyword": "VARCHAR(200) NOT NULL DEFAULT ''",
        "source_landing_page": "VARCHAR(200) NOT NULL DEFAULT ''",
        "utm_source": "VARCHAR(100) NOT NULL DEFAULT ''",
        "utm_medium": "VARCHAR(100) NOT NULL DEFAULT ''",
        "utm_campaign": "VARCHAR(200) NOT NULL DEFAULT ''",
        "utm_content": "VARCHAR(200) NOT NULL DEFAULT ''",
        "utm_term": "VARCHAR(200) NOT NULL DEFAULT ''",
    },
    "uploaded_documents": {
        "parse_status": "VARCHAR(30) NOT NULL DEFAULT 'pending_parse'",
        "verify_status": "VARCHAR(30) NOT NULL DEFAULT 'unverified'",
        "parsed_json": "TEXT NOT NULL DEFAULT '{}'",
        "parse_error": "TEXT NOT NULL DEFAULT ''",
        "file_size": "INTEGER NOT NULL DEFAULT 0",
        "file_hash": "VARCHAR(64) NOT NULL DEFAULT ''",
        "note": "TEXT NOT NULL DEFAULT ''",
        "verified_by": "INTEGER",
        "verified_at": "DATETIME",
        "customer_id": "INTEGER",
        "uploaded_source": "VARCHAR(30) NOT NULL DEFAULT 'staff'",
        "deleted_at":"DATETIME","deleted_by":"INTEGER","delete_reason":"TEXT NOT NULL DEFAULT ''",
    },
    "users": {"org_id": "INTEGER","last_login_at":"DATETIME","last_login_ip":"VARCHAR(100) NOT NULL DEFAULT ''",
        "failed_login_count":"INTEGER NOT NULL DEFAULT 0","locked_until":"DATETIME","password_changed_at":"DATETIME",
        "force_password_change":"BOOLEAN NOT NULL DEFAULT 0","two_factor_enabled":"BOOLEAN NOT NULL DEFAULT 0",
        "two_factor_secret_mock":"VARCHAR(200) NOT NULL DEFAULT ''","session_version":"INTEGER NOT NULL DEFAULT 1"},
    "consulting_cases": {
        "org_id": "INTEGER", "owner_user_id": "INTEGER", "owner_org_id": "INTEGER",
        "consultant_user_id": "INTEGER",
        "show_consultant_contact": "BOOLEAN NOT NULL DEFAULT 0",
    },
    "financing_projects": {
        "org_id": "INTEGER", "owner_user_id": "INTEGER", "owner_org_id": "INTEGER",
        "consultant_user_id": "INTEGER",
        "deleted_at":"DATETIME","deleted_by":"INTEGER","delete_reason":"TEXT NOT NULL DEFAULT ''",
    },
    "customer_accounts":{"deleted_at":"DATETIME","deleted_by":"INTEGER","delete_reason":"TEXT NOT NULL DEFAULT ''"},
    "funding_applications": {"org_id": "INTEGER", "institution_contact_id": "INTEGER"},
    "bank_products": {
        "city": "VARCHAR(100) NOT NULL DEFAULT ''", "province": "VARCHAR(100) NOT NULL DEFAULT ''",
        "min_amount": "FLOAT NOT NULL DEFAULT 0", "min_rate": "FLOAT", "max_rate": "FLOAT",
        "min_term_months": "INTEGER", "max_term_months": "INTEGER",
        "required_documents": "TEXT NOT NULL DEFAULT ''", "repayment_methods": "TEXT NOT NULL DEFAULT ''",
        "target_customer_type": "TEXT NOT NULL DEFAULT ''", "advantages": "TEXT NOT NULL DEFAULT ''",
        "disadvantages": "TEXT NOT NULL DEFAULT ''", "suitable_scenarios": "TEXT NOT NULL DEFAULT ''",
        "data_source": "VARCHAR(30) NOT NULL DEFAULT 'mock'",
    },
}


def migrate_database() -> list[str]:
    """为旧 SQLite 数据库补列；新库由 SQLAlchemy 正常建表。"""
    if engine.dialect.name != "sqlite":
        return []
    changed: list[str] = []
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as connection:
        for table, columns in SQLITE_COLUMNS.items():
            if table not in existing_tables:
                continue
            existing_columns = {item["name"] for item in inspector.get_columns(table)}
            for name, definition in columns.items():
                if name not in existing_columns:
                    connection.execute(
                        text(f'ALTER TABLE "{table}" ADD COLUMN "{name}" {definition}')
                    )
                    changed.append(f"{table}.{name}")

        if "leads" in existing_tables:
            connection.execute(
                text(
                    "UPDATE leads SET conversion_status='未成交' "
                    "WHERE conversion_status IS NULL OR conversion_status='' "
                    "OR conversion_status='new'"
                )
            )
            connection.execute(
                text(
                    "UPDATE leads SET follow_status='待联系' "
                    "WHERE follow_status IS NULL OR follow_status=''"
                )
            )
            connection.execute(
                text("UPDATE leads SET updated_at=created_at WHERE updated_at IS NULL")
            )
        if "orders" in existing_tables:
            connection.execute(
                text(
                    "UPDATE orders SET product_code='299_report' "
                    "WHERE product_code IS NULL OR product_code=''"
                )
            )
            connection.execute(
                text(
                    "UPDATE orders SET pay_channel='mock' "
                    "WHERE pay_channel IS NULL OR pay_channel=''"
                )
            )
    return changed
