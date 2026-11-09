"""Review warnings: pure function plus the GET route (computed on read, nothing stored)."""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.features.documents.review_warnings import review_warnings
from app.main import app
from testkit import make_document, make_user


def doc(**fields: Any) -> dict[str, Any]:
    base: dict[str, Any] = {"uploadStatus": "processed", "lineItems": []}
    base.update(fields)
    return base


def items(*amounts: Any) -> list[dict[str, Any]]:
    return [{"srNo": str(n), "description": "Item", "amount": a} for n, a in enumerate(amounts, 1)]


def codes(d: dict[str, Any]) -> list[str]:
    return [w["code"] for w in review_warnings(d)]


# ---------------------------------------------------------------- line items vs total basic
def test_sums_equal_no_warning() -> None:
    assert codes(doc(totalBasicAmount="300.00", lineItems=items("100.00", "200.00"))) == []


def test_sum_smaller_than_total_warns_with_both_figures() -> None:
    (w,) = review_warnings(doc(totalBasicAmount="310.00", lineItems=items("100.00", "200.00")))
    assert w["code"] == "line_items_total"
    assert "300.00" in w["message"] and "310.00" in w["message"]


def test_sum_larger_than_total_warns() -> None:
    assert codes(doc(totalBasicAmount="250.00", lineItems=items("100.00", "200.00"))) == [
        "line_items_total"
    ]


def test_difference_of_half_a_paisa_is_ignored() -> None:
    assert codes(doc(totalBasicAmount="300.005", lineItems=items("100.00", "200.00"))) == []


def test_unparseable_amount_skips_the_check() -> None:
    assert codes(doc(totalBasicAmount="999.00", lineItems=items("100.00", "1O0.00"))) == []
    assert codes(doc(totalBasicAmount="999.00", lineItems=items("100.00", None))) == []
    assert codes(doc(totalBasicAmount="999.00", lineItems=items("nan"))) == []


def test_no_line_items_or_no_total_no_warning() -> None:
    assert codes(doc(totalBasicAmount="100.00")) == []
    assert codes(doc(lineItems=items("100.00"))) == []
    assert codes(doc(totalBasicAmount="not a number", lineItems=items("100.00"))) == []


def test_commas_parse() -> None:
    d = doc(totalBasicAmount="1,234.50", lineItems=items("1,000.00", "234.50"))
    assert codes(d) == []


# ---------------------------------------------------------------------------- grand total
def test_grand_total_within_a_rupee_is_fine() -> None:
    d = doc(
        totalBasicAmount="1000.00",
        cgstAmount="90.00",
        sgstAmount="90.00",
        cgstRate="9",
        sgstRate="9",
        totalAmount="1180.50",
    )
    assert codes(d) == []


def test_grand_total_off_by_five_warns() -> None:
    d = doc(
        totalBasicAmount="1000.00",
        cgstAmount="90.00",
        sgstAmount="90.00",
        totalAmount="1185.00",
    )
    (w,) = review_warnings(d)
    assert w["code"] == "grand_total"
    assert "1,180.00" in w["message"] and "1,185.00" in w["message"]


def test_empty_tax_with_empty_or_zero_rate_counts_as_zero() -> None:
    d = doc(totalBasicAmount="1000.00", totalAmount="1000.00", igstAmount="", igstRate="0")
    assert codes(d) == []
    d = doc(totalBasicAmount="1000.00", totalAmount="1000.00", cgstRate="0.00%")
    assert codes(d) == []


def test_empty_tax_amount_with_a_rate_skips_the_check() -> None:
    d = doc(totalBasicAmount="1000.00", totalAmount="5000.00", cgstAmount=None, cgstRate="9")
    assert codes(d) == []


def test_igst_only_invoice() -> None:
    ok = doc(totalBasicAmount="1000.00", igstAmount="180.00", igstRate="18", totalAmount="1180.00")
    assert codes(ok) == []
    bad = doc(totalBasicAmount="1000.00", igstAmount="180.00", igstRate="18", totalAmount="1200.00")
    assert codes(bad) == ["grand_total"]


def test_missing_basic_or_total_skips_grand_total() -> None:
    assert codes(doc(igstAmount="180.00", totalAmount="1180.00")) == []
    assert codes(doc(totalBasicAmount="1000.00", igstAmount="180.00")) == []


# ----------------------------------------------------------------- total auto-adjusted
def test_tba_adjusted_warning() -> None:
    assert codes(doc(totalBasicAmountAutoCorrected=True)) == ["tba_adjusted"]
    assert codes(doc(totalBasicAmountAutoCorrected=False)) == []
    assert codes(doc()) == []


def test_tba_adjusted_only_for_processed() -> None:
    assert review_warnings(doc(uploadStatus="failed", totalBasicAmountAutoCorrected=True)) == []


def test_warning_order() -> None:
    d = doc(
        totalBasicAmount="1000.00",
        lineItems=items("100.00"),
        totalBasicAmountAutoCorrected=True,
        igstAmount="0",
        totalAmount="5000.00",
        multiPage=True,
    )
    assert codes(d) == ["line_items_total", "tba_adjusted", "grand_total", "multi_page"]


# ------------------------------------------------------------------------- multi page, status
def test_multi_page() -> None:
    (w,) = review_warnings(doc(multiPage=True))
    assert w["code"] == "multi_page" and "more than one page" in w["message"]
    assert codes(doc(multiPage=False)) == []


