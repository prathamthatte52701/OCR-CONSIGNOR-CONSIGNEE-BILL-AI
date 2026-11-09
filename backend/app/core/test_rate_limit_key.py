"""The per-IP rate-limit key is `request.client.host` and nothing else, so uvicorn's own
`--proxy-headers --forwarded-allow-ips=<proxy>` (which rewrites request.client only for a trusted
proxy) is the single place a proxy address can change it. A forged X-Forwarded-For header that no
trusted proxy rewrote must be ignored."""

from starlette.requests import Request

from app.core.rate_limit import limiter, user_or_ip_key


def _request(client: tuple[str, int] | None, headers: dict[str, str]) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "query_string": b"",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "client": client,
    }
    return Request(scope)


def test_key_is_the_connecting_address() -> None:
    assert limiter._key_func(_request(("203.0.113.7", 5555), {})) == "203.0.113.7"


def test_spoofed_forwarded_headers_are_ignored() -> None:
    spoof = {
        "X-Forwarded-For": "198.51.100.99",
        "X-Real-IP": "198.51.100.98",
        "Forwarded": "for=198.51.100.97",
    }
    request = _request(("203.0.113.7", 5555), spoof)
    assert limiter._key_func(request) == "203.0.113.7"
    assert user_or_ip_key(request) == "203.0.113.7"


def test_a_rewritten_client_host_is_what_the_key_uses() -> None:
    """What uvicorn does for a trusted proxy: it replaces request.client with the forwarded
    address. The key follows request.client, so that rewrite is all it needs."""
    assert limiter._key_func(_request(("198.51.100.5", 0), {})) == "198.51.100.5"


def test_no_client_does_not_crash() -> None:
    assert isinstance(limiter._key_func(_request(None, {})), str)
