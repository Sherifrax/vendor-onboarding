"""Final-gate rules and idempotent vendor creation."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.mail import Mailer, send
from app.models import Request, Vendor
from app.services.audit import log
from app.services.dispatch import contact_email
from app.services.normalise import normalise_country, normalise_name

_CLEARED = {
    "financial": {"cleared_automatically", "cleared_by_human_review"},
    "duplicate": {"cleared_automatically", "cleared_by_human_review"},
    "documents": {"accepted"},
    "compliance": {"clear"},
}


@dataclass(frozen=True)
class GateResult:
    """The only terminal or waiting outcomes emitted by the final gate."""

    outcome: str
    reason: str | None = None


def _clearance_values(request: Request) -> dict[str, str | None]:
    return {
        "financial": request.financial_clearance,
        "duplicate": request.duplicate_clearance,
        "documents": request.documents_clearance,
        "compliance": request.compliance_clearance,
    }


async def run(session: AsyncSession, tracking_id: str, mailer: Mailer) -> GateResult:
    """Read state fresh, apply HOLD-before-WAIT, then create one vendor at most."""

    request = await session.scalar(
        select(Request).where(Request.tracking_id == tracking_id).with_for_update()
    )
    if request is None:
        return GateResult("HOLD", "request not found")
    if request.status == "vendor_created" or request.status.startswith("on_hold_"):
        return GateResult("SKIP")

    values = _clearance_values(request)
    rejected = next(
        (
            name
            for name, value in values.items()
            if value and value not in _CLEARED[name] and not value.startswith("pending")
        ),
        None,
    )
    if rejected is not None:
        reason = f"{rejected} clearance is {values[rejected]}"
        request.status = f"on_hold_{rejected}"
        request.gate_status = "HOLD"
        await log(session, tracking_id, "gate", request.status, "HOLD", reason, "system")
        await send(
            session,
            mailer,
            request.requestor_email or "",
            "Vendor request on hold",
            f"Your request is on hold: {reason}.",
            "gate_hold",
            tracking_id,
        )
        return GateResult("HOLD", reason)

    if any(value not in _CLEARED[name] for name, value in values.items()):
        request.gate_status = "WAIT"
        await log(session, tracking_id, "gate", "waiting", "WAIT", "clearances pending", "system")
        return GateResult("WAIT")

    vendor_id = request.vendor_id or f"VEN-{request.thread_id}"
    vendor = Vendor(
        vendor_id=vendor_id,
        company_name=request.company_name or "",
        normalised_name=normalise_name(request.company_name),
        vendor_country=request.vendor_country or "",
        normalised_country=normalise_country(request.vendor_country),
        addresses_contacts={
            "documentation_contact": request.documentation_contact,
            "authorized_contact": request.authorized_contact,
        },
        payment_terms_days=request.payment_terms_days,
        estimated_annual_spend_usd=request.estimated_annual_spend_usd,
        idempotency_key=f"VEND-{request.thread_id}",
        request_tracking_id=request.tracking_id,
        status="active",
        is_synthetic=False,
    )
    try:
        async with session.begin_nested():
            session.add(vendor)
            await session.flush()
    except IntegrityError:
        request.status = "vendor_created"
        request.gate_status = "SKIP"
        return GateResult("SKIP")

    request.vendor_id = vendor_id
    request.status = "vendor_created"
    request.gate_status = "CREATE"
    await log(
        session,
        tracking_id,
        "gate",
        "vendor_created",
        "CREATE",
        "all checks cleared",
        "system",
        vendor_id,
    )
    settings = get_settings()
    notices = [
        (
            request.requestor_email or "",
            "Vendor created",
            "Your vendor request has been created.",
            "vendor_created_requestor",
        ),
        (
            contact_email(request.authorized_contact) or "",
            "Vendor onboarding complete",
            "Welcome. Your onboarding is complete.",
            "vendor_created_vendor",
        ),
        (
            settings.master_data_email,
            "New vendor created",
            f"Vendor {vendor_id} was created for request {tracking_id}.",
            "vendor_created_master_data",
        ),
    ]
    for recipient, subject, body, kind in notices:
        await send(session, mailer, recipient, subject, body, kind, tracking_id)
    return GateResult("CREATE")
