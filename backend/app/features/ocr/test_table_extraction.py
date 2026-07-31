from app.features.ocr.table_extraction import build_line_items, detect_multi_page

_STANDARD_COLUMN_MAP = {
    "srNo": 0,
    "description": 1,
    "hsnSac": 2,
    "basic": 3,
    "quantity": 4,
    "amount": 5,
}


def test_build_line_items_maps_positionally() -> None:
    rows = [
        (
            [("", 1), ("WIDGET A", 1), ("993729", 1), ("1,000.00", 1), ("1", 1), ("1,000.00", 1)],
            _STANDARD_COLUMN_MAP,
        ),
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
        ([("", 1), ("", 1), ("", 1), ("", 1), ("", 1), ("", 1)], _STANDARD_COLUMN_MAP),
        (
            [("1", 1), ("REAL ITEM", 1), ("993729", 1), ("500.00", 1), ("1", 1), ("500.00", 1)],
            _STANDARD_COLUMN_MAP,
        ),
    ]
    items = build_line_items(rows)
    assert len(items) == 1
    assert items[0]["description"] == "REAL ITEM"


def test_build_line_items_reads_reordered_columns_by_header_position() -> None:
    # Real sample: PP-Structure detected the column order as Description, HSN/SAC, Basic,
    # Quantity, Amount, SR No - SR No last, not first. Values must still land correctly.
    reordered_map = {
        "description": 0,
        "hsnSac": 1,
        "basic": 2,
        "quantity": 3,
        "amount": 4,
        "srNo": 5,
    }
    rows = [
        (
            [
                ("SC REAMER 13.984xFL60xOAL108-WOLF", 1),
                ("998729", 1),
                ("1,500.00", 1),
                ("10", 1),
                ("15,000.00", 1),
                ("", 1),
            ],
            reordered_map,
        ),
    ]
    items = build_line_items(rows)
    assert items == [
        {
            "srNo": None,
            "description": "SC REAMER 13.984xFL60xOAL108-WOLF",
            "hsnSac": "998729",
            "basic": "1,500.00",
            "quantity": "10",
            "amount": "15,000.00",
        }
    ]


def test_build_line_items_missing_amount_column_comes_back_none() -> None:
    # Real sample: a table whose header never had a separate Amount cell at all (the
    # printed row's Amount value simply wasn't detected as its own column by PP-Structure).
    no_amount_map = {"srNo": 0, "description": 1, "hsnSac": 2, "basic": 3, "quantity": 4}
    rows = [
        (
            [("5", 1), ("SHANK GSC ED32226", 1), ("993729", 1), ("10,000.00", 1), ("1", 1)],
            no_amount_map,
        ),
    ]
    items = build_line_items(rows)
    assert items[0]["amount"] is None


def test_detect_multi_page_true_when_total_greater_than_one() -> None:
    assert detect_multi_page("... Page 1 of 2 ...") is True
    assert detect_multi_page("... Page 1of2 ...") is True  # no spaces, real-sample OCR shape


def test_detect_multi_page_false_for_single_page() -> None:
    assert detect_multi_page("... Page 1 of 1 ...") is False


def test_detect_multi_page_false_when_absent() -> None:
    assert detect_multi_page("no page marker here") is False
