"""Document list: search, challan date / month filters, IST ranges, needsReview, server sort."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

from app.features.documents.list_query import build_list_query, upload_range_start_utc
from app.main import app
from testkit import make_document, make_user

URL = "/api/documents"


@pytest.fixture(scope="module")
def client() -> Any:
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def ids_of(resp: Any) -> set[str]:
    assert resp.status_code == 200, resp.text
    return {item["id"] for item in resp.json()["items"]}


async def doc(user: dict[str, Any], **fields: Any) -> str:
    return str((await make_document(user["_id"], with_files=False, **fields))["id"])


# ------------------------------------------------------------------ search


async def test_search_matches_invoice_code_and_consignee_case_insensitively(
    client: TestClient,
) -> None:
    u = await make_user()
    a = await doc(u, invoiceNo="INV-100", consigneeCode="C1", consignee="Acme Traders")
    b = await doc(u, invoiceNo="X5", consigneeCode="ZED77", consignee="Other")
    c = await doc(u, invoiceNo="X6", consigneeCode="Q", consignee="Big ACME Ltd")

    def hit(text: str) -> set[str]:
        return ids_of(client.get(URL, params={"search": text}, headers=u["headers"]))

    assert hit("inv-100") == {a}
    assert hit("zed77") == {b}
    assert hit("acme") == {a, c}
    assert hit("  acme  ") == {a, c}  # stripped
    assert hit("nothing") == set()


async def test_search_special_characters_are_literal(client: TestClient) -> None:
    u = await make_user()
    plain = await doc(u, invoiceNo="ABC123")
    dotted = await doc(u, invoiceNo="A.C(1")
    assert ids_of(client.get(URL, params={"search": "A.C(1"}, headers=u["headers"])) == {dotted}
    assert ids_of(client.get(URL, params={"search": ".*"}, headers=u["headers"])) == set()
    assert plain not in ids_of(client.get(URL, params={"search": "A.C"}, headers=u["headers"]))


async def test_search_rejects_nul_and_over_100_chars(client: TestClient) -> None:
    u = await make_user()
    assert client.get(URL, params={"search": "a\x00b"}, headers=u["headers"]).status_code == 400
    assert client.get(URL, params={"search": "x" * 101}, headers=u["headers"]).status_code == 400
    assert client.get(URL, params={"search": "x" * 100}, headers=u["headers"]).status_code == 200


# ------------------------------------------------------------------ date / month


async def test_date_picker_matches_the_stored_formats(client: TestClient) -> None:
    u = await make_user()
    a = await doc(u, challanDate="01/07/2026")
    b = await doc(u, challanDate="01.07.26")
    c = await doc(u, challanDate="1-7-2026")
    other = [
        await doc(u, challanDate="11/07/2026"),
        await doc(u, challanDate="01/07/2025"),
        await doc(u, challanDate="02/07/2026"),
        await doc(u, challanDate="01/17/2026"),
        await doc(u),  # no challanDate at all
    ]
    got = ids_of(client.get(URL, params={"date": "2026-07-01"}, headers=u["headers"]))
    assert got == {a, b, c} and not got & set(other)


@pytest.mark.parametrize("bad", ["2026", "01/07/2026", "2026-13-01", "2026-02-30", "20260701", "x"])
async def test_bad_date_is_400(client: TestClient, bad: str) -> None:
    u = await make_user()
    assert client.get(URL, params={"date": bad}, headers=u["headers"]).status_code == 400


async def test_date_and_month_together_is_400(client: TestClient) -> None:
    u = await make_user()
    r = client.get(URL, params={"date": "2026-07-01", "month": "2026-07"}, headers=u["headers"])
    assert r.status_code == 400


async def test_month_and_none(client: TestClient) -> None:
    u = await make_user()
    july = [
        await doc(u, challanDate="01/07/2026"),
        await doc(u, challanDate="15.07.26"),
        await doc(u, challanDate="3-7-2026"),
    ]
    await doc(u, challanDate="01/08/2026")
    await doc(u, challanDate="01/07/2025")
    nodate = [
        await doc(u),
        await doc(u, challanDate=None),
        await doc(u, challanDate=""),
        await doc(u, challanDate="garbage"),
    ]
    assert ids_of(client.get(URL, params={"month": "2026-07"}, headers=u["headers"])) == set(july)
    assert ids_of(client.get(URL, params={"month": "none"}, headers=u["headers"])) == set(nodate)
    assert client.get(URL, params={"month": "2026-7"}, headers=u["headers"]).status_code == 400


# ------------------------------------------------------------------ range (IST)


def test_range_starts_are_ist_buckets_in_utc() -> None:
    now = datetime(2026, 11, 3, 20, 0, tzinfo=UTC)  # = 04 Nov 2026 01:30 IST (a Wednesday)
    assert upload_range_start_utc("today", now) == datetime(2026, 11, 3, 18, 30, tzinfo=UTC)
    assert upload_range_start_utc("week", now) == datetime(2026, 11, 1, 18, 30, tzinfo=UTC)
    assert upload_range_start_utc("month", now) == datetime(2026, 10, 31, 18, 30, tzinfo=UTC)
    assert upload_range_start_utc("year", now) == datetime(2025, 12, 31, 18, 30, tzinfo=UTC)
    q = build_list_query(ObjectId(), date_range="today", now=now)
    assert q["$and"] == [{"createdAt": {"$gte": datetime(2026, 11, 3, 18, 30, tzinfo=UTC)}}]


async def test_range_filters_by_upload_time(client: TestClient) -> None:
    u = await make_user()
    fresh = await doc(u, createdAt=datetime.now(UTC))
    old = await doc(u, createdAt=datetime.now(UTC) - timedelta(days=800))
    got = ids_of(client.get(URL, params={"range": "today"}, headers=u["headers"]))
    assert fresh in got and old not in got
    assert client.get(URL, params={"range": "decade"}, headers=u["headers"]).status_code == 422


# ------------------------------------------------------------------ needsReview + combos


async def test_needs_review_keeps_the_search_condition(client: TestClient) -> None:
    u = await make_user()
    failed_hit = await doc(u, invoiceNo="AAA1", uploadStatus="failed")
    low_hit = await doc(u, invoiceNo="AAA2", hasLowConfidenceFields=True)
    clean_hit = await doc(u, invoiceNo="AAA3")
    failed_miss = await doc(u, invoiceNo="BBB1", uploadStatus="failed")
    p = {"search": "aaa", "needsReview": "true"}
    assert ids_of(client.get(URL, params=p, headers=u["headers"])) == {failed_hit, low_hit}
    only_review = ids_of(client.get(URL, params={"needsReview": "true"}, headers=u["headers"]))
    assert only_review == {failed_hit, low_hit, failed_miss}
    assert clean_hit not in only_review


async def test_search_and_month_none_do_not_overwrite_each_other(client: TestClient) -> None:
    u = await make_user()
    keep = await doc(u, invoiceNo="KEEP", challanDate="")
    await doc(u, invoiceNo="KEEP", challanDate="01/07/2026")
    await doc(u, invoiceNo="DROP")
    p = {"search": "keep", "month": "none"}
    assert ids_of(client.get(URL, params=p, headers=u["headers"])) == {keep}


# ------------------------------------------------------------------ sort


async def test_sort_validation(client: TestClient) -> None:
    u = await make_user()
    for params in ({"sort": "totals"}, {"sort": "invoiceNo", "order": "up"}, {"order": "x"}):
        assert client.get(URL, params=params, headers=u["headers"]).status_code == 422


@pytest.mark.parametrize("order", ["asc", "desc"])
async def test_sort_walk_returns_each_document_exactly_once(client: TestClient, order: str) -> None:
    u = await make_user()
    created = [
        await doc(u, invoiceNo=name)
        for name in ["b1", "B1", "a1", "A1", "a1", "c9", None, "b1", "d"]
    ]
    seen: list[str] = []
    for page in range(1, 8):
        r = client.get(
            URL,
            params={"sort": "invoiceNo", "order": order, "limit": 2, "page": page},
            headers=u["headers"],
        )
        assert r.status_code == 200
        items = r.json()["items"]
        seen += [i["id"] for i in items]
        if not items:
            break
    assert sorted(seen) == sorted(created) and len(set(seen)) == len(seen)


async def test_sort_by_invoice_is_case_insensitive_and_directional(client: TestClient) -> None:
    u = await make_user()
    await doc(u, invoiceNo="b")
    await doc(u, invoiceNo="A")
    await doc(u, invoiceNo="c")

    def names(order: str) -> list[str]:
        r = client.get(URL, params={"sort": "invoiceNo", "order": order}, headers=u["headers"])
        return [i["invoiceNo"] for i in r.json()["items"]]

    assert names("asc") == ["A", "b", "c"]
    assert names("desc") == ["c", "b", "A"]


async def test_sort_by_challan_date_normalises_to_yyyymmdd(client: TestClient) -> None:
    u = await make_user()
    await doc(u, invoiceNo="d3", challanDate="3-1-2027")
    await doc(u, invoiceNo="d1", challanDate="15.06.26")
    await doc(u, invoiceNo="d2", challanDate="01/07/2026")
    await doc(u, invoiceNo="none", challanDate="garbage")
    r = client.get(URL, params={"sort": "challanDate", "order": "asc"}, headers=u["headers"])
    assert [i["invoiceNo"] for i in r.json()["items"]] == ["none", "d1", "d2", "d3"]
    r = client.get(URL, params={"sort": "challanDate", "order": "desc"}, headers=u["headers"])
    assert [i["invoiceNo"] for i in r.json()["items"]] == ["d3", "d2", "d1", "none"]


async def test_default_sort_is_created_at_desc(client: TestClient) -> None:
    u = await make_user()
    now = datetime.now(UTC)
    await doc(u, invoiceNo="old", createdAt=now - timedelta(days=2))
    await doc(u, invoiceNo="new", createdAt=now)
    r = client.get(URL, headers=u["headers"])
    assert [i["invoiceNo"] for i in r.json()["items"]] == ["new", "old"]
