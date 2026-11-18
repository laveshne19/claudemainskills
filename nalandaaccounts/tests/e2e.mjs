// Browser test of the portal. Needs playwright. Usage: NODE_PATH=$(npm root -g) node tests/e2e.mjs [screenshot_dir] [base_url]
// With no base_url it starts the local server. With a base_url it tests the real deployed site (needs SYNC_KEY in the environment).
import { createRequire } from "node:module";
const { chromium } = createRequire(import.meta.url)("playwright"); // NODE_PATH works for require, not for import
import { readFileSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { startLocal } from "../server/local.mjs";
import { makeLedgers, pushSync } from "./fixtures.mjs";
import { ledgerId } from "../server/util.mjs";

const shots = process.argv[2] || tmpdir();
const live = process.argv[3] || "";
const SYNC_KEY = process.env.SYNC_KEY || "k".repeat(48);
const results = [];
const check = (name, ok, extra) => { results.push({ name, ok: !!ok, extra }); if (!ok) console.log("FAIL", name, extra ?? ""); };

let local = null, base = live;
if (!live) { local = await startLocal({ env: { SESSION_SECRET: "s".repeat(48), SYNC_KEY } }); base = local.url; }

const ledgers = makeLedgers();
const dealers = ledgers.filter((l) => l.kind === "debtor");
const alpha = dealers[0].name, beta = dealers[1].name, gamma = dealers[2].name;

// first run set up through the same API the sync agent uses
const boot = await fetch(base + "/api/admin/bootstrap", { method: "POST", headers: { "content-type": "application/json", authorization: "Bearer " + SYNC_KEY }, body: JSON.stringify({ username: "lavesh", name: "Lavesh", password: "Temp-Pass-12345" }) });
check("bootstrap creates the master", boot.status === 201 || boot.status === 409, boot.status);
await pushSync(base, SYNC_KEY, ledgers);

const browser = await chromium.launch();
const mk = async (w = 1300, h = 900) => {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, acceptDownloads: true });
  const page = await ctx.newPage();
  const errs = [];
  page.on("pageerror", (e) => errs.push("pageerror " + e.message));
  page.on("console", (m) => { if (m.type() === "error" && !m.text().startsWith("Failed to load resource")) errs.push("console " + m.text()); }); // expected 401/400/404 answers are not page errors
  await page.addInitScript(() => document.addEventListener("securitypolicyviolation", (e) => console.error("CSP VIOLATION " + e.violatedDirective + " " + e.blockedURI)));
  return { ctx, page, errs };
};
const shot = (p, n) => p.screenshot({ path: join(shots, "portal-" + n + ".png") });

// ------------------------------------------------------------- master
const M = await mk();
const p = M.page;
await p.goto(base + "/");
await p.waitForSelector("#loginForm");
await shot(p, "1-login");
await p.fill("#u", "lavesh"); await p.fill("#p", "wrong-password-1"); await p.click("#loginForm button");
await p.waitForSelector(".banner.bad");
check("wrong password gives a plain message", /not right/.test(await p.textContent(".banner.bad")));
await p.fill("#u", "lavesh"); await p.fill("#p", "Temp-Pass-12345"); await p.click("#loginForm button");
await p.waitForSelector("#pwForm");
check("temporary password forces a change", /Choose your own password/.test(await p.textContent("h1")));
await p.fill("#cur", "Temp-Pass-12345"); await p.fill("#nw", "short"); await p.fill("#nw2", "short"); await p.click("#pwForm button[type=submit]");
await p.waitForSelector(".banner.bad");
check("weak new password is refused", /at least 10/.test(await p.textContent(".banner.bad")));
await p.fill("#cur", "Temp-Pass-12345"); await p.fill("#nw", "Better-Pass-98765"); await p.fill("#nw2", "Better-Pass-98765"); await p.click("#pwForm button[type=submit]");
await p.waitForSelector(".kpis");
check("master lands on the dealers list", (await p.locator("tr.link").count()) >= 30);
check("company name and freshness shown", /DEMO DATA/.test(await p.textContent("header.top")) && /Updated/.test(await p.textContent("header.top")));
const tabs = await p.locator("nav.tabs a").allTextContents();
check("master sees all tabs", ["Dealers", "Payables", "Assign dealers", "Users", "Sync"].every((t) => tabs.includes(t)), tabs.join(","));
await shot(p, "2-dealers");

