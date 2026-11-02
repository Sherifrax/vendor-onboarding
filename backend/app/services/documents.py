"""Safe upload, simulated classification, and reviewer routing."""

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.mail import Mailer, send
from app.models import Document, Request
from app.services.audit import log
from app.services.gate import run as run_gate
from app.services.tokens import create
from app.storage import LocalStorage, Storage

MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
_SIGNATURES = {
    "application/pdf": b"%PDF-",
    "image/png": b"\x89PNG\r\n\x1a\n",
    "image/jpeg": b"\xff\xd8\xff",
}
_EXTENSIONS = {"application/pdf": {".pdf"}, "image/png": {".png"}, "image/jpeg": {".jpg", ".jpeg"}}


@dataclass(frozen=True)
class ClassifiedDocument:
    """A bounded classification result; uncertain is always safe to escalate."""

    label: str
    reason: str


def sniff_mime(content: bytes) -> str | None:
    """Identify the supported file types from byte signatures, never an extension."""

    for mime, signature in _SIGNATURES.items():
        if content.startswith(signature):
            return mime
    return None


def validate_upload(filename: str, content: bytes) -> tuple[str | None, str | None]:
    """Return a safe MIME or an explicit rejection reason."""

    if not content:
        return None, "file is empty"
    if len(content) > MAX_DOCUMENT_BYTES:
        return None, "file exceeds the 10 MB limit"
    mime = sniff_mime(content)
    if mime is None:
        return None, "file content is not a supported PDF, PNG, or JPEG"
    if Path(filename).suffix.lower() not in _EXTENSIONS[mime]:
        return None, "file extension does not match its content"
    return mime, None


async def _download_url(
    session: AsyncSession, storage: Storage, document: Document, tracking_id: str
) -> str:
    if not isinstance(storage, LocalStorage):
        return await storage.presigned_get_url(document.storage_key)
    token = await create(
        session,
        tracking_id,
        "document_download",
        {"storage_key": document.storage_key, "document_id": document.id},
        ttl_hours=24,
    )
    return f"{get_settings().public_base_url}/documents/download/{token}"


async def upload(
    session: AsyncSession,
    request: Request,
    files: dict[str, tuple[str, bytes]],
    required_types: list[str],
    classifier,
    storage: Storage,
    mailer: Mailer,
) -> str:
    """Persist uploads, fail closed for missing/rejected files, or route to review."""

    missing = [document_type for document_type in required_types if document_type not in files]
    if missing:
        return await _hold_missing_or_rejected(
            session, request, mailer, f"Missing required document: {', '.join(missing)}"
        )

    documents: list[Document] = []
    for document_type in required_types:
        filename, content = files[document_type]
        mime, error = validate_upload(filename, content)
        if error:
            return await _hold_missing_or_rejected(
                session, request, mailer, f"{document_type}: {error}"
            )
        classification: ClassifiedDocument = await classifier.classify_document(
            document_type, content, mime
        )
        if classification.label not in {"accepted", "received", "uncertain", "rejected"}:
            classification = ClassifiedDocument("uncertain", "classifier returned an invalid label")
        key = f"{request.tracking_id}/{hashlib.sha256(content).hexdigest()}-{Path(filename).name}"
        await storage.put(key, content, mime)
        document = Document(
            tracking_id=request.tracking_id,
            document_type=document_type,
            storage_key=key,
            original_filename=Path(filename).name,
            mime=mime,
            size_bytes=len(content),
            status=classification.label,
            ai_label=classification.label,
            ai_reason=classification.reason,
        )
        session.add(document)
        await session.flush()
        documents.append(document)
        if classification.label == "rejected":
            return await _hold_missing_or_rejected(
                session,
                request,
                mailer,
                f"{document_type} was rejected: {classification.reason}",
            )

    request.documents_clearance = "pending_review"
    request.status = "documents_pending_review"
    links = [
        await _download_url(session, storage, document, request.tracking_id)
        for document in documents
    ]
    review_token = await create(
        session,
        request.tracking_id,
        "document_review",
        {"document_ids": [document.id for document in documents]},
    )
    await log(
        session,
        request.tracking_id,
        "documents",
        "pending_review",
        "REVIEW",
        "documents received; simulated classification requires reviewer",
        "system",
    )
    await send(
        session,
        mailer,
        get_settings().master_data_email,
        "Vendor documents require review",
        "Review links:\n"
        + "\n".join(links)
        + f"\n\nDecision: {get_settings().public_base_url}/forms/review/{review_token}",
        "document_review",
        request.tracking_id,
    )
    return "pending_review"


async def _hold_missing_or_rejected(
    session: AsyncSession, request: Request, mailer: Mailer, reason: str
) -> str:
    request.documents_clearance = "rejected"
    await log(session, request.tracking_id, "documents", "rejected", "HOLD", reason, "system")
    await send(
        session,
        mailer,
        request.requestor_email or "",
        "Vendor document request on hold",
        reason,
        "document_hold",
        request.tracking_id,
    )
    await run_gate(session, request.tracking_id, mailer)
    return "held"


async def review(
    session: AsyncSession,
    tracking_id: str,
    document_ids: list[int],
    decision: str,
    notes: str,
    mailer: Mailer,
) -> str:
    """Apply a reviewer decision across the uploaded-document set and call the gate."""

    documents = (
        await session.scalars(
            select(Document).where(
                Document.tracking_id == tracking_id, Document.id.in_(document_ids)
            )
        )
    ).all()
    request = await session.get(Request, tracking_id)
    assert request is not None
    if decision == "accept_all":
        for document in documents:
            document.status = "accepted"
            document.reviewer = "document_reviewer"
            document.reviewed_at = datetime.now(UTC)
        request.documents_clearance = "accepted"
        await log(session, tracking_id, "document_review", "accepted", "PASS", notes, "reviewer")
    else:
        for document in documents:
            document.status = "rejected"
            document.reviewer = "document_reviewer"
            document.reviewed_at = datetime.now(UTC)
            document.rejection_reason = notes
        request.documents_clearance = "rejected"
        await log(session, tracking_id, "document_review", "rejected", "HOLD", notes, "reviewer")
    return (await run_gate(session, tracking_id, mailer)).outcome
