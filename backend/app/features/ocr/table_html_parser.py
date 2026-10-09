"""Deterministic HTML-table-row parser (stdlib html.parser, no new dependency). PP-Structure's
pred_html is a flat, non-nested table, so a simple state machine over <tr>/<td> is enough -
no need for a full HTML/DOM library."""

import re
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


def _looks_like_column_header(row: Row) -> bool:
    joined = " ".join(text.upper() for text, _ in row)
    # "SR"/"SL No." is sometimes OCR'd as "SP No." (R/L -> P misread) - "DESCRIPTION" is a
    # literal word only the header row ever spells out (real item descriptions are always
    # part-code abbreviations, never that word), so it alone is already a strong anchor;
    # this only needs to rule out matching a stray unrelated row that happens to also
    # contain "DESCRIPTION" with no header-shaped label at all, which real samples never do.
    if "DESCRIPTION" not in joined:
        return False
    if "SR" in joined or "SL" in joined or "SP" in joined:
        return True
    # SR No column cropped off the photo: only "No." is left of it, but the other labels are there
    return any(label in joined for label in ("HSN", "BASIC", "QUANTITY"))


def _contains_summary_keyword(row: Row) -> bool:
    joined = " ".join(text.upper() for text, _ in row)
    return any(keyword in joined for keyword in _SUMMARY_KEYWORDS)


# Real samples show PP-Structure's own detected column ORDER varies between documents
# (one photo's table came out "SR No, Description, HSN/SAC, Basic, Quantity, Amount";
# another came out "Description, HSN/SAC, Basic, Quantity, Amount, SR No" - SR No last)
# and colspan usage is inconsistent even row-to-row within one table (the Description
# cell sometimes spans 2 of the model's grid columns, sometimes 1, and a printed row can
# be missing a column's cell entirely, e.g. no separate Amount cell at all). A fixed
# left-to-right positional mapping breaks on both cases. Instead, every field's LOGICAL
# column position is read off the header row's own text once (cumulative colspan, so a
# colspan=2 header cell occupies two logical slots), and every data row is read back
# using that same cumulative-colspan position - never a fixed index - so column order and
# uneven colspans on either row don't matter, only where each label's own text actually
# sits relative to the others.
_HEADER_FIELD_LABELS: dict[str, str] = {
    "SRNO": "srNo",
    "SLNO": "srNo",
    "DESCRIPTION": "description",
    "HSNSAC": "hsnSac",
    "HSN": "hsnSac",
    "SAC": "hsnSac",
    "BASIC": "basic",
    "QUANTITY": "quantity",
    "QTY": "quantity",
    "AMOUNT": "amount",
}


def _normalize_header_cell(text: str) -> str:
    return re.sub(r"[^A-Z]", "", text.upper())


def build_column_map(header_row: Row) -> dict[str, int]:
    """Maps each recognized logical field name to the logical column index (cumulative
    colspan) it starts at in THIS row - built once from the header, then reused to read
    every data row in the same table by matching position, not by index or column count."""
    column_map: dict[str, int] = {}
    logical_col = 0
    for text, colspan in header_row:
        normalized = _normalize_header_cell(text)
        for label, field in _HEADER_FIELD_LABELS.items():
            if field in column_map:
                continue
            if label in normalized:
                column_map[field] = logical_col
                break
        logical_col += colspan
    return column_map


def read_row_by_column_map(row: Row, column_map: dict[str, int]) -> dict[str, str | None]:
    """Reads a data row's cell text at each field's logical column position (same
    cumulative-colspan indexing used to build column_map from the header). A field whose
    header column was never found (e.g. this table has no separate Amount cell at all)
    or whose position isn't present on this particular row (a colspan difference from the
    header) comes back None - honest, not a fabricated 0 or empty string."""
    position_lookup: dict[int, str | None] = {}
    logical_col = 0
    for text, colspan in row:
        position_lookup[logical_col] = text or None
        logical_col += colspan
    return {field: position_lookup.get(idx) for field, idx in column_map.items()}


_HSN_CELL_RE = re.compile(r"^\s*\d{6}\s*$")
_SR_CELL_RE = re.compile(r"^\s*\d{1,2}\s*$")


def _read_row_from_hsn_cell(row: Row) -> dict[str, str | None] | None:
    """Reads an item row outward from its HSN/SAC cell (always the 6-digit cell, followed by
    basic, quantity, amount). Used only when the header-position read did not land on an HSN
    cell - an empty SR No cell that PP-Structure drops from one row shifts every later column
    of that row by one, which the header's logical column map cannot see."""
    texts = [text for text, _ in row]
    hsn_index = next((i for i, text in enumerate(texts) if _HSN_CELL_RE.match(text)), None)
    if hsn_index is None:
        return None
    before = texts[:hsn_index]
    after = [t for t in texts[hsn_index + 1 :] if not any(k in t.upper() for k in _SUMMARY_KEYWORDS)]
    described = [t for t in before if re.search(r"[A-Za-z]", t)]
    return {
        "srNo": next((t for t in before if _SR_CELL_RE.match(t)), None),
        "description": max(described, key=len) if described else None,
        "hsnSac": texts[hsn_index],
        "basic": (after[0] or None) if len(after) > 0 else None,
        "quantity": (after[1] or None) if len(after) > 1 else None,
        "amount": (after[2] or None) if len(after) > 2 else None,
    }


def read_item_row(row: Row, column_map: dict[str, int]) -> dict[str, str | None]:
    fields = read_row_by_column_map(row, column_map)
    hsn = fields.get("hsnSac")
    if hsn is not None and _HSN_CELL_RE.match(hsn):
        return fields
    anchored = _read_row_from_hsn_cell(row)
    return anchored if anchored is not None else fields


def _strip_summary_cells(row: Row) -> Row:
    return [cell for cell in row if not any(k in cell[0].upper() for k in _SUMMARY_KEYWORDS)]


def find_item_rows(rows: list[Row]) -> list[tuple[Row, dict[str, int]]]:
    """Locates the header row, builds its column map, then collects every row after it
    that isn't itself a header or tax-summary row. Returns each item row paired with the
    column map so the caller (table_extraction.build_line_items) can read fields by their
    actual position rather than assuming a fixed left-to-right order."""
    item_rows: list[tuple[Row, dict[str, int]]] = []
    column_map: dict[str, int] = {}
    seen_header = False

    for row in rows:
        if not seen_header:
            if _looks_like_column_header(row):
                seen_header = True
                column_map = build_column_map(row)
            continue
        if _looks_like_column_header(row):
            break
        if _contains_summary_keyword(row):
            # The last item row is sometimes glued to the "Total Basic Amount" label cell.
            # A row that still carries its own HSN cell is that item row, not the summary.
            if any(_HSN_CELL_RE.match(text) for text, _ in row):
                item_rows.append((_strip_summary_cells(row), column_map))
            break
        item_rows.append((row, column_map))

    return item_rows