await p.fill("#q", alpha.slice(0, 5)); await p.waitForTimeout(150);
check("search narrows the list", (await p.locator("tr.link").count()) < dealers.length);
await p.fill("#q", "");
await p.selectOption("#sort", "outstanding"); await p.waitForTimeout(150);
const firstAmounts = (await p.locator("tr.link td:nth-child(3)").allTextContents()).slice(0, 3).map((t) => Number(t.replace(/[^0-9]/g, "")));
check("sorted by highest balance", firstAmounts[0] >= firstAmounts[1] && firstAmounts[1] >= firstAmounts[2], firstAmounts.join(","));
await p.click('#chips [data-f="b3"]'); await p.waitForTimeout(150);
const over90 = await p.locator("tr.link").count();
check("over 90 filter works", over90 >= 1 && over90 < dealers.length, over90);
await p.click('#chips [data-f="all"]');

// ----- one dealer and the PDF
await p.fill("#q", alpha); await p.waitForTimeout(150);
await p.locator("tr.link").first().click();
await p.waitForSelector('[data-act="pdf"]');
check("dealer page shows bills and statement", /Unpaid bills/.test(await p.textContent("main")) && /Statement/.test(await p.textContent("main")));
await shot(p, "3-dealer");
const [dl] = await Promise.all([p.waitForEvent("download"), p.click('[data-act="pdf"]')]);
const pdfPath = join(mkdtempSync(join(tmpdir(), "pdf-")), dl.suggestedFilename());
await dl.saveAs(pdfPath);
const pdf = readFileSync(pdfPath);
check("PDF downloads with a sensible name", /^Statement .*\.pdf$/.test(dl.suggestedFilename()), dl.suggestedFilename());
check("PDF is a real PDF", pdf.subarray(0, 5).toString() === "%PDF-" && pdf.length > 3000, pdf.length);
writeFileSync(join(shots, "portal-statement.pdf"), pdf);
await p.selectOption("#per", "90");
check("period can be changed", /Last 90 days/.test(await p.textContent("main")));

// ----- master creates a salesperson and assigns dealers
await p.goto(base + "/#/users"); await p.waitForSelector('[data-act="adduser"]');
await p.click('[data-act="adduser"]');
await p.fill("#nu", "bad name!"); await p.fill("#nn", "Rohit"); await p.click('[data-act="saveuser"]');
await p.waitForSelector("#dlg .banner.bad");
check("bad user name is refused", /User name/.test(await p.textContent("#dlg .banner.bad")));
await p.fill("#nu", "rohit"); await p.selectOption("#nr", "sales"); await p.click('[data-act="saveuser"]');
await p.waitForSelector("#sec");
const temp = (await p.textContent("#sec")).trim();
check("temporary password is shown once", /^[a-zA-Z2-9]{12}$/.test(temp), temp);
await shot(p, "4-new-user");
await p.click('[data-act="closedlg"]');
check("user list shows rohit as temporary", /rohit/.test(await p.textContent("main")) && /temporary password/.test(await p.textContent("main")));

await p.goto(base + "/#/assign"); await p.waitForSelector("#asu");
await p.fill("#asq", alpha); await p.waitForTimeout(250);
await p.locator('input[data-id]').first().check();
await p.fill("#asq", beta); await p.waitForTimeout(250);
await p.locator('input[data-id]').first().check();
await p.fill("#asq", "");
check("two changes waiting to be saved", /Save 2 changes/.test(await p.textContent('[data-act="assave"]')));
await p.click('[data-act="assave"]');
await p.waitForFunction(() => /Saved 2 dealers/.test(document.querySelector("#toast").textContent), null, { timeout: 8000 });
await p.waitForSelector('[data-act="assave"][disabled]'); // page reloaded from the server
check("assignment saved", /2 dealers/.test(await p.textContent(".pill.info")));
// paste a list too
await p.fill("#csv", `${gamma}, rohit\nNo Such Dealer, rohit\n${beta}, ghost`);
await p.click('[data-act="csvcheck"]');
await p.waitForSelector("#csvOut .banner");
const csvTxt = await p.textContent("#csvOut");
check("pasted list reports matches and problems", /1 matched/.test(csvTxt) && /1 dealer names not found/.test(csvTxt) && /unknown user/.test(csvTxt), csvTxt);
await p.click('[data-act="csvapply"]');
await p.waitForFunction(() => /Saved 1 dealer/.test(document.querySelector("#toast").textContent), null, { timeout: 8000 });
await p.waitForFunction(() => /3 dealers/.test(document.querySelector(".pill.info")?.textContent || ""), null, { timeout: 8000 });
await shot(p, "5-assign");

await p.goto(base + "/#/sync"); await p.waitForSelector(".head h1");
check("sync page shows the last sync", /Data is fresh/.test(await p.textContent("main")) && /ledgers/.test(await p.textContent("main")));
await p.goto(base + "/#/payables"); await p.waitForFunction(() => /Total payable/.test(document.body.textContent));
check("payables lists vendors", (await p.locator("tr.link").count()) === 5);

