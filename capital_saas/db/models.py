from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.database import Base


class Assessment(Base):
    __tablename__ = "assessments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    company_name: Mapped[str] = mapped_column(String(200))
    contact_name: Mapped[str] = mapped_column(String(100), default="")
    phone: Mapped[str] = mapped_column(String(30), default="")
    wechat_id: Mapped[str] = mapped_column(String(100), default="")
    city: Mapped[str] = mapped_column(String(100), default="")
    industry: Mapped[str] = mapped_column(String(100))
    years: Mapped[int] = mapped_column(Integer)
    employee_count: Mapped[int] = mapped_column(Integer)
    annual_revenue: Mapped[float] = mapped_column(Float)
    net_profit: Mapped[float] = mapped_column(Float)
    monthly_cashflow: Mapped[float] = mapped_column(Float)
    debt_total: Mapped[float] = mapped_column(Float)
    short_debt: Mapped[float] = mapped_column(Float)
    receivable_days: Mapped[int] = mapped_column(Integer)
    funding_need: Mapped[float] = mapped_column(Float)
    funding_purpose: Mapped[str] = mapped_column(String(300))
    has_collateral: Mapped[bool] = mapped_column(Boolean)
    tax_status: Mapped[bool] = mapped_column(Boolean)
    credit_status: Mapped[bool] = mapped_column(Boolean)
    knows_cashflow: Mapped[bool] = mapped_column(Boolean)
    has_budget: Mapped[bool] = mapped_column(Boolean)
    leverage_attitude: Mapped[str] = mapped_column(String(20))
    asset_efficiency: Mapped[str] = mapped_column(String(20))
    fund_usage_plan: Mapped[bool] = mapped_column(Boolean)
    score: Mapped[int] = mapped_column(Integer)
    grade: Mapped[str] = mapped_column(String(2))
    risk_level: Mapped[str] = mapped_column(String(20))
    funding_probability: Mapped[str] = mapped_column(String(20))
    source_channel: Mapped[str] = mapped_column(String(100), default="", index=True)
    source_campaign: Mapped[str] = mapped_column(String(200), default="")
    source_keyword: Mapped[str] = mapped_column(String(200), default="")
    source_landing_page: Mapped[str] = mapped_column(String(200), default="", index=True)
    utm_source: Mapped[str] = mapped_column(String(100), default="")
    utm_medium: Mapped[str] = mapped_column(String(100), default="")
    utm_campaign: Mapped[str] = mapped_column(String(200), default="")
    utm_content: Mapped[str] = mapped_column(String(200), default="")
    utm_term: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    delete_reason: Mapped[str] = mapped_column(Text, default="")

    report: Mapped["Report | None"] = relationship(back_populates="assessment", uselist=False)
    orders: Mapped[list["Order"]] = relationship(back_populates="assessment")
    lead: Mapped["Lead | None"] = relationship(back_populates="assessment", uselist=False)
    follow_tasks: Mapped[list["FollowTask"]] = relationship(back_populates="assessment")
    events: Mapped[list["Event"]] = relationship(back_populates="assessment")


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assessment_id: Mapped[int] = mapped_column(
        ForeignKey("assessments.id"), unique=True, index=True
    )
    free_summary_json: Mapped[str] = mapped_column(Text)
    full_report_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    html_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_unlocked: Mapped[bool] = mapped_column(Boolean, default=False)
    public_token: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True)
    token_expired_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    review_status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    review_note: Mapped[str] = mapped_column(Text, default="")
    current_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    delete_reason: Mapped[str] = mapped_column(Text, default="")

    assessment: Mapped[Assessment] = relationship(back_populates="report")


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id"), index=True)
    product_code: Mapped[str] = mapped_column(String(50), default="299_report", index=True)
    product_name: Mapped[str] = mapped_column(String(200))
    amount: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    pay_channel: Mapped[str] = mapped_column(String(30), default="mock")
    transaction_id: Mapped[str] = mapped_column(String(100), default="")
    buyer_contact: Mapped[str] = mapped_column(String(100), default="")
    org_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"), nullable=True, index=True)
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    owner_org_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"), nullable=True, index=True)
    source_partner_id: Mapped[int | None] = mapped_column(ForeignKey("channel_partners.id"), nullable=True, index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customer_accounts.id"), nullable=True, index=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    refund_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    source_channel: Mapped[str] = mapped_column(String(100), default="", index=True)
    source_campaign: Mapped[str] = mapped_column(String(200), default="")
    source_keyword: Mapped[str] = mapped_column(String(200), default="")
    source_landing_page: Mapped[str] = mapped_column(String(200), default="")
    utm_source: Mapped[str] = mapped_column(String(100), default="")
    utm_medium: Mapped[str] = mapped_column(String(100), default="")
    utm_campaign: Mapped[str] = mapped_column(String(200), default="")
    utm_content: Mapped[str] = mapped_column(String(200), default="")
    utm_term: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    assessment: Mapped[Assessment] = relationship(back_populates="orders")


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assessment_id: Mapped[int] = mapped_column(
        ForeignKey("assessments.id"), unique=True, index=True
    )
    company_name: Mapped[str] = mapped_column(String(200))
    contact_name: Mapped[str] = mapped_column(String(100), default="")
    phone: Mapped[str] = mapped_column(String(30), default="")
    wechat_id: Mapped[str] = mapped_column(String(100), default="")
    city: Mapped[str] = mapped_column(String(100), default="")
    lead_grade: Mapped[str] = mapped_column(String(10))
    lead_score: Mapped[int] = mapped_column(Integer, default=0)
    conversion_status: Mapped[str] = mapped_column(String(30), default="未成交")
    recommended_product: Mapped[str] = mapped_column(String(200))
    follow_status: Mapped[str] = mapped_column(String(30), default="待联系")
    next_follow_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_follow_note: Mapped[str] = mapped_column(Text, default="")
    assigned_sales: Mapped[str] = mapped_column(String(100), default="")
    assigned_sales_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    org_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"), nullable=True, index=True)
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    owner_org_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"), nullable=True, index=True)
    source_partner_id: Mapped[int | None] = mapped_column(ForeignKey("channel_partners.id"), nullable=True, index=True)
    pilot_batch_id: Mapped[int | None] = mapped_column(ForeignKey("pilot_batches.id"), nullable=True, index=True)
    pilot_stage: Mapped[str] = mapped_column(String(40), default="", index=True)
    pilot_note: Mapped[str] = mapped_column(Text, default="")
    sales_script: Mapped[str] = mapped_column(Text, default="{}")
    source_channel: Mapped[str] = mapped_column(String(100), default="", index=True)
    source_campaign: Mapped[str] = mapped_column(String(200), default="")
    source_keyword: Mapped[str] = mapped_column(String(200), default="")
    source_landing_page: Mapped[str] = mapped_column(String(200), default="", index=True)
    utm_source: Mapped[str] = mapped_column(String(100), default="")
    utm_medium: Mapped[str] = mapped_column(String(100), default="")
    utm_campaign: Mapped[str] = mapped_column(String(200), default="")
    utm_content: Mapped[str] = mapped_column(String(200), default="")
    utm_term: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    delete_reason: Mapped[str] = mapped_column(Text, default="")

    assessment: Mapped[Assessment] = relationship(back_populates="lead")
    follow_tasks: Mapped[list["FollowTask"]] = relationship(back_populates="lead")
    events: Mapped[list["Event"]] = relationship(back_populates="lead")
    assigned_sales_user: Mapped["User | None"] = relationship(foreign_keys=[assigned_sales_id])
    follow_logs: Mapped[list["LeadFollowLog"]] = relationship(back_populates="lead")
    tag_links: Mapped[list["LeadTag"]] = relationship(back_populates="lead", cascade="all, delete-orphan")


class FollowTask(Base):
    __tablename__ = "follow_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"), index=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id"), index=True)
    task_type: Mapped[str] = mapped_column(String(30))
    task_title: Mapped[str] = mapped_column(String(200))
    task_content: Mapped[str] = mapped_column(Text, default="")
    priority: Mapped[str] = mapped_column(String(20), default="medium", index=True)
    due_time: Mapped[datetime] = mapped_column(DateTime, index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now
    )

    lead: Mapped[Lead] = relationship(back_populates="follow_tasks")
    assessment: Mapped[Assessment] = relationship(back_populates="follow_tasks")


