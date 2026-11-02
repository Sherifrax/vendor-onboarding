"""Country document requirements resolved from seeded database rows."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CountryRequirement
from app.services.normalise import normalise_country


@dataclass(frozen=True)
class RequirementDecision:
    """Exact document checklist or a fail-closed manual review outcome."""

    clearance: str
    document_types: list[str]

    @property
    def needs_manual_review(self) -> bool:
        return self.clearance == "pending_manual_review"


async def resolve(session: AsyncSession, vendor_country: str | None) -> RequirementDecision:
    """Combine universal and country rows; unknown countries never receive a guessed list."""

    country = normalise_country(vendor_country)
    requirements = (
        await session.scalars(
            select(CountryRequirement).where(CountryRequirement.country.in_(("*", country)))
        )
    ).all()
    country_specific = [row.document_type for row in requirements if row.country == country]
    if not country_specific:
        return RequirementDecision("pending_manual_review", [])
    universal = [row.document_type for row in requirements if row.country == "*"]
    return RequirementDecision("pending_upload", [*universal, *country_specific])
