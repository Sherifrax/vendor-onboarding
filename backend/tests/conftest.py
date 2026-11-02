"""Shared test fixtures for the backend suite."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    """Provide an isolated HTTP client for endpoint tests."""

    return TestClient(app)
