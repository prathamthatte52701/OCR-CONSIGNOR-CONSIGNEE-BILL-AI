// Shared helpers for the browser (Playwright) checks in this folder.
//
// - No new project dependency: Playwright is resolved from PLAYWRIGHT_PATH, a normal install, or the
//   npx cache, and the system Chrome/Edge is used if the bundled Chromium is missing.
// - No backend and no database needed: every /api call is answered by page.route() mocks, so these
//   checks can never touch real data.
// Run any script with:  node e2e/test_xxx.cjs   (from frontend/)

const { spawn, execSync } = require("node:child_process");
const fs = require("node:fs");
const http = require("node:http");
const os = require("node:os");
const path = require("node:path");

function resolvePlaywright() {
  const candidates = [process.env.PLAYWRIGHT_PATH, "playwright"];
  const npxCache = path.join(process.env.LOCALAPPDATA || os.homedir(), "npm-cache", "_npx");
  if (fs.existsSync(npxCache)) {
    for (const dir of fs.readdirSync(npxCache)) {
      candidates.push(path.join(npxCache, dir, "node_modules", "playwright"));
    }
  }
  for (const candidate of candidates.filter(Boolean)) {
    try {
      return require(candidate);
    } catch {
      /* try next */
    }
  }
  throw new Error("Playwright not found. Set PLAYWRIGHT_PATH to a playwright package directory.");
}

async function launchBrowser() {
  const { chromium } = resolvePlaywright();
  try {
    return await chromium.launch({ headless: true });
  } catch {
    return chromium.launch({ headless: true, channel: "chrome" });
  }
}

function waitForHttp(url, timeoutMs = 60000) {
  const deadline = Date.now() + timeoutMs;
  return new Promise((resolve, reject) => {
    const attempt = () => {
      http
        .get(url, (res) => {
          res.resume();
          resolve();
        })
        .on("error", () => {
          if (Date.now() > deadline) reject(new Error(`Timed out waiting for ${url}`));
          else setTimeout(attempt, 400);
        });
    };
    attempt();
  });
}

// Starts `vite` for an app directory on a fixed port; returns { url, stop }.
async function startVite(appDir, port) {
  const child = spawn("npx", ["vite", "--port", String(port), "--strictPort"], {
    cwd: appDir,
    shell: true,
    stdio: "ignore",
  });
  const url = `http://localhost:${port}`;
  await waitForHttp(url);
  return {
    url,
    stop() {
      try {
        execSync(`taskkill /pid ${child.pid} /T /F`, { stdio: "ignore" });
      } catch {
        child.kill();
      }
    },
  };
}

function createRunner() {
  const results = [];
  return {
    results,
    async check(name, fn) {
      try {
        await fn();
        results.push({ name, ok: true });
        console.log(`PASS  ${name}`);
      } catch (err) {
        results.push({ name, ok: false, error: String(err && err.message ? err.message : err) });
        console.log(`FAIL  ${name}\n      ${String(err && err.message ? err.message : err).split("\n")[0]}`);
      }
    },
    summary() {
      const passed = results.filter((r) => r.ok).length;
      console.log(`\nSUMMARY: ${passed}/${results.length} passed, ${results.length - passed} failed`);
      return results.length === passed ? 0 : 1;
    },
  };
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

// Seeds the persisted zustand auth store (frontend) so a page loads as a logged-in user.
async function seedFrontendAuth(context, user = {}) {
  const state = {
    state: { token: "fake.jwt.token", username: "tester", email: "t@example.invalid", role: "user", ...user },
    version: 0,
  };
  // Seed only on the FIRST document load of the context - init scripts re-run on every
  // navigation, which would otherwise undo a logout the app just performed.
  await context.addInitScript((value) => {
    if (!sessionStorage.getItem("e2e-seeded")) {
      localStorage.setItem("main-ocr-auth", value);
      sessionStorage.setItem("e2e-seeded", "1");
    }
  }, JSON.stringify(state));
}

async function seedAdminAuth(context, user = {}) {
  const state = { token: "fake.jwt.token", username: "admin1", email: "a@example.invalid", role: "admin", ...user };
  await context.addInitScript((value) => {
    if (!sessionStorage.getItem("e2e-seeded")) {
      localStorage.setItem("main-ocr-admin-auth", value);
      sessionStorage.setItem("e2e-seeded", "1");
    }
  }, JSON.stringify(state));
}

module.exports = {
  launchBrowser,
  startVite,
  createRunner,
  assert,
  seedFrontendAuth,
  seedAdminAuth,
};
