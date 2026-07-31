import pytest

from app.features.ocr.json_parsing import parse_json_object


def test_plain_json() -> None:
    assert parse_json_object('{"a": 1, "b": null}') == {"a": 1, "b": None}


def test_json_in_markdown_fence() -> None:
    raw = '```json\n{"a": 1}\n```'
    assert parse_json_object(raw) == {"a": 1}


def test_json_with_stray_commentary() -> None:
    raw = 'Here is the result:\n{"a": 1}\nHope that helps!'
    assert parse_json_object(raw) == {"a": 1}


def test_no_json_raises() -> None:
    with pytest.raises(ValueError):
        parse_json_object("no json here at all")
