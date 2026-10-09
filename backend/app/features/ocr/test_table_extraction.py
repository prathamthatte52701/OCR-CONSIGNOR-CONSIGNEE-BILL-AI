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


def _html(*rows: str) -> str:
    return "<html><body><table>" + "".join(f"<tr>{r}</tr>" for r in rows) + "</table></html>"


def _tds(*cells: str) -> str:
    return "".join(f"<td>{c}</td>" for c in cells)


def test_header_without_sr_label_still_finds_item_rows() -> None:
    from app.features.ocr.table_html_parser import find_item_rows, parse_table_rows

    html = _html(
        _tds("UNCODED RGP"),
        _tds("No.", "Description", "HSN/SAC", "Basic", "Quantity", "Amount"),
        _tds("", "HOB ED846", "998729", "10,000.00", "1", "10,000.00"),
        _tds("Total Basic Amount", "10,000.00"),
    )
    assert len(find_item_rows(parse_table_rows(html))) == 1


def test_last_item_row_glued_to_total_basic_amount_is_kept() -> None:
    from app.features.ocr.table_html_parser import find_item_rows, parse_table_rows

    html = _html(
        _tds("SR No.", "Description", "HSN/SAC", "Basic", "Quantity", "Amount"),
        _tds("2", "HOB 5390", "998729", "400.00", "1", "400.00", "Total Basic Amount"),
        _tds("CGST", "0.00"),
    )
    items = build_line_items(find_item_rows(parse_table_rows(html)))
    assert [(i["description"], i["amount"]) for i in items] == [("HOB 5390", "400.00")]


def test_row_missing_its_empty_sr_cell_is_read_from_the_hsn_cell() -> None:
    from app.features.ocr.table_html_parser import find_item_rows, parse_table_rows

    html = _html(
        _tds("SR No.", "Description", "HSN/SAC", "Basic", "Quantity", "Amount"),
        _tds("HOB ED2473(126999)", "998729", "5,000.00", "1", "5,000.00"),
        _tds("Total Basic Amount", "5,000.00"),
    )
    (item,) = build_line_items(find_item_rows(parse_table_rows(html)))
    assert (item["description"], item["hsnSac"], item["basic"], item["quantity"], item["amount"]) == (
        "HOB ED2473(126999)", "998729", "5,000.00", "1", "5,000.00",
    )


def test_missing_or_wrong_quantity_is_rebuilt_from_amount_over_basic() -> None:
    from app.features.ocr.table_html_parser import find_item_rows, parse_table_rows

    html = _html(
        _tds("SR No.", "Description", "HSN/SAC", "Basic", "Quantity", "Amount"),
        _tds("2", "SC DRILL A", "993729", "1,400.00", "", "8,400.00"),
        _tds("3", "SC DRILL B", "993729", "900.00", "7", "900.00"),
        _tds("4", "SC DRILL C", "993729", "900.00", "2", "1,800.00"),
        _tds("Total Basic Amount", "11,100.00"),
    )
    items = build_line_items(find_item_rows(parse_table_rows(html)))
    assert [i["quantity"] for i in items] == ["6", "1", "2"]
