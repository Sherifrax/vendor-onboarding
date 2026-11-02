"""Pydantic boundaries for intake inputs and extracted request data."""

from pydantic import BaseModel, ConfigDict, Field


class IncomingEmail(BaseModel):
    """Untrusted email payload accepted by the manual intake endpoint."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    from_email: str = Field(alias="from", min_length=3, max_length=320)
    subject: str = Field(min_length=1, max_length=998)
    body: str = Field(min_length=1, max_length=50_000)
    thread_id: str | None = Field(default=None, max_length=255)
    message_id: str | None = Field(default=None, max_length=255)


class ExtractedRequest(BaseModel):
    """Values an extractor may return; decisions remain in deterministic code."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    requestor_name: str | None = None
    requestor_email: str | None = None
    company_name: str | None = None
    entities_locations: str | None = None
    documentation_contact: str | None = None
    authorized_contact: str | None = None
    services_products: str | None = None
    vendor_country: str | None = None
    payment_terms_days: int | None = None
    estimated_annual_spend_usd: float | None = None
    currency: str | None = None
    business_justification: str | None = None


class IntakeResponse(BaseModel):
    """Stable response returned after one intake pipeline pass."""

    tracking_id: str
    outcome: str
