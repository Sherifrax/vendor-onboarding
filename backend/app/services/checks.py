"""Phase 3 orchestration for compliance, finance, duplicates, and requirements."""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.mail import Mailer, send
from app.models import Request
from app.services.audit import log
from app.services.compliance import screen
from app.services.duplicates import detect
from app.services.financial import evaluate
from app.services.requirements import resolve


@dataclass(frozen=True)
class ChecksResult:
    """The stage at which Phase 3 leaves the shared request state."""

    outcome: str


async def run(
    session: AsyncSession, request: Request, mailer: Mailer, *, run_compliance: bool = True
) -> ChecksResult:
    """Run compliance first, then deterministic independent checks and fail closed."""

    if run_compliance:
        compliance = await screen(session, request.company_name, request.vendor_country)
        request.compliance_clearance = compliance.clearance
        await log(
            session,
            request.tracking_id,
            "compliance",
            compliance.clearance,
            "HOLD" if compliance.is_hold else "PASS",
            compliance.reason,
            "system",
        )
        if compliance.is_hold:
            request.status = "on_hold_compliance"
            await send(
                session,
                mailer,
                recipient=request.requestor_email or "",
                subject="SIMULATED compliance review pending",
                body="SIMULATED compliance screening is pending review for this request.",
                kind="compliance_hold",
                tracking_id=request.tracking_id,
            )
            return ChecksResult("compliance_hold")

    financial = evaluate(
        request.payment_terms_days,
        request.estimated_annual_spend_usd,
        request.currency,
    )
    request.financial_clearance = financial.clearance
    await log(
        session,
        request.tracking_id,
        "financial",
        financial.clearance,
        "ESCALATE" if financial.clearance == "pending_manager" else "PASS",
        financial.reason,
        "system",
    )
    if financial.clearance == "pending_financial_data":
        request.status = "needs_info"
        await send(
            session,
            mailer,
            recipient=request.requestor_email or "",
            subject="Vendor request: financial information needed",
            body="Please provide valid payment terms, annual spend, and USD currency.",
            kind="financial_info_needed",
            tracking_id=request.tracking_id,
        )
        return ChecksResult("pending_financial_data")

    duplicate = await detect(session, request.company_name, request.vendor_country)
    request.duplicate_clearance = duplicate.clearance
    duplicate_reason = duplicate.reason
    if duplicate.score is not None:
        duplicate_reason = f"{duplicate_reason}; Dice score={duplicate.score:.3f}"
    await log(
        session,
        request.tracking_id,
        "duplicate",
        duplicate.clearance,
        "HOLD" if duplicate.clearance == "blocked_duplicate" else "REVIEW",
        duplicate_reason,
        "system",
    )
    if duplicate.clearance == "blocked_duplicate":
        request.status = "on_hold_duplicate"
        await send(
            session,
            mailer,
            recipient=request.requestor_email or "",
            subject="Vendor request on hold",
            body="The vendor request is on hold because a duplicate was identified.",
            kind="duplicate_hold",
            tracking_id=request.tracking_id,
        )
        return ChecksResult("blocked_duplicate")

    requirements = await resolve(session, request.vendor_country)
    request.documents_clearance = requirements.clearance
    if requirements.needs_manual_review:
        request.status = "manual_requirements_review"
        settings = get_settings()
        await log(
            session,
            request.tracking_id,
            "requirements",
            requirements.clearance,
            "HOLD",
            "unknown country; manual requirements review required",
            "system",
        )
        for recipient in (settings.sourcing_manager_email, settings.master_data_email):
            await send(
                session,
                mailer,
                recipient=recipient,
                subject="Manual vendor document requirements review needed",
                body=f"Request {request.tracking_id} has an unknown vendor country.",
                kind="manual_requirements_review",
                tracking_id=request.tracking_id,
            )
        return ChecksResult("manual_requirements_review")

    request.status = "checks_complete"
    await log(
        session,
        request.tracking_id,
        "requirements",
        requirements.clearance,
        "WAIT",
        f"document checklist resolved: {', '.join(requirements.document_types)}",
        "system",
    )
    return ChecksResult(financial.clearance)