class AdvisorBooking(Base):
    __tablename__ = "advisor_bookings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id"), index=True)
    report_id: Mapped[int | None] = mapped_column(ForeignKey("reports.id"), nullable=True, index=True)
    lead_id: Mapped[int | None] = mapped_column(ForeignKey("leads.id"), nullable=True, index=True)
    company_name: Mapped[str] = mapped_column(String(200), default="")
    contact_name: Mapped[str] = mapped_column(String(100), default="")
    phone: Mapped[str] = mapped_column(String(50), default="")
    wechat_id: Mapped[str] = mapped_column(String(100), default="")
    city: Mapped[str] = mapped_column(String(100), default="")
    service_type: Mapped[str] = mapped_column(String(80), default="high_ticket_consulting", index=True)
    urgency: Mapped[str] = mapped_column(String(30), default="normal", index=True)
    consultation_focus: Mapped[str] = mapped_column(Text, default="")
    preferred_time: Mapped[str] = mapped_column(String(200), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    internal_note: Mapped[str] = mapped_column(Text, default="")
    booking_status: Mapped[str] = mapped_column(String(30), default="submitted", index=True)
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    consultant_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    follow_task_id: Mapped[int | None] = mapped_column(ForeignKey("follow_tasks.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assessment_id: Mapped[int | None] = mapped_column(
        ForeignKey("assessments.id"), nullable=True, index=True
    )
    lead_id: Mapped[int | None] = mapped_column(
        ForeignKey("leads.id"), nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(50), index=True)
    event_data_json: Mapped[str] = mapped_column(Text, default="{}")
    source_channel: Mapped[str] = mapped_column(String(100), default="", index=True)
    source_campaign: Mapped[str] = mapped_column(String(200), default="")
    source_keyword: Mapped[str] = mapped_column(String(200), default="")
    source_landing_page: Mapped[str] = mapped_column(String(200), default="")
    utm_source: Mapped[str] = mapped_column(String(100), default="")
    utm_medium: Mapped[str] = mapped_column(String(100), default="")
    utm_campaign: Mapped[str] = mapped_column(String(200), default="")
    utm_content: Mapped[str] = mapped_column(String(200), default="")
    utm_term: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    assessment: Mapped[Assessment | None] = relationship(back_populates="events")
    lead: Mapped[Lead | None] = relationship(back_populates="events")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(300))
    display_name: Mapped[str] = mapped_column(String(100), default="")
    phone: Mapped[str] = mapped_column(String(50), default="")
    role: Mapped[str] = mapped_column(String(20), default="viewer")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    org_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_login_ip: Mapped[str] = mapped_column(String(100), default="")
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    force_password_change: Mapped[bool] = mapped_column(Boolean, default=False)
    two_factor_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    two_factor_secret_mock: Mapped[str] = mapped_column(String(200), default="")
    session_version: Mapped[int] = mapped_column(Integer, default=1)
    follow_logs: Mapped[list["LeadFollowLog"]] = relationship(back_populates="user")


class SystemSetting(Base):
    __tablename__ = "system_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    value: Mapped[str] = mapped_column(Text, default="")
    description: Mapped[str] = mapped_column(String(300), default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now
    )


class ABExperiment(Base):
    __tablename__ = "ab_experiments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    experiment_key: Mapped[str] = mapped_column(String(100), index=True)
    variant: Mapped[str] = mapped_column(String(50))
    description: Mapped[str] = mapped_column(String(300), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class ABAssignment(Base):
    __tablename__ = "ab_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(String(100), index=True)
    experiment_key: Mapped[str] = mapped_column(String(100), index=True)
    variant: Mapped[str] = mapped_column(String(50), index=True)
    assessment_id: Mapped[int | None] = mapped_column(ForeignKey("assessments.id"), nullable=True, index=True)
    lead_id: Mapped[int | None] = mapped_column(ForeignKey("leads.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class LeadFollowLog(Base):
    __tablename__ = "lead_follow_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    action_type: Mapped[str] = mapped_column(String(50), index=True)
    content: Mapped[str] = mapped_column(Text, default="")
    old_status: Mapped[str] = mapped_column(String(100), default="")
    new_status: Mapped[str] = mapped_column(String(100), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    lead: Mapped[Lead] = relationship(back_populates="follow_logs")
    user: Mapped[User | None] = relationship(back_populates="follow_logs")


class SalesScriptTemplate(Base):
    __tablename__ = "sales_script_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    scenario: Mapped[str] = mapped_column(String(100), index=True)
    lead_grade: Mapped[str] = mapped_column(String(10), default="")
    product_code: Mapped[str] = mapped_column(String(50), default="")
    content: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    color: Mapped[str] = mapped_column(String(20), default="#c9a45c")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    lead_links: Mapped[list["LeadTag"]] = relationship(back_populates="tag", cascade="all, delete-orphan")


class LeadTag(Base):
    __tablename__ = "lead_tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"), index=True)
    tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    lead: Mapped[Lead] = relationship(back_populates="tag_links")
    tag: Mapped[Tag] = relationship(back_populates="lead_links")


class ReportVersion(Base):
    __tablename__ = "report_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("reports.id"), index=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id"), index=True)
    version_no: Mapped[int] = mapped_column(Integer)
    product_code: Mapped[str] = mapped_column(String(50), default="299_report")
    generator_mode: Mapped[str] = mapped_column(String(30), default="mock")
    quality_score: Mapped[int] = mapped_column(Integer, default=0)
    report_json: Mapped[str] = mapped_column(Text)
    html_content: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(100), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class BankProduct(Base):
    __tablename__ = "bank_products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_code: Mapped[str] = mapped_column(String(80), default="", index=True)
    bank_name: Mapped[str] = mapped_column(String(100), default="模拟银行")
    bank_type: Mapped[str] = mapped_column(String(50), index=True)
    product_name: Mapped[str] = mapped_column(String(150), index=True)
    product_type: Mapped[str] = mapped_column(String(80), index=True)
    city: Mapped[str] = mapped_column(String(100), default="", index=True)
    province: Mapped[str] = mapped_column(String(100), default="")
    suitable_industry: Mapped[str] = mapped_column(String(300), default="通用")
    min_revenue: Mapped[float] = mapped_column(Float, default=0)
    min_years: Mapped[int] = mapped_column(Integer, default=1)
    requires_tax_normal: Mapped[bool] = mapped_column(Boolean, default=False)
    requires_credit_normal: Mapped[bool] = mapped_column(Boolean, default=True)
    requires_collateral: Mapped[bool] = mapped_column(Boolean, default=False)
    max_amount: Mapped[float] = mapped_column(Float, default=0)
    min_amount: Mapped[float] = mapped_column(Float, default=0)
    min_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    min_term_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_term_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    interest_rate_range: Mapped[str] = mapped_column(String(80), default="以审批为准")
    loan_term: Mapped[str] = mapped_column(String(80), default="12-36个月")
    application_requirements: Mapped[str] = mapped_column(Text, default="")
    risk_notes: Mapped[str] = mapped_column(Text, default="")
    required_documents: Mapped[str] = mapped_column(Text, default="")
    repayment_methods: Mapped[str] = mapped_column(Text, default="")
    target_customer_type: Mapped[str] = mapped_column(Text, default="")
    advantages: Mapped[str] = mapped_column(Text, default="")
    disadvantages: Mapped[str] = mapped_column(Text, default="")
    suitable_scenarios: Mapped[str] = mapped_column(Text, default="")
    institution_category: Mapped[str] = mapped_column(Text, default="")
    product_group: Mapped[str] = mapped_column(Text, default="")
    guarantee_method: Mapped[str] = mapped_column(Text, default="")
    amount_description: Mapped[str] = mapped_column(Text, default="")
    application_process: Mapped[str] = mapped_column(Text, default="")
    access_conditions_json: Mapped[str] = mapped_column(Text, default="")
    company_requirements: Mapped[str] = mapped_column(Text, default="")
    guarantor_requirements: Mapped[str] = mapped_column(Text, default="")
    borrower_requirements: Mapped[str] = mapped_column(Text, default="")
    credit_requirements: Mapped[str] = mapped_column(Text, default="")
    tax_requirements: Mapped[str] = mapped_column(Text, default="")
    invoice_requirements: Mapped[str] = mapped_column(Text, default="")
    cashflow_requirements: Mapped[str] = mapped_column(Text, default="")
    revenue_requirements: Mapped[str] = mapped_column(Text, default="")
    business_license_requirements: Mapped[str] = mapped_column(Text, default="")
    prohibited_conditions_json: Mapped[str] = mapped_column(Text, default="")
    required_documents_json: Mapped[str] = mapped_column(Text, default="")
    extra_fields_json: Mapped[str] = mapped_column(Text, default="{}")
    update_note: Mapped[str] = mapped_column(Text, default="")
    data_source: Mapped[str] = mapped_column(String(30), default="mock", index=True)
    source_file_name: Mapped[str] = mapped_column(String(300), default="")
    source_batch_id: Mapped[str] = mapped_column(String(80), default="", index=True)
    imported_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class ConsultingCase(Base):
    __tablename__ = "consulting_cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[int | None] = mapped_column(ForeignKey("leads.id"), nullable=True, index=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id"), index=True)
    report_id: Mapped[int | None] = mapped_column(ForeignKey("reports.id"), nullable=True)
    product_code: Mapped[str] = mapped_column(String(50), default="1999_structure_plan")
    case_status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    consultant_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    org_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"), nullable=True, index=True)
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    owner_org_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"), nullable=True, index=True)
    consultant_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    case_summary: Mapped[str] = mapped_column(Text, default="")
    service_goal: Mapped[str] = mapped_column(Text, default="")
    next_meeting_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    show_consultant_contact: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class UploadedDocument(Base):
    __tablename__ = "uploaded_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"), index=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id"), index=True)
    file_name: Mapped[str] = mapped_column(String(300))
    file_path: Mapped[str] = mapped_column(String(500))
    file_type: Mapped[str] = mapped_column(String(30))
    document_category: Mapped[str] = mapped_column(String(100), default="其他补充资料")
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customer_accounts.id"), nullable=True, index=True)
    uploaded_source: Mapped[str] = mapped_column(String(30), default="staff", index=True)
    parse_status: Mapped[str] = mapped_column(String(30), default="pending_parse", index=True)
    verify_status: Mapped[str] = mapped_column(String(30), default="unverified", index=True)
    parsed_json: Mapped[str] = mapped_column(Text, default="{}")
    parse_error: Mapped[str] = mapped_column(Text, default="")
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    file_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    note: Mapped[str] = mapped_column(Text, default="")
    verified_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    delete_reason: Mapped[str] = mapped_column(Text, default="")


