from fastapi.testclient import TestClient


def test_openapi_exposes_health_endpoint(client: TestClient) -> None:
    """The initial API exposes its planned health endpoint."""

    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert "/health" in response.json()["paths"]