// ------------------------------------------------------------- salesperson
const R = await mk();
const q = R.page;
await q.goto(base + "/"); await q.waitForSelector("#loginForm");
await q.fill("#u", "rohit"); await q.fill("#p", temp); await q.click("#loginForm button");
await q.waitForSelector("#pwForm");
await q.fill("#cur", temp); await q.fill("#nw", "Sales-Pass-24680"); await q.fill("#nw2", "Sales-Pass-24680"); await q.click("#pwForm button[type=submit]");
await q.waitForSelector(".kpis");
check("salesperson sees exactly the 3 assigned dealers", (await q.locator("tr.link").count()) === 3, await q.locator("tr.link").count());
const names = await q.locator("tr.link td:first-child b").allTextContents();
check("and only those", [alpha, beta, gamma].every((n) => names.includes(n)), names.join("|"));
check("no master tabs for a salesperson", (await q.locator("nav.tabs a").count()) === 0);
check("no payables in the salesperson totals", !/Total payable/.test(await q.textContent("main")));
await shot(q, "6-sales-list");
// a dealer that is not theirs, by direct address
const other = dealers.find((d) => ![alpha, beta, gamma].includes(d.name));
await q.goto(base + "/#/dealer/" + ledgerId(other.name));
await q.waitForSelector(".banner.bad");
check("someone else's dealer is 'not found'", /not found, or is not assigned/.test(await q.textContent("main")));
await q.goto(base + "/#/users"); await q.waitForTimeout(400);
check("the users page is not available to a salesperson", !/Add user/.test(await q.textContent("#root")));
await q.goto(base + "/#/dealer/" + ledgerId(alpha)); await q.waitForSelector('[data-act="pdf"]');
const [dl2] = await Promise.all([q.waitForEvent("download"), q.click('[data-act="pdf"]')]);
check("salesperson can download their dealer's PDF", dl2.suggestedFilename().endsWith(".pdf"));

// the master takes a dealer away: the salesperson loses it at once
await p.goto(base + "/#/assign"); await p.waitForSelector("#asu");
await p.selectOption("#asu", "rohit"); await p.fill("#asq", alpha); await p.waitForTimeout(250);
await p.locator('input[data-id]').first().uncheck();
await p.click('[data-act="assave"]'); await p.waitForFunction(() => /Saved 1 dealer/.test(document.querySelector("#toast").textContent), null, { timeout: 8000 });
await q.goto(base + "/#/dealers"); await q.reload(); await q.waitForSelector(".kpis");
check("an unassigned dealer disappears for the salesperson", (await q.locator("tr.link").count()) === 2);

// the master disables the account: the open session ends
await p.goto(base + "/#/users"); await p.waitForSelector('[data-act="toggle"][data-u="rohit"]');
await p.click('[data-act="toggle"][data-u="rohit"]'); await p.waitForTimeout(500);
await q.reload(); await q.waitForSelector("#loginForm");
check("a disabled user is signed out", true);
await q.fill("#u", "rohit"); await q.fill("#p", "Sales-Pass-24680"); await q.click("#loginForm button");
await q.waitForSelector(".banner.bad");
check("and cannot sign back in", /not right/.test(await q.textContent(".banner.bad")));

// ------------------------------------------------------------- phone
const P = await mk(390, 844);
await P.page.goto(base + "/"); await P.page.fill("#u", "lavesh"); await P.page.fill("#p", "Better-Pass-98765"); await P.page.click("#loginForm button");
await P.page.waitForSelector(".dcard");
check("phone shows cards, no sideways scroll", !(await P.page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 2)));
await shot(P.page, "7-phone");
await P.page.locator(".dcard").first().click(); await P.page.waitForSelector('[data-act="pdf"]');
check("phone dealer page has no sideways scroll", !(await P.page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 2)));
await P.page.emulateMedia({ colorScheme: "dark" }); await shot(P.page, "8-phone-dark");

// ------------------------------------------------------------- sign out and errors
await p.goto(base + "/"); await p.waitForSelector(".kpis"); await p.click('[data-act="logout"]'); await p.waitForSelector("#loginForm");
check("sign out returns to the sign in page", true);
const after = await fetch(base + "/api/dealers"); check("API refuses after sign out", after.status === 401);
for (const x of [M, R, P]) check("no browser or security policy errors", x.errs.length === 0, x.errs.join(" | "));

await browser.close();
if (local) local.server.close();
const bad = results.filter((r) => !r.ok);
console.log(JSON.stringify({ total: results.length, passed: results.length - bad.length, failed: bad.map((b) => b.name + " " + (b.extra ?? "")) }, null, 1));
process.exit(bad.length ? 1 : 0);
