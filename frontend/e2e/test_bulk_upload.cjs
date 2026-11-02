// Bulk upload (up to 5 sets) + paginated review. Backend fully mocked (page.route), tiny
// generated files, no real data. Run: node e2e/test_bulk_upload.cjs   (from frontend/, port 6003)
const path = require("node:path");
const { launchBrowser, startVite, createRunner, assert, seedFrontendAuth } = require("./helpers.cjs");

const JPG = (name, size = 100) => ({
  name,
  mimeType: "image/jpeg",
  buffer: Buffer.concat([Buffer.from([0xff, 0xd8, 0xff]), Buffer.alloc(size - 3)]),
});

const DETAIL = { invoiceNo: "INV-1", createdAt: "2026-07-01T10:00:00Z", lineItems: [] };

(async () => {
  const runner = createRunner();
  const vite = await startVite(path.join(__dirname, ".."), 6003);
  const browser = await launchBrowser();

  // answers: queue of arrays returned by successive POST /documents/bulk-upload calls
  const open = async (answers = []) => {
    const context = await browser.newContext();
    await seedFrontendAuth(context);
    const page = await context.newPage();
    const state = { posts: [], answers: [...answers], gets: {} };
    await page.route(
      (u) => u.pathname.startsWith("/api/"),
      async (route) => {
        const req = route.request();
        const url = new URL(req.url());
        const respond = (status, body) =>
          route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
        if (url.pathname === "/api/auth/me")
          return respond(200, { id: "1", username: "tester", email: "t@example.invalid", role: "user" });
        if (url.pathname === "/api/documents/bulk-upload" && req.method() === "POST") {
          const body = (req.postDataBuffer() || Buffer.alloc(0)).toString("latin1");
          state.posts.push({
            part1: (body.match(/name="part1"/g) || []).length,
            part2: (body.match(/name="part2"/g) || []).length,
          });
          return respond(201, { results: state.answers.shift() || [] });
        }
        const m = url.pathname.match(/^\/api\/documents\/(d\d+)$/);
        if (m && req.method() === "GET") {
          const id = m[1];
          const n = (state.gets[id] = (state.gets[id] || 0) + 1);
          // d1 / d3: still processing for the first 2 polls, then processed / failed
          if (id === "d1") return respond(200, { ...DETAIL, id, uploadStatus: n > 2 ? "processed" : "processing" });
          if (id === "d3")
            return respond(
              200,
              n > 2
                ? { ...DETAIL, id, uploadStatus: "failed", processingError: "ocr failed on Part 2" }
                : { ...DETAIL, id, uploadStatus: "processing" }
            );
          return respond(200, { ...DETAIL, id, uploadStatus: "processed" });
        }
        if (url.pathname === "/api/documents") return respond(200, { items: [], total: 0, page: 1, limit: 30 });
        return respond(404, { detail: "unmocked " + url.pathname });
      }
    );
    await page.goto(`${vite.url}/upload`);
    await page.getByRole("tab", { name: /Bulk/ }).click();
    await page.locator('input[aria-label="Part 1"]').first().waitFor({ state: "attached", timeout: 10000 });
    return { context, page, state };
  };
  const in1 = (p, i) => p.locator('input[aria-label="Part 1"]').nth(i);
  const in2 = (p, i) => p.locator('input[aria-label="Part 2"]').nth(i);
  const main = (p) => p.getByRole("button", { name: /^(Upload all|Retry failed sets|Uploading)/ });
  const addSet = (p) => p.getByRole("button", { name: "Add set" });
  const fill = async (p, i) => {
    await in1(p, i).setInputFiles(JPG(`a${i}.jpg`));
    await in2(p, i).setInputFiles(JPG(`b${i}.jpg`));
  };

  try {
    await runner.check("a. one row at start, button disabled", async () => {
      const { page, context } = await open();
      assert((await page.locator('input[aria-label="Part 1"]').count()) === 1, "not exactly one row");
      assert(await main(page).isDisabled(), "button enabled with no files");
      await context.close();
    });

    await runner.check("b. only Part 1 -> 'Part 2 missing' + disabled; both -> enabled", async () => {
      const { page, context } = await open();
      await in1(page, 0).setInputFiles(JPG("a.jpg"));
      await page.getByText("Part 2 missing").waitFor({ timeout: 3000 });
      assert(await main(page).isDisabled(), "enabled with one part");
      await in2(page, 0).setInputFiles(JPG("b.jpg"));
      assert(await main(page).isEnabled(), "disabled with both parts");
      await context.close();
    });

    await runner.check("c. Add set stops at 5, Remove brings it back", async () => {
      const { page, context } = await open();
      for (let i = 0; i < 4; i++) await addSet(page).click();
      assert((await page.locator('input[aria-label="Part 1"]').count()) === 5, "not 5 rows");
      assert((await addSet(page).count()) === 0, "Add set still offered at 5");
      await page.getByRole("button", { name: /Remove/ }).first().click();
      assert((await addSet(page).count()) === 1, "Add set not back after Remove");
      await context.close();
    });

    await runner.check("d. a row with one part keeps the button disabled", async () => {
      const { page, context } = await open();
      await addSet(page).click();
      await fill(page, 0);
      await in1(page, 1).setInputFiles(JPG("only.jpg"));
      assert(await main(page).isDisabled(), "enabled with an incomplete row");
      await context.close();
    });

    // ---- e..k: one page, in order
    const first = [
      { index: 0, id: "d1" },
      { index: 1, error: "Set 2, Part 2: PDF must be 4 pages or less." },
      { index: 2, id: "d3" },
    ];
    const retry = [{ index: 0, error: "Set 1, Part 2: still too many pages" }];
    const last = [
      { index: 0, id: "d5" },
      { index: 1, id: "d6" },
    ];
    const { page, context, state } = await open([first, retry, last]);

    await runner.check("e. 3 sets sent; error shown without 'Set 2,' prefix; 2 created; review '1 of 2'", async () => {
      await addSet(page).click();
      await addSet(page).click();
      for (let i = 0; i < 3; i++) await fill(page, i);
      await main(page).click();
      await page.getByText("1 of 2", { exact: true }).waitFor({ timeout: 8000 });
      assert(state.posts[0].part1 === 3 && state.posts[0].part2 === 3, "request did not carry 3 pairs");
      await page.getByText("Part 2: PDF must be 4 pages or less.").waitFor({ timeout: 3000 });
      const body = await page.locator("body").innerText();
      assert(!/Set 2, Part 2/.test(body), "server 'Set 2,' prefix still shown");
      assert((await page.locator("ul li").count()) === 2, "progress list is not 2 sets");
      await page
        .getByText("1 set could not be uploaded - fix them above and press the button.")
        .waitFor({ timeout: 3000 });
    });

    await runner.check("f. Reading... turns into 'All 2 read'", async () => {
      await page.getByText(/^Reading \d of 2/).first().waitFor({ timeout: 3000 });
      await page.getByText("All 2 read").waitFor({ timeout: 20000 });
    });

    await runner.check("g. Next / Previous work, last page disables Next, failed doc error visible", async () => {
      const next = page.getByRole("button", { name: /Next/ });
      const prev = page.getByRole("button", { name: /Previous/ });
      assert(await prev.isDisabled(), "Previous enabled on page 1");
      await next.click();
      await page.getByText("2 of 2", { exact: true }).waitFor({ timeout: 3000 });
      assert(await next.isDisabled(), "Next enabled on the last page");
      await page.getByText("Error: ocr failed on Part 2").waitFor({ timeout: 5000 });
      await prev.click();
      await page.getByText("1 of 2", { exact: true }).waitFor({ timeout: 3000 });
    });

    await runner.check("h. embedded detail: 4 sections + Reprocess, no Back", async () => {
      for (const h of ["Consignee", "Consignor", "Line Items", "Tax Summary"])
        await page.getByRole("heading", { name: h, exact: true }).waitFor({ timeout: 5000 });
      assert((await page.getByRole("button", { name: /Reprocess/ }).count()) >= 1, "no Reprocess button");
      assert((await page.getByRole("button", { name: /Back/ }).count()) === 0, "Back button is shown");
    });

    await runner.check("i. Retry (1): answer 'Set 1, ...' still shown under 'Set 2' without prefix", async () => {
      const btn = page.getByRole("button", { name: "Retry failed sets (1)" });
      assert(await btn.isEnabled(), "retry button not enabled");
      await btn.click();
      await page.getByText("Part 2: still too many pages").waitFor({ timeout: 5000 });
      assert(state.posts[1].part1 === 1 && state.posts[1].part2 === 1, "retry did not carry exactly one pair");
      const body = await page.locator("body").innerText();
      assert(!/Set 1, Part 2/.test(body), "retry prefix 'Set 1,' still shown");
      const card = page.locator("div.rounded-lg", { hasText: "Part 2: still too many pages" }).last();
      assert((await card.getByText("Set 2", { exact: true }).count()) === 1, "error not under header Set 2");
    });

    await runner.check("j. new row next to a failed row: enabled when complete, one request with both", async () => {
      await addSet(page).click();
      assert(await main(page).isDisabled(), "enabled while the new row is empty");
      await fill(page, 1);
      const btn = page.getByRole("button", { name: "Upload all (2)" });
      assert(await btn.isEnabled(), "not enabled with both rows complete");
      await btn.click();
      await page.waitForFunction(() => !document.body.innerText.includes("Add set"), null, { timeout: 8000 });
      assert(state.posts[2].part1 === 2 && state.posts[2].part2 === 2, "one request did not carry both rows");
    });

    await runner.check("k. after full success the form is gone; Start new batch -> one empty row", async () => {
      assert((await page.locator('input[aria-label="Part 1"]').count()) === 0, "form still visible");
      await page.getByRole("button", { name: "Start new batch" }).click();
      assert((await page.locator('input[aria-label="Part 1"]').count()) === 1, "not one empty row");
      assert(await main(page).isDisabled(), "button enabled on a fresh batch");
    });
    await context.close();
  } finally {
    await browser.close();
    vite.stop();
  }
  process.exit(runner.summary());
})();
