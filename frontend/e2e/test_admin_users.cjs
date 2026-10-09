// T5: admin Users panel - Pending tab + badge, Approve/Reject, Rejected tab (Re-approve/Delete),
// Revoke on approved users. Backend fully mocked (page.route) - touches no real data.
// Run: node e2e/test_admin_users.cjs
const path = require("node:path");
const { launchBrowser, startVite, createRunner, assert, seedAdminAuth } = require("./helpers.cjs");

const mkUser = (id, status, role = "user") => ({
  id,
  username: `user${id}`,
  email: `user${id}@example.invalid`,
  role,
  status,
  createdAt: "2026-07-01T10:00:00Z",
});

(async () => {
  const runner = createRunner();
  const vite = await startVite(path.join(__dirname, "..", "..", "admin"), 7000);
  const browser = await launchBrowser();

  // Opens the admin Users page with an in-memory fake backend. Returns { page, calls, users }.
  const open = async ({ failNext } = {}) => {
    const context = await browser.newContext();
    await seedAdminAuth(context);
    const page = await context.newPage();
    const users = [
      mkUser("p1", "pending"),
      mkUser("p2", "pending"),
      mkUser("a1", "approved"),
      mkUser("r1", "rejected"),
      mkUser("adm", "approved", "admin"),
    ];
    const calls = [];
    let failures = failNext || 0;
    await page.route(
      (url) => url.pathname.startsWith("/api/"),
      async (route) => {
        const req = route.request();
        const url = new URL(req.url());
        const respond = (status, body) =>
          route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
        if (url.pathname === "/api/auth/me") {
          return respond(200, { id: "x", username: "admin1", email: "a@example.invalid", role: "admin" });
        }
        if (url.pathname === "/api/admin/users" && req.method() === "GET") {
          const status = url.searchParams.get("status");
          const items = users.filter((u) => !status || u.status === status);
          return respond(200, {
            items,
            total: items.length,
            page: 1,
            limit: 30,
            pendingCount: users.filter((u) => u.status === "pending").length,
          });
        }
        const m = url.pathname.match(/^\/api\/admin\/users\/([^/]+)(?:\/(approve|reject))?$/);
        if (m && (req.method() === "POST" || req.method() === "DELETE")) {
          calls.push(`${req.method()} ${url.pathname}`);
          if (failures > 0) {
            failures -= 1;
            return respond(400, { detail: "Admin accounts cannot be rejected." });
          }
          const user = users.find((u) => u.id === m[1]);
          if (req.method() === "DELETE") users.splice(users.indexOf(user), 1);
          else user.status = m[2] === "approve" ? "approved" : "rejected";
          return respond(200, req.method() === "DELETE" ? { message: "deleted" } : { ...user });
        }
        return respond(404, { detail: "unmocked " + url.pathname });
      }
    );
    await page.goto(`${vite.url}/users`);
    await page.getByRole("button", { name: /^Pending/ }).waitFor({ timeout: 10000 });
    return { context, page, calls, users };
  };
  const row = (page, id) => page.locator("a", { hasText: `user${id}@example.invalid` });

  await runner.check("Pending is the default tab and shows a count badge", async () => {
    const { context, page } = await open();
    await row(page, "p1").waitFor();
    assert((await page.getByTestId("pending-badge").innerText()) === "2", "badge should read 2");
    assert((await row(page, "p2").count()) === 1, "second pending user missing");
    assert((await row(page, "a1").count()) === 0, "approved user leaked into Pending tab");
    await context.close();
  });

  await runner.check("pending rows offer Approve and Reject; approve acts instantly", async () => {
    const { context, page, calls } = await open();
    const r = row(page, "p1");
    await r.getByRole("button", { name: "Approve" }).waitFor();
    assert((await r.getByRole("button", { name: "Reject" }).count()) === 1, "Reject missing");
    await r.getByRole("button", { name: "Approve" }).click();
    await page.waitForFunction(() => !document.body.innerText.includes("userp1@example.invalid"), null, { timeout: 8000 });
    assert(calls.join() === "POST /api/admin/users/p1/approve", `unexpected calls: ${calls}`);
    assert(!page.url().includes("/users/p1"), "clicking a button must not open the user page");
    await context.close();
  });

  await runner.check("Reject asks for confirmation; Cancel sends nothing", async () => {
    const { context, page, calls } = await open();
    await row(page, "p1").getByRole("button", { name: "Reject" }).click();
    await page.getByRole("heading", { name: "Reject this sign-up?" }).waitFor();
    await page.getByRole("button", { name: "Cancel" }).click();
    await page.waitForTimeout(500);
    assert(calls.length === 0, `Cancel must not call the API, got ${calls}`);
    await context.close();
  });

  await runner.check("confirming Reject rejects the user and moves them out of Pending", async () => {
    const { context, page, calls } = await open();
    await row(page, "p1").getByRole("button", { name: "Reject" }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Reject" }).click();
    await page.waitForFunction(() => !document.body.innerText.includes("userp1@example.invalid"), null, { timeout: 8000 });
    assert(calls.join() === "POST /api/admin/users/p1/reject", `unexpected calls: ${calls}`);
    await context.close();
  });

  await runner.check("Rejected tab shows Re-approve and Delete (and nothing else)", async () => {
    const { context, page } = await open();
    await page.getByRole("button", { name: "Rejected" }).click();
    const r = row(page, "r1");
    await r.waitFor();
    assert((await r.getByRole("button", { name: "Re-approve" }).count()) === 1, "Re-approve missing");
    assert((await r.getByRole("button", { name: "Delete" }).count()) === 1, "Delete missing");
    assert((await r.getByRole("button", { name: "Reject" }).count()) === 0, "Reject should not show here");
    await context.close();
  });

  await runner.check("Re-approve works without a prompt", async () => {
    const { context, page, calls } = await open();
    await page.getByRole("button", { name: "Rejected" }).click();
    await row(page, "r1").getByRole("button", { name: "Re-approve" }).click();
    await page.waitForFunction(() => !document.body.innerText.includes("userr1@example.invalid"), null, { timeout: 8000 });
    assert(calls.join() === "POST /api/admin/users/r1/approve", `unexpected calls: ${calls}`);
    await context.close();
  });

  await runner.check("Delete needs confirmation, warns it is permanent, then deletes", async () => {
    const { context, page, calls } = await open();
    await page.getByRole("button", { name: "Rejected" }).click();
    await row(page, "r1").getByRole("button", { name: "Delete" }).click();
    await page.getByRole("heading", { name: "Permanently delete this user?" }).waitFor();
    assert((await page.getByRole("dialog").innerText()).includes("There is no undo"), "missing permanence warning");
    assert(calls.length === 0, "API called before confirming");
    await page.getByRole("dialog").getByRole("button", { name: "Delete" }).click();
    await page.waitForFunction(() => !document.body.innerText.includes("userr1@example.invalid"), null, { timeout: 8000 });
    assert(calls.join() === "DELETE /api/admin/users/r1", `unexpected calls: ${calls}`);
    await context.close();
  });

  await runner.check("Approved tab: non-admin gets Revoke (confirmed), admin row has no actions", async () => {
    const { context, page, calls } = await open();
    await page.getByRole("button", { name: "Approved" }).click();
    await row(page, "a1").waitFor();
    assert((await row(page, "adm").getByRole("button").count()) === 0, "admin row must have no action buttons");
    await row(page, "a1").getByRole("button", { name: "Revoke" }).click();
    await page.getByRole("heading", { name: "Revoke access?" }).waitFor();
    await page.getByRole("dialog").getByRole("button", { name: "Revoke" }).click();
    await page.waitForFunction(() => !document.body.innerText.includes("usera1@example.invalid"), null, { timeout: 8000 });
    assert(calls.join() === "POST /api/admin/users/a1/reject", `unexpected calls: ${calls}`);
    await context.close();
  });

  await runner.check("double-clicking Approve sends exactly ONE request", async () => {
    const { context, page, calls } = await open();
    await row(page, "p1").getByRole("button", { name: "Approve" }).dblclick();
    await page.waitForTimeout(1200);
    assert(calls.length === 1, `expected 1 request, got ${calls.length}: ${calls}`);
    await context.close();
  });

  await runner.check("a server error shows a message and keeps the list intact", async () => {
    const { context, page, calls } = await open({ failNext: 1 });
    await row(page, "p1").getByRole("button", { name: "Approve" }).click();
    await page.getByText("Admin accounts cannot be rejected.").first().waitFor({ timeout: 8000 });
    assert(calls.length === 1, "request should have been attempted once");
    assert((await row(page, "p1").count()) === 1, "user vanished after a failed action");
    await context.close();
  });

  await browser.close();
  vite.stop();
  process.exit(runner.summary());
})().catch((err) => {
  console.error("E2E crashed:", err);
  process.exit(2);
});
