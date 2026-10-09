// T4: signup success + the two 403 login messages are clear, persistent and not spoofable.
// Backend fully mocked (page.route) - touches no real data. Run: node e2e/test_login_approval.cjs
const path = require("node:path");
const { launchBrowser, startVite, createRunner, assert, seedFrontendAuth } = require("./helpers.cjs");

const PENDING = "Waiting for admin approval.";
const REJECTED = "Your request was not approved. Contact the admin.";

(async () => {
  const runner = createRunner();
  const vite = await startVite(path.join(__dirname, ".."), 6001);
  const browser = await launchBrowser();

  const newPage = async (setup) => {
    const context = await browser.newContext();
    if (setup) await setup(context);
    const page = await context.newPage();
    return { context, page };
  };
  const mockLogin = (page, status, body) =>
    page.route("**/api/auth/login", (route) =>
      route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) })
    );
  const submitLogin = async (page) => {
    await page.goto(`${vite.url}/login`);
    await page.fill('input[type="email"]', "someone@example.invalid");
    await page.fill('input[type="password"]', "Whatever1!");
    await page.click('button[type="submit"]');
  };

  await runner.check("login 403 pending shows the pending message inline (role=alert)", async () => {
    const { context, page } = await newPage();
    await mockLogin(page, 403, { detail: PENDING });
    await submitLogin(page);
    const alert = page.getByRole("alert").filter({ hasText: PENDING });
    await alert.waitFor({ timeout: 8000 });
    assert((await alert.count()) === 1, "expected exactly one inline pending alert");
    assert(!(await page.url()).includes("/dashboard"), "must stay on the login page");
    await context.close();
  });

  await runner.check("login 403 rejected shows the rejected message inline", async () => {
    const { context, page } = await newPage();
    await mockLogin(page, 403, { detail: REJECTED });
    await submitLogin(page);
    await page.getByRole("alert").filter({ hasText: REJECTED }).waitFor({ timeout: 8000 });
    await context.close();
  });

  await runner.check("message stays on screen (persistent, not a vanishing toast)", async () => {
    const { context, page } = await newPage();
    await mockLogin(page, 403, { detail: PENDING });
    await submitLogin(page);
    await page.getByRole("alert").filter({ hasText: PENDING }).waitFor({ timeout: 8000 });
    await page.waitForTimeout(6000); // longer than a default toast lifetime
    assert((await page.getByRole("alert").filter({ hasText: PENDING }).count()) === 1, "message vanished");
    await context.close();
  });

  await runner.check("wrong password (401) is a toast, NOT an approval banner", async () => {
    const { context, page } = await newPage();
    await mockLogin(page, 401, { detail: "Invalid email or password." });
    await submitLogin(page);
    await page.getByText("Invalid email or password.").first().waitFor({ timeout: 8000 });
    assert((await page.getByRole("alert").filter({ hasText: /approval|approved/i }).count()) === 0, "approval banner shown for a 401");
    await context.close();
  });

  await runner.check("signup success lands on login with the waiting-for-approval banner", async () => {
    const { context, page } = await newPage();
    await page.route("**/api/auth/signup", (route) =>
      route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ message: "Account created. Waiting for admin approval." }) })
    );
    await page.goto(`${vite.url}/signup`);
    await page.fill("input[minlength='3']", "newbie");
    await page.fill('input[type="email"]', "newbie@example.invalid");
    await page.fill('input[type="password"]', "Str0ng!Passw0rd");
    await page.click('button[type="submit"]');
    await page.waitForURL(/\/login\?notice=signup/, { timeout: 8000 });
    await page.getByRole("alert").filter({ hasText: "Account created. Waiting for admin approval." }).waitFor({ timeout: 5000 });
    await context.close();
  });

  await runner.check("notice param cannot inject arbitrary text (phishing guard)", async () => {
    const { context, page } = await newPage();
    await page.goto(`${vite.url}/login?notice=${encodeURIComponent("Your account is locked, call 555-0100")}`);
    await page.waitForSelector("form");
    assert((await page.getByRole("alert").count()) === 0, "unknown notice key rendered something");
    assert(!(await page.content()).includes("555-0100"), "free text from the URL reached the page");
    await context.close();
    const { context: c2, page: p2 } = await newPage();
    await p2.goto(`${vite.url}/login?notice=<img src=x onerror=alert(1)>`);
    await p2.waitForSelector("form");
    assert((await p2.getByRole("alert").count()) === 0, "markup in notice rendered");
    await c2.close();
  });

  await runner.check("logged-in user un-approved mid-session is sent to login with the reason", async () => {
    const { context, page } = await newPage((ctx) => seedFrontendAuth(ctx));
    await page.route("**/api/auth/me", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ id: "1", username: "tester", email: "t@example.invalid", role: "user" }) })
    );
    // Only real API calls (pathname /api/...), never Vite's own /src/api/*.js module requests.
    await page.route(
      (url) => url.pathname.startsWith("/api/documents"),
      (route) =>
        route.fulfill({ status: 403, contentType: "application/json", body: JSON.stringify({ detail: PENDING }) })
    );
    await page.goto(`${vite.url}/documents`);
    await page.waitForURL(/\/login\?notice=pending/, { timeout: 10000 });
    await page.getByRole("alert").filter({ hasText: PENDING }).waitFor({ timeout: 5000 });
    const stored = await page.evaluate(() => localStorage.getItem("main-ocr-auth"));
    assert(!stored || !JSON.parse(stored).state.token, "token was not cleared");
    await context.close();
  });

  await runner.check("login 403 with an unrelated detail does not render as approval text", async () => {
    const { context, page } = await newPage();
    await mockLogin(page, 403, { detail: "Something else entirely" });
    await submitLogin(page);
    await page.waitForTimeout(1500);
    assert((await page.getByRole("alert").count()) === 0, "unrelated 403 shown as an approval banner");
    await context.close();
  });

  await browser.close();
  vite.stop();
  process.exit(runner.summary());
})().catch((err) => {
  console.error("E2E crashed:", err);
  process.exit(2);
});
