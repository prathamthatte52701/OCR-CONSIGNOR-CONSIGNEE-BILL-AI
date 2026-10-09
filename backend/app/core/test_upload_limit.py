import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.core.upload_limit import TOO_BIG_DETAIL, UploadSizeLimitMiddleware

LIMIT = 1000

_app = FastAPI()
_app.add_middleware(UploadSizeLimitMiddleware, limits={"/guarded": LIMIT})


@_app.post("/guarded")
async def guarded(request: Request) -> dict[str, int]:
    return {"size": len(await request.body())}


@_app.post("/open")
async def open_route(request: Request) -> dict[str, int]:
    return {"size": len(await request.body())}


client = TestClient(_app, raise_server_exceptions=False)


def test_small_body_passes() -> None:
    r = client.post("/guarded", content=b"x" * 100)
    assert r.status_code == 200 and r.json() == {"size": 100}


def test_oversized_declared_body_gets_413() -> None:
    r = client.post("/guarded", content=b"x" * (LIMIT + 1))
    assert r.status_code == 413 and r.json()["detail"] == TOO_BIG_DETAIL


def test_unguarded_route_is_untouched() -> None:
    r = client.post("/open", content=b"x" * (LIMIT * 10))
    assert r.status_code == 200


# --- T10: declared Content-Length is refused BEFORE a single body byte is read -----------------


class _Probe:
    """Calls the middleware at ASGI level and records whether the body or the app was touched."""

    def __init__(self) -> None:
        self.receive_calls = 0
        self.app_calls = 0
        self.sent: list[dict[str, object]] = []

    async def run(self, content_length: bytes | None, method: str = "POST") -> None:
        async def inner(scope: object, receive: object, send: object) -> None:
            self.app_calls += 1

        async def receive() -> dict[str, object]:
            self.receive_calls += 1
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message: dict[str, object]) -> None:
            self.sent.append(message)

        headers = [(b"content-length", content_length)] if content_length is not None else []
        scope = {"type": "http", "method": method, "path": "/guarded", "headers": headers}
        await UploadSizeLimitMiddleware(inner, limits={"/guarded": LIMIT})(scope, receive, send)  # type: ignore[arg-type]


@pytest.mark.parametrize("declared", [b"1001", b"99999999999", b"-5", b"abc", b"1e9", b""])
async def test_bad_or_oversized_declared_length_is_413_without_reading_the_body(
    declared: bytes,
) -> None:
    probe = _Probe()
    await probe.run(declared)
    assert probe.sent[0]["status"] == 413
    assert probe.receive_calls == 0 and probe.app_calls == 0  # never read, never forwarded


@pytest.mark.parametrize("declared", [b"0", b"1", b"1000"])
async def test_declared_length_within_the_limit_is_forwarded(declared: bytes) -> None:
    probe = _Probe()
    await probe.run(declared)
    assert probe.app_calls == 1


async def test_patch_is_guarded_and_get_is_not() -> None:
    patch, get = _Probe(), _Probe()
    await patch.run(b"5000", method="PATCH")
    await get.run(b"5000", method="GET")
    assert patch.sent[0]["status"] == 413 and patch.app_calls == 0
    assert get.app_calls == 1


async def test_custom_message_is_used() -> None:
    sent: list[dict[str, object]] = []

    async def inner(scope: object, receive: object, send: object) -> None:
        return None

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, object]) -> None:
        sent.append(message)

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/guarded",
        "headers": [(b"content-length", b"9999")],
    }
    middleware = UploadSizeLimitMiddleware(inner, limits={"/guarded": LIMIT}, detail="custom text")
    await middleware(scope, receive, send)  # type: ignore[arg-type]
    assert b"custom text" in b"".join(m.get("body", b"") for m in sent)  # type: ignore[misc]
