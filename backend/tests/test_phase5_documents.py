"""Phase 5 private upload, review, and storage checkpoint coverage."""

import asyncio
import re
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import Document, EmailOutbox, Request, Vendor
from app.services.documents import ClassifiedDocument
from app.services.tokens import create

REQUIRED_TYPES = ["Vendor Master Form", "GST Registration Certificate"]
PDF = b"%PDF-1.7\nprivate vendor document\n"
PNG = b"\x89PNG\r\n\x1a\nprivate image"


async def create_upload_request() -> tuple[str, str]:
    """Create an otherwise-ready Singapore request and its vendor upload action."""

    suffix = uuid4().hex
    tracking_id = f"VR-documents-{suffix}"
    async with SessionLocal.begin() as session:
        session.add(
            Request(
                tracking_id=tracking_id,
                thread_id=f"documents-{suffix}",
                message_ids=[],
                status="awaiting_actions",
                request_json={},
                vendor_id=f"VEN-documents-{suffix}",
                requestor_email="requestor@example.test",
                company_name=f"Document Vendor {suffix}",
                vendor_country="Singapore",
                documentation_contact="Docs (docs@example.test)",
                authorized_contact="Owner (owner@example.test)",
                payment_terms_days=100,
                estimated_annual_spend_usd=50_000,
                currency="USD",
                financial_clearance="cleared_automatically",
                duplicate_clearance="cleared_automatically",
                documents_clearance="pending_upload",
                compliance_clearance="clear",
            )
        )
        await session.flush()
        token = await create(
            session, tracking_id, "document_upload", {"document_types": REQUIRED_TYPES}
        )
    return tracking_id, token


def upload_files(*files: tuple[str, bytes]) -> dict[str, tuple[str, bytes, str]]:
    """Build form names matching the server-rendered upload form."""

    return {
        f"file_{index}": (filename, content, "application/octet-stream")
        for index, (filename, content) in enumerate(files)
    }


async def review_token(tracking_id: str) -> str:
    """Read the local ConsoleMailer review link generated during an upload."""

    async with SessionLocal() as session:
        message = await session.scalar(
            select(EmailOutbox).where(
                EmailOutbox.tracking_id == tracking_id, EmailOutbox.kind == "document_review"
            )
        )
        assert message is not None
        match = re.search(r"/forms/review/([A-Za-z0-9_-]+)", message.body)
        assert match is not None
        return match.group(1)


def test_missing_required_upload_holds_and_names_the_document(client: TestClient) -> None:
    """A partial form is held instead of guessing that the missing file is acceptable."""

    tracking_id, token = asyncio.run(create_upload_request())
    response = client.post(f"/forms/documents/{token}", files=upload_files(("master.pdf", PDF)))
    assert "held" in response.text

    async def scenario() -> None:
        async with SessionLocal() as session:
            request = await session.get(Request, tracking_id)
            assert request is not None
            assert request.status == "on_hold_documents"
            email = await session.scalar(
                select(EmailOutbox).where(
                    EmailOutbox.tracking_id == tracking_id, EmailOutbox.kind == "document_hold"
                )
            )
            assert email is not None
            assert "GST Registration Certificate" in email.body

    asyncio.run(scenario())


def test_received_documents_route_to_reviewer_with_private_links(client: TestClient) -> None:
    """Received files route to review and local files are exposed only by signed URLs."""

    tracking_id, token = asyncio.run(create_upload_request())
    response = client.post(
        f"/forms/documents/{token}",
        files=upload_files(("master.pdf", PDF), ("gst.png", PNG)),
    )
    assert "pending_review" in response.text

    async def scenario() -> str:
        async with SessionLocal() as session:
            request = await session.get(Request, tracking_id)
            assert request is not None
            assert request.documents_clearance == "pending_review"
            message = await session.scalar(
                select(EmailOutbox).where(
                    EmailOutbox.tracking_id == tracking_id, EmailOutbox.kind == "document_review"
                )
            )
            assert message is not None
            match = re.search(r"/documents/download/([A-Za-z0-9_-]+)", message.body)
            assert match is not None
            return match.group(1)

    download_token = asyncio.run(scenario())
    download = client.get(f"/documents/download/{download_token}")
    assert download.status_code == 200
    assert download.content == PDF
    assert client.get("/data/documents/not-public.pdf").status_code == 404


def test_reviewer_accept_creates_vendor_and_reject_persists_reason(client: TestClient) -> None:
    """Reviewer decisions update every document and resume the final gate."""

    accepted_tracking, accepted_token = asyncio.run(create_upload_request())
    client.post(
        f"/forms/documents/{accepted_token}",
        files=upload_files(("master.pdf", PDF), ("gst.png", PNG)),
    )
    accept_review_token = asyncio.run(review_token(accepted_tracking))
    assert (
        "CREATE"
        in client.post(
            f"/forms/review/{accept_review_token}",
            data={"decision": "accept_all", "notes": "verified"},
        ).text
    )

    rejected_tracking, rejected_token = asyncio.run(create_upload_request())
    client.post(
        f"/forms/documents/{rejected_token}",
        files=upload_files(("master.pdf", PDF), ("gst.png", PNG)),
    )
    reject_review_token = asyncio.run(review_token(rejected_tracking))
    assert (
        "HOLD"
        in client.post(
            f"/forms/review/{reject_review_token}",
            data={"decision": "reject", "notes": "illegible"},
        ).text
    )

    async def scenario() -> None:
        async with SessionLocal() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(Vendor)
                    .where(Vendor.request_tracking_id == accepted_tracking)
                )
                == 1
            )
            rejected = (
                await session.scalars(
                    select(Document).where(Document.tracking_id == rejected_tracking)
                )
            ).all()
            assert rejected and all(document.status == "rejected" for document in rejected)
            assert all(document.rejection_reason == "illegible" for document in rejected)

    asyncio.run(scenario())


def test_renamed_executable_is_rejected_by_content(client: TestClient) -> None:
    """An executable renamed as a PDF never reaches storage or AI classification."""

    tracking_id, token = asyncio.run(create_upload_request())
    response = client.post(
        f"/forms/documents/{token}",
        files=upload_files(("master.pdf", b"MZ executable bytes"), ("gst.png", PNG)),
    )
    assert "held" in response.text

    async def scenario() -> None:
        async with SessionLocal() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(Document)
                    .where(Document.tracking_id == tracking_id)
                )
                == 0
            )

    asyncio.run(scenario())


class UncertainClassifier:
    """Classifier double for the review-band regression path."""

    async def classify_document(
        self, document_type: str, content: bytes, mime: str
    ) -> ClassifiedDocument:
        return ClassifiedDocument("uncertain", "test uncertainty")


def test_uncertain_classification_is_reviewed_not_autoaccepted(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ambiguous classification cannot clear the document gate automatically."""

    monkeypatch.setattr(client.app.state, "document_classifier", UncertainClassifier())
    tracking_id, token = asyncio.run(create_upload_request())
    client.post(
        f"/forms/documents/{token}",
        files=upload_files(("master.pdf", PDF), ("gst.png", PNG)),
    )

    async def scenario() -> None:
        async with SessionLocal() as session:
            labels = (
                await session.scalars(
                    select(Document.ai_label).where(Document.tracking_id == tracking_id)
                )
            ).all()
            assert labels == ["uncertain", "uncertain"]
            request = await session.get(Request, tracking_id)
            assert request is not None
            assert request.documents_clearance == "pending_review"

    asyncio.run(scenario())
