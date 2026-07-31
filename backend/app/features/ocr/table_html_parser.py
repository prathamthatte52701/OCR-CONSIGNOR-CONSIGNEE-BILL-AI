"""Deterministic HTML-table-row parser (stdlib html.parser, no new dependency). PP-Structure's
pred_html is a flat, non-nested table, so a simple state machine over <tr>/<td> is enough -
no need for a full HTML/DOM library."""

from html.parser import HTMLParser

Cell = tuple[str, int]  # (text, colspan)
Row = list[Cell]


class _TableRowParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[Row] = []
        self._current_row: Row | None = None
        self._current_cell_text: list[str] = []
        self._current_colspan = 1
        self._in_cell = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._current_row = []
        elif tag == "td":
            self._in_cell = True
            self._current_cell_text = []
            attrs_dict = dict(attrs)
            self._current_colspan = int(attrs_dict.get("colspan") or 1)

    def handle_endtag(self, tag: str) -> None:
        if tag == "td":
            text = "".join(self._current_cell_text).strip()
            if self._current_row is not None:
                self._current_row.append((text, self._current_colspan))
            self._in_cell = False
        elif tag == "tr":
            if self._current_row is not None:
                self.rows.append(self._current_row)
            self._current_row = None

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._current_cell_text.append(data)


def parse_table_rows(html: str) -> list[Row]:
    parser = _TableRowParser()
    parser.feed(html)
    return parser.rows


# Row-shape (colspan merging) is NOT a reliable boundary signal on its own - real samples
# show the tax-summary section sometimes rendered as plain 6-cell rows just like item rows,
# depending on how the table-recognition model perceived that photo's cell borders. These
# fixed label strings are a much more reliable signal since they always appear verbatim.
_SUMMARY_KEYWORDS = (
    "CGST",
    "SGST",
    "IGST",
    "TOTAL BASIC AMOUNT",
    "TOTAL AMOUNT",
    "INPUT TAX CREDIT",
)


def _is_plain_item_row(row: Row) -> bool:
    return len(row) == 6 and all(colspan == 1 for _, colspan in row)


def _looks_like_column_header(row: Row) -> bool:
    joined = " ".join(text.upper() for text, _ in row)
    return "DESCRIPTION" in joined and ("SR" in joined or "SL" in joined)


def _contains_summary_keyword(row: Row) -> bool:
    joined = " ".join(text.upper() for text, _ in row)
    return any(keyword in joined for keyword in _SUMMARY_KEYWORDS)


def find_item_rows(rows: list[Row]) -> list[Row]:
    """Item rows are collected while a row still looks like a plain 6-column item row and
    contains no summary-section keyword; the first row that fails either check ends item
    collection permanently (tax summary + trailing junk follows and is not returned - the
    caller sources tax-summary figures from the full-page OCR text instead, since PP-Structure
    sometimes excludes the totals from the detected table's own bounding box)."""
    item_rows: list[Row] = []
    seen_header = False
    collecting_items = False

    for row in rows:
        if not seen_header:
            if _looks_like_column_header(row):
                seen_header = True
                collecting_items = True
            continue
        if collecting_items and _is_plain_item_row(row) and not _contains_summary_keyword(row):
            item_rows.append(row)
            continue
        collecting_items = False

    return item_rows
