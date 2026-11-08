import assert from "node:assert/strict";
import test from "node:test";
import {
  buildSummaryText,
  canSend,
  clampText,
  countChars,
  mergeMessages,
  userIdFromToken,
  validateFile,
} from "./chatCore.js";
import { CHAT_COLORS, colorById } from "./chatColors.js";
import { chatAdminKey, CHAT_OPEN_KEY, removeChatKeys } from "./layoutStorage.js";

test("buildSummaryText: 0, 1, many", () => {
  assert.equal(buildSummaryText({ processedToday: 0 }), "Today I processed 0 documents.");
  assert.equal(buildSummaryText({ processedToday: 1 }), "Today I processed 1 document.");
  assert.equal(buildSummaryText({ processedToday: 7 }), "Today I processed 7 documents.");
  assert.equal(buildSummaryText({}), "Today I processed 0 documents.");
});

test("mergeMessages dedupes by id (incoming wins) and orders by time", () => {
  const a = { id: "a", createdAt: "2026-01-01T10:00:00Z", text: "old" };
  const b = { id: "b", createdAt: "2026-01-01T09:00:00Z", text: "b" };
  const out = mergeMessages([a], [b, { ...a, text: "new" }]);
  assert.deepEqual(out.map((m) => m.id), ["b", "a"]);
  assert.equal(out[1].text, "new");
});

test("text limits count code points", () => {
  assert.equal(countChars("a😀"), 2);
  assert.equal(clampText("😀".repeat(1001)).length, 2000); // 1000 emoji = 2000 UTF-16 units
  assert.equal(canSend({ text: "   " }), false);
  assert.equal(canSend({ text: "", file: {} }), true);
  assert.equal(canSend({ text: "x".repeat(1001) }), false);
});

test("validateFile: types and the 2 MB image / 3 MB PDF limits", () => {
  const f = (type, size) => ({ type, size, name: "x" });
  assert.equal(validateFile(f("image/png", 2 * 1024 * 1024)), null);
  assert.equal(validateFile(f("image/png", 2 * 1024 * 1024 + 1)), "Images can be up to 2 MB.");
  assert.equal(validateFile(f("application/pdf", 3 * 1024 * 1024)), null);
  assert.equal(validateFile(f("application/pdf", 3 * 1024 * 1024 + 1)), "PDFs can be up to 3 MB.");
  assert.match(validateFile(f("text/plain", 10)), /not allowed/);
});

test("userIdFromToken reads the payload, never throws", () => {
  const payload = btoa(JSON.stringify({ userId: "u1" })).replace(/=+$/, "");
  assert.equal(userIdFromToken(`h.${payload}.s`), "u1");
  assert.equal(userIdFromToken("garbage"), null);
  assert.equal(userIdFromToken(null), null);
});

test("colours: unknown id falls back to the first", () => {
  assert.equal(colorById("nope").id, CHAT_COLORS[0].id);
  assert.equal(colorById("rose").id, "rose");
});

test("removeChatKeys clears only chat keys", () => {
  const data = new Map([
    [CHAT_OPEN_KEY, "true"],
    [chatAdminKey("u1"), "adm"],
    ["main-ocr-sidebar-hidden", "1"],
  ]);
  const storage = {
    get length() {
      return data.size;
    },
    key: (i) => [...data.keys()][i] ?? null,
    removeItem: (k) => data.delete(k),
  };
  assert.equal(removeChatKeys(storage), 2);
  assert.deepEqual([...data.keys()], ["main-ocr-sidebar-hidden"]);
});
