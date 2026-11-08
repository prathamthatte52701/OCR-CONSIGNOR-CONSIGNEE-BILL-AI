import assert from "node:assert/strict";
import test from "node:test";
import {
  CLEAR_RANGES,
  badgeText,
  clearSummary,
  filterThreads,
  isTyped,
  overlayUnread,
  pickSelected,
  unreadForAdmin,
  unreadTotal,
  userIdFromToken,
} from "./chatAdminCore.js";
import { CHAT_OPEN_KEY, chatUserKey, removeChatUserKeys } from "./layoutStorage.js";

const threads = [
  { userId: "a", name: "Asha", unreadCount: 0 },
  { userId: "b", name: "Bela", unreadCount: 3 },
];

test("unread totals and badge text", () => {
  assert.equal(unreadTotal([{ count: 2 }, { count: 3 }]), 5);
  assert.equal(unreadTotal(null), 0);
  assert.equal(badgeText(0), "");
  assert.equal(badgeText(7), "7");
  assert.equal(badgeText(120), "99+");
});

test("overlayUnread: the fresher counts win, a missing user has none", () => {
  const out = overlayUnread(threads, [{ userId: "a", count: 4 }]);
  assert.deepEqual(out.map((t) => t.unreadCount), [4, 0]);
  assert.equal(overlayUnread(threads, null), threads);
});

test("pickSelected: remembered, else first with unread, else first", () => {
  assert.equal(pickSelected(threads, "a"), "a");
  assert.equal(pickSelected(threads, "gone"), "b");
  assert.equal(pickSelected([{ userId: "x", unreadCount: 0 }], null), "x");
  assert.equal(pickSelected([], null), null);
});

test("unreadForAdmin only counts user messages addressed to this admin", () => {
  const msgs = [
    { fromRole: "user", toAdminId: "me", readAt: null },
    { fromRole: "user", toAdminId: "other", readAt: null },
    { fromRole: "user", toAdminId: "me", readAt: "t" },
    { fromRole: "admin", toAdminId: null, readAt: null },
  ];
  assert.equal(unreadForAdmin(msgs, "me").length, 1);
});

test("thread search is case-insensitive", () => {
  assert.deepEqual(filterThreads(threads, " BE ").map((t) => t.userId), ["b"]);
  assert.equal(filterThreads(threads, "").length, 2);
});

test("clear ranges and the DELETE word", () => {
  assert.deepEqual(
    CLEAR_RANGES.map((r) => r.id).slice(0, 7),
    ["24h", "3d", "1w", "1m", "3m", "6m", "1y"]
  );
  assert.equal(isTyped("DELETE"), true);
  assert.equal(isTyped("delete"), false);
  assert.equal(isTyped("DELETE "), false);
  assert.equal(clearSummary("1w", 0), "No messages match this range.");
  assert.equal(clearSummary("1w", 2, 1), "2 messages and 1 file will be deleted (older than 1 week)");
});

test("userIdFromToken reads the payload, never throws", () => {
  const payload = btoa(JSON.stringify({ userId: "adm1" })).replace(/=+$/, "");
  assert.equal(userIdFromToken(`h.${payload}.s`), "adm1");
  assert.equal(userIdFromToken("garbage"), null);
  assert.equal(userIdFromToken(undefined), null);
});

test("removeChatUserKeys clears only the admin chat keys", () => {
  const data = new Map([
    [CHAT_OPEN_KEY, "true"],
    [chatUserKey("adm1"), "u1"],
    ["main-ocr-admin-auth", "{}"],
  ]);
  const storage = {
    get length() {
      return data.size;
    },
    key: (i) => [...data.keys()][i] ?? null,
    removeItem: (k) => data.delete(k),
  };
  assert.equal(removeChatUserKeys(storage), 2);
  assert.deepEqual([...data.keys()], ["main-ocr-admin-auth"]);
});
