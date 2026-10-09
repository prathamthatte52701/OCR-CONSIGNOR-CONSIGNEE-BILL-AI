from app.features.ocr.pipeline import split_into_columns


def _line(text: str, x1: int, x2: int, y1: int = 0) -> dict:
    return {"text": text, "confidence": 1.0, "box": [x1, y1, x2, y1 + 10]}


def test_splits_left_and_right_columns() -> None:
    lines = [
        _line("Consignee Code", 10, 100, y1=0),
        _line("341198", 10, 100, y1=10),
        _line("Name", 500, 600, y1=0),
        _line("VE Commercial Vehicles", 500, 700, y1=10),
    ]
    left, right = split_into_columns(lines)
    assert "Consignee Code" in left
    assert "341198" in left
    assert "Name" in right
    assert "VE Commercial Vehicles" in right


def test_preserves_top_to_bottom_order_within_column() -> None:
    lines = [
        _line("second", 10, 100, y1=50),
        _line("first", 10, 100, y1=10),
    ]
    left, _ = split_into_columns(lines)
    assert left.index("first") < left.index("second")


def test_empty_input() -> None:
    assert split_into_columns([]) == ("", "")


def test_value_slightly_above_label_stays_on_the_labels_row() -> None:
    lines = [
        _line("Consignee Code", 10, 100, y1=0),
        _line("Request No", 500, 600, y1=14),
        _line("0000166771", 640, 740, y1=10),
        _line("PO No", 500, 560, y1=40),
        _line("3242064440", 640, 740, y1=36),
    ]
    _, right = split_into_columns(lines)
    assert right.split("\n") == ["Request No  0000166771", "PO No  3242064440"]
