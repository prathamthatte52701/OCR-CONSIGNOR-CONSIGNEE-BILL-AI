"""Every API response carries the security headers; a route-set CSP is kept; HSTS only in
production."""

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from fastapi.testclient import TestClient

from app.core.security_headers import SecurityHeadersMiddleware
from app.main import app

CHAT_CSP = "default-src 'none'; sandbox"


def _app(production: bool) -> TestClient:
    a = FastAPI()
    a.add_middleware(SecurityHeadersMiddleware, is_production=production)

    @a.get("/plain")
    def plain() -> PlainTextResponse:
        return PlainTextResponse("ok")

    @a.get("/own-csp")
    def own() -> PlainTextResponse:
        return PlainTextResponse("ok", headers={"Content-Security-Policy": CHAT_CSP})

    return TestClient(a)


def test_real_app_sends_the_headers_even_on_404() -> None:
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/definitely-not-a-route")
    assert r.status_code == 404
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert r.headers["referrer-policy"] == "strict-origin-when-cross-origin"


def test_default_csp_is_applied() -> None:
    r = _app(False).get("/plain")
    assert r.headers["content-security-policy"] == "default-src 'self'; frame-ancestors 'none'"


def test_a_route_set_csp_is_not_overwritten() -> None:
    r = _app(False).get("/own-csp")
    assert r.headers["content-security-policy"] == CHAT_CSP
    assert r.headers["x-content-type-options"] == "nosniff"


def test_hsts_only_in_production() -> None:
    assert "strict-transport-security" not in _app(False).get("/plain").headers
    hsts = _app(True).get("/plain").headers["strict-transport-security"]
    assert "max-age=63072000" in hsts and "includeSubDomains" in hsts
