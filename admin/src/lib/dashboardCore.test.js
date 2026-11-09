import assert from "node:assert/strict";
import test from "node:test";
import {
  activityCategory,
  fmt,
  describeActivity,
  lastN,
  relativeTime,
  seriesOk,
  successRate,
  sum,
  trendText,
} from "./dashboardCore.js";

test("trendText: up, down, flat, missing", () => {
  assert.equal(trendText(5, 2), "▲ +3 vs previous 7 days");
  assert.equal(trendText(1, 4), "▼ -3 vs previous 7 days");
  assert.equal(trendText(2, 2), "No change vs previous 7 days");
  assert.equal(trendText(undefined, 2), null);
});

test("successRate: one decimal, null when nothing finished or missing", () => {
  assert.equal(successRate(2, 1), 66.7);
  assert.equal(successRate(0, 0), null);
  assert.equal(successRate(3, undefined), null);
});

test("series helpers", () => {
  assert.equal(sum([1, 2, 3]), 6);
  assert.equal(sum(null), 0);
  assert.deepEqual(lastN([1, 2, 3, 4], 2), [3, 4]);
  assert.equal(lastN([], 2), undefined);
  assert.equal(seriesOk(["a", "b"], [1, 2]), true);
  assert.equal(seriesOk(["a", "b"], [1]), false);
  assert.equal(seriesOk(["a"], [1]), false);
});

test("describeActivity is a safe sentence, never raw data", () => {
  const who = { username: "alice" };
  assert.equal(describeActivity({ action: "login", user: who }), "alice logged in");
  assert.equal(
    describeActivity({ action: "document_uploaded", user: who, count: 3 }),
    "alice uploaded 3 documents"
  );
  assert.equal(describeActivity({ action: "weird_new_thing", user: null }), "A removed user: weird new thing");
  assert.equal(activityCategory("document_deleted"), "Documents");
  assert.equal(activityCategory("user_updated"), "Admin action");
});

test("relativeTime", () => {
  const now = Date.parse("2026-01-10T12:00:00Z");
  assert.equal(relativeTime("2026-01-10T11:59:50Z", now), "just now");
  assert.equal(relativeTime("2026-01-10T10:00:00Z", now), "2 hours ago");
  assert.equal(relativeTime("garbage", now), "");
});

test("fmt: thousands separator, dash for undefined, null, NaN or non-numbers", () => {
  assert.equal(fmt(1234567), "1,234,567");
  assert.equal(fmt(0), "0");
  for (const bad of [undefined, null, NaN, Infinity, "12", {}]) assert.equal(fmt(bad), "-");
});
