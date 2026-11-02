"""Fail-closed duplicate detection against the simulated vendor master."""

from collections import Counter
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Vendor
from app.services.normalise import normalise_country, normalise_name


@dataclass(frozen=True)
class DuplicateDecision:
    """Duplicate result plus an auditable reason and optional similarity score."""

    clearance: str
    reason: str
    score: float | None = None


def dice_coefficient(left: str, right: str) -> float:
    """Return multiset-aware Dice similarity across non-whitespace bigrams."""

    # Separators only delimit words; letting spaces count as matching bigrams
    # inflates near-matches without adding vendor-name evidence.
    left = "".join(left.split())
    right = "".join(right.split())
    if len(left) < 2 or len(right) < 2:
        return 1.0 if left == right else 0.0
    left_bigrams = Counter(left[index : index + 2] for index in range(len(left) - 1))
    right_bigrams = Counter(right[index : index + 2] for index in range(len(right) - 1))
    shared = sum((left_bigrams & right_bigrams).values())
    return 2 * shared / (sum(left_bigrams.values()) + sum(right_bigrams.values()))


async def detect(
    session: AsyncSession, company_name: str | None, vendor_country: str | None
) -> DuplicateDecision:
    """Detect exact and near duplicates; database uncertainty always becomes HOLD."""

    name = normalise_name(company_name)
    country = normalise_country(vendor_country)
    if not name or not country:
        return DuplicateDecision("blocked_duplicate", "missing readable name or country")
    try:
        vendors = (await session.scalars(select(Vendor))).all()
    except SQLAlchemyError:
        return DuplicateDecision("blocked_duplicate", "vendor master could not be read")

    for vendor in vendors:
        if not vendor.normalised_name:
            return DuplicateDecision("blocked_duplicate", "vendor master contains unreadable name")
        if normalise_country(vendor.normalised_country) != country:
            continue
        candidate = normalise_name(vendor.normalised_name)
        if candidate == name:
            return DuplicateDecision("blocked_duplicate", "exact normalised name match")
        score = dice_coefficient(name, candidate)
        if score >= 0.75:
            return DuplicateDecision("pending_review", "similar vendor name requires review", score)
    return DuplicateDecision("cleared_automatically", "no duplicate match")