class AIGenerationLog(Base):
    __tablename__ = "ai_generation_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id"), index=True)
    report_id: Mapped[int | None] = mapped_column(ForeignKey("reports.id"), nullable=True, index=True)
    section_name: Mapped[str] = mapped_column(String(120), index=True)
    ai_mode: Mapped[str] = mapped_column(String(30), default="mock")
    model_name: Mapped[str] = mapped_column(String(100), default="")
    prompt_name: Mapped[str] = mapped_column(String(150), default="")
    status: Mapped[str] = mapped_column(String(30), default="success", index=True)
    error_message: Mapped[str] = mapped_column(Text, default="")
    token_usage_json: Mapped[str] = mapped_column(Text, default="{}")
    quality_score: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class DocumentParseTask(Base):
    __tablename__ = "document_parse_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("uploaded_documents.id"), index=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"), index=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id"), index=True)
    task_status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    parser_type: Mapped[str] = mapped_column(String(30), default="unknown")
    result_json: Mapped[str] = mapped_column(Text, default="{}")
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class DueDiligenceReport(Base):
    __tablename__ = "due_diligence_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"), unique=True, index=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id"), index=True)
    report_id: Mapped[int | None] = mapped_column(ForeignKey("reports.id"), nullable=True)
    dd_status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    completeness_score: Mapped[int] = mapped_column(Integer, default=0)
    extracted_company_json: Mapped[str] = mapped_column(Text, default="{}")
    extracted_financial_json: Mapped[str] = mapped_column(Text, default="{}")
    document_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    risk_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    advisor_notes: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class FinancingApplicationPackage(Base):
    __tablename__ = "financing_application_packages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"), index=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id"), index=True)
    package_name: Mapped[str] = mapped_column(String(200))
    package_status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    target_product_code: Mapped[str] = mapped_column(String(50), default="699_bank_match")
    target_bank_product_id: Mapped[int | None] = mapped_column(ForeignKey("bank_products.id"), nullable=True)
    document_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    checklist_json: Mapped[str] = mapped_column(Text, default="{}")
    missing_json: Mapped[str] = mapped_column(Text, default="[]")
    advisor_note: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class FinancingProject(Base):
    __tablename__ = "financing_projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"), index=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id"), index=True)
    consulting_case_id: Mapped[int | None] = mapped_column(ForeignKey("consulting_cases.id"), nullable=True)
    application_package_id: Mapped[int | None] = mapped_column(ForeignKey("financing_application_packages.id"), nullable=True)
    project_name: Mapped[str] = mapped_column(String(200))
    project_status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    target_amount: Mapped[float] = mapped_column(Float, default=0)
    approved_amount: Mapped[float] = mapped_column(Float, default=0)
    actual_disbursed_amount: Mapped[float] = mapped_column(Float, default=0)
    expected_rate: Mapped[float] = mapped_column(Float, default=0)
    final_rate: Mapped[float] = mapped_column(Float, default=0)
    expected_term: Mapped[int] = mapped_column(Integer, default=12)
    final_term: Mapped[int] = mapped_column(Integer, default=0)
    funding_purpose: Mapped[str] = mapped_column(Text, default="")
    project_owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    org_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"), nullable=True, index=True)
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    owner_org_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"), nullable=True, index=True)
    consultant_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    priority: Mapped[str] = mapped_column(String(20), default="medium", index=True)
    start_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    expected_close_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    success_result: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    failure_reason: Mapped[str] = mapped_column(Text, default="")
    project_summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    delete_reason: Mapped[str] = mapped_column(Text, default="")


