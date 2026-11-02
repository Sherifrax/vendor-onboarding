"""Shared test fixtures for the backend suite."""

import pytest
from fastapi.testclient import TestClient

from app.ai import FakeAI
from app.main import app


@pytest.fixture
def client() -> TestClient:
    """Provide an isolated HTTP client for endpoint tests."""

    return TestClient(app)


@pytest.fixture(autouse=True)
def fake_extractor_for_tests() -> None:
    """Keep tests deterministic even when a developer enables local live extraction."""

    original = app.state.extractor
    app.state.extractor = FakeAI()
    yield
    app.state.extractor = original
