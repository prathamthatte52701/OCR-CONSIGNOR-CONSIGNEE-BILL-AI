"""T9: password rules - 8..64 BYTES, character classes, control/whitespace ban, common-password
blocklist (lowercase + strip trailing digits/symbols), and "contains your username / email"."""

import pytest

from app.core import common_passwords
from app.core.security import hash_password, verify_password
from app.core.validators import (
    PASSWORD_COMMON_ERROR,
    PASSWORD_LENGTH_ERROR,
    PASSWORD_PERSONAL_ERROR,
    PASSWORD_RULE_ERROR,
    is_common_password,
    is_valid_password,
    password_problem,
)

STRONG = "Zr8!kQ2mXv"


def test_a_strong_password_passes_everything() -> None:
    assert password_problem(STRONG, "alice", "alice@example.com") is None
    assert is_valid_password(STRONG)


@pytest.mark.parametrize(
    ("password", "ok"),
    [
        ("Ab1!" + "x" * 3, False),  # 7 bytes
        ("Ab1!" + "x" * 4, True),  # 8 bytes
        ("Ab1!" + "x" * 60, True),  # 64 bytes
        ("Ab1!" + "x" * 61, False),  # 65 bytes
        ("Ab1!" + "x" * 500, False),
        ("Ab1!" + "é" * 30, True),  # 4 + 60 = 64 bytes although only 34 characters
        ("Ab1!" + "é" * 31, False),  # 66 bytes although only 35 characters
        ("Ab1!" + "\U0001f600" * 15, True),  # 4 + 60 = 64 bytes (4-byte emoji)
        ("Ab1!" + "\U0001f600" * 16, False),  # 68 bytes
        ("Aé1!", True),  # 5 bytes is too short, see next line
    ],
)
def test_length_is_counted_in_bytes_not_characters(password: str, ok: bool) -> None:
    if password == "Aé1!":
        ok = False  # 5 bytes: below the 8-byte minimum
    assert is_valid_password(password) is ok
    if not ok and len(password.encode()) > 64:
        assert password_problem(password) == PASSWORD_LENGTH_ERROR


def test_a_64_byte_password_is_never_truncated_by_bcrypt() -> None:
    """bcrypt only reads 72 bytes; capping at 64 means the whole password always counts."""
    base = "Ab1!" + "x" * 59
    one, two = base + "a", base + "b"  # identical except for the LAST byte
    assert len(one.encode()) == len(two.encode()) == 64
    hashed = hash_password(one)
    assert verify_password(one, hashed) is True
    assert verify_password(two, hashed) is False


@pytest.mark.parametrize(
    "password",
    ["abcdef1!", "ABCDEF1!", "Abcdefg!", "Abcdefg1", "Abcdefg1_".replace("_", " ")],
)
def test_each_character_class_is_required(password: str) -> None:
    assert password_problem(password) == PASSWORD_RULE_ERROR


@pytest.mark.parametrize(
    "password",
    [
        "Abc def1!",
        " Abcdef1!",
        "Abcdef1! ",
        "Abcdef1!\t",
        "Abcdef1!\n",
        "Abc\x00def1!",
        "Abcdef1!\x7f",
        "Abcdef1! x",
    ],
)
def test_whitespace_and_control_characters_are_rejected(password: str) -> None:
    assert is_valid_password(password) is False
    assert password_problem(password) == PASSWORD_RULE_ERROR


def test_lone_surrogates_do_not_crash_validation() -> None:
    bad = "Ab1!\ud800xxxx"  # cannot be encoded as UTF-8
    assert is_valid_password(bad) is False
    assert password_problem(bad) == PASSWORD_LENGTH_ERROR


@pytest.mark.parametrize(
    "password",
    [
        "Password1!",
        "Password123#",
        "pAssw0rd!!",
        "P@ssw0rd",
        "Welcome@1",
        "Welcome123!",
        "Admin#2024",
        "Qwerty123!",
        "Qwerty@2024",
        "Letmein1!",
        "Iloveyou1!",
        "Changeme1!",
        "Secret#99",
        "Football1!",
    ],
)
def test_common_passwords_are_blocked_including_decorated_variants(password: str) -> None:
    assert is_common_password(password) is True
    assert password_problem(password) == PASSWORD_COMMON_ERROR


@pytest.mark.parametrize(
    "password", [STRONG, "Tr0ub4dor&3x", "correct-Horse9battery", "Zq!9wXe#2Lp"]
)
def test_uncommon_passwords_are_not_blocked(password: str) -> None:
    assert is_common_password(password) is False


def test_blocklist_is_big_enough_and_well_formed() -> None:
    words = common_passwords.COMMON_BASE_WORDS
    assert len(words) >= 200
    for must in ("password", "admin", "welcome", "qwerty", "letmein", "iloveyou"):
        assert must in words
    for word in words:
        assert word == word.lower() and not any(c.isspace() for c in word), word


def test_all_uppercase_variant_is_still_caught_by_the_blocklist_itself() -> None:
    # (the full validator reports the missing lower-case letter first; the blocklist is case-blind)
    assert is_common_password("PASSWORD123#") is True


@pytest.mark.parametrize(
    ("password", "username", "email"),
    [
        ("Alice#2026x", "alice", "someone@example.com"),
        ("xxALICExx#9", "alice", "someone@example.com"),
        ("John.Doe#1234", "zzzz", "john.doe@example.com"),
        ("My-john.doe-9X!", "zzzz", "John.Doe@Example.com"),
        ("Qq1!abcXYZ", "abc", "other@example.com"),  # 3-char username is still banned
    ],
)
def test_password_containing_username_or_email_local_part_is_rejected(
    password: str, username: str, email: str
) -> None:
    assert password_problem(password, username, email) == PASSWORD_PERSONAL_ERROR


def test_generic_short_parts_do_not_ban_normal_passwords() -> None:
    # a 2-character email local part must not reject every password containing those letters
    assert password_problem(STRONG, "alice", "ab@example.com") is None
    assert password_problem("Zr8!ab2mXv", "alice", "ab@example.com") is None


def test_email_domain_is_not_part_of_the_check() -> None:
    assert password_problem("Zr8!gmail9X", "alice", "someone@gmail.com") is None


def test_problems_are_reported_in_priority_order() -> None:
    assert password_problem("Ab1!", "ab1!", "x@y.com") == PASSWORD_LENGTH_ERROR  # length first
    assert password_problem("abcdefgh", "abcdefgh", "x@y.com") == PASSWORD_RULE_ERROR  # classes
    assert password_problem("Password1!", "password", "x@y.com") == PASSWORD_COMMON_ERROR  # list