class FundingApplication(Base):
    __tablename__ = "funding_applications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("financing_projects.id"), index=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"), index=True)
    bank_product_id: Mapped[int | None] = mapped_column(ForeignKey("bank_products.id"), nullable=True)
    org_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"), nullable=True, index=True)
    institution_contact_id: Mapped[int | None] = mapped_column(ForeignKey("institution_contacts.id"), nullable=True)
    institution_name: Mapped[str] = mapped_column(String(150))
    institution_type: Mapped[str] = mapped_column(String(30), default="bank", index=True)
    product_name: Mapped[str] = mapped_column(String(150))
    apply_amount: Mapped[float] = mapped_column(Float, default=0)
    approved_amount: Mapped[float] = mapped_column(Float, default=0)
    final_amount: Mapped[float] = mapped_column(Float, default=0)
    expected_rate: Mapped[float] = mapped_column(Float, default=0)
    approved_rate: Mapped[float] = mapped_column(Float, default=0)
    loan_term: Mapped[int] = mapped_column(Integer, default=12)
    repayment_method: Mapped[str] = mapped_column(String(30), default="interest_first")
    application_status: Mapped[str] = mapped_column(String(30), default="planned", index=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    disbursed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rejection_reason: Mapped[str] = mapped_column(Text, default="")
    supplement_required: Mapped[bool] = mapped_column(Boolean, default=False)
    supplement_note: Mapped[str] = mapped_column(Text, default="")
    contact_person: Mapped[str] = mapped_column(String(100), default="")
    contact_phone: Mapped[str] = mapped_column(String(50), default="")
    advisor_note: Mapped[str] = mapped_column(Text, default="")
    risk_notes: Mapped[str] = mapped_column(Text, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class ProjectTimelineEvent(Base):
    __tablename__ = "project_timeline_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("financing_projects.id"), index=True)
    funding_application_id: Mapped[int | None] = mapped_column(ForeignKey("funding_applications.id"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(50), index=True)
    event_title: Mapped[str] = mapped_column(String(200))
    event_content: Mapped[str] = mapped_column(Text, default="")
    old_status: Mapped[str] = mapped_column(String(50), default="")
    new_status: Mapped[str] = mapped_column(String(50), default="")
    operator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)


class ProjectTask(Base):
    __tablename__ = "project_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("financing_projects.id"), index=True)
    funding_application_id: Mapped[int | None] = mapped_column(ForeignKey("funding_applications.id"), nullable=True)
    task_type: Mapped[str] = mapped_column(String(50), index=True)
    task_title: Mapped[str] = mapped_column(String(200))
    task_content: Mapped[str] = mapped_column(Text, default="")
    priority: Mapped[str] = mapped_column(String(20), default="medium", index=True)
    due_time: Mapped[datetime] = mapped_column(DateTime, index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    assigned_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class ProjectReview(Base):
    __tablename__ = "project_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("financing_projects.id"), unique=True, index=True)
    review_status: Mapped[str] = mapped_column(String(30), default="draft")
    target_amount: Mapped[float] = mapped_column(Float, default=0)
    approved_amount: Mapped[float] = mapped_column(Float, default=0)
    disbursed_amount: Mapped[float] = mapped_column(Float, default=0)
    approval_days: Mapped[int] = mapped_column(Integer, default=0)
    final_rate: Mapped[float] = mapped_column(Float, default=0)
    success_factors_json: Mapped[str] = mapped_column(Text, default="[]")
    failure_reasons_json: Mapped[str] = mapped_column(Text, default="[]")
    lessons_learned: Mapped[str] = mapped_column(Text, default="")
    reusable_case_summary: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class SuccessCase(Base):
    __tablename__ = "success_cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("financing_projects.id"), unique=True, index=True)
    industry: Mapped[str] = mapped_column(String(100), default="")
    company_scale: Mapped[str] = mapped_column(String(100), default="")
    funding_amount: Mapped[float] = mapped_column(Float, default=0)
    product_type: Mapped[str] = mapped_column(String(100), default="")
    institution_type: Mapped[str] = mapped_column(String(50), default="")
    approval_days: Mapped[int] = mapped_column(Integer, default=0)
    rate_range: Mapped[str] = mapped_column(String(100), default="")
    case_title: Mapped[str] = mapped_column(String(200))
    case_summary: Mapped[str] = mapped_column(Text, default="")
    key_success_factors: Mapped[str] = mapped_column(Text, default="")
    anonymized: Mapped[bool] = mapped_column(Boolean, default=True)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class RejectionReasonLibrary(Base):
    __tablename__ = "rejection_reason_library"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reason_category: Mapped[str] = mapped_column(String(100), index=True)
    reason_detail: Mapped[str] = mapped_column(Text)
    related_project_id: Mapped[int | None] = mapped_column(ForeignKey("financing_projects.id"), nullable=True)
    related_application_id: Mapped[int | None] = mapped_column(ForeignKey("funding_applications.id"), nullable=True)
    improvement_suggestion: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_name: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    org_type: Mapped[str] = mapped_column(String(30), default="branch", index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"), nullable=True, index=True)
    city: Mapped[str] = mapped_column(String(100), default="")
    province: Mapped[str] = mapped_column(String(100), default="")
    address: Mapped[str] = mapped_column(String(300), default="")
    manager_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class ChannelPartner(Base):
    __tablename__ = "channel_partners"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    partner_name: Mapped[str] = mapped_column(String(200))
    contact_name: Mapped[str] = mapped_column(String(100), default="")
    phone: Mapped[str] = mapped_column(String(50), default="")
    wechat_id: Mapped[str] = mapped_column(String(100), default="")
    city: Mapped[str] = mapped_column(String(100), default="")
    source_code: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    commission_rate: Mapped[float] = mapped_column(Float, default=0)
    settlement_mode: Mapped[str] = mapped_column(String(30), default="manual")
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class InstitutionContact(Base):
    __tablename__ = "institution_contacts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    institution_name: Mapped[str] = mapped_column(String(200), index=True)
    institution_type: Mapped[str] = mapped_column(String(50), default="bank")
    bank_type: Mapped[str] = mapped_column(String(80), default="")
    city: Mapped[str] = mapped_column(String(100), default="", index=True)
    contact_name: Mapped[str] = mapped_column(String(100))
    contact_role: Mapped[str] = mapped_column(String(100), default="客户经理")
    phone: Mapped[str] = mapped_column(String(50), default="")
    wechat_id: Mapped[str] = mapped_column(String(100), default="")
    email: Mapped[str] = mapped_column(String(150), default="")
    product_focus: Mapped[str] = mapped_column(String(300), default="")
    cooperation_level: Mapped[str] = mapped_column(String(5), default="B")
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    rejection_count: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class CommissionRule(Base):
    __tablename__ = "commission_rules"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rule_name: Mapped[str] = mapped_column(String(200))
    role_type: Mapped[str] = mapped_column(String(50), default="sales")
    product_code: Mapped[str] = mapped_column(String(50), default="")
    trigger_event: Mapped[str] = mapped_column(String(50), index=True)
    commission_type: Mapped[str] = mapped_column(String(30), default="percentage")
    commission_value: Mapped[float] = mapped_column(Float, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class CommissionRecord(Base):
    __tablename__ = "commission_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    org_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"), nullable=True, index=True)
    partner_id: Mapped[int | None] = mapped_column(ForeignKey("channel_partners.id"), nullable=True, index=True)
    related_order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), nullable=True)
    related_project_id: Mapped[int | None] = mapped_column(ForeignKey("financing_projects.id"), nullable=True)
    trigger_event: Mapped[str] = mapped_column(String(50), index=True)
    base_amount: Mapped[float] = mapped_column(Float, default=0)
    commission_amount: Mapped[float] = mapped_column(Float, default=0)
    settlement_status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    settlement_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class CustomerAccount(Base):
    __tablename__ = "customer_accounts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"), unique=True, index=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id"), index=True)
    company_name: Mapped[str] = mapped_column(String(200))
    contact_name: Mapped[str] = mapped_column(String(100), default="")
    phone: Mapped[str] = mapped_column(String(50), default="")
    wechat_id: Mapped[str] = mapped_column(String(100), default="")
    email: Mapped[str] = mapped_column(String(150), default="")
    login_phone: Mapped[str] = mapped_column(String(50), default="", index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    delete_reason: Mapped[str] = mapped_column(Text, default="")


class CustomerAccessToken(Base):
    __tablename__ = "customer_access_tokens"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customer_accounts.id"), index=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"), index=True)
    token: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    token_type: Mapped[str] = mapped_column(String(30), default="portal_login", index=True)
    expired_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class CustomerTask(Base):
    __tablename__ = "customer_tasks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customer_accounts.id"), index=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"), index=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id"), index=True)
    related_document_id: Mapped[int | None] = mapped_column(ForeignKey("uploaded_documents.id"), nullable=True)
    related_project_id: Mapped[int | None] = mapped_column(ForeignKey("financing_projects.id"), nullable=True)
    task_type: Mapped[str] = mapped_column(String(40), default="other", index=True)
    task_title: Mapped[str] = mapped_column(String(200))
    task_content: Mapped[str] = mapped_column(Text, default="")
    priority: Mapped[str] = mapped_column(String(20), default="medium", index=True)
    due_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class CustomerMessage(Base):
    __tablename__ = "customer_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customer_accounts.id"), index=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"), index=True)
    sender_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    message_type: Mapped[str] = mapped_column(String(40), default="system", index=True)
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="unread", index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class CustomerConfirmation(Base):
    __tablename__ = "customer_confirmations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customer_accounts.id"), index=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"), index=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id"), index=True)
    related_project_id: Mapped[int | None] = mapped_column(ForeignKey("financing_projects.id"), nullable=True)
    confirmation_type: Mapped[str] = mapped_column(String(50), index=True)
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ip_address: Mapped[str] = mapped_column(String(100), default="")
    user_agent: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class NotificationTemplate(Base):
    __tablename__ = "notification_templates"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_key: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    template_name: Mapped[str] = mapped_column(String(200))
    audience_type: Mapped[str] = mapped_column(String(30), index=True)
    channel: Mapped[str] = mapped_column(String(30), default="in_app", index=True)
    category: Mapped[str] = mapped_column(String(30), default="service", index=True)
    title_template: Mapped[str] = mapped_column(String(300))
    content_template: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class NotificationJob(Base):
    __tablename__ = "notification_jobs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_key: Mapped[str] = mapped_column(String(100), index=True)
    audience_type: Mapped[str] = mapped_column(String(30), index=True)
    channel: Mapped[str] = mapped_column(String(30), index=True)
    category: Mapped[str] = mapped_column(String(30), default="service", index=True)
    recipient_type: Mapped[str] = mapped_column(String(30), index=True)
    recipient_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    recipient_customer_id: Mapped[int | None] = mapped_column(ForeignKey("customer_accounts.id"), nullable=True, index=True)
    recipient_phone: Mapped[str] = mapped_column(String(50), default="")
    recipient_email: Mapped[str] = mapped_column(String(150), default="")
    recipient_wechat_id: Mapped[str] = mapped_column(String(150), default="")
    title: Mapped[str] = mapped_column(String(300))
    content: Mapped[str] = mapped_column(Text)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    related_type: Mapped[str] = mapped_column(String(50), default="", index=True)
    related_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    send_status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class NotificationLog(Base):
    __tablename__ = "notification_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("notification_jobs.id"), index=True)
    channel: Mapped[str] = mapped_column(String(30), index=True)
    status: Mapped[str] = mapped_column(String(30), index=True)
    request_payload_json: Mapped[str] = mapped_column(Text, default="{}")
    response_json: Mapped[str] = mapped_column(Text, default="{}")
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customer_accounts.id"), nullable=True, index=True)
    receive_in_app: Mapped[bool] = mapped_column(Boolean, default=True)
    receive_email: Mapped[bool] = mapped_column(Boolean, default=False)
    receive_sms: Mapped[bool] = mapped_column(Boolean, default=False)
    receive_wecom: Mapped[bool] = mapped_column(Boolean, default=False)
    quiet_hours_start: Mapped[str] = mapped_column(String(10), default="22:00")
    quiet_hours_end: Mapped[str] = mapped_column(String(10), default="08:00")
    is_unsubscribed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class InternalNotification(Base):
    __tablename__ = "internal_notifications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    content: Mapped[str] = mapped_column(Text)
    notification_type: Mapped[str] = mapped_column(String(50), default="system", index=True)
    status: Mapped[str] = mapped_column(String(20), default="unread", index=True)
    related_type: Mapped[str] = mapped_column(String(50), default="")
    related_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action_url: Mapped[str] = mapped_column(String(300), default="")
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customer_accounts.id"), nullable=True, index=True)
    actor_type: Mapped[str] = mapped_column(String(30), default="system", index=True)
    action: Mapped[str] = mapped_column(String(100), index=True)
    target_type: Mapped[str] = mapped_column(String(80), default="", index=True)
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    before_json: Mapped[str] = mapped_column(Text, default="{}")
    after_json: Mapped[str] = mapped_column(Text, default="{}")
    ip_address: Mapped[str] = mapped_column(String(100), default="")
    user_agent: Mapped[str] = mapped_column(String(500), default="")
    risk_level: Mapped[str] = mapped_column(String(20), default="low", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)


