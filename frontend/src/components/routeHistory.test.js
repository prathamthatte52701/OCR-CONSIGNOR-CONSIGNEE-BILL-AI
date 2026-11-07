import assert from "node:assert/strict";
import test from "node:test";

globalThis.window = { history: { state: { idx: 0 } } };
const { isSafePath, previousPath, recordLocation, safePath } = await import("./routeHistory.js");

test("push then back: previousPath is the page we came from", () => {
  window.history.state = { idx: 3 };
  recordLocation("/documents");
  window.history.state = { idx: 4 };
  recordLocation("/documents/abc");
  assert.equal(previousPath(), "/documents");
});

test("fallback: no history info means no previous path", () => {
  window.history.state = null;
  assert.equal(previousPath(), undefined);
  window.history.state = { idx: 0 };
  assert.equal(previousPath(), undefined);
});

test("rejects external and unsafe targets", () => {
  for (const bad of ["https://evil.example", "//evil.example", "/\\evil", "javascript:alert(1)", "", null]) {
    assert.equal(isSafePath(bad), false, String(bad));
    assert.equal(safePath(bad, "/documents"), "/documents");
  }
  assert.equal(safePath("/documents?page=2&status=failed"), "/documents?page=2&status=failed");
});
