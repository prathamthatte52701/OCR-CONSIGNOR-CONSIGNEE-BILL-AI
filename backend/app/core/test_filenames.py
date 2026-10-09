"""T10: untrusted filenames can never inject a header, escape a zip, or crash an encoder."""

import pytest

from app.core.filenames import MAX_FILENAME_LENGTH, attachment_header, safe_filename


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("invoice.jpg", "invoice.jpg"),
        ("my scan (1).png", "my scan (1).png"),
        ("../../etc/passwd", "passwd"),
        ("..\\..\\windows\\system32\\cmd.exe", "cmd.exe"),
        ("/absolute/path/file.pdf", "file.pdf"),
        ("C:\\Users\\x\\file.jpg", "file.jpg"),
        ("..", "FALLBACK"),
        (".", "FALLBACK"),
        ("...", "FALLBACK"),
        ("", "FALLBACK"),
        (None, "FALLBACK"),
        ("   ", "FALLBACK"),
        (".hidden", "hidden"),
        ("a/b/", "FALLBACK"),
    ],
)
def test_paths_and_dots_are_stripped(raw: str | None, expected: str) -> None:
    assert safe_filename(raw, "FALLBACK") == expected


@pytest.mark.parametrize(
    "hostile",
    [
        'a"b.jpg',
        "a\r\nSet-Cookie: x=1.jpg",
        "a\nX-Injected: 1.jpg",
        "a\x00b.jpg",
        "a;b=c.jpg",
        'a\\b"c.jpg',
        "<script>alert(1)</script>.jpg",
        "हिन्दी.jpg",
        "名前.jpg",
        "emoji\U0001f600.jpg",
        "a\u202egpj.exe",  # right-to-left override trick
    ],
)
def test_nothing_survives_that_could_break_a_header(hostile: str) -> None:
    name = safe_filename(hostile, "FALLBACK")
    assert name.isascii()
    assert not any(ch in name for ch in '"\r\n\x00\\/;<>')
    header = attachment_header(hostile, "FALLBACK")["Content-Disposition"]
    assert header.startswith('attachment; filename="') and header.endswith('"')
    assert header.count('"') == 2  # only the two delimiters - no quote can escape
    assert "\r" not in header and "\n" not in header
    header.encode("latin-1")  # exactly what the ASGI server does - must never raise


def test_long_names_are_truncated() -> None:
    name = safe_filename("x" * 5000 + ".jpg", "FALLBACK")
    assert 0 < len(name) <= MAX_FILENAME_LENGTH


def test_name_made_only_of_replaced_characters_falls_back() -> None:
    assert safe_filename("हिन्दी", "part1") == "part1"
    assert safe_filename('""";;;', "part1") == "part1"
