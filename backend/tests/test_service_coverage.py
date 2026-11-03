"""Focused coverage for deterministic fail-closed service branches."""

import asyncio
from uuid import uuid4

from app.ai import FakeAI
from app.db import SessionLocal
from app.mail import ConsoleMailer
from app.models import Request
from app.schemas import ExtractedRequest, IncomingEmail
from app.services.checks import run
from app.services.documents import upload, validate_upload
from app.services.duplicates import dice_coefficient, normalise_country, normalise_name
from app.services.intake import process_email
from app.services.requirements import resolve
from app.services.validate import validate_request


def test_check_service_paths_and_requirement_resolution() -> None:
    async def scenario() -> None:
        async with SessionLocal.begin() as session:
            suffix = uuid4().hex
            request = Request(
                tracking_id=f"VR-coverage-{suffix}",
                thread_id=f"coverage-{suffix}",
                message_ids=[],
                status="validated",
                request_json={},
                company_name="Coverage Vendor",
                vendor_country="Singapore",
                requestor_email="coverage@example.test",
                payment_terms_days=100,
                estimated_annual_spend_usd=100,
                currency="USD",
            )
            session.add(request)
            result = await run(session, request, ConsoleMailer())
            assert result.outcome == "cleared_automatically"
            assert request.documents_clearance == "pending_upload"
            assert (await resolve(session, "Atlantis")).needs_manual_review

    asyncio.run(scenario())


def test_normalisation_and_validation_negative_paths() -> None:
    assert normalise_name("Acme & Co., Ltd.") == "acme and"
    assert normalise_country("SGP") == "singapore"
    assert dice_coefficient("abc", "xyz") == 0
    assert dice_coefficient("", "") == 1
    result = validate_request(ExtractedRequest())
    assert not result.is_valid


def test_intake_service_directly_covers_new_and_replay_paths() -> None:
    async def scenario() -> None:
        suffix = uuid4().hex
        email = IncomingEmail(
            from_email="coverage@example.test",
            subject="coverage",
            body=(
                "Q1 Company Name: Coverage Intake\nQ2 Entities/Locations: Singapore\n"
                "Q3 Documentation Contact: docs@example.test\n"
                "Q4 Authorized Contact: owner@example.test\n"
                "Q5 Services/Products: supplies\nPayment Terms: 100 days\n"
                "Estimated Annual Spend: $100 USD\nVendor Country: Singapore\n"
                "Business Justification: testing"
            ),
            thread_id=f"intake-{suffix}",
            message_id=f"message-{suffix}",
        )
        async with SessionLocal.begin() as session:
            result = await process_email(session, email, FakeAI(), ConsoleMailer())
            assert result.outcome == "cleared_automatically"
        async with SessionLocal.begin() as session:
            result = await process_email(session, email, FakeAI(), ConsoleMailer())
            assert result.outcome == "replay_ignored"

    asyncio.run(scenario())


def test_document_service_direct_upload_routes_to_review() -> None:
    async def scenario() -> None:
        suffix = uuid4().hex
        async with SessionLocal.begin() as session:
            request = Request(
                tracking_id=f"VR-upload-{suffix}",
                thread_id=f"upload-{suffix}",
                message_ids=[],
                status="awaiting_actions",
                request_json={},
                documents_clearance="pending_upload",
            )
            session.add(request)
            await session.flush()
            from app.main import app

            result = await upload(
                session,
                request,
                {"Vendor Master Form": ("form.pdf", b"%PDF-1.4\nform")},
                ["Vendor Master Form"],
                FakeAI(),
                app.state.storage,
                ConsoleMailer(),
            )
            assert result == "pending_review"

    asyncio.run(scenario())


def test_document_validation_rejects_empty_and_bad_content() -> None:
    assert validate_upload("empty.pdf", b"")[1] == "file is empty"
    assert validate_upload("bad.pdf", b"not a document")[1] is not None
    assert validate_upload("wrong.exe", b"%PDF-1.4")[1] is not None
