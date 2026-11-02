// F1-F5: Part 1 / Part 2 upload slots. Backend fully mocked (page.route), tiny generated files.
// Run: node e2e/test_upload_slots.cjs
const path = require("node:path");
const { launchBrowser, startVite, createRunner, assert, seedFrontendAuth } = require("./helpers.cjs");

const JPG = (name, size = 100) => ({
  name,
  mimeType: "image/jpeg",
  buffer: Buffer.concat([Buffer.from([0xff, 0xd8, 0xff]), Buffer.alloc(size - 3)]),
});

(async () => {
  const runner = createRunner();
  const vite = await startVite(path.join(__dirname, ".."), 6002);
  const browser = await launchBrowser();

  // mode: "ok" | "429" | "500" | "slow"
  const open = async (mode = "ok") => {
    const context = await browser.newContext();
    await seedFrontendAuth(context);
    const page = await context.newPage();
    const posts = [];
    await page.route(
      (u) => u.pathname.startsWith("/api/"),
      async (route) => {
        const req = route.request();
        const url = new URL(req.url());
        const respond = (status, body) =>
          route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
        if (url.pathname === "/api/auth/me")
          return respond(200, { id: "1", username: "tester", email: "t@example.invalid", role: "user" });
        if (url.pathname === "/api/documents/upload" && req.method() === "POST") {
          posts.push(1);
          if (mode === "429") return respond(429, { error: "Rate limit exceeded: 120 per 1 hour" });
          if (mode === "500") return respond(500, { detail: "Internal failure" });
          if (mode === "slow") await new Promise((r) => setTimeout(r, 800));
          return respond(201, { id: "d1", uploadStatus: "processing" });
        }
        if (url.pathname === "/api/documents/d1")
          return respond(200, { id: "d1", uploadStatus: "processing", createdAt: "2026-07-01T10:00:00Z", lineItems: [] });
        if (url.pathname === "/api/documents") return respond(200, { items: [], total: 0, page: 1, limit: 30 });
        return respond(404, { detail: "unmocked " + url.pathname });
      }
    );
    await page.goto(`${vite.url}/upload`);
    await page.locator('input[aria-label="Part 1"]').waitFor({ state: "attached", timeout: 10000 });
    return { context, page, posts };
  };
  const in1 = (p) => p.locator('input[aria-label="Part 1"]');
  const in2 = (p) => p.locator('input[aria-label="Part 2"]');
  const btn = (p) => p.getByRole("button", { name: /Upload document|Uploading/ });
  const both = async (page) => {
    await in1(page).setInputFiles(JPG("a.jpg"));
    await in2(page).setInputFiles(JPG("b.jpg"));
  };

  try {
    await runner.check("labels Part 1 / Part 2, no document-type text", async () => {
      const { page, context } = await open();
      const body = await page.locator("body").innerText();
      assert(body.includes("Part 1") && body.includes("Part 2"), "labels missing");
      assert(!/Tax Invoice|Delivery Challan|document type/i.test(body), "document-type text present");
      await context.close();
    });

    await runner.check("empty file -> inline error, nothing selected", async () => {
      const { page, context } = await open();
      await in1(page).setInputFiles({ name: "e.jpg", mimeType: "image/jpeg", buffer: Buffer.alloc(0) });
      await page.getByText("This file is empty.").waitFor({ timeout: 3000 });
      assert((await page.getByText("e.jpg").count()) === 0, "empty file got selected");
      await context.close();
    });

    await runner.check("wrong type (text/plain named .jpg) -> inline error", async () => {
      const { page, context } = await open();
      await in2(page).setInputFiles({ name: "x.jpg", mimeType: "text/plain", buffer: Buffer.from("hello") });
      await page.getByText("Only JPG, JPEG, PNG, and PDF files are allowed.").waitFor({ timeout: 3000 });
      assert((await page.getByText("x.jpg").count()) === 0, "bad file selected");
      await context.close();
    });

    await runner.check("5 MB + 1 byte -> size error; exactly 5 MB accepted", async () => {
      const { page, context } = await open();
      await in1(page).setInputFiles(JPG("big.jpg", 5 * 1024 * 1024 + 1));
      await page.getByText("File size must be 5 MB or less.").waitFor({ timeout: 3000 });
      await in1(page).setInputFiles(JPG("edge.jpg", 5 * 1024 * 1024));
      await page.getByText("edge.jpg").waitFor({ timeout: 3000 });
      assert((await page.getByText("File size must be 5 MB or less.").count()) === 0, "error not cleared");
      await context.close();
    });

    await runner.check("drag over highlights; drop accepts file", async () => {
      const { page, context } = await open();
      const slot = page.getByTestId("slot-Part 1");
      const dt = await page.evaluateHandle(() => {
        const d = new DataTransfer();
        d.items.add(new File([new Uint8Array([0xff, 0xd8, 0xff, 1, 2])], "drop.jpg", { type: "image/jpeg" }));
        return d;
      });
      await slot.dispatchEvent("dragover", { dataTransfer: dt });
      assert((await slot.getAttribute("data-drag")) === "true", "no highlight on dragover");
      await slot.dispatchEvent("drop", { dataTransfer: dt });
      await page.getByText("drop.jpg").waitFor({ timeout: 3000 });
      assert((await slot.getAttribute("data-drag")) === "false", "highlight stuck after drop");
      await context.close();
    });

    await runner.check("name + size shown; Clear removes; Replace swaps", async () => {
      const { page, context } = await open();
      await in1(page).setInputFiles(JPG("a.jpg", 2048));
      await page.getByText("a.jpg").waitFor();
      await page.getByText("2 KB").waitFor();
      await page.getByRole("button", { name: "Clear" }).click();
      assert((await page.getByText("a.jpg").count()) === 0, "not cleared");
      await in1(page).setInputFiles(JPG("a.jpg", 2048));
      await in1(page).setInputFiles(JPG("b.jpg", 4096));
      await page.getByText("b.jpg").waitFor();
      assert((await page.getByText("a.jpg").count()) === 0, "old file still shown");
      await context.close();
    });

    await runner.check("button disabled until both chosen", async () => {
      const { page, context } = await open();
      assert(await btn(page).isDisabled(), "enabled with none");
      await in1(page).setInputFiles(JPG("a.jpg"));
      assert(await btn(page).isDisabled(), "enabled with one");
      await in2(page).setInputFiles(JPG("b.jpg"));
      assert(await btn(page).isEnabled(), "disabled with both");
      await context.close();
    });

    await runner.check("uploading: disabled, spinner text, one POST on double click", async () => {
      const { page, context, posts } = await open("slow");
      await both(page);
      await btn(page).dblclick();
      await page.getByRole("button", { name: "Uploading..." }).waitFor({ timeout: 2000 });
      assert(await btn(page).isDisabled(), "button enabled while uploading");
      await page.waitForURL(/\/documents\/d1/, { timeout: 5000 });
      assert(posts.length === 1, `expected 1 POST, got ${posts.length}`);
      await context.close();
    });

    await runner.check("success navigates to the document", async () => {
      const { page, context } = await open();
      await both(page);
      await btn(page).click();
      await page.waitForURL(/\/documents\/d1/, { timeout: 5000 });
      await context.close();
    });

    await runner.check("429 shows upload-limit message under the form", async () => {
      const { page, context } = await open("429");
      await both(page);
      await btn(page).click();
      await page
        .getByRole("alert")
        .filter({ hasText: "Too many uploads. Please wait a few minutes and try again." })
        .waitFor({ timeout: 4000 });
      await context.close();
    });

    await runner.check("500 shows server message under the form", async () => {
      const { page, context } = await open("500");
      await both(page);
      await btn(page).click();
      await page.getByRole("alert").filter({ hasText: "Internal failure" }).waitFor({ timeout: 4000 });
      assert(await btn(page).isEnabled(), "button stuck disabled after error");
      await context.close();
    });
  } finally {
    await browser.close();
    vite.stop();
  }
  process.exit(runner.summary());
})();