@pytest.mark.parametrize("status", ["processing", "failed", "uploaded"])
def test_only_processed_documents_get_warnings(status: str) -> None:
    d = doc(uploadStatus=status, multiPage=True, totalBasicAmount="9.00", lineItems=items("1.00"))
    assert review_warnings(d) == []


# ------------------------------------------------------------------------------------ route
@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


async def test_get_has_review_warnings_list_does_not_and_edit_clears_them(
    client: TestClient,
) -> None:
    user = await make_user()
    d = await make_document(
        user["_id"],
        totalBasicAmount="300.00",
        multiPage=True,
        lineItems=[
            {"srNo": "1", "description": "Item", "amount": "100.00"},
            {"srNo": "2", "description": "Item", "amount": "150.00"},
        ],
    )
    h = user["headers"]
    got = client.get(f"/api/documents/{d['id']}", headers=h).json()
    assert {w["code"] for w in got["reviewWarnings"]} == {"line_items_total", "multi_page"}
    listed = client.get("/api/documents", headers=h).json()["items"]
    assert listed and all("reviewWarnings" not in item for item in listed)

    fix = client.patch(
        f"/api/documents/{d['id']}/correct",
        json={"field": "lineItems.1.amount", "value": "200.00"},
        headers=h,
    )
    assert fix.status_code == 200
    after = client.get(f"/api/documents/{d['id']}", headers=h).json()
    assert [w["code"] for w in after["reviewWarnings"]] == ["multi_page"]


async def test_manual_edit_of_the_total_clears_tba_adjusted(client: TestClient) -> None:
    user = await make_user()
    d = await make_document(
        user["_id"], totalBasicAmount="100.00", totalBasicAmountAutoCorrected=True
    )
    h = user["headers"]
    first = client.get(f"/api/documents/{d['id']}", headers=h).json()
    assert [w["code"] for w in first["reviewWarnings"]] == ["tba_adjusted"]
    fix = client.patch(
        f"/api/documents/{d['id']}/correct",
        json={"field": "totalBasicAmount", "value": "100.00"},
        headers=h,
    )
    assert fix.status_code == 200
    after = client.get(f"/api/documents/{d['id']}", headers=h).json()
    assert after["reviewWarnings"] == []


async def test_document_without_issues_returns_an_empty_list(client: TestClient) -> None:
    user = await make_user()
    d = await make_document(user["_id"])
    got = client.get(f"/api/documents/{d['id']}", headers=user["headers"]).json()
    assert got["reviewWarnings"] == []


# ---------------------------------------------------------------- date plausibility
from datetime import date  # noqa: E402

TODAY = date(2026, 7, 10)


def date_warnings(d: dict[str, Any]) -> list[dict[str, str]]:
    return [w for w in review_warnings(d, today=TODAY) if w["code"] == "date_implausible"]


def test_implausible_date_warns_with_short_message() -> None:
    d = doc(challanDate="12/07/2031", consignee="SECRET CO", invoiceNo="M123")
    (w,) = date_warnings(d)
    assert w["message"] == "Date looks wrong (12/07/2031) - please check it against the original."
    assert "SECRET" not in w["message"] and "M123" not in w["message"]


def test_plausible_missing_or_unreadable_date_does_not_warn() -> None:
    for value in ("10/07/2026", "11/07/2026", None, "", "garbage", "31/02/2026"):
        assert date_warnings(doc(challanDate=value)) == []
    assert date_warnings({"uploadStatus": "failed", "challanDate": "12/07/2031"}) == []
    assert review_warnings({"uploadStatus": "processing", "challanDate": "01/01/2099"}) == []


# ---------------------------------------------------------------- serial numbers
def serials(*values: Any) -> dict[str, Any]:
    return doc(lineItems=[{"srNo": v, "description": "SECRET TEXT"} for v in values])


@pytest.mark.parametrize("bad", ["", None, "E", ".", "-", "1T"])
def test_empty_or_non_numeric_serial_warns(bad: Any) -> None:
    (w,) = review_warnings(serials("2", bad, "4"))
    assert w["code"] == "serial_numbers"
    assert w["message"].startswith("Line item 2:")
    assert "SECRET" not in w["message"]


def test_repeated_or_decreasing_serial_warns() -> None:
    assert codes(serials("2", "3", "3")) == ["serial_numbers"]
    assert codes(serials("2", "5", "4")) == ["serial_numbers"]


def test_clean_continuation_list_and_no_items_give_no_serial_warning() -> None:
    assert codes(serials(*[str(n) for n in range(2, 13)])) == []
    assert codes(doc()) == []


def test_serial_warning_lists_at_most_five_positions() -> None:
    (w,) = review_warnings(serials(*[""] * 8))
    assert "1, 2, 3, 4, 5, ..." in w["message"] and "6" not in w["message"]


# ---------------------------------------------------------------- junk descriptions
def descs(*values: Any) -> dict[str, Any]:
    return doc(lineItems=[{"srNo": str(n), "description": v} for n, v in enumerate(values, 1)])


@pytest.mark.parametrize("bad", ["", None, "  ", "EN", "-.", "|||)(", "a)(|/"])
def test_empty_short_or_symbol_description_warns(bad: Any) -> None:
    (w,) = review_warnings(descs("HOB ED23167", bad))
    assert w["code"] == "descriptions"
    assert w["message"].startswith("Line item 2:")
    assert "HOB" not in w["message"]


@pytest.mark.parametrize(
    "ok", ["END", "HOEED2316743875)90x140-A", "HOB ED23167 Ø90x140-A", "SANDVK"]
)
def test_normal_noisy_description_does_not_warn(ok: str) -> None:
    assert codes(descs(ok)) == []
