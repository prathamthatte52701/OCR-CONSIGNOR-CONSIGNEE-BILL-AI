from app.features.ocr.table_html_parser import find_item_rows, parse_table_rows

SAMPLE_HTML = (
    "<html><body><table><tbody>"
    '<tr><td colspan="6">UNCODED RGP</td></tr>'
    "<tr><td>SRNo.</td><td>Description</td><td>HSN/SAC</td><td>Basic</td>"
    "<td>Quantity</td><td>Amount</td></tr>"
    "<tr><td></td><td>WIDGET A</td><td>993729</td><td>1,000.00</td>"
    "<td>1</td><td>1,000.00</td></tr>"
    "<tr><td>2</td><td>WIDGET B</td><td>993729</td><td>2,000.00</td>"
    "<td>1</td><td>2,000.00</td></tr>"
    '<tr><td colspan="5">Total Basic Amount</td><td>3,000.00</td></tr>'
    '<tr><td colspan="3">CGST</td><td colspan="2">0.00</td><td>0.00</td></tr>'
    "</tbody></table></body></html>"
)


def test_parse_table_rows_extracts_cells_and_colspan() -> None:
    rows = parse_table_rows(SAMPLE_HTML)
    assert rows[0] == [("UNCODED RGP", 6)]
    assert rows[2][0] == ("", 1)
    assert rows[2][1] == ("WIDGET A", 1)


def test_find_item_rows_skips_title_and_header() -> None:
    item_rows = find_item_rows(parse_table_rows(SAMPLE_HTML))
    assert len(item_rows) == 2
    assert item_rows[0][1][0] == "WIDGET A"
    assert item_rows[1][1][0] == "WIDGET B"


def test_find_item_rows_stops_at_summary_keyword() -> None:
    item_rows = find_item_rows(parse_table_rows(SAMPLE_HTML))
    # "Total Basic Amount" / "CGST" rows must never appear as item rows.
    joined = " ".join(cell[0] for row in item_rows for cell in row)
    assert "CGST" not in joined
    assert "Total Basic Amount" not in joined


def test_find_item_rows_boundary_survives_non_colspan_summary() -> None:
    # Real sample: summary rows sometimes render as plain 6-cell rows too (no colspan) -
    # the keyword check must still catch them, not just the colspan-shape check.
    html = (
        "<html><body><table><tbody>"
        "<tr><td>SRNo.</td><td>Description</td><td>HSN/SAC</td><td>Basic</td>"
        "<td>Quantity</td><td>Amount</td></tr>"
        "<tr><td>1</td><td>WIDGET A</td><td>993729</td><td>1,000.00</td>"
        "<td>1</td><td>1,000.00</td></tr>"
        "<tr><td></td><td>CGST</td><td>0.00</td><td>0.00</td><td></td><td></td></tr>"
        "<tr><td>9</td><td>WIDGET GHOST</td><td>993729</td><td>500.00</td>"
        "<td>1</td><td>500.00</td></tr>"
        "</tbody></table></body></html>"
    )
    item_rows = find_item_rows(parse_table_rows(html))
    assert len(item_rows) == 1
    assert item_rows[0][1][0] == "WIDGET A"


def test_empty_html_returns_no_rows() -> None:
    assert find_item_rows(parse_table_rows("")) == []
