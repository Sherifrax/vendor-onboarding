"""Dashboard read APIs expose workflow evidence only to the in-memory admin session."""

import asyncio
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.models import Request


def test_admin_dashboard_reads_require_token_and_return_request_detail(client: TestClient) -> None:
    """The Phase 7 API supports list/detail views without exposing action-token hashes."""

    tracking_id = f"VR-dashboard-{uuid4().hex}"

    async def setup() -> None:
        async with SessionLocal.begin() as session:
            session.add(
                Request(
                    tracking_id=tracking_id,
                    thread_id=tracking_id.removeprefix("VR-"),
                    message_ids=[],
                    status="awaiting_actions",
                    request_json={},
                    company_name="Dashboard Vendor",
                    vendor_country="Singapore",
                )
            )

    asyncio.run(setup())
    assert client.get("/requests").status_code == 401
    assert client.get("/documents/1/content").status_code == 401
    headers = {"X-Admin-Token": "change-me"}
    rows = client.get("/requests", headers=headers).json()
    assert any(row["tracking_id"] == tracking_id for row in rows)
    detail = client.get(f"/requests/{tracking_id}", headers=headers).json()
    assert detail["request"]["company_name"] == "Dashboard Vendor"
    assert set(detail) == {"request", "documents", "audit", "emails"}
