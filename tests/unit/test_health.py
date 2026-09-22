from fastapi.testclient import TestClient

from aipy.shared.config import AppSettings
from apps.api.main import create_app


def test_liveness_endpoint() -> None:
    client = TestClient(create_app(AppSettings(environment="test")))

    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json()["status"] == "alive"


def test_readiness_endpoint() -> None:
    client = TestClient(create_app(AppSettings(environment="test")))

    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {}}


def test_readiness_failure_returns_service_unavailable() -> None:
    app = create_app(
        AppSettings(environment="test"),
        readiness_checks={"database": lambda: False},
    )
    client = TestClient(app)

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {"database": False},
    }
