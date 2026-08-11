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
        "failed_login_count":"INTEGER NOT NULL DEFAULT 0",
        "locked_until":"DATETIME",
        "password_changed_at":"DATETIME",
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
    return changed
