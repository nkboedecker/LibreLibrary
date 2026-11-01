"""Test the application's public surface."""

from fastapi.testclient import TestClient

from librelibrary import __version__
from librelibrary.app import create_app
from librelibrary.settings import Settings


def test_health_reports_ok_and_version() -> None:
    """The health endpoint answers without authentication."""
    response = TestClient(create_app()).get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


def test_health_is_in_the_openapi_spec() -> None:
    """The health endpoint is documented."""
    spec = create_app().openapi()

    assert spec["paths"]["/api/v1/health"]["get"]["operationId"] == "health_get"


def _redirect_location(settings: Settings, headers: dict[str, str]) -> str:
    """Request the health check with a trailing slash and return the redirect target."""
    client = TestClient(
        create_app(settings), client=("127.0.0.1", 50000), follow_redirects=False
    )
    response = client.get("/api/v1/health/", headers=headers)

    assert response.status_code == 307
    return str(response.headers["location"])


def test_forwarded_proto_is_used_behind_a_trusted_proxy() -> None:
    """A redirect keeps the client's scheme when a trusted proxy ended TLS."""
    settings = Settings(trusted_proxies=["127.0.0.1/32"])

    location = _redirect_location(settings, {"X-Forwarded-Proto": "https"})

    assert location == "https://testserver/api/v1/health"


def test_forwarded_proto_is_ignored_from_untrusted_clients() -> None:
    """A forged header can't change the scheme of a redirect."""
    location = _redirect_location(Settings(), {"X-Forwarded-Proto": "https"})

    assert location == "http://testserver/api/v1/health"


def test_unknown_forwarded_proto_is_ignored() -> None:
    """Only http and https are believed, even from a trusted proxy."""
    settings = Settings(trusted_proxies=["127.0.0.1/32"])

    location = _redirect_location(settings, {"X-Forwarded-Proto": "gopher"})

    assert location == "http://testserver/api/v1/health"
