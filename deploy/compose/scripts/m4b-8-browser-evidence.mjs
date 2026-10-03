/**
 * M4b-8 browser evidence (dev compose). Requires stack up + m4b-8-seed-users.py.
 * Screenshots omit password entry (filled after capture where noted).
 */
import { chromium } from "playwright";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

const BASE = process.env.AS_COMPOSE_HTTPS_URL ?? "https://localhost:8443";
const PASSWORD = process.env.M4B8_E2E_PASSWORD ?? "";
const DATE = process.env.M4B8_ARTIFACT_DATE ?? "2026-10-03";
const REPO_ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), "../../..");
const OUT_DIR = path.join(REPO_ROOT, "artifacts", "m4b-8", DATE, "screenshots");
const HEALTH_URL =
  process.env.AS_TESTBED_HEALTH_URL ?? "http://10.89.0.30:8080/health";

if (!PASSWORD || PASSWORD.length < 12) {
  console.error("Set M4B8_E2E_PASSWORD (12+ chars) before running.");
  process.exit(1);
}

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

async function login(page, userId, label) {
  await page.goto(`${BASE}/`, { waitUntil: "networkidle" });
  await page.click("#login-button");
  await page.waitForSelector("#login-dialog[open], #login-form");
  if (label) {
    await shot(page, `01-login-dialog-${label}`);
  }
  await page.fill("#login-user-id", userId);
  await page.fill("#login-password", PASSWORD);
  await page.click("#login-submit");
  await page.waitForSelector("#logout-button:not([hidden])", { timeout: 15_000 });
  const loginErr = await page.locator("#login-error:not([hidden])").textContent().catch(() => "");
  if (loginErr) throw new Error(`login failed for ${userId}: ${loginErr}`);
  record(`login-${userId}`, "PASS");
  await shot(page, `02-signed-in-${userId}`);
}

async function closeReviewDialog(page) {
  const open = await page.evaluate(() => Boolean(document.querySelector("#review-dialog")?.open));
  if (open) {
    await page.locator("#review-dialog [data-close-dialog]").first().click();
    await page.waitForFunction(() => !document.querySelector("#review-dialog")?.open, null, {
      timeout: 5_000,
    });
  }
}

async function logout(page) {
  const button = page.locator("#logout-button");
  if (await button.isVisible()) {
    await button.click();
    await page.waitForSelector("#login-button:not([hidden])", { timeout: 10_000 });
  }
}

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ ignoreHTTPSErrors: true });
const page = await context.newPage();

try {
  await login(page, "admin", "shell");
  const requests = [];
  page.on("request", (req) => {
    const url = req.url();
    if (url.includes("/internal/v1/")) {
      requests.push({ method: req.method(), path: url.replace(BASE, "") });
    }
  });

  await page.click('[data-nav-target="operations"]');
  await page.waitForSelector("#operations-view:not([hidden])");
  const fleetIds = ["as-e2e-1", "as-e2e-2"];
  for (const [index, instanceId] of fleetIds.entries()) {
    const exists = await page.locator("table", { hasText: instanceId }).count();
    if (exists) continue;
    await page.click("#create-instance-button");
    await page.fill("#instance-id-field", instanceId);
    await page.fill("#instance-health-url", HEALTH_URL);
    if (index === 0) await shot(page, "03-fleet-instance-form");
    await page.click("#instance-form-submit");
    await page.waitForFunction(() => !document.querySelector("#instance-dialog")?.open, null, {
      timeout: 15_000,
    });
    await page.waitForTimeout(800);
  }
  await shot(page, "04-fleet-inventory");
  record("fleet-instances", "PASS", fleetIds.join(", "));

  await logout(page);
  await login(page, "ops-e2e", null);

  await page.click('[data-nav-target="rules"]');
  const ruleId = `e2e-called-${Date.now()}`;
  await page.click("#create-rule-button");
  await page.fill("#rule-id", ruleId);
  await page.fill("#rule-name", "E2E called prefix");
  // Live M4 console locks match field/type to called + prefix (disabled selects).
  await page.fill("#rule-match-value", "+86139000");
  await page.selectOption("#rule-target", { label: "Translation" });
  await page.fill("#rule-target-detail", "return-uas");
  await shot(page, "05-rule-create-called-prefix");
  const ruleResponse = page.waitForResponse(
    (r) => r.url().includes("/internal/v1/managed-rules") && r.request().method() === "POST",
    { timeout: 15_000 },
  );
  await page.click("#rule-form-submit");
  const created = await ruleResponse;
  if (!created.ok()) {
    throw new Error(`managed-rules POST failed: ${created.status()} ${await created.text()}`);
  }
  await page.waitForFunction(() => !document.querySelector("#rule-dialog")?.open, null, {
    timeout: 5_000,
  });
  await page.waitForTimeout(1000);
  await shot(page, "06-rules-after-propose");

  await page.click('[data-nav-target="change-orders"]');
  await page.waitForTimeout(1000);
  const submitLink = page.locator('button[data-open-order]').filter({ hasText: "Submit" }).first();
  await submitLink.click();
  await page.waitForSelector("#review-dialog[open]");
  await shot(page, "07-change-order-submit-dialog");
  await page.click("#approve-change");
  await page.waitForFunction(() => !document.querySelector("#review-dialog")?.open, null, {
    timeout: 10_000,
  });
  record("operator-submit", "PASS");

  await logout(page);
  await login(page, "mgr-e2e", null);

  await page.click('[data-nav-target="change-orders"]');
  await page.waitForTimeout(1000);
  const reviewLink = page.locator('button[data-open-order]').filter({ hasText: "Review" }).first();
  await reviewLink.click();
  await page.waitForSelector("#review-dialog[open]");
  await shot(page, "08-approver-review");
  await page.click("#approve-change");
  await page.waitForFunction(() => !document.querySelector("#review-dialog")?.open, null, {
    timeout: 10_000,
  });
  await page.click('[data-nav-target="change-orders"]');
  await page.waitForSelector("#change-orders-view:not([hidden])");
  await page.locator("#change-orders-view button[data-open-order]").first().click();
  await page.waitForSelector("#distribution-start", { timeout: 10_000 });
  await shot(page, "09-distribution-panel");
  await page.click("#distribution-start");
  await page.waitForTimeout(3000);
  await shot(page, "10-distribution-in-progress");
  record("distribution-start", "PASS");

  const sameOrigin = requests.some((r) => r.path.startsWith("/internal/v1/"));
  record("same-origin-api", sameOrigin ? "PASS" : "FAIL", JSON.stringify(requests.slice(0, 8)));

  await closeReviewDialog(page);
  await page.click('[data-nav-target="call-traces"]');
  await shot(page, "11-call-traces-blocked-ui");
  record("call-id-trace", "BLOCKED", "REQ-F-13 / M4 adjudication");

  await mkdir(path.dirname(OUT_DIR), { recursive: true });
  await writeFile(
    path.join(REPO_ROOT, "artifacts", "m4b-8", DATE, "browser-evidence-log.json"),
    JSON.stringify({ base: BASE, log, apiSample: requests.slice(0, 20) }, null, 2),
  );
  console.log(`M4b-8 browser evidence written under artifacts/m4b-8/${DATE}/`);
} catch (err) {
  record("fatal", "FAIL", String(err));
  await shot(page, "error-state").catch(() => {});
  throw err;
} finally {
  await browser.close();
}
