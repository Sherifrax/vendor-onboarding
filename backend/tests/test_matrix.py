"""Comparable end-to-end acceptance matrix (T01–T23)."""

import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_intake import (
    test_incomplete_email_notifies_requestor_with_each_missing_field as incomplete,
)
from test_intake import (
    test_replay_is_ignored_and_same_thread_reply_updates_existing_request as replay,
)
from test_phase3_checks import (
    test_exact_and_similar_vendor_names_take_distinct_paths as duplicate_paths,
)
from test_phase3_checks import (
    test_simulated_compliance_holds_without_vendor_or_manager_messages as compliance_hold,
)
from test_phase3_checks import (
    test_vendor_master_read_error_fails_closed as vendor_read_error,
)
from test_phase4_gate import (
    test_dispatches_independent_manager_and_document_actions as dispatch,
)
from test_phase4_gate import (
    test_manager_approval_creates_vendor_and_second_gate_skips as manager_approval,
)
from test_phase4_gate import (
    test_manager_more_information_reply_resumes_without_rescreening as more_information,
)
from test_phase4_gate import (
    test_manager_rejection_holds_without_creating_vendor as manager_rejection,
)
from test_phase5_documents import (
    PDF,
    create_upload_request,
    upload_files,
)
from test_phase5_documents import (
    test_missing_required_upload_holds_and_names_the_document as missing_upload,
)
from test_phase5_documents import (
    test_received_documents_route_to_reviewer_with_private_links as stored_documents,
)
from test_phase5_documents import (
    test_reviewer_accept_creates_vendor_and_reject_persists_reason as reviewer_paths,
)
from test_phase5_documents import (
    test_uncertain_classification_is_reviewed_not_autoaccepted as uncertain_documents,
)
from test_phase6_reminders_errors import (
    test_job_wrapper_records_unexpected_failure as failing_job,
)
from test_phase6_reminders_errors import (
    test_reminder_ages_and_reruns_are_idempotent as reminders,
)

from app.models import Document, Request
from app.services.documents import ClassifiedDocument


def test_t01_singapore_vendor_all_gates_clear_created_once(client: TestClient) -> None:
    manager_approval(client)


def test_t02_incomplete_request_notifies_missing_fields(client: TestClient) -> None:
    incomplete(client)


def test_t03_flagged_vendor_is_held(client: TestClient) -> None:
    compliance_hold(client, "Lab Review Vendor", "flagged_for_review")


def test_t04_verification_error_is_held(client: TestClient) -> None:
    compliance_hold(client, "Lab Error Vendor", "verification_error")


def test_t05_exact_name_match_is_blocked(client: TestClient) -> None:
    duplicate_paths(client)


def test_t06_replayed_email_is_ignored(client: TestClient) -> None:
    replay(client)


def test_t07_manager_rejection_creates_no_vendor(client: TestClient) -> None:
    manager_rejection(client)


def test_t08_missing_required_upload_is_held(client: TestClient) -> None:
    missing_upload(client)


def test_t09_uncertain_document_routes_to_reviewer(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    uncertain_documents(client, monkeypatch)


def test_t10_reviewer_rejection_updates_tracker(client: TestClient) -> None:
    reviewer_paths(client)


def test_t11_uploaded_files_have_register_rows(client: TestClient) -> None:
    stored_documents(client)


def test_t12_reviewer_accept_and_reject_paths(client: TestClient) -> None:
    reviewer_paths(client)


def test_t13_dispatch_stamps_document_tracking(client: TestClient) -> None:
    dispatch(client)


def test_t14_day_three_reminder(client: TestClient) -> None:
    reminders()


def test_t15_day_seven_second_reminder(client: TestClient) -> None:
    reminders()


def test_t16_reminder_rerun_does_not_repeat(client: TestClient) -> None:
    reminders()


def test_t17_day_ten_escalates_once(client: TestClient) -> None:
    reminders()


def test_t18_failing_job_alerts_and_audits(monkeypatch: pytest.MonkeyPatch) -> None:
    failing_job(monkeypatch)


def test_t19_similar_name_enters_review_band(client: TestClient) -> None:
    duplicate_paths(client)


def test_t20_manager_more_information_loops_back(client: TestClient) -> None:
    more_information(client)


def test_t21_ai_rejected_document_holds(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    class RejectedClassifier:
        async def classify_document(
            self, document_type: str, content: bytes, mime: str
        ) -> ClassifiedDocument:
            return ClassifiedDocument("rejected", "simulated hard rejection")

    monkeypatch.setattr(client.app.state, "document_classifier", RejectedClassifier())
    tracking_id, token = asyncio.run(create_upload_request())
    response = client.post(
        f"/forms/documents/{token}",
        files=upload_files(("master.pdf", PDF), ("gst.pdf", PDF)),
    )
    assert "held" in response.text

    async def verify() -> None:
        from app.db import SessionLocal

        async with SessionLocal() as session:
            request = await session.get(Request, tracking_id)
            documents = (
                await session.scalars(select(Document).where(Document.tracking_id == tracking_id))
            ).all()
            assert request is not None and request.documents_clearance == "rejected"
            assert documents and documents[0].status == "rejected"

    asyncio.run(verify())


def test_t22_unreadable_vendor_table_holds(monkeypatch: pytest.MonkeyPatch) -> None:
    vendor_read_error(monkeypatch)


def test_t23_document_types_keep_canonical_names(client: TestClient) -> None:
    stored_documents(client)
