"""Deterministic validation for fields extracted from untrusted email."""

import math
import re
from dataclasses import dataclass

from app.schemas import ExtractedRequest

REQUIRED_FIELDS = {
    "requestor_name": "requestor name",
    "requestor_email": "requestor email",
    "company_name": "company name",
    "entities_locations": "entities/locations",
    "documentation_contact": "documentation contact",
    "authorized_contact": "authorized contact",
    "services_products": "services/products",
    "vendor_country": "vendor country",
    "payment_terms_days": "payment terms",
    "estimated_annual_spend_usd": "estimated annual spend",
    "currency": "currency",
    "business_justification": "business justification",
}
PLACEHOLDER_PATTERN = re.compile(
    r"\b(tbd|n/?a|unknown|lorem ipsum)\b|example\.com|\[[^\]]+\]", re.I
)
EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


@dataclass(frozen=True)
class ValidationResult:
    """Outcome and exact human-readable problems for the requestor."""

    missing_or_invalid: list[str]

    @property
    def is_valid(self) -> bool:
        return not self.missing_or_invalid


def _invalid_text(value: str | None) -> bool:
    return value is None or not value.strip() or bool(PLACEHOLDER_PATTERN.search(value))


def validate_request(request: ExtractedRequest) -> ValidationResult:
    """Return required names for missing or invalid values; never infer a value."""

    problems: list[str] = []
    for field, display_name in REQUIRED_FIELDS.items():
        value = getattr(request, field)
        if isinstance(value, str) and _invalid_text(value):
            problems.append(display_name)
        elif value is None:
            problems.append(display_name)

    for field, display_name in {
        "requestor_email": "requestor email",
        "documentation_contact": "documentation contact",
        "authorized_contact": "authorized contact",
    }.items():
        value = getattr(request, field)
        if isinstance(value, str) and not EMAIL_PATTERN.search(value):
            if display_name not in problems:
                problems.append(display_name)

    if request.payment_terms_days is not None and request.payment_terms_days < 0:
        if "payment terms" not in problems:
            problems.append("payment terms")
    spend = request.estimated_annual_spend_usd
    if spend is not None and (spend < 0 or not math.isfinite(spend)):
        if "estimated annual spend" not in problems:
            problems.append("estimated annual spend")
    return ValidationResult(missing_or_invalid=problems)
