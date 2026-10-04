/**
 * M5 / 7.2d — HTTPS-only console login via ingress (kind + port-forward).
 * Requires M5_7_2D_E2E_PASSWORD (or M4B8_E2E_PASSWORD), HOSTALIASES or /etc/hosts for ingress host.
 */
import { chromium } from "playwright";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

const HOST = process.env.M5_INGRESS_HOST ?? "console.m5.test";
const HTTPS_PORT = process.env.M5_INGRESS_HTTPS_PORT ?? "18443";
const BASE = `https://${HOST}:${HTTPS_PORT}`;
const PASSWORD = process.env.M5_7_2D_E2E_PASSWORD ?? process.env.M4B8_E2E_PASSWORD ?? "";
const DATE = process.env.M5_ARTIFACT_DATE ?? new Date().toISOString().slice(0, 10);
const REPO_ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), "../../..");
const OUT_DIR = path.join(REPO_ROOT, "artifacts", "m5", DATE, "7.2d-screenshots");

if (!PASSWORD || PASSWORD.length < 12) {
  console.error("Set M5_7_2D_E2E_PASSWORD (12+ chars).");
  process.exit(1);
}

// Corporate HTTP proxies break loopback ingress checks (same as m4b-8 / m5-lib).
process.env.NO_PROXY = "*";
process.env.no_proxy = "*";

const log = [];
function record(step, status, detail = "") {
  log.push({ step, status, detail, at: new Date().toISOString() });
}

async function shot(page, name) {
  await mkdir(OUT_DIR, { recursive: true });
  const file = path.join(OUT_DIR, `${name}.png`);
  await page.screenshot({ path: file, fullPage: true });
  return file;
}

const browser = await chromium.launch({
  headless: true,
  args: [`--host-resolver-rules=MAP ${HOST} 127.0.0.1`],
});
const context = await browser.newContext({ ignoreHTTPSErrors: true });
const page = await context.newPage();

const insecurePosts = [];
page.on("request", (req) => {
  const url = req.url();
  if (req.method() === "POST" && url.startsWith("http://")) {
    insecurePosts.push(url);
  }
});

try {
  await page.goto(`${BASE}/`, { waitUntil: "networkidle" });
  record("https-root", "PASS", BASE);
  await shot(page, "01-https-console");

  await page.click("#login-button");
  await page.waitForSelector("#login-dialog[open], #login-form");
  await page.fill("#login-user-id", "admin");
  await page.fill("#login-password", PASSWORD);
  await page.click("#login-submit");
  await page.waitForSelector("#logout-button:not([hidden])", { timeout: 20_000 });
  const loginErr = await page.locator("#login-error:not([hidden])").textContent().catch(() => "");
  if (loginErr) throw new Error(`login failed: ${loginErr}`);
  record("https-login", "PASS");
  await shot(page, "02-signed-in-admin");

  if (insecurePosts.length > 0) {
    record("no-plain-http-post", "FAIL", insecurePosts.join(", "));
    throw new Error(`credential/API POST over HTTP: ${insecurePosts.join(", ")}`);
  }
  record("no-plain-http-post", "PASS");

  await mkdir(path.dirname(OUT_DIR), { recursive: true });
  await writeFile(
    path.join(REPO_ROOT, "artifacts", "m5", DATE, "7.2d-browser-log.json"),
    JSON.stringify({ base: BASE, log }, null, 2),
  );
  console.log(`7.2d browser evidence: artifacts/m5/${DATE}/`);
} catch (err) {
  record("fatal", "FAIL", String(err));
  await shot(page, "error").catch(() => {});
  throw err;
} finally {
  await browser.close();
}
