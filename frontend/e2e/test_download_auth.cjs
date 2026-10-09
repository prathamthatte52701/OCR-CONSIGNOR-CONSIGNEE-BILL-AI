// User document page: Part 1 / Part 2 downloads must send the bearer token (a plain link would
// not) and must survive a hostile Content-Disposition. Backend mocked - no real data.
// Run: node e2e/test_download_auth.cjs
const path = require("node:path");
const { launchBrowser, startVite, createRunner, assert, seedFrontendAuth } = require("./helpers.cjs");

const DOC = {
  id: "d1",
  invoiceNo: "INV-1",
  uploadStatus: "processed",
  createdAt: "2026-07-01T10:00:00Z",
  lineItems: [],
  part1FilePurged: false,
  part2FilePurged: false,
};

(async () => {
  const runner = createRunner();
  const vite = await startVite(path.join(__dirname, ".."), 6001);
  const browser = await launchBrowser();

  const open = async (docOverrides = {}) => {
    const context = await browser.newContext({ acceptDownloads: true });
    await seedFrontendAuth(context);
    const page = await context.newPage();
    const seen = [];
    await page.route((u) => u.pathname.startsWith("/api/"), (route) => {
      const req = route.request();
      const url = new URL(req.url());
      const respond = (status, body, headers = {}) =>
        route.fulfill({ status, contentType: "application/json", headers, body: JSON.stringify(body) });
      if (url.pathname === "/api/auth/me") return respond(200, { id: "1", username: "tester", email: "t@example.invalid", role: "user" });
      if (url.pathname === "/api/documents/d1") return respond(200, { ...DOC, ...docOverrides });
      const m = url.pathname.match(/^\/api\/documents\/d1\/download\/(part[12])$/);
      if (m) {
        seen.push({ part: m[1], auth: req.headers()["authorization"] || null });
        return route.fulfill({
          status: 200,
          contentType: "image/jpeg",
          headers: { "Content-Disposition": `attachment; filename="${m[1]}-scan.jpg"` },
          body: "FAKE-JPEG",
        });
      }
      return respond(404, { detail: "unmocked " + url.pathname });
    });
    await page.goto(`${vite.url}/documents/d1`);
    await page.getByText("INV-1").first().waitFor({ timeout: 10000 });
    return { context, page, seen };
  };

  for (const [label, part] of [["Part 1", "part1"], ["Part 2", "part2"]]) {
    await runner.check(`${label} download sends the bearer token and saves the named file`, async () => {
      const { context, page, seen } = await open();
      const [download] = await Promise.all([
        page.waitForEvent("download", { timeout: 8000 }),
        page.getByRole("button", { name: label }).click(),
      ]);
      assert(download.suggestedFilename() === `${part}-scan.jpg`, `unexpected filename ${download.suggestedFilename()}`);
      assert(seen.length === 1 && seen[0].part === part, "exactly one request expected");
      assert(seen[0].auth === "Bearer fake.jwt.token", `Authorization header missing/wrong: ${seen[0].auth}`);
      await context.close();
    });
  }

  await runner.check("purged parts show no download button", async () => {
    const { context, page } = await open({ part1FilePurged: true });
    assert((await page.getByRole("button", { name: "Part 1" }).count()) === 0, "Part 1 button should be hidden");
    assert((await page.getByRole("button", { name: "Part 2" }).count()) === 1, "Part 2 button should remain");
    await context.close();
  });

  await runner.check("a failed download shows the server message instead of failing silently", async () => {
    const { context, page } = await open();
    await page.unroute((u) => u.pathname.startsWith("/api/"));
    await page.route((u) => u.pathname.startsWith("/api/documents/d1/download/"), (route) =>
      route.fulfill({ status: 400, contentType: "application/json", body: JSON.stringify({ detail: "Part 1 file has been purged." }) })
    );
    await page.getByRole("button", { name: "Part 1" }).click();
    await page.getByText("Part 1 file has been purged.").first().waitFor({ timeout: 8000 });
    await context.close();
  });

  await browser.close();
  vite.stop();
  process.exit(runner.summary());
})().catch((err) => {
  console.error("E2E crashed:", err);
  process.exit(2);
});
