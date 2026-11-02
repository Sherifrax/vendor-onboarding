"""Idempotent local reference data seed."""

import asyncio

from app.db import SessionLocal
from app.models import ComplianceFixture, CountryRequirement, Request, Vendor
from sqlalchemy import select


async def add_once(
    session, model, where: dict[str, object], values: dict[str, object]
) -> None:
    """Insert one seed record only when its stable natural key is absent."""

    if await session.scalar(select(model).filter_by(**where)) is None:
        session.add(model(**values))


async def seed_synthetic_vendor(
    session, thread_id: str, company_name: str, country: str
) -> None:
    """Create a request/vendor pair required by the vendor foreign key."""

    tracking_id = f"VR-SEED-{thread_id}"
    await add_once(
        session,
        Request,
        {"tracking_id": tracking_id},
        {
            "tracking_id": tracking_id,
            "thread_id": f"seed-{thread_id.lower()}",
            "message_ids": [],
            "status": "vendor_created",
            "request_json": {},
        },
    )
    await add_once(
        session,
        Vendor,
        {"vendor_id": f"VEN-SEED-{thread_id}"},
        {
            "vendor_id": f"VEN-SEED-{thread_id}",
            "company_name": company_name,
            "normalised_name": company_name.lower(),
            "vendor_country": country.title(),
            "normalised_country": country,
            "addresses_contacts": {},
            "idempotency_key": f"VEND-SEED-{thread_id}",
            "request_tracking_id": tracking_id,
            "status": "active",
            "is_synthetic": True,
        },
    )


async def main() -> None:
    async with SessionLocal() as s:
        requirements = [
            ("*", "Vendor Master Form"),
            ("singapore", "GST Registration Certificate"),
            ("singapore", "ACRA Business Registration Certificate"),
            ("australia", "ABN Registration Certificate"),
            ("australia", "GST Registration Evidence"),
        ]
        for country, document_type in requirements:
            await add_once(
                s,
                CountryRequirement,
                {"country": country, "document_type": document_type},
                {
                    "country": country,
                    "document_type": document_type,
                    "validation_rule": "required",
                },
            )
        fixtures = [
            ("acme supplies pte ltd", "clear"),
            ("lab review vendor", "flagged_for_review"),
            ("lab error vendor", "verification_error"),
        ]
        for name, result in fixtures:
            await add_once(
                s,
                ComplianceFixture,
                {"vendor_name_normalised": name, "country": "singapore"},
                {
                    "vendor_name_normalised": name,
                    "country": "singapore",
                    "result": result,
                    "note": "SIMULATED fixture",
                },
            )
        await seed_synthetic_vendor(s, "HARBOR", "Harbor Office Supplies", "singapore")
        await seed_synthetic_vendor(s, "SOUTHERN", "Southern Stationery", "australia")
        await seed_synthetic_vendor(s, "NORTHSTAR", "Northstar Components", "singapore")
        await s.commit()


if __name__ == "__main__":
    asyncio.run(main())
