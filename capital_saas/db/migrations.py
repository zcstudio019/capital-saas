from sqlalchemy import inspect, text

from db.database import engine
from utils.logger import logger


SQLITE_COLUMNS = {
    "assessments": {
        "customer_id": "INTEGER",
        "contact_name": "VARCHAR(100) NOT NULL DEFAULT ''",
        "phone": "VARCHAR(30) NOT NULL DEFAULT ''",
        "wechat_id": "VARCHAR(100) NOT NULL DEFAULT ''",
        "city": "VARCHAR(100) NOT NULL DEFAULT ''",
        "registered_capital": "FLOAT",
        "net_profit_margin": "FLOAT",
        "collateral_types": "TEXT NOT NULL DEFAULT ''",
        "enterprise_credit_status": "VARCHAR(30) NOT NULL DEFAULT 'unknown'",
        "legal_credit_status": "VARCHAR(30) NOT NULL DEFAULT 'unknown'",
        "credit_query_count_6m": "INTEGER NOT NULL DEFAULT 0",
        "credit_card_usage_rate": "FLOAT",
        "lender_count": "INTEGER NOT NULL DEFAULT 0",
        "online_loan_status": "VARCHAR(30) NOT NULL DEFAULT 'unknown'",
        "public_inflow_monthly": "FLOAT NOT NULL DEFAULT 0",
        "public_outflow_monthly": "FLOAT NOT NULL DEFAULT 0",
        "operating_flow_ratio": "FLOAT",
        "public_private_ratio": "FLOAT",
        "internal_transfer_ratio": "FLOAT",
        "fast_in_out_status": "VARCHAR(30) NOT NULL DEFAULT 'unknown'",
        "tax_credit_grade": "VARCHAR(10) NOT NULL DEFAULT 'unknown'",
        "tax_paid_12m": "FLOAT NOT NULL DEFAULT 0",
        "invoiced_revenue_12m": "FLOAT NOT NULL DEFAULT 0",
        "tax_arrears_status": "VARCHAR(30) NOT NULL DEFAULT 'unknown'",
        "revenue_growth_rate": "FLOAT",
        "enforcement_status": "VARCHAR(30) NOT NULL DEFAULT 'unknown'",
        "dishonest_status": "VARCHAR(30) NOT NULL DEFAULT 'unknown'",
        "consumption_restriction_status": "VARCHAR(30) NOT NULL DEFAULT 'unknown'",
        "lawsuit_plaintiff_status": "VARCHAR(30) NOT NULL DEFAULT 'unknown'",
        "lawsuit_defendant_status": "VARCHAR(30) NOT NULL DEFAULT 'unknown'",
        "admin_penalty_status": "VARCHAR(30) NOT NULL DEFAULT 'unknown'",
        "property_value": "FLOAT NOT NULL DEFAULT 0",
        "factory_value": "FLOAT NOT NULL DEFAULT 0",
        "land_value": "FLOAT NOT NULL DEFAULT 0",
        "vehicle_value": "FLOAT NOT NULL DEFAULT 0",
        "equipment_value": "FLOAT NOT NULL DEFAULT 0",
        "financeable_receivables": "FLOAT NOT NULL DEFAULT 0",
        "inventory_value": "FLOAT NOT NULL DEFAULT 0",
        "external_investment_value": "FLOAT NOT NULL DEFAULT 0",
        "intellectual_property_types": "TEXT NOT NULL DEFAULT ''",
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
        "customer_id": "INTEGER",
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
        "cashflow_assessment_id": "INTEGER",
        "cashflow_report_id": "INTEGER",
        "report_type": "VARCHAR(80) NOT NULL DEFAULT 'capital_health_summary'",
        "source_type": "VARCHAR(80) NOT NULL DEFAULT 'capital_assessment'",
        "source_id": "INTEGER",
        "lead_id": "INTEGER",
        "organization_id": "INTEGER",
        "assigned_user_id": "INTEGER",
        "company_name": "VARCHAR(200) NOT NULL DEFAULT ''",
        "score": "INTEGER",
        "grade": "VARCHAR(30) NOT NULL DEFAULT ''",
        "generation_status": "VARCHAR(30) NOT NULL DEFAULT 'generated'",
        "customer_id": "INTEGER",
        "public_token": "VARCHAR(100)",
        "token_expired_at": "DATETIME",
        "review_status": "VARCHAR(30) NOT NULL DEFAULT 'draft'",
        "reviewed_by": "INTEGER",
        "reviewed_at": "DATETIME",
        "review_note": "TEXT NOT NULL DEFAULT ''",
        "current_version_id": "INTEGER",
        "deleted_at":"DATETIME","deleted_by":"INTEGER","delete_reason":"TEXT NOT NULL DEFAULT ''",
    },
    "report_versions": {
        "access_level": "VARCHAR(40) NOT NULL DEFAULT 'free'",
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
    "users": {"display_name":"VARCHAR(100) NOT NULL DEFAULT ''","phone":"VARCHAR(50) NOT NULL DEFAULT ''","org_id": "INTEGER","last_login_at":"DATETIME","last_login_ip":"VARCHAR(100) NOT NULL DEFAULT ''",
        "failed_login_count":"INTEGER NOT NULL DEFAULT 0","locked_until":"DATETIME","password_changed_at":"DATETIME",
        "force_password_change":"BOOLEAN NOT NULL DEFAULT 0","two_factor_enabled":"BOOLEAN NOT NULL DEFAULT 0",
        "two_factor_secret_mock":"VARCHAR(200) NOT NULL DEFAULT ''","session_version":"INTEGER NOT NULL DEFAULT 1"},
    "consulting_cases": {
        "org_id": "INTEGER", "owner_user_id": "INTEGER", "owner_org_id": "INTEGER",
        "consultant_user_id": "INTEGER",
        "show_consultant_contact": "BOOLEAN NOT NULL DEFAULT 0",
    },
    "advisor_bookings": {
        "customer_id": "INTEGER",
        "city": "VARCHAR(100) NOT NULL DEFAULT ''",
        "service_type": "VARCHAR(80) NOT NULL DEFAULT 'high_ticket_consulting'",
        "urgency": "VARCHAR(30) NOT NULL DEFAULT 'normal'",
        "internal_note": "TEXT NOT NULL DEFAULT ''",
        "owner_user_id": "INTEGER",
        "consultant_user_id": "INTEGER",
    },
    "financing_projects": {
        "customer_id": "INTEGER",
        "org_id": "INTEGER", "owner_user_id": "INTEGER", "owner_org_id": "INTEGER",
        "consultant_user_id": "INTEGER",
        "deleted_at":"DATETIME","deleted_by":"INTEGER","delete_reason":"TEXT NOT NULL DEFAULT ''",
    },
    "customer_accounts":{
        "name":"VARCHAR(100) NOT NULL DEFAULT ''",
        "password_hash":"VARCHAR(300) NOT NULL DEFAULT ''",
        "status":"VARCHAR(20) NOT NULL DEFAULT 'active'",
        "client_login_method":"VARCHAR(20) NOT NULL DEFAULT 'password'",
        "registration_method":"VARCHAR(20) NOT NULL DEFAULT 'password'",
        "registration_source":"VARCHAR(40) NOT NULL DEFAULT 'historical_data'",
        "city":"VARCHAR(100) NOT NULL DEFAULT ''",
        "failed_login_count":"INTEGER NOT NULL DEFAULT 0",
        "locked_until":"DATETIME",
        "password_changed_at":"DATETIME",
        "activated_at":"DATETIME",
        "terms_accepted_at":"DATETIME",
        "privacy_accepted_at":"DATETIME",
        "deleted_at":"DATETIME","deleted_by":"INTEGER","delete_reason":"TEXT NOT NULL DEFAULT ''"
    },
    "internal_notifications": {
        "action_url": "VARCHAR(300) NOT NULL DEFAULT ''",
    },
    "funding_applications": {"org_id": "INTEGER", "institution_contact_id": "INTEGER"},
    "bank_products": {
        "product_code": "VARCHAR(80) NOT NULL DEFAULT ''",
        "city": "VARCHAR(100) NOT NULL DEFAULT ''", "province": "VARCHAR(100) NOT NULL DEFAULT ''",
        "min_amount": "FLOAT NOT NULL DEFAULT 0", "min_rate": "FLOAT", "max_rate": "FLOAT",
        "min_term_months": "INTEGER", "max_term_months": "INTEGER",
        "required_documents": "TEXT NOT NULL DEFAULT ''", "repayment_methods": "TEXT NOT NULL DEFAULT ''",
        "target_customer_type": "TEXT NOT NULL DEFAULT ''", "advantages": "TEXT NOT NULL DEFAULT ''",
        "disadvantages": "TEXT NOT NULL DEFAULT ''", "suitable_scenarios": "TEXT NOT NULL DEFAULT ''",
        "data_source": "VARCHAR(30) NOT NULL DEFAULT 'mock'",
        "institution_category": "TEXT NOT NULL DEFAULT ''", "product_group": "TEXT NOT NULL DEFAULT ''",
        "guarantee_method": "TEXT NOT NULL DEFAULT ''", "amount_description": "TEXT NOT NULL DEFAULT ''",
        "application_process": "TEXT NOT NULL DEFAULT ''", "access_conditions_json": "TEXT NOT NULL DEFAULT ''",
        "company_requirements": "TEXT NOT NULL DEFAULT ''", "guarantor_requirements": "TEXT NOT NULL DEFAULT ''",
        "borrower_requirements": "TEXT NOT NULL DEFAULT ''", "credit_requirements": "TEXT NOT NULL DEFAULT ''",
        "tax_requirements": "TEXT NOT NULL DEFAULT ''", "invoice_requirements": "TEXT NOT NULL DEFAULT ''",
        "cashflow_requirements": "TEXT NOT NULL DEFAULT ''", "revenue_requirements": "TEXT NOT NULL DEFAULT ''",
        "business_license_requirements": "TEXT NOT NULL DEFAULT ''", "prohibited_conditions_json": "TEXT NOT NULL DEFAULT ''",
        "required_documents_json": "TEXT NOT NULL DEFAULT ''", "extra_fields_json": "TEXT NOT NULL DEFAULT '{}'",
        "update_note": "TEXT NOT NULL DEFAULT ''", "source_file_name": "VARCHAR(300) NOT NULL DEFAULT ''",
        "source_batch_id": "VARCHAR(80) NOT NULL DEFAULT ''", "imported_at": "DATETIME",
    },
}


def _make_customer_account_anchors_nullable(changed: list[str]) -> None:
    """Allow a customer to register before creating the first assessment.

    SQLite cannot alter a column's NULL constraint in place, so legacy
    customer_accounts tables are rebuilt once while preserving rows, foreign
    keys and useful indexes. New databases already use the nullable model.
    """
    inspector = inspect(engine)
    if "customer_accounts" not in inspector.get_table_names():
        return
    columns = inspector.get_columns("customer_accounts")
    anchors = {item["name"]: item for item in columns if item["name"] in {"lead_id", "assessment_id"}}
    if not any(item.get("nullable") is False for item in anchors.values()):
        return

    with engine.begin() as connection:
        raw_columns = connection.exec_driver_sql("PRAGMA table_info('customer_accounts')").mappings().all()
        foreign_keys = connection.exec_driver_sql("PRAGMA foreign_key_list('customer_accounts')").mappings().all()
        index_rows = connection.exec_driver_sql("PRAGMA index_list('customer_accounts')").mappings().all()
        index_specs: list[tuple[bool, list[str]]] = []
        for index in index_rows:
            names = [
                row["name"] for row in connection.exec_driver_sql(
                    f'PRAGMA index_info("{index["name"]}")'
                ).mappings().all()
            ]
            if names:
                index_specs.append((bool(index["unique"]), names))

        definitions: list[str] = []
        for column in raw_columns:
            part = f'"{column["name"]}" {column["type"] or ""}'.rstrip()
            if column["pk"]:
                part += " PRIMARY KEY"
            elif column["name"] not in {"lead_id", "assessment_id"} and column["notnull"]:
                part += " NOT NULL"
            if column["dflt_value"] is not None:
                part += f' DEFAULT {column["dflt_value"]}'
            definitions.append(part)
        for fk in foreign_keys:
            clause = (
                f'FOREIGN KEY ("{fk["from"]}") REFERENCES "{fk["table"]}" ("{fk["to"]}")'
            )
            if fk["on_update"] and fk["on_update"] != "NO ACTION":
                clause += f' ON UPDATE {fk["on_update"]}'
            if fk["on_delete"] and fk["on_delete"] != "NO ACTION":
                clause += f' ON DELETE {fk["on_delete"]}'
            definitions.append(clause)

        connection.exec_driver_sql("DROP TABLE IF EXISTS customer_accounts_registration_tmp")
        connection.exec_driver_sql(
            "CREATE TABLE customer_accounts_registration_tmp (" + ", ".join(definitions) + ")"
        )
        names = ", ".join(f'"{item["name"]}"' for item in raw_columns)
        connection.exec_driver_sql(
            f"INSERT INTO customer_accounts_registration_tmp ({names}) "
            f"SELECT {names} FROM customer_accounts"
        )
        connection.exec_driver_sql("DROP TABLE customer_accounts")
        connection.exec_driver_sql(
            "ALTER TABLE customer_accounts_registration_tmp RENAME TO customer_accounts"
        )

        created: set[tuple[str, ...]] = set()
        for unique, index_columns in index_specs:
            key = tuple(index_columns)
            if key in created:
                continue
            created.add(key)
            suffix = "_".join(index_columns)
            unique_sql = "UNIQUE " if unique else ""
            where = " WHERE login_phone <> ''" if unique and index_columns == ["login_phone"] else ""
            quoted = ", ".join(f'"{name}"' for name in index_columns)
            connection.exec_driver_sql(
                f'CREATE {unique_sql}INDEX "ix_customer_accounts_rebuilt_{suffix}" '
                f'ON customer_accounts ({quoted}){where}'
            )
        if ("registration_source",) not in created:
            connection.exec_driver_sql(
                "CREATE INDEX ix_customer_accounts_registration_source "
                "ON customer_accounts (registration_source)"
            )
    changed.extend(["customer_accounts.lead_id_nullable", "customer_accounts.assessment_id_nullable"])


def _make_report_assessment_columns_nullable(changed: list[str]) -> None:
    """Allow unified reports and versions to originate outside capital assessments."""
    if engine.dialect.name != "sqlite":
        return
    for table, nullable_names in (("reports", {"assessment_id"}), ("report_versions", {"assessment_id"})):
        inspector = inspect(engine)
        if table not in inspector.get_table_names():
            continue
        columns = inspector.get_columns(table)
        if not any(item["name"] in nullable_names and item.get("nullable") is False for item in columns):
            continue
        with engine.begin() as connection:
            raw = connection.exec_driver_sql(f'PRAGMA table_info("{table}")').mappings().all()
            foreign_keys = connection.exec_driver_sql(f'PRAGMA foreign_key_list("{table}")').mappings().all()
            indexes = connection.exec_driver_sql(f'PRAGMA index_list("{table}")').mappings().all()
            index_specs = []
            for index in indexes:
                names = [row["name"] for row in connection.exec_driver_sql(
                    f'PRAGMA index_info("{index["name"]}")').mappings().all()]
                if names:
                    index_specs.append((bool(index["unique"]), names))
            definitions = []
            for column in raw:
                part = f'"{column["name"]}" {column["type"] or ""}'.rstrip()
                if column["pk"]:
                    part += " PRIMARY KEY"
                elif column["name"] not in nullable_names and column["notnull"]:
                    part += " NOT NULL"
                if column["dflt_value"] is not None:
                    part += f' DEFAULT {column["dflt_value"]}'
                definitions.append(part)
            for fk in foreign_keys:
                clause = f'FOREIGN KEY ("{fk["from"]}") REFERENCES "{fk["table"]}" ("{fk["to"]}")'
                if fk["on_update"] and fk["on_update"] != "NO ACTION": clause += f' ON UPDATE {fk["on_update"]}'
                if fk["on_delete"] and fk["on_delete"] != "NO ACTION": clause += f' ON DELETE {fk["on_delete"]}'
                definitions.append(clause)
            temp = f"{table}_source_nullable_tmp"
            connection.exec_driver_sql(f'DROP TABLE IF EXISTS "{temp}"')
            connection.exec_driver_sql(f'CREATE TABLE "{temp}" ({", ".join(definitions)})')
            names = ", ".join(f'"{item["name"]}"' for item in raw)
            connection.exec_driver_sql(f'INSERT INTO "{temp}" ({names}) SELECT {names} FROM "{table}"')
            connection.exec_driver_sql(f'DROP TABLE "{table}"')
            connection.exec_driver_sql(f'ALTER TABLE "{temp}" RENAME TO "{table}"')
            created = set()
            for unique, index_columns in index_specs:
                key = tuple(index_columns)
                if key in created:
                    continue
                created.add(key)
                unique_sql = "UNIQUE " if unique else ""
                suffix = "_".join(index_columns)
                quoted = ", ".join(f'"{name}"' for name in index_columns)
                connection.exec_driver_sql(f'CREATE {unique_sql}INDEX "ix_{table}_rebuilt_{suffix}" ON "{table}" ({quoted})')
        changed.append(f"{table}.assessment_id_nullable")


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
        if "users" in existing_tables:
            result = connection.execute(
                text(
                    "UPDATE users SET role='super_admin', is_active=1 "
                    "WHERE username='admin' AND (role NOT IN ('admin', 'super_admin') OR is_active=0)"
                )
            )
            if result.rowcount:
                changed.append("users.admin_role_repaired")
                logger.warning("DEFAULT_ADMIN_ROLE_REPAIR migration repaired rows=%s", result.rowcount)
    _make_customer_account_anchors_nullable(changed)
    _make_report_assessment_columns_nullable(changed)
    if engine.dialect.name == "sqlite":
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_reports_cashflow_report_id "
                "ON reports(cashflow_report_id) WHERE cashflow_report_id IS NOT NULL"
            )
            connection.exec_driver_sql(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_reports_source "
                "ON reports(source_type, source_id) WHERE source_id IS NOT NULL"
            )
    return changed
