// T7 (UI): profile shows the email read-only; the admin panel can change a user's email (with a
// confirmation, and without any call when nothing changed). Backend mocked - no real data.
// Run: node e2e/test_email_admin_only.cjs
const path = require("node:path");
const { launchBrowser, startVite, createRunner, assert, seedAdminAuth, seedFrontendAuth } = require("./helpers.cjs");

const USER = { id: "u1", username: "alice", email: "alice@example.invalid", role: "user", status: "approved", createdAt: "2026-07-01T10:00:00Z" };

(async () => {
  const runner = createRunner();
  const appVite = await startVite(path.join(__dirname, ".."), 6001);
  const adminVite = await startVite(path.join(__dirname, "..", "..", "admin"), 7000);
  const browser = await launchBrowser();

  await runner.check("profile page: email is plain text, no email input, with the read-only note", async () => {
    const context = await browser.newContext();
    await seedFrontendAuth(context, { email: "me@example.invalid" });
    const page = await context.newPage();
    await page.route((u) => u.pathname.startsWith("/api/"), (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ id: "1", username: "tester", email: "me@example.invalid", role: "user" }) })
    );
    await page.goto(`${appVite.url}/profile`);
    await page.getByText("me@example.invalid").first().waitFor({ timeout: 10000 });
    assert((await page.locator('input[type="email"]').count()) === 0, "profile must not offer an email input");
    assert((await page.getByText(/Only an admin can change it/).count()) === 1, "read-only note missing");
    await context.close();
  });

  const openAdmin = async (opts = {}) => {
    const context = await browser.newContext();
    await seedAdminAuth(context);
    const page = await context.newPage();
    const patches = [];
    await page.route((u) => u.pathname.startsWith("/api/"), (route) => {
      const req = route.request();
      const url = new URL(req.url());
      const respond = (status, body) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
      if (url.pathname === "/api/auth/me") return respond(200, { id: "x", username: "admin1", email: "a@example.invalid", role: "admin" });
      if (url.pathname === "/api/admin/users/u1" && req.method() === "GET") return respond(200, USER);
      if (url.pathname === "/api/admin/users/u1" && req.method() === "PATCH") {
        const body = JSON.parse(req.postData());
        patches.push(body);
        if (opts.fail) return respond(400, { detail: "That email is already in use." });
        return respond(200, { ...USER, email: body.email.trim().toLowerCase() });
      }
      if (url.pathname === "/api/admin/documents") return respond(200, { items: [], total: 0, page: 1, limit: 30 });
      return respond(404, { detail: "unmocked " + url.pathname });
    });
    await page.goto(`${adminVite.url}/users/u1`);
    await page.getByText("alice@example.invalid").first().waitFor({ timeout: 10000 });
    return { context, page, patches };
  };

  await runner.check("admin: Change email opens an input pre-filled with the current email", async () => {
    const { context, page } = await openAdmin();
    await page.getByRole("button", { name: "Change email" }).click();
    assert((await page.getByLabel("New email").inputValue()) === USER.email, "input should be pre-filled");
    await context.close();
  });

  await runner.check("admin: saving an unchanged email sends nothing and opens no dialog", async () => {
    const { context, page, patches } = await openAdmin();
    await page.getByRole("button", { name: "Change email" }).click();
    await page.getByRole("button", { name: "Save" }).click();
    await page.waitForTimeout(600);
    assert(patches.length === 0, "no PATCH expected for an unchanged email");
    assert((await page.getByRole("dialog").count()) === 0, "dialog should not open");
    await context.close();
  });

  await runner.check("admin: a new email needs confirmation; Cancel sends nothing", async () => {
    const { context, page, patches } = await openAdmin();
    await page.getByRole("button", { name: "Change email" }).click();
    await page.getByLabel("New email").fill("bob@example.invalid");
    await page.getByRole("button", { name: "Save" }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByRole("heading", { name: "Change this user's email?" }).waitFor();
    assert((await dialog.innerText()).includes("logged out everywhere"), "must warn about the forced logout");
    await dialog.getByRole("button", { name: "Cancel" }).click();
    await page.waitForTimeout(500);
    assert(patches.length === 0, "Cancel must not send the change");
    await context.close();
  });

  await runner.check("admin: confirming sends ONE PATCH with the email and updates the page", async () => {
    const { context, page, patches } = await openAdmin();
    await page.getByRole("button", { name: "Change email" }).click();
    await page.getByLabel("New email").fill(" Bob@Example.INVALID ");
    await page.getByRole("button", { name: "Save" }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Change email" }).click();
    await page.getByText("bob@example.invalid").first().waitFor({ timeout: 8000 });
    assert(patches.length === 1 && patches[0].email.trim() === "Bob@Example.INVALID", `unexpected PATCH: ${JSON.stringify(patches)}`);
    await context.close();
  });

  await runner.check("admin: a server rejection (already in use) shows the message and keeps the old email", async () => {
    const { context, page } = await openAdmin({ fail: true });
    await page.getByRole("button", { name: "Change email" }).click();
    await page.getByLabel("New email").fill("taken@example.invalid");
    await page.getByRole("button", { name: "Save" }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Change email" }).click();
    await page.getByText("That email is already in use.").first().waitFor({ timeout: 8000 });
    assert((await page.getByText("alice@example.invalid").count()) >= 1, "old email should still show");
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
