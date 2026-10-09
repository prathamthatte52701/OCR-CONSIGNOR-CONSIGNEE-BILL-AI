"""T14: python-jose -> PyJWT. Tokens already issued to logged-in users (minted with the OLD library
before the swap, kept in test_fixtures/jose_tokens.json with a TEST secret) must still decode;
new tokens keep the same claims / header / 7-day TTL; the algorithm stays pinned to HS256."""

import base64
import json
import time
from pathlib import Path
from typing import Any

import jwt
import pytest

from app.core import security
from app.core.config import settings
from app.core.security import TOKEN_TTL, decode_token, sign_token

FIXTURE = json.loads((Path(__file__).parent / "test_fixtures" / "jose_tokens.json").read_text())
SECRET = FIXTURE["secret"]


@pytest.fixture(autouse=True)
def _fixture_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sign / verify with the fixture's TEST secret (never the real JWT_SECRET)."""
    monkeypatch.setattr(settings, "jwt_secret", SECRET)


def _b64(data: dict[str, Any]) -> str:
    return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()


# ----------------------------------------------------------- tokens from the OLD library


def test_a_token_minted_by_python_jose_still_decodes() -> None:
    claims = decode_token(FIXTURE["validUntil2100"])
    assert claims == {
        "userId": FIXTURE["userId"],
        "tokenVersion": FIXTURE["tokenVersion"],
        "role": FIXTURE["role"],
        "exp": 4102444800,
    }


def test_an_expired_old_token_is_still_rejected() -> None:
    assert decode_token(FIXTURE["expired2020"]) is None


def test_old_token_is_rejected_under_a_different_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "jwt_secret", "a-completely-different-secret-0123456789")
    assert decode_token(FIXTURE["validUntil2100"]) is None


# ---------------------------------------------------------- new tokens: same shape as before


def test_new_tokens_keep_the_same_claims_header_and_seven_day_ttl() -> None:
    token = sign_token("abc123", 5, "user")
    old_header = jwt.get_unverified_header(FIXTURE["validUntil2100"])
    assert jwt.get_unverified_header(token) == old_header == {"alg": "HS256", "typ": "JWT"}
    claims = jwt.decode(token, SECRET, algorithms=["HS256"])
    assert set(claims) == {"userId", "tokenVersion", "role", "exp"}  # exactly the old claim set
    assert (claims["userId"], claims["tokenVersion"], claims["role"]) == ("abc123", 5, "user")
    assert TOKEN_TTL.days == 7
    assert abs(claims["exp"] - (time.time() + 7 * 86400)) < 10


def test_sign_then_decode_round_trip() -> None:
    assert decode_token(sign_token("u1", 0, "admin")) == {
        "userId": "u1",
        "tokenVersion": 0,
        "role": "admin",
        "exp": pytest.approx(time.time() + 7 * 86400, abs=10),
    }


# ------------------------------------------------------------------ attacks on the decoder


def test_alg_none_unsigned_token_is_refused() -> None:
    payload = {"userId": FIXTURE["userId"], "tokenVersion": 3, "role": "admin", "exp": 4102444800}
    unsigned = f"{_b64({'alg': 'none', 'typ': 'JWT'})}.{_b64(payload)}."
    assert decode_token(unsigned) is None
    assert decode_token(unsigned.rstrip(".")) is None


@pytest.mark.parametrize("algorithm", ["HS384", "HS512"])
def test_other_hmac_algorithms_with_the_right_secret_are_refused(algorithm: str) -> None:
    token = jwt.encode(
        {"userId": "u", "tokenVersion": 0, "role": "admin", "exp": 4102444800},
        SECRET,
        algorithm=algorithm,
    )
    assert decode_token(token) is None  # the pin: only HS256 is ever accepted


def test_tampered_payload_and_signature_are_refused() -> None:
    head, body, sig = FIXTURE["validUntil2100"].split(".")
    forged_claims = {
        "userId": FIXTURE["userId"],
        "tokenVersion": 3,
        "role": "admin",
        "exp": 9999999999,
    }
    assert decode_token(f"{head}.{_b64(forged_claims)}.{sig}") is None  # payload changed
    flipped = sig[:-2] + ("AA" if not sig.endswith("AA") else "BB")
    assert decode_token(f"{head}.{body}.{flipped}") is None  # signature changed
    assert decode_token(f"{head}.{body}.") is None  # signature stripped


def test_a_token_without_an_expiry_is_refused() -> None:
    forever = jwt.encode(
        {"userId": "u", "tokenVersion": 0, "role": "admin"}, SECRET, algorithm="HS256"
    )
    assert decode_token(forever) is None


def test_a_token_signed_with_the_wrong_secret_is_refused() -> None:
    forged = jwt.encode(
        {"userId": "u", "tokenVersion": 0, "role": "admin", "exp": 4102444800},
        "attacker-guess-0123456789abcdef0123456789",
        algorithm="HS256",
    )
    assert decode_token(forged) is None


@pytest.mark.parametrize(
    "garbage",
    [
        "",
        " ",
        "a.b.c",
        "a.b",
        "....",
        "not a jwt",
        "\x00",
        "é" * 50,
        pytest.param("A" * 100_000, id="100k-chars"),
        "Bearer x.y.z",
    ],
)
def test_garbage_never_raises_it_just_returns_none(garbage: str) -> None:
    assert decode_token(garbage) is None


def test_a_token_expiring_right_now_is_refused() -> None:
    now = int(time.time())
    stale = jwt.encode(
        {"userId": "u", "tokenVersion": 0, "role": "x", "exp": now - 1}, SECRET, algorithm="HS256"
    )
    assert decode_token(stale) is None


# ------------------------------------------------------------------------ the swap is total


def test_python_jose_is_no_longer_used_anywhere_in_the_app() -> None:
    root = Path(__file__).resolve().parents[1]
    offenders = [
        str(p.relative_to(root))
        for p in root.rglob("*.py")
        if p.name != Path(__file__).name and "jose" in p.read_text(encoding="utf-8").lower()
    ]
    # "jose" may appear only as a word inside comments/docs that explain the history
    for path in offenders:
        text = (root / path).read_text(encoding="utf-8")
        assert "from jose" not in text and "import jose" not in text, path
    assert not hasattr(security, "JWTError")
