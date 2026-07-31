from app.features.ocr.table_extraction import build_line_items, detect_multi_page


def test_build_line_items_maps_positionally() -> None:
    rows = [
        [("", 1), ("WIDGET A", 1), ("993729", 1), ("1,000.00", 1), ("1", 1), ("1,000.00", 1)],
    ]
    items = build_line_items(rows)
    assert items == [
        {
            "srNo": None,
            "description": "WIDGET A",
            "hsnSac": "993729",
            "basic": "1,000.00",
            "quantity": "1",
            "amount": "1,000.00",
        }
    ]


def test_build_line_items_drops_ghost_rows_with_no_description() -> None:
    rows = [
        [("", 1), ("", 1), ("", 1), ("", 1), ("", 1), ("", 1)],
        [("1", 1), ("REAL ITEM", 1), ("993729", 1), ("500.00", 1), ("1", 1), ("500.00", 1)],
    ]
    items = build_line_items(rows)
    assert len(items) == 1
    assert items[0]["description"] == "REAL ITEM"


def test_detect_multi_page_true_when_total_greater_than_one() -> None:
    assert detect_multi_page("... Page 1 of 2 ...") is True
    assert detect_multi_page("... Page 1of2 ...") is True  # no spaces, real-sample OCR shape


def test_detect_multi_page_false_for_single_page() -> None:
    assert detect_multi_page("... Page 1 of 1 ...") is False


def test_detect_multi_page_false_when_absent() -> None:
    assert detect_multi_page("no page marker here") is False
