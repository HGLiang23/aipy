from fastapi.testclient import TestClient

from aipy.shared.config import AppSettings
from apps.api.main import create_app
from apps.api.routes.health import DATABASE_CHECK, REDIS_CHECK


def test_liveness_endpoint() -> None:
    client = TestClient(create_app(AppSettings(environment="test")))

    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json()["status"] == "alive"


def test_readiness_endpoint() -> None:
    """With no probes registered, readiness trivially passes."""

    client = TestClient(create_app(AppSettings(environment="test"), readiness_checks={}))

    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {}}


def test_readiness_defaults_probe_the_real_dependencies() -> None:
    """The default app must wire database and Redis, not an empty mapping.

    Deliberately does not assert the outcome: whether the dependencies answer
    depends on where the suite runs (CI has both services up; a bare checkout has
    neither). What matters is that the probes exist at all - without them a
    Kubernetes readinessProbe would report a database-less instance as usable.
    """

    client = TestClient(create_app(AppSettings(environment="test")))

    response = client.get("/health/ready")

    assert set(response.json()["checks"]) == {DATABASE_CHECK, REDIS_CHECK}


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


def test_readiness_reports_a_raising_probe_as_not_ready() -> None:
    def explode() -> bool:
        raise RuntimeError("connection refused")

    app = create_app(AppSettings(environment="test"), readiness_checks={"redis": explode})
    client = TestClient(app)

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "checks": {"redis": False}}
