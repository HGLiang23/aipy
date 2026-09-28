"""Regression tests for the logout cookie contract.

``logout`` used to build a brand-new ``Response`` for its 204 and then delete the
cookies on the *injected* response object, which FastAPI discards in that path.
The browser kept both cookies, so "logged out" was only true on the server.
"""

from fastapi.testclient import TestClient

from aipy.shared.config import AppSettings
from apps.api.main import create_app


def _client() -> TestClient:
    return TestClient(create_app(AppSettings(environment="test")))


def test_logout_clears_both_auth_cookies() -> None:
    client = _client()
    client.cookies.set("access_token", "stale")
    client.cookies.set("refresh_token", "stale")

    response = client.post("/api/v1/auth/logout")

    assert response.status_code == 204
    cookies = response.headers.get_list("set-cookie")
    assert any(cookie.startswith("access_token=") for cookie in cookies), cookies
    assert any(cookie.startswith("refresh_token=") for cookie in cookies), cookies
    assert all("Max-Age=0" in cookie for cookie in cookies), cookies


def test_logout_expires_the_refresh_cookie_on_its_own_path() -> None:
    response = _client().post("/api/v1/auth/logout")

    refresh_headers = [
        cookie
        for cookie in response.headers.get_list("set-cookie")
        if cookie.startswith("refresh_token=")
    ]

    assert refresh_headers
    # The refresh cookie is scoped narrowly, so its deletion must be too.
    assert "Path=/api/v1/auth" in refresh_headers[0]


def test_logout_is_idempotent_without_any_cookies() -> None:
    response = _client().post("/api/v1/auth/logout")

    assert response.status_code == 204
    assert len(response.headers.get_list("set-cookie")) == 2