class LegalDocument(Base):
    __tablename__ = "legal_documents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_key: Mapped[str] = mapped_column(String(100), index=True)
    title: Mapped[str] = mapped_column(String(300))
    content: Mapped[str] = mapped_column(Text)
    version: Mapped[str] = mapped_column(String(30), default="1.0")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class LegalAcceptance(Base):
    __tablename__ = "legal_acceptances"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customer_accounts.id"), index=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"), index=True)
    document_key: Mapped[str] = mapped_column(String(100), index=True)
    document_version: Mapped[str] = mapped_column(String(30))
    accepted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    ip_address: Mapped[str] = mapped_column(String(100), default="")
    user_agent: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class WorkerRun(Base):
    __tablename__ = "worker_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    worker_name: Mapped[str] = mapped_column(String(80), index=True)
    run_status: Mapped[str] = mapped_column(String(30), default="running", index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    processed_count: Mapped[int] = mapped_column(Integer, default=0)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class SetupProgress(Base):
    __tablename__ = "setup_progress"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    step_key: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    completed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class PilotBatch(Base):
    __tablename__ = "pilot_batches"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_name: Mapped[str] = mapped_column(String(200), index=True)
    batch_status: Mapped[str] = mapped_column(String(30), default="planning", index=True)
    start_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    end_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    target_customer_count: Mapped[int] = mapped_column(Integer, default=0)
    target_paid_count: Mapped[int] = mapped_column(Integer, default=0)
    target_revenue: Mapped[float] = mapped_column(Float, default=0)
    target_document_upload_count: Mapped[int] = mapped_column(Integer, default=0)
    target_project_count: Mapped[int] = mapped_column(Integer, default=0)
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class PilotInviteCode(Base):
    __tablename__ = "pilot_invite_codes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pilot_batch_id: Mapped[int] = mapped_column(ForeignKey("pilot_batches.id"), index=True)
    invite_code: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    channel_name: Mapped[str] = mapped_column(String(100), default="")
    max_uses: Mapped[int] = mapped_column(Integer, default=0)
    used_count: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class CustomerFeedback(Base):
    __tablename__ = "customer_feedback"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customer_accounts.id"), nullable=True, index=True)
    lead_id: Mapped[int | None] = mapped_column(ForeignKey("leads.id"), nullable=True, index=True)
    assessment_id: Mapped[int | None] = mapped_column(ForeignKey("assessments.id"), nullable=True, index=True)
    pilot_batch_id: Mapped[int | None] = mapped_column(ForeignKey("pilot_batches.id"), nullable=True, index=True)
    feedback_type: Mapped[str] = mapped_column(String(50), default="other", index=True)
    rating: Mapped[int] = mapped_column(Integer, default=0, index=True)
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text, default="")
    page_url: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(30), default="new", index=True)
    handled_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    handled_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class OperationIssue(Base):
    __tablename__ = "operation_issues"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    issue_type: Mapped[str] = mapped_column(String(50), default="operation_issue", index=True)
    source: Mapped[str] = mapped_column(String(50), default="admin_created", index=True)
    severity: Mapped[str] = mapped_column(String(20), default="medium", index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    related_lead_id: Mapped[int | None] = mapped_column(ForeignKey("leads.id"), nullable=True, index=True)
    related_customer_id: Mapped[int | None] = mapped_column(ForeignKey("customer_accounts.id"), nullable=True)
    related_order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), nullable=True)
    related_project_id: Mapped[int | None] = mapped_column(ForeignKey("financing_projects.id"), nullable=True)
    page_url: Mapped[str] = mapped_column(String(500), default="")
    screenshot_note: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="open", index=True)
    assigned_to: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    resolution_note: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class OperationDailyReport(Base):
    __tablename__ = "operation_daily_reports"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_date: Mapped[datetime] = mapped_column(DateTime, index=True)
    pilot_batch_id: Mapped[int | None] = mapped_column(ForeignKey("pilot_batches.id"), nullable=True, index=True)
    visits_count: Mapped[int] = mapped_column(Integer, default=0)
    assessments_count: Mapped[int] = mapped_column(Integer, default=0)
    leads_count: Mapped[int] = mapped_column(Integer, default=0)
    paid_orders_count: Mapped[int] = mapped_column(Integer, default=0)
    revenue: Mapped[float] = mapped_column(Float, default=0)
    document_upload_count: Mapped[int] = mapped_column(Integer, default=0)
    project_created_count: Mapped[int] = mapped_column(Integer, default=0)
    feedback_count: Mapped[int] = mapped_column(Integer, default=0)
    issue_count: Mapped[int] = mapped_column(Integer, default=0)
    key_findings: Mapped[str] = mapped_column(Text, default="")
    risks: Mapped[str] = mapped_column(Text, default="")
    next_actions: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class OperationWeeklyReport(Base):
    __tablename__ = "operation_weekly_reports"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    week_start: Mapped[datetime] = mapped_column(DateTime, index=True)
    week_end: Mapped[datetime] = mapped_column(DateTime, index=True)
    pilot_batch_id: Mapped[int | None] = mapped_column(ForeignKey("pilot_batches.id"), nullable=True, index=True)
    total_visits: Mapped[int] = mapped_column(Integer, default=0)
    total_assessments: Mapped[int] = mapped_column(Integer, default=0)
    total_paid_orders: Mapped[int] = mapped_column(Integer, default=0)
    total_revenue: Mapped[float] = mapped_column(Float, default=0)
    conversion_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    channel_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    product_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    feedback_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    issue_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    key_lessons: Mapped[str] = mapped_column(Text, default="")
    next_week_plan: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
