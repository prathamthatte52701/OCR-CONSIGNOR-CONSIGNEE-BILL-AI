// T13: keyboard shortcuts.
//   Enter confirms / Escape cancels in the user app's GlobalConfirmDialog and the admin ConfirmModal;
//   Enter runs the Documents search; Enter saves an editable field;
//   Enter must NOT confirm the admin Nuke dialog (Escape may close it).
// Backend fully mocked (page.route) - touches no real data. Run: node e2e/test_shortcuts.cjs
const path = require("node:path");
const { launchBrowser, startVite, createRunner, assert, seedFrontendAuth, seedAdminAuth } = require("./helpers.cjs");

const results = []; // (kept for the report) - same objects as runner.results
const DOC = {
  id: "d1",
  invoiceNo: "INV-1",
  reason: "Old",
  uploadStatus: "processed",
  createdAt: "2026-07-01T10:00:00Z",
  lineItems: [],
  part1FilePurged: false,
  part2FilePurged: false,
};
const ADMIN_USER = { id: "u1", username: "alice", email: "alice@example.invalid", role: "user", status: "approved", createdAt: "2026-07-01T10:00:00Z" };

(async () => {
  const runner = createRunner();
  results.push(...runner.results);
  const appVite = await startVite(path.join(__dirname, ".."), 6001);
  const adminVite = await startVite(path.join(__dirname, "..", "..", "admin"), 7000);
  const browser = await launchBrowser();

  // ---------------------------------------------------------------- user app helpers
  const openDoc = async () => {
    const context = await browser.newContext();
    await seedFrontendAuth(context);
    const page = await context.newPage();
    const calls = [];
    await page.route((u) => u.pathname.startsWith("/api/"), (route) => {
      const req = route.request();
      const url = new URL(req.url());
      const respond = (status, body) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
      if (url.pathname === "/api/auth/me") return respond(200, { id: "1", username: "tester", email: "t@example.invalid", role: "user" });
      if (url.pathname === "/api/documents/d1" && req.method() === "GET") return respond(200, DOC);
      if (url.pathname === "/api/documents/d1" && req.method() === "DELETE") {
        calls.push("DELETE");
        return respond(200, { message: "deleted" });
      }
      if (url.pathname === "/api/documents/d1/correct" && req.method() === "PATCH") {
        calls.push("PATCH " + req.postData());
        // slow server: the request is still in flight while the user hits Enter again
        return new Promise((resolve) => setTimeout(() => resolve(respond(200, { message: "ok" })), 400));
      }
      if (url.pathname === "/api/documents") {
        calls.push("LIST " + url.search);
        return respond(200, { items: [], total: 0, page: 1, limit: 30 });
      }
      return respond(404, { detail: "unmocked " + url.pathname });
    });
    await page.goto(`${appVite.url}/documents/d1`);
    await page.getByText("INV-1").first().waitFor({ timeout: 10000 });
    return { context, page, calls };
  };
  const openDeleteDialog = async (page) => {
    await page.getByRole("button", { name: "Delete", exact: true }).first().click();
    await page.getByRole("heading", { name: "Permanently delete this document?" }).waitFor();
  };
  const dialogGone = (page) => page.waitForFunction(() => !document.querySelector("dialog[open]"), null, { timeout: 5000 });

  // ------------------------------------------------------------------- user app: dialog
  await runner.check("[app] dialog opens with focus on the dialog itself, not on Cancel", async () => {
    const { context, page } = await openDoc();
    await openDeleteDialog(page);
    const tag = await page.evaluate(() => document.activeElement && document.activeElement.tagName);
    assert(tag === "DIALOG", `expected focus on DIALOG, got ${tag}`);
    await context.close();
  });

  await runner.check("[app] Enter confirms the dialog (one DELETE, dialog closes)", async () => {
    const { context, page, calls } = await openDoc();
    await openDeleteDialog(page);
    await page.keyboard.press("Enter");
    await dialogGone(page);
    await page.waitForTimeout(400);
    assert(calls.filter((c) => c === "DELETE").length === 1, `expected one DELETE, got ${JSON.stringify(calls)}`);
    await context.close();
  });

  await runner.check("[app] Escape cancels the dialog and sends nothing", async () => {
    const { context, page, calls } = await openDoc();
    await openDeleteDialog(page);
    await page.keyboard.press("Escape");
    await dialogGone(page);
    await page.waitForTimeout(400);
    assert(!calls.includes("DELETE"), "Escape must not delete");
    await context.close();
  });

  await runner.check("[app] Enter with focus on the Cancel button cancels (ignored as a confirm key)", async () => {
    const { context, page, calls } = await openDoc();
    await openDeleteDialog(page);
    await page.getByRole("button", { name: "Cancel" }).focus();
    await page.keyboard.press("Enter");
    await dialogGone(page);
    await page.waitForTimeout(400);
    assert(!calls.includes("DELETE"), "Enter on Cancel must not confirm");
    await context.close();
  });

  await runner.check("[app] two quick Enters still send exactly ONE request", async () => {
    const { context, page, calls } = await openDoc();
    await openDeleteDialog(page);
    await Promise.all([page.keyboard.press("Enter"), page.keyboard.press("Enter")]);
    await page.waitForTimeout(800);
    assert(calls.filter((c) => c === "DELETE").length === 1, `got ${JSON.stringify(calls)}`);
    await context.close();
  });

  await runner.check("[app] a held Enter (key repeat) confirms once, never twice", async () => {
    const { context, page, calls } = await openDoc();
    await openDeleteDialog(page);
    await page.keyboard.down("Enter");
    await page.keyboard.down("Enter"); // second down = auto-repeat (event.repeat === true)
    await page.keyboard.down("Enter");
    await page.keyboard.up("Enter");
    await page.waitForTimeout(800);
    assert(calls.filter((c) => c === "DELETE").length === 1, `got ${JSON.stringify(calls)}`);
    await context.close();
  });

  await runner.check("[app] clicking the Cancel / Delete buttons still works with the mouse", async () => {
    const { context, page, calls } = await openDoc();
    await openDeleteDialog(page);
    await page.getByRole("dialog").getByRole("button", { name: "Cancel" }).click();
    await dialogGone(page);
    assert(!calls.includes("DELETE"), "Cancel click deleted");
    await openDeleteDialog(page);
    await page.getByRole("dialog").getByRole("button", { name: "Delete", exact: true }).click();
    await dialogGone(page);
    await page.waitForTimeout(400);
    assert(calls.filter((c) => c === "DELETE").length === 1, `got ${JSON.stringify(calls)}`);
    await context.close();
  });

  // ------------------------------------------------------------ user app: fields / search
  await runner.check("[app] Enter saves an editable field (exactly one PATCH)", async () => {
    const { context, page, calls } = await openDoc();
    // Grab the element once: its `value` attribute (the locator) changes as soon as we type.
    const input = await page.locator('input[value="Old"]').elementHandle();
    await input.fill("New value");
    await input.press("Enter");
    await input.press("Enter"); // a second Enter while the first save is in flight: ignored
    await page.waitForTimeout(800);
    const patches = calls.filter((c) => c.startsWith("PATCH"));
    assert(patches.length === 1, `expected 1 PATCH, got ${JSON.stringify(calls)}`);
    assert(patches[0].includes("reason") && patches[0].includes("New value"), `wrong body ${patches[0]}`);
    await context.close();
  });

  await runner.check("[app] two Enter keydowns in the SAME tick still save only once", async () => {
    const { context, page, calls } = await openDoc();
    const input = await page.locator('input[value="Old"]').elementHandle();
    await input.fill("Burst value");
    await input.evaluate((el) => {
      for (let i = 0; i < 3; i++) el.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    });
    await page.waitForTimeout(1000);
    const patches = calls.filter((c) => c.startsWith("PATCH"));
    assert(patches.length === 1, `expected 1 PATCH from a same-tick burst, got ${patches.length}`);
    await context.close();
  });

  await runner.check("[app] Enter in a Documents filter input runs the search", async () => {
    const { context, page, calls } = await openDoc();
    calls.length = 0;
    await page.goto(`${appVite.url}/documents`);
    await page.getByPlaceholder("Invoice No").waitFor({ timeout: 10000 });
    await page.waitForTimeout(500);
    calls.length = 0;
    await page.getByPlaceholder("Invoice No").fill("ABC-77");
    await page.getByPlaceholder("Invoice No").press("Enter");
    await page.waitForFunction(() => location.search.includes("invoiceNo=ABC-77"), null, { timeout: 5000 });
    await page.waitForTimeout(500);
    assert(calls.some((c) => c.includes("invoiceNo=ABC-77")), `search request not seen: ${JSON.stringify(calls)}`);
    await page.getByPlaceholder("Consignee Code").fill("341198");
    await page.getByPlaceholder("Consignee Code").press("Enter");
    await page.waitForFunction(() => location.search.includes("consigneeCode=341198"), null, { timeout: 5000 });
    await context.close();
  });

  // ------------------------------------------------------------------ admin: ConfirmModal
  const openAdminUsers = async () => {
    const context = await browser.newContext();
    await seedAdminAuth(context);
    const page = await context.newPage();
    const calls = [];
    const users = [{ ...ADMIN_USER, id: "a1", status: "approved" }];
    await page.route((u) => u.pathname.startsWith("/api/"), (route) => {
      const req = route.request();
      const url = new URL(req.url());
      const respond = (status, body) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
      if (url.pathname === "/api/auth/me") return respond(200, { id: "x", username: "admin1", email: "a@example.invalid", role: "admin" });
      if (url.pathname === "/api/admin/users" && req.method() === "GET") {
        const items = users;
        return respond(200, { items, total: items.length, page: 1, limit: 30, pendingCount: 0 });
      }
      if (/^\/api\/admin\/users\/a1\/reject$/.test(url.pathname)) {
        calls.push("REJECT");
        users[0].status = "rejected";
        return respond(200, { ...users[0] });
      }
      return respond(404, { detail: "unmocked " + url.pathname });
    });
    await page.goto(`${adminVite.url}/users`);
    await page.getByRole("button", { name: /^Approved/ }).click();
    await page.getByRole("button", { name: "Revoke" }).waitFor({ timeout: 10000 });
    return { context, page, calls };
  };
  const openRevoke = async (page) => {
    await page.getByRole("button", { name: "Revoke" }).click();
    await page.getByRole("heading", { name: "Revoke access?" }).waitFor();
  };

  await runner.check("[admin] modal opens with focus on the dialog, Enter confirms (one request)", async () => {
    const { context, page, calls } = await openAdminUsers();
    await openRevoke(page);
    assert((await page.evaluate(() => document.activeElement.tagName)) === "DIALOG", "focus should be on the dialog");
    await page.keyboard.press("Enter");
    await dialogGone(page);
    await page.waitForTimeout(500);
    assert(calls.filter((c) => c === "REJECT").length === 1, `got ${JSON.stringify(calls)}`);
    await context.close();
  });

  await runner.check("[admin] Escape cancels the modal and sends nothing", async () => {
    const { context, page, calls } = await openAdminUsers();
    await openRevoke(page);
    await page.keyboard.press("Escape");
    await dialogGone(page);
    await page.waitForTimeout(400);
    assert(calls.length === 0, `Escape sent ${JSON.stringify(calls)}`);
    await context.close();
  });

  await runner.check("[admin] Enter on the focused Cancel button cancels, never confirms", async () => {
    const { context, page, calls } = await openAdminUsers();
    await openRevoke(page);
    await page.getByRole("dialog").getByRole("button", { name: "Cancel" }).focus();
    await page.keyboard.press("Enter");
    await dialogGone(page);
    await page.waitForTimeout(400);
    assert(calls.length === 0, `got ${JSON.stringify(calls)}`);
    await context.close();
  });

  await runner.check("[admin] two quick Enters / held Enter -> exactly one request", async () => {
    const { context, page, calls } = await openAdminUsers();
    await openRevoke(page);
    await page.keyboard.down("Enter");
    await page.keyboard.down("Enter");
    await page.keyboard.up("Enter");
    await Promise.all([page.keyboard.press("Enter"), page.keyboard.press("Enter")]);
    await page.waitForTimeout(800);
    assert(calls.filter((c) => c === "REJECT").length === 1, `got ${JSON.stringify(calls)}`);
    await context.close();
  });

  // ------------------------------------------------------------------ admin: Nuke dialog
  const openNuke = async () => {
    const context = await browser.newContext();
    await seedAdminAuth(context);
    const page = await context.newPage();
    const calls = [];
    await page.route((u) => u.pathname.startsWith("/api/"), (route) => {
      const req = route.request();
      const url = new URL(req.url());
      const respond = (status, body) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
      if (url.pathname === "/api/auth/me") return respond(200, { id: "x", username: "admin1", email: "a@example.invalid", role: "admin" });
      if (url.pathname === "/api/admin/users/u1" && req.method() === "GET") return respond(200, ADMIN_USER);
      if (url.pathname === "/api/admin/documents") return respond(200, { items: [], total: 0, page: 1, limit: 30 });
      if (url.pathname === "/api/admin/users/u1/nuke") {
        calls.push("NUKE");
        return respond(200, { message: "Deleted 0 documents.", deletedCount: 0 });
      }
      return respond(404, { detail: "unmocked " + url.pathname });
    });
    await page.goto(`${adminVite.url}/users/u1`);
    await page.getByRole("button", { name: /Nuke this user/ }).click();
    const dialog = page.getByRole("dialog");
    await dialog.waitFor();
    await dialog.locator('input[type="password"]').nth(0).fill("Admin#Pass1");
    await dialog.locator('input[type="password"]').nth(1).fill("Admin#Pass1");
    await dialog.locator("input.font-mono").fill("NUKE USER");
    return { context, page, calls, dialog };
  };

  await runner.check("[admin nuke] Enter in every field and on the dialog does NOT nuke", async () => {
    const { context, page, calls, dialog } = await openNuke();
    const confirmButton = dialog.getByRole("button", { name: "Nuke user's documents" });
    assert(await confirmButton.isEnabled(), "precondition: the form is fully valid, so only Enter could be a (wrong) trigger");
    for (const input of [dialog.locator('input[type="password"]').nth(0), dialog.locator('input[type="password"]').nth(1), dialog.locator("input.font-mono")]) {
      await input.press("Enter");
    }
    await dialog.locator("select").press("Enter");
    await dialog.locator("h2").click();
    await page.keyboard.press("Enter");
    await page.keyboard.press("Enter");
    await page.waitForTimeout(800);
    assert(calls.length === 0, `Enter triggered the nuke: ${JSON.stringify(calls)}`);
    assert((await dialog.count()) === 1, "dialog should still be open");
    await context.close();
  });

  await runner.check("[admin nuke] Escape closes the dialog without nuking", async () => {
    const { context, page, calls } = await openNuke();
    await page.keyboard.press("Escape");
    await dialogGone(page);
    await page.waitForTimeout(400);
    assert(calls.length === 0, "Escape must not nuke");
    await context.close();
  });

  await runner.check("[admin nuke] an explicit click on the red button still works (once)", async () => {
    const { context, page, calls, dialog } = await openNuke();
    await dialog.getByRole("button", { name: "Nuke user's documents" }).click();
    await page.waitForTimeout(900);
    assert(calls.length === 1, `expected exactly one NUKE, got ${JSON.stringify(calls)}`);
    await context.close();
  });

  await browser.close();
  appVite.stop();
  adminVite.stop();
  process.exit(runner.summary());
})().catch((err) => {
  console.error("E2E crashed:", err);
  process.exit(2);
});
