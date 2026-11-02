"""Phase 2 intake orchestration: extract, identify, upsert, validate, notify."""

import hashlib
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import ExtractionError, RequestExtractor
from app.mail import Mailer, send
from app.models import Request
from app.schemas import ExtractedRequest, IncomingEmail
from app.services.audit import log
from app.services.checks import run as run_checks
from app.services.dispatch import dispatch
from app.services.validate import ValidationResult, validate_request


@dataclass(frozen=True)
class IntakeResult:
    """Result returned to the router after a committed intake transaction."""

    tracking_id: str
    outcome: str


def _stable_digest(*values: str) -> str:
    return hashlib.sha256("\x1f".join(values).encode()).hexdigest()[:24]


def derive_thread_id(email: IncomingEmail) -> str:
    """Use provided provider thread IDs, otherwise derive a stable manual-demo ID."""

    return email.thread_id or f"manual-{_stable_digest(email.from_email, email.subject)}"


def derive_message_id(email: IncomingEmail, thread_id: str) -> str:
    """Use provider message IDs, otherwise deduplicate identical manual submissions."""

    digest = _stable_digest(thread_id, email.from_email, email.subject, email.body)
    return email.message_id or f"manual-{digest}"


def _apply_extracted(request: Request, extracted: ExtractedRequest) -> None:
    for field, value in extracted.model_dump().items():
        setattr(request, field, value)
    request.request_json = {
        **extracted.model_dump(mode="json"),
        "identity": {
            "vendor_id": request.vendor_id,
            "idempotency_key": f"VEND-{request.thread_id}",
        },
    }


async def process_email(
    session: AsyncSession,
    email: IncomingEmail,
    extractor: RequestExtractor,
    mailer: Mailer,
) -> IntakeResult:
    """Run Phase 2 intake without invoking checks reserved for later phases."""

    thread_id = derive_thread_id(email)
    message_id = derive_message_id(email, thread_id)
    existing = await session.scalar(select(Request).where(Request.thread_id == thread_id))
    tracking_id = f"VR-{thread_id}"
    if existing is not None and message_id in existing.message_ids:
        await log(
            session,
            existing.tracking_id,
            "intake",
            "replayed",
            "IGNORE",
            "message_id already processed",
            "system",
        )
        return IntakeResult(existing.tracking_id, "replay_ignored")

    try:
        extracted = await extractor.extract_request(email)
    except ExtractionError as error:
        request = existing or Request(
            tracking_id=tracking_id,
            thread_id=thread_id,
            message_ids=[],
            status="received",
            request_json={},
            vendor_id=f"VEN-{thread_id}",
        )
        if existing is None:
            session.add(request)
        request.message_ids = [*request.message_ids, message_id]
        request.status = "on_hold_extraction_error"
        await log(
            session,
            request.tracking_id,
            "extraction",
            request.status,
            "HOLD",
            str(error),
            "system",
        )
        return IntakeResult(request.tracking_id, "hold")

    request = existing or Request(
        tracking_id=tracking_id,
        thread_id=thread_id,
        message_ids=[],
        status="received",
        request_json={},
        vendor_id=f"VEN-{thread_id}",
    )
    if existing is None:
        session.add(request)
    prior_company_name = request.company_name
    prior_vendor_country = request.vendor_country
    request.message_ids = [*request.message_ids, message_id]
    _apply_extracted(request, extracted)
    validation = validate_request(extracted)
    if not validation.is_valid:
        return await _record_needs_info(session, request, email, mailer, validation)

    request.status = "validated"
    await log(
        session,
        request.tracking_id,
        "validation",
        "validated",
        "PASS",
        "all required Phase 2 fields present",
        "system",
    )
    checks = await run_checks(
        session,
        request,
        mailer,
        run_compliance=existing is None
        or prior_company_name != request.company_name
        or prior_vendor_country != request.vendor_country,
    )
    await dispatch(session, request, mailer)
    return IntakeResult(request.tracking_id, checks.outcome)


async def _record_needs_info(
    session: AsyncSession,
    request: Request,
    email: IncomingEmail,
    mailer: Mailer,
    validation: ValidationResult,
) -> IntakeResult:
    request.status = "needs_info"
    problems = ", ".join(validation.missing_or_invalid)
    requestor_email = request.requestor_email or email.from_email
    request.requestor_email = requestor_email
    await log(
        session,
        request.tracking_id,
        "validation",
        "needs_info",
        "HOLD",
        problems,
        "system",
    )
    await send(
        session,
        mailer,
        recipient=requestor_email,
        subject="Vendor request: information needed",
        body=f"Please provide the following missing or invalid fields: {problems}",
        kind="needs_info",
        tracking_id=request.tracking_id,
    )
    return IntakeResult(request.tracking_id, "needs_info")
