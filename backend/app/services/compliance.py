"""SIMULATED compliance screening from seeded fixtures only."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ComplianceFixture
from app.services.normalise import normalise_country, normalise_name


@dataclass(frozen=True)
class ComplianceDecision:
    """A simulated screening outcome that never claims real sanctions coverage."""

    clearance: str
    reason: str

    @property
    def is_hold(self) -> bool:
        return self.clearance != "clear"


async def screen(
    session: AsyncSession, company_name: str | None, vendor_country: str | None
) -> ComplianceDecision:
    """Find a simulated fixture match or return the explicit no-match simulation result."""

    name = normalise_name(company_name, drop_legal_suffixes=False)
    country = normalise_country(vendor_country)
    fixture = await session.scalar(
        select(ComplianceFixture).where(
            ComplianceFixture.vendor_name_normalised == name,
            ComplianceFixture.country == country,
        )
    )
    if fixture is None:
        return ComplianceDecision("clear", "SIMULATED, no match in fixtures")
    return ComplianceDecision(fixture.result, f"SIMULATED: {fixture.note}")
