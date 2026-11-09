"""Email validation and normalisation as the app really does them."""

import pytest

from app.core.validators import is_valid_email, normalize_email


@pytest.mark.parametrize("email", ["a.b+c@example.co.in", "x@y.io", "UPPER@Example.COM"])
def test_normal_emails_are_valid(email: str) -> None:
    assert is_valid_email(email)


@pytest.mark.parametrize(
    "email",
    ["", "plain", "no-at.example.com", "@example.com", "a@", "a@b", "a b@x.com", "a@@x.com"],
)
def test_bad_forms_are_rejected(email: str) -> None:
    assert not is_valid_email(email)


def test_normalize_trims_and_lowercases() -> None:
    assert normalize_email("  Mixed.Case@Example.COM \n") == "mixed.case@example.com"
    assert normalize_email("a@b.co") == "a@b.co"


def test_normalised_email_is_still_valid() -> None:
    assert is_valid_email(normalize_email("  A@B.CO "))
