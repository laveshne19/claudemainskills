// Tests the DEPLOYED portal end to end, then leaves it clean: sample data loaded, test user disabled, master on a fresh temporary password.
//   NODE_USE_ENV_PROXY=1 NODE_PATH=$(npm root -g) BASE=https://nalandaaccounts.netlify.app SYNC_KEY=... \
//     BOOT_PW=... TEST_PW=... FINAL_PW_FILE=/path node tests/live_smoke.mjs [screenshot_dir]
import { createRequire } from "node:module";
import { readFileSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { makeLedgers, pushSync } from "./fixtures.mjs";
import { ledgerId } from "../server/util.mjs";
import { istDate } from "../server/util.mjs";

const { chromium } = createRequire(import.meta.url)("playwright");
const BASE = process.env.BASE, KEY = process.env.SYNC_KEY, BOOT = process.env.BOOT_PW, TEST = process.env.TEST_PW;
const shots = process.argv[2] || tmpdir();
const results = [];
const check = (name, ok, extra) => { results.push({ name, ok: !!ok, extra }); if (!ok) console.log("FAIL", name, extra ?? ""); };

async function call(method, path, { body, cookie, bearer } = {}) {
  const headers = { "content-type": "application/json" };
  if (cookie) headers.cookie = cookie;
  if (bearer) headers.authorization = "Bearer " + bearer;
  if (method !== "GET") headers["x-requested-with"] = "nalanda";
  const r = await fetch(BASE + path, { method, headers, body: body ? JSON.stringify(body) : undefined });
  const sc = r.headers.get("set-cookie");
  let json = {}; try { json = await r.json(); } catch {}
  return { status: r.status, json, cookie: sc ? sc.split(";")[0] : null, setCookie: sc };
}

// ---- master setup
const boot = await call("POST", "/api/admin/bootstrap", { bearer: KEY, body: { username: "lavesh", name: "Lavesh Bansal", password: BOOT } });
check("master created (or already there)", boot.status === 201 || boot.status === 409, boot.status);
let login = await call("POST", "/api/login", { body: { username: "lavesh", password: BOOT } });
let master = login.cookie;
if (login.status === 200 && login.json.user.mustChange) {
  const c = await call("POST", "/api/change-password", { cookie: master, body: { current: BOOT, next: TEST } });
  check("forced password change works live", c.status === 200, JSON.stringify(c.json));
  master = c.cookie;
} else {
  login = await call("POST", "/api/login", { body: { username: "lavesh", password: TEST } });
  master = login.cookie;
}
check("master signed in", !!master);
check("cookie is locked down", /HttpOnly/.test(login.setCookie || "") && /Secure/.test(login.setCookie || "") && /SameSite=Strict/.test(login.setCookie || ""), login.setCookie);

// ---- sample data, clearly labelled, through the real sync API
const today = istDate(Date.now());
const ledgers = makeLedgers({ today, dealers: 40, vendors: 5 });
const sync = await pushSync(BASE, KEY, ledgers, { company: "DEMO DATA (sample, not real)" });
check("sample data accepted by the live sync API", sync.ok && sync.ledgers === 45, JSON.stringify(sync));
const d = await call("GET", "/api/dealers", { cookie: master });
check("master sees all 45 ledgers", d.json.rows?.length === 45, d.json.rows?.length);
check("totals add up", d.json.totals.receivable > 0 && d.json.today === today);

// ---- a test salesperson, three dealers
const dealers = ledgers.filter((l) => l.kind === "debtor");
const mine = dealers.slice(0, 3).map((x) => x.name), other = dealers[10];
await call("PATCH", "/api/users/smoketest", { cookie: master, body: { active: true } });
let u = await call("POST", "/api/users", { cookie: master, body: { username: "smoketest", name: "Smoke Test", role: "sales" } });
if (u.status === 409) u = await call("PATCH", "/api/users/smoketest", { cookie: master, body: { resetPassword: true, active: true } });
const SALES_PW = "Check-Pass-24680";
const sl = await call("POST", "/api/login", { body: { username: "smoketest", password: u.json.tempPassword } });
const sc = await call("POST", "/api/change-password", { cookie: sl.cookie, body: { current: u.json.tempPassword, next: SALES_PW } });
const sales = sc.cookie;
check("test salesperson ready", sc.status === 200, JSON.stringify(sc.json));
const assign = await call("PUT", "/api/mapping", { cookie: master, body: { mode: "replace", assignments: Object.fromEntries(mine.map((n) => [ledgerId(n), ["smoketest"]])) } });
check("three dealers assigned", assign.json.applied === 3, JSON.stringify(assign.json));
const sd = await call("GET", "/api/dealers", { cookie: sales });
check("salesperson sees exactly their three", sd.json.rows.length === 3 && sd.json.rows.every((r) => mine.includes(r.name)), sd.json.rows?.length);
check("no payables for a salesperson", sd.json.totals.payable === 0);
check("another dealer is not found for them", (await call("GET", "/api/ledger/" + ledgerId(other.name), { cookie: sales })).status === 404);
check("their own dealer opens", (await call("GET", "/api/ledger/" + ledgerId(mine[0]), { cookie: sales })).status === 200);
check("users page is master only", (await call("GET", "/api/users", { cookie: sales })).status === 403);
check("data is refused without a session", (await call("GET", "/api/dealers")).status === 401);
const wrong = await call("POST", "/api/login", { body: { username: "lavesh", password: "definitely-wrong-1" } });
check("wrong password refused with a plain message", wrong.status === 401 && /not right/.test(wrong.json.error));

// ---- the real browser on the real site
const proxy = process.env.HTTPS_PROXY ? { server: process.env.HTTPS_PROXY } : undefined;
const browser = await chromium.launch({ proxy });
const ctx = await browser.newContext({ viewport: { width: 1300, height: 900 }, acceptDownloads: true });
const page = await ctx.newPage();
const errs = [];
page.on("pageerror", (e) => errs.push("pageerror " + e.message));
page.on("console", (m) => { if (m.type() === "error" && !m.text().startsWith("Failed to load resource")) errs.push("console " + m.text()); });
await page.addInitScript(() => document.addEventListener("securitypolicyviolation", (e) => console.error("CSP VIOLATION " + e.violatedDirective + " " + e.blockedURI)));
await page.goto(BASE + "/");
await page.waitForSelector("#loginForm");
await page.screenshot({ path: join(shots, "live-1-login.png") });
await page.fill("#u", "lavesh"); await page.fill("#p", TEST); await page.click("#loginForm button");
await page.waitForSelector(".kpis");
check("browser: master sees the dealer list on the live site", (await page.locator("tr.link").count()) >= 30);
check("browser: sample data is clearly labelled", /DEMO DATA/.test(await page.textContent("header.top")));
await page.screenshot({ path: join(shots, "live-2-dealers.png") });
await page.fill("#q", mine[0]); await page.waitForTimeout(200);
await page.locator("tr.link").first().click();
await page.waitForSelector('[data-act="pdf"]');
await page.screenshot({ path: join(shots, "live-3-dealer.png") });
const [dl] = await Promise.all([page.waitForEvent("download"), page.click('[data-act="pdf"]')]);
const pdfPath = join(mkdtempSync(join(tmpdir(), "pdf-")), dl.suggestedFilename());
await dl.saveAs(pdfPath);
const pdf = readFileSync(pdfPath);
check("browser: PDF statement downloads on the live site", pdf.subarray(0, 5).toString() === "%PDF-" && pdf.length > 3000, pdf.length);
writeFileSync(join(shots, "live-statement.pdf"), pdf);
check("browser: no page errors or security policy violations", errs.length === 0, errs.join(" | "));
await browser.close();

// ---- leave it clean
await call("PUT", "/api/mapping", { cookie: master, body: { mode: "replace", assignments: {} } });
await call("PATCH", "/api/users/smoketest", { cookie: master, body: { active: false } });
check("the test user cannot sign in any more", (await call("POST", "/api/login", { body: { username: "smoketest", password: SALES_PW } })).status === 401);
const reset = await call("PATCH", "/api/users/lavesh", { cookie: master, body: { resetPassword: true } });
check("master reset to a fresh temporary password", reset.status === 200 && !!reset.json.tempPassword);
writeFileSync(process.env.FINAL_PW_FILE, reset.json.tempPassword);
check("old master password no longer works", (await call("POST", "/api/login", { body: { username: "lavesh", password: TEST } })).status === 401);

const bad = results.filter((r) => !r.ok);
console.log(JSON.stringify({ total: results.length, passed: results.length - bad.length, failed: bad.map((b) => b.name + " " + (b.extra ?? "")) }, null, 1));
process.exit(bad.length ? 1 : 0);
