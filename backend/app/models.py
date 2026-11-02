"""PostgreSQL persistence models for the vendor-onboarding state machine."""

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Timestamped:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Request(Timestamped, Base):
    __tablename__ = "requests"
    tracking_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    thread_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    message_ids: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    status: Mapped[str] = mapped_column(String(100), nullable=False, default="received")
    requestor_name: Mapped[str | None] = mapped_column(String(255))
    requestor_email: Mapped[str | None] = mapped_column(String(320))
    company_name: Mapped[str | None] = mapped_column(String(500))
    entities_locations: Mapped[str | None] = mapped_column(Text)
    documentation_contact: Mapped[str | None] = mapped_column(Text)
    authorized_contact: Mapped[str | None] = mapped_column(Text)
    services_products: Mapped[str | None] = mapped_column(Text)
    vendor_country: Mapped[str | None] = mapped_column(String(100))
    payment_terms_days: Mapped[int | None] = mapped_column(Integer)
    estimated_annual_spend_usd: Mapped[float | None] = mapped_column()
    currency: Mapped[str | None] = mapped_column(String(10))
    business_justification: Mapped[str | None] = mapped_column(Text)
    request_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    financial_clearance: Mapped[str | None] = mapped_column(String(100))
    duplicate_clearance: Mapped[str | None] = mapped_column(String(100))
    documents_clearance: Mapped[str | None] = mapped_column(String(100))
    compliance_clearance: Mapped[str | None] = mapped_column(String(100))
    gate_status: Mapped[str | None] = mapped_column(String(100))
    documents_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reminder_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    vendor_id: Mapped[str | None] = mapped_column(String(255), unique=True)


class Vendor(Base):
    __tablename__ = "vendors"
    vendor_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    company_name: Mapped[str] = mapped_column(String(500), nullable=False)
    normalised_name: Mapped[str] = mapped_column(String(500), nullable=False)
    vendor_country: Mapped[str] = mapped_column(String(100), nullable=False)
    normalised_country: Mapped[str] = mapped_column(String(100), nullable=False)
    addresses_contacts: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    payment_terms_days: Mapped[int | None] = mapped_column(Integer)
    estimated_annual_spend_usd: Mapped[float | None] = mapped_column()
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    request_tracking_id: Mapped[str] = mapped_column(
        ForeignKey("requests.tracking_id"), unique=True
    )
    status: Mapped[str] = mapped_column(String(100), nullable=False, default="active")
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    tracking_id: Mapped[str] = mapped_column(ForeignKey("requests.tracking_id"), nullable=False)
    document_type: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    mime: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="received")
    ai_label: Mapped[str | None] = mapped_column(String(50))
    ai_reason: Mapped[str | None] = mapped_column(Text)
    reviewer: Mapped[str | None] = mapped_column(String(255))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_log"
    event_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    tracking_id: Mapped[str | None] = mapped_column(String(255), index=True)
    vendor_id: Mapped[str | None] = mapped_column(String(255))
    timestamp_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    stage: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(100), nullable=False)
    decision: Mapped[str] = mapped_column(String(100), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)


class CountryRequirement(Base):
    __tablename__ = "country_requirements"
    id: Mapped[int] = mapped_column(primary_key=True)
    country: Mapped[str] = mapped_column(String(100), nullable=False)
    document_type: Mapped[str] = mapped_column(String(255), nullable=False)
    validation_rule: Mapped[str | None] = mapped_column(Text)


class ComplianceFixture(Base):
    __tablename__ = "compliance_fixtures"
    id: Mapped[int] = mapped_column(primary_key=True)
    vendor_name_normalised: Mapped[str] = mapped_column(String(500), nullable=False)
    country: Mapped[str] = mapped_column(String(100), nullable=False)
    result: Mapped[str] = mapped_column(String(50), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)


class ActionToken(Base):
    __tablename__ = "action_tokens"
    token_hash: Mapped[str] = mapped_column(String(128), primary_key=True)
    tracking_id: Mapped[str] = mapped_column(ForeignKey("requests.tracking_id"), nullable=False)
    purpose: Mapped[str] = mapped_column(String(100), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class EmailOutbox(Base):
    __tablename__ = "email_outbox"
    id: Mapped[int] = mapped_column(primary_key=True)
    tracking_id: Mapped[str | None] = mapped_column(ForeignKey("requests.tracking_id"))
    recipient: Mapped[str] = mapped_column(String(320), nullable=False)
    subject: Mapped[str] = mapped_column(String(998), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    message_id: Mapped[str | None] = mapped_column(String(255))
