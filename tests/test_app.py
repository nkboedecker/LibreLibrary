"""Test the application's public surface."""

from fastapi.testclient import TestClient

from librelibrary import __version__
from librelibrary.app import create_app


def test_health_reports_ok_and_version() -> None:
    """The health endpoint answers without authentication."""
    response = TestClient(create_app()).get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


def test_health_is_in_the_openapi_spec() -> None:
    """The health endpoint is documented."""
    spec = create_app().openapi()

    assert spec["paths"]["/api/v1/health"]["get"]["operationId"] == "health_get"
