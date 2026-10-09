from app.core.validators import is_valid_email, is_valid_password, is_valid_username


def test_username_length_bounds() -> None:
    assert is_valid_username("abc") is True
    assert is_valid_username("abcdefgh") is True
    assert is_valid_username("ab") is False
    assert is_valid_username("abcdefghi") is False


def test_username_rejects_whitespace_only() -> None:
    assert is_valid_username("   ") is False
    assert is_valid_username("a b") is True  # mixed content allowed, matches reference behavior


def test_password_requires_all_classes() -> None:
    assert is_valid_password("Abcdef1!") is True
    assert is_valid_password("abcdef1!") is False  # no upper
    assert is_valid_password("ABCDEF1!") is False  # no lower
    assert is_valid_password("Abcdefg!") is False  # no digit
    assert is_valid_password("Abcdefg1") is False  # no special


def test_password_rejects_whitespace_anywhere() -> None:
    assert is_valid_password("Abc def1!") is False
    assert is_valid_password(" Abcdef1!") is False
    assert is_valid_password("Abcdef1! ") is False


def test_password_length_bounds_are_8_to_64_bytes() -> None:
    assert is_valid_password("Ab1!" + "a" * 4) is True  # 8 bytes, valid
    assert is_valid_password("Ab1!aa") is False  # 6 bytes, too short
    assert is_valid_password("Ab1!" + "a" * 60) is True  # exactly 64 bytes
    assert is_valid_password("Ab1!" + "a" * 61) is False  # 65 bytes, too long


def test_email_basic_shape() -> None:
    assert is_valid_email("user@example.com") is True
    assert is_valid_email("bad-email") is False
    assert is_valid_email("user@") is False
    assert is_valid_email("user @example.com") is False


def test_common_password_blocklist_catches_variants() -> None:
    from app.core.validators import is_common_password

    assert is_common_password("Password1!") is True
    assert is_common_password("PASSWORD123#") is True
    assert is_common_password("Qwerty@2024") is True
    assert is_common_password("Zr8!kQ2mXv") is False
