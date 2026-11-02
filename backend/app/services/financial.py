"""Deterministic USD-only escalation rules."""

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class FinancialDecision:
    """One of the exact financial clearance states used by the final gate."""

    clearance: str
    reason: str


def evaluate(
    payment_terms_days: int | None,
    estimated_annual_spend_usd: float | None,
    currency: str | None,
) -> FinancialDecision:
    """Apply R1–R5 in first-match order and never infer a currency conversion."""

    if (
        payment_terms_days is None
        or payment_terms_days < 0
        or estimated_annual_spend_usd is None
        or estimated_annual_spend_usd < 0
        or not isfinite(estimated_annual_spend_usd)
        or currency != "USD"
    ):
        return FinancialDecision(
            "pending_financial_data",
            "payment terms, spend, or USD currency is missing or invalid",
        )
    if payment_terms_days >= 90:
        return FinancialDecision("cleared_automatically", "terms are at least 90 days")
    if payment_terms_days < 45:
        return FinancialDecision("pending_manager", "terms are below 45 days")
    if estimated_annual_spend_usd > 100_000:
        return FinancialDecision("pending_manager", "45–89 day terms with spend above USD 100000")
    return FinancialDecision(
        "cleared_automatically", "45–89 day terms with spend at or below USD 100000"
    )
