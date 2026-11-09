"""Password hashing: right password verifies, wrong or oversize input is a plain False."""

from app.core.security import hash_password, verify_password


def test_correct_password_still_verifies() -> None:
    assert verify_password("Lg9@12345", hash_password("Lg9@12345"))


def test_wrong_password_is_rejected() -> None:
    assert not verify_password("nope", hash_password("Lg9@12345"))


def test_over_72_byte_password_is_rejected_not_a_crash() -> None:
    h = hash_password("Lg9@12345")
    assert verify_password("A" * 73, h) is False
    assert verify_password("A" * 100000, h) is False


def test_malformed_stored_hash_is_false_not_a_crash() -> None:
    assert verify_password("Lg9@12345", "not-a-bcrypt-hash") is False


def test_hashes_are_salted() -> None:
    assert hash_password("Lg9@12345") != hash_password("Lg9@12345")
