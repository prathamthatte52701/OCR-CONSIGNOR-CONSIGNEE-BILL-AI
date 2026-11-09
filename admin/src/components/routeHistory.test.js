import assert from "node:assert/strict";
import test from "node:test";
import { isSafePath, safePath } from "./routeHistory.js";

test("rejects external and unsafe targets", () => {
  const bad = ["https://evil.example", "//evil.example", "/\\evil", "javascript:alert(1)", "", null];
  for (const b of bad) {
    assert.equal(isSafePath(b), false, String(b));
    assert.equal(safePath(b, "/documents"), "/documents");
  }
});

test("rejects paths with whitespace", () => {
  for (const b of ["/a b", "/a\tb", "/a\nb", " /a"]) {
    assert.equal(isSafePath(b), false, JSON.stringify(b));
  }
});

test("allows same-app paths", () => {
  assert.equal(isSafePath("/x"), true);
  assert.equal(safePath("/documents?page=2&status=failed"), "/documents?page=2&status=failed");
});
