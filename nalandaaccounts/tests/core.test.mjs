import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createApp } from "../server/core.mjs";
import { memoryStore } from "../server/store.mjs";
import { CSP } from "../server/csp.mjs";
import { deriveBillsFIFO, ageBills, bucketOf } from "../server/ageing.mjs";
import { ledgerId, istDate } from "../server/util.mjs";

const SESSION_SECRET = "s".repeat(48);
const SYNC_KEY = "k".repeat(48);
const T0 = Date.parse("2026-09-30T06:00:00Z"); // 30 Sep 2026 11:30 IST

function mk({ now = T0, secureCookie = true, env = { SESSION_SECRET, SYNC_KEY } } = {}) {
  const clock = { t: now };
  const store = memoryStore();
  const app = createApp({ store, env, now: () => clock.t, secureCookie, log: () => {} });
  async function call(method, path, { body, cookie, key, csrf = true, ip, raw } = {}) {
    const headers = new Headers();
    if (body !== undefined || raw) headers.set("content-type", "application/json");
    if (cookie) headers.set("cookie", cookie);
    if (key) headers.set("authorization", "Bearer " + key);
    if (csrf && method !== "GET") headers.set("x-requested-with", "nalanda");
    if (ip) headers.set("x-nf-client-connection-ip", ip);
    const res = await app(new Request("https://example.test" + path, { method, headers, body: raw ?? (body !== undefined ? JSON.stringify(body) : undefined) }));
    const text = await res.text();
    let json = null; try { json = JSON.parse(text); } catch {}
    const sc = res.headers.get("set-cookie");
    return { status: res.status, json, headers: res.headers, cookie: sc ? sc.split(";")[0] : null, setCookie: sc };
  }
  return { app, store, call, clock };
}

const led = (name, over = {}) => ({
  name, group: "Sundry Debtors", kind: "debtor", city: "Chandigarh", phone: "9000000000",
  opening: { amount: 0, side: "Dr" }, closing: { amount: 10000, side: "Dr" },
  vouchers: [
    { date: "2026-08-01", type: "Sales", number: "INV-1", particulars: "Sales", debit: 6000, credit: 0 },
    { date: "2026-09-01", type: "Sales", number: "INV-2", particulars: "Sales", debit: 4000, credit: 0 },
  ], ...over,
});

async function setup(opts) {
  const w = mk(opts);
  const b = await w.call("POST", "/api/admin/bootstrap", { key: SYNC_KEY, body: { username: "lavesh", name: "Lavesh", password: "Temp-Pass-12345" } });
  assert.equal(b.status, 201);
  const l = await w.call("POST", "/api/login", { body: { username: "lavesh", password: "Temp-Pass-12345" } });
  assert.equal(l.status, 200);
  let cookie = l.cookie;
  const c = await w.call("POST", "/api/change-password", { cookie, body: { current: "Temp-Pass-12345", next: "Better-Pass-98765" } });
  assert.equal(c.status, 200);
  cookie = c.cookie;
  w.master = cookie;
  return w;
}

async function sync(w, ledgers, { full = true, run = "run-" + Math.random().toString(36).slice(2, 10) } = {}) {
  assert.equal((await w.call("POST", "/api/sync/start", { key: SYNC_KEY, body: { runId: run, company: "TEST CO", full } })).status, 200);
  for (let i = 0; i < ledgers.length; i += 500) {
    const r = await w.call("POST", "/api/sync/ledgers", { key: SYNC_KEY, body: { runId: run, ledgers: ledgers.slice(i, i + 500) } });
    assert.equal(r.status, 200, JSON.stringify(r.json));
  }
  const f = await w.call("POST", "/api/sync/finish", { key: SYNC_KEY, body: { runId: run } });
  assert.equal(f.status, 200);
  return f.json;
}

async function addUser(w, username, role = "sales") {
  const r = await w.call("POST", "/api/users", { cookie: w.master, body: { username, name: username, role } });
  assert.equal(r.status, 201);
  const l = await w.call("POST", "/api/login", { body: { username, password: r.json.tempPassword } });
  const c = await w.call("POST", "/api/change-password", { cookie: l.cookie, body: { current: r.json.tempPassword, next: "Sales-Pass-98765" } });
  assert.equal(c.status, 200, JSON.stringify(c.json));
  return { cookie: c.cookie, temp: r.json.tempPassword };
}

// ------------------------------------------------------------------ configuration
test("health is public, everything else refuses to run without secrets", async () => {
  const w = mk({ env: {} });
  assert.deepEqual((await w.call("GET", "/api/health")).json, { ok: true, configured: false });
  assert.equal((await w.call("GET", "/api/dealers")).status, 503);
  const short = mk({ env: { SESSION_SECRET: "short", SYNC_KEY: "short" } });
  assert.equal((await short.call("POST", "/api/login", { body: { username: "a", password: "b" } })).status, 503);
});

test("security headers on every API answer", async () => {
  const w = mk();
  const r = await w.call("GET", "/api/me");
  assert.equal(r.headers.get("cache-control"), "no-store");
  assert.equal(r.headers.get("x-content-type-options"), "nosniff");
  assert.equal(r.status, 401);
});

test("netlify.toml repeats the same content security policy", () => {
  const toml = readFileSync(new URL("../netlify.toml", import.meta.url), "utf8");
  assert.ok(toml.includes(`Content-Security-Policy = "${CSP}"`), "CSP in netlify.toml differs from server/csp.mjs");
  assert.ok(CSP.includes("script-src 'self'") && !CSP.includes("unsafe-eval"));
});

// ------------------------------------------------------------------ bootstrap and login
test("bootstrap needs the sync key, works once, and rejects weak passwords", async () => {
  const w = mk();
  const body = { username: "lavesh", name: "Lavesh", password: "Temp-Pass-12345" };
  assert.equal((await w.call("POST", "/api/admin/bootstrap", { body })).status, 401);
  assert.equal((await w.call("POST", "/api/admin/bootstrap", { key: "x".repeat(48), body })).status, 401);
  assert.equal((await w.call("POST", "/api/admin/bootstrap", { key: SYNC_KEY, body: { ...body, password: "short" } })).status, 400);
  assert.equal((await w.call("POST", "/api/admin/bootstrap", { key: SYNC_KEY, body: { ...body, username: "A B" } })).status, 400);
  assert.equal((await w.call("POST", "/api/admin/bootstrap", { key: SYNC_KEY, body })).status, 201);
  assert.equal((await w.call("POST", "/api/admin/bootstrap", { key: SYNC_KEY, body: { ...body, username: "second" } })).status, 409);
});

test("passwords are never stored in plain text", async () => {
  const w = mk();
  await w.call("POST", "/api/admin/bootstrap", { key: SYNC_KEY, body: { username: "lavesh", name: "L", password: "Temp-Pass-12345" } });
  const u = await w.store.get("user/lavesh");
  assert.equal(u.password.alg, "scrypt");
  assert.ok(!JSON.stringify(u).includes("Temp-Pass-12345"));
});

test("login gives one vague answer, sets a locked down cookie, and locks after repeated failures", async () => {
  const w = await setup();
  const bad1 = await w.call("POST", "/api/login", { body: { username: "lavesh", password: "wrong-password" } });
  const bad2 = await w.call("POST", "/api/login", { body: { username: "nobody", password: "wrong-password" } });
  assert.equal(bad1.status, 401); assert.equal(bad2.status, 401);
  assert.equal(bad1.json.error, bad2.json.error); // cannot tell who exists
  const ok = await w.call("POST", "/api/login", { body: { username: "lavesh", password: "Better-Pass-98765" } });
  assert.equal(ok.status, 200);
  for (const part of ["HttpOnly", "Secure", "SameSite=Strict", "Path=/"]) assert.ok(ok.setCookie.includes(part), part);
  for (let i = 0; i < 5; i++) await w.call("POST", "/api/login", { body: { username: "lavesh", password: "nope-nope-nope" } });
  const locked = await w.call("POST", "/api/login", { body: { username: "lavesh", password: "Better-Pass-98765" } });
  assert.equal(locked.status, 429, "even the right password is refused while locked");
  w.clock.t += 16 * 60 * 1000;
  assert.equal((await w.call("POST", "/api/login", { body: { username: "lavesh", password: "Better-Pass-98765" } })).status, 200);
});

test("one address cannot hammer many user names", async () => {
  const w = mk();
  let last;
  for (let i = 0; i < 41; i++) last = await w.call("POST", "/api/login", { body: { username: "user" + i + "xx", password: "bad-password-1" }, ip: "9.9.9.9" });
  assert.equal(last.status, 429);
  assert.equal((await w.call("POST", "/api/login", { body: { username: "someone", password: "bad-password-1" }, ip: "8.8.8.8" })).status, 401);
});

test("a first login must change the temporary password, which signs out other sessions", async () => {
  const w = mk();
  await w.call("POST", "/api/admin/bootstrap", { key: SYNC_KEY, body: { username: "lavesh", name: "L", password: "Temp-Pass-12345" } });
  const l = await w.call("POST", "/api/login", { body: { username: "lavesh", password: "Temp-Pass-12345" } });
  assert.equal(l.json.user.mustChange, true);
  const blocked = await w.call("GET", "/api/dealers", { cookie: l.cookie });
  assert.equal(blocked.status, 403); assert.equal(blocked.json.mustChange, true);
  assert.equal((await w.call("GET", "/api/me", { cookie: l.cookie })).status, 200);
  assert.equal((await w.call("POST", "/api/change-password", { cookie: l.cookie, body: { current: "wrong", next: "Better-Pass-98765" } })).status, 400);
  assert.equal((await w.call("POST", "/api/change-password", { cookie: l.cookie, body: { current: "Temp-Pass-12345", next: "short" } })).status, 400);
  assert.equal((await w.call("POST", "/api/change-password", { cookie: l.cookie, body: { current: "Temp-Pass-12345", next: "lavesh-is-me-1" } })).status, 400);
  const ok = await w.call("POST", "/api/change-password", { cookie: l.cookie, body: { current: "Temp-Pass-12345", next: "Better-Pass-98765" } });
  assert.equal(ok.status, 200);
  assert.equal((await w.call("GET", "/api/dealers", { cookie: ok.cookie })).status, 200);
  assert.equal((await w.call("GET", "/api/me", { cookie: l.cookie })).status, 401, "the old session is dead");
});

test("sessions expire, can be tampered with by no one, and need the custom header to change anything", async () => {
  const w = await setup();
  assert.equal((await w.call("GET", "/api/me", { cookie: w.master })).status, 200);
  const forged = w.master.replace(/.$/, (c) => (c === "A" ? "B" : "A"));
  assert.equal((await w.call("GET", "/api/me", { cookie: forged })).status, 401);
  assert.equal((await w.call("GET", "/api/me", { cookie: "na_session=garbage" })).status, 401);
  assert.equal((await w.call("POST", "/api/users", { cookie: w.master, csrf: false, body: { username: "abc", role: "sales" } })).status, 403);
  w.clock.t += 8 * 86400 * 1000;
  assert.equal((await w.call("GET", "/api/me", { cookie: w.master })).status, 401);
});

test("bad or oversized JSON is refused politely", async () => {
  const w = mk();
  assert.equal((await w.call("POST", "/api/login", { raw: "{not json" })).status, 400);
  assert.equal((await w.call("POST", "/api/login", { raw: JSON.stringify({ username: "a".repeat(70000) }) })).status, 413);
});

// ------------------------------------------------------------------ users
test("only the master manages users, and the last master is protected", async () => {
  const w = await setup();
  const s = await addUser(w, "rohit", "sales");
  assert.equal((await w.call("GET", "/api/users", { cookie: s.cookie })).status, 403);
  assert.equal((await w.call("POST", "/api/users", { cookie: s.cookie, body: { username: "evil", role: "master" } })).status, 403);
  assert.equal((await w.call("GET", "/api/mapping", { cookie: s.cookie })).status, 403);
  const dup = await w.call("POST", "/api/users", { cookie: w.master, body: { username: "rohit", role: "sales" } });
  assert.equal(dup.status, 409);
  assert.equal((await w.call("POST", "/api/users", { cookie: w.master, body: { username: "Bad Name!", role: "sales" } })).status, 400);
  assert.equal((await w.call("POST", "/api/users", { cookie: w.master, body: { username: "okname", role: "emperor" } })).status, 400);
  const r = await w.call("POST", "/api/users", { cookie: w.master, body: { username: "temp1", role: "sales" } });
  assert.match(r.json.tempPassword, /^[a-zA-Z2-9]{12}$/);
  const list = await w.call("GET", "/api/users", { cookie: w.master });
  assert.ok(!JSON.stringify(list.json).includes("scrypt"), "password hashes never leave the server");
  assert.equal((await w.call("PATCH", "/api/users/lavesh", { cookie: w.master, body: { active: false } })).status, 400);
  assert.equal((await w.call("PATCH", "/api/users/lavesh", { cookie: w.master, body: { role: "sales" } })).status, 400);
});

test("disabling or resetting a user ends their sessions at once", async () => {
  const w = await setup();
  const s = await addUser(w, "navneet", "sales");
  assert.equal((await w.call("GET", "/api/me", { cookie: s.cookie })).status, 200);
  const reset = await w.call("PATCH", "/api/users/navneet", { cookie: w.master, body: { resetPassword: true } });
  assert.equal(reset.status, 200);
  assert.equal((await w.call("GET", "/api/me", { cookie: s.cookie })).status, 401);
  const l = await w.call("POST", "/api/login", { body: { username: "navneet", password: reset.json.tempPassword } });
  assert.equal(l.json.user.mustChange, true);
  await w.call("PATCH", "/api/users/navneet", { cookie: w.master, body: { active: false } });
  assert.equal((await w.call("GET", "/api/me", { cookie: l.cookie })).status, 401);
  assert.equal((await w.call("POST", "/api/login", { body: { username: "navneet", password: reset.json.tempPassword } })).status, 401);
});

// ------------------------------------------------------------------ sync
test("the sync agent needs its key, and bad data is rejected with reasons", async () => {
  const w = await setup();
  assert.equal((await w.call("POST", "/api/sync/start", { body: { runId: "run-123456" } })).status, 401);
  assert.equal((await w.call("POST", "/api/sync/start", { key: "wrong".repeat(10), body: { runId: "run-123456" } })).status, 401);
  assert.equal((await w.call("POST", "/api/sync/start", { key: SYNC_KEY, body: { runId: "../x" } })).status, 400);
  assert.equal((await w.call("POST", "/api/sync/ledgers", { key: SYNC_KEY, body: { runId: "neverstarted", ledgers: [] } })).status, 404);
  await w.call("POST", "/api/sync/start", { key: SYNC_KEY, body: { runId: "run-123456", company: "X" } });
  const bad = await w.call("POST", "/api/sync/ledgers", { key: SYNC_KEY, body: { runId: "run-123456", ledgers: [led("A", { closing: { amount: -5, side: "Dr" } }), { name: "" }, led("B", { vouchers: [{ date: "31/12/2026", debit: 1, credit: 0 }] })] } });
  assert.equal(bad.status, 400);
  assert.ok(bad.json.problems.length >= 3);
  const many = await w.call("POST", "/api/sync/ledgers", { key: SYNC_KEY, body: { runId: "run-123456", ledgers: Array.from({ length: 501 }, (_, i) => led("L" + i)) } });
  assert.equal(many.status, 400);
  assert.equal((await w.call("POST", "/api/sync/ledgers", { key: SYNC_KEY, raw: JSON.stringify({ runId: "run-123456", pad: "x".repeat(5.2 * 1024 * 1024) }) })).status, 413);
});

test("a full sync replaces everything, a partial sync keeps the rest, a repeated batch does not double up", async () => {
  const w = await setup();
  await sync(w, [led("Alpha Traders"), led("Beta Traders"), led("Gamma Traders")]);
  let d = await w.call("GET", "/api/dealers", { cookie: w.master });
  assert.equal(d.json.rows.length, 3);
  assert.equal(d.json.company, "TEST CO");
  await sync(w, [led("Alpha Traders", { closing: { amount: 500, side: "Dr" } })], { full: false });
  d = await w.call("GET", "/api/dealers", { cookie: w.master });
  assert.equal(d.json.rows.length, 3);
  assert.equal(d.json.rows.find((r) => r.name === "Alpha Traders").outstanding, 500);
  const run = "run-dupes01";
  await w.call("POST", "/api/sync/start", { key: SYNC_KEY, body: { runId: run } });
  for (let i = 0; i < 2; i++) await w.call("POST", "/api/sync/ledgers", { key: SYNC_KEY, body: { runId: run, ledgers: [led("Delta Traders")] } });
  assert.equal((await w.call("POST", "/api/sync/finish", { key: SYNC_KEY, body: { runId: run } })).json.ledgers, 1);
  d = await w.call("GET", "/api/dealers", { cookie: w.master });
  assert.deepEqual(d.json.rows.map((r) => r.name), ["Delta Traders"], "full sync dropped the others");
  const st = await w.call("GET", "/api/sync/status", { cookie: w.master });
  assert.ok(st.json.meta.history.length >= 3);
});

// ------------------------------------------------------------------ who sees what
test("a salesperson only ever sees the dealers assigned to them", async () => {
  const w = await setup();
  await sync(w, [led("Alpha Traders"), led("Beta Traders"), led("Vendor One", { kind: "creditor", group: "Sundry Creditors", closing: { amount: 7000, side: "Cr" }, vouchers: [{ date: "2026-09-10", type: "Purchase", number: "P-1", particulars: "Goods", debit: 0, credit: 7000 }] })]);
  const rohit = await addUser(w, "rohit"); const navneet = await addUser(w, "navneet"); const acc = await addUser(w, "accounts1", "accounts");
  const idA = ledgerId("Alpha Traders"), idB = ledgerId("Beta Traders"), idV = ledgerId("Vendor One");

  assert.equal((await w.call("GET", "/api/dealers", { cookie: rohit.cookie })).json.rows.length, 0, "nothing until assigned");
  const m = await w.call("PUT", "/api/mapping", { cookie: w.master, body: { assignments: { [idA]: ["rohit"], [idB]: ["navneet", "rohit", "ghost"], [idV]: ["rohit"], "no-such-id": ["rohit"] } } });
  assert.equal(m.status, 200); assert.equal(m.json.applied, 2); assert.equal(m.json.skippedCount, 2);

  const r = (await w.call("GET", "/api/dealers", { cookie: rohit.cookie })).json;
  assert.deepEqual(r.rows.map((x) => x.name).sort(), ["Alpha Traders", "Beta Traders"]);
  assert.equal(r.totals.payable, 0, "salespeople never see payables");
  assert.equal(r.rows[0].assigned, undefined, "assignments are not shown to salespeople");
  assert.deepEqual((await w.call("GET", "/api/dealers", { cookie: navneet.cookie })).json.rows.map((x) => x.name), ["Beta Traders"]);
  assert.equal((await w.call("GET", "/api/ledger/" + idA, { cookie: navneet.cookie })).status, 404, "not theirs");
  assert.equal((await w.call("GET", "/api/ledger/" + idV, { cookie: rohit.cookie })).status, 404, "a vendor is never visible to sales");
  assert.equal((await w.call("GET", "/api/ledger/" + idA, { cookie: rohit.cookie })).status, 200);
  assert.equal((await w.call("GET", "/api/ledger/does-not-exist", { cookie: rohit.cookie })).status, 404);
  for (const bad of ["..%2F..%2Fuser%2Flavesh", "user/lavesh", "A_B", "x".repeat(200)]) assert.equal((await w.call("GET", "/api/ledger/" + bad, { cookie: w.master })).status, 404, bad);

  assert.equal((await w.call("GET", "/api/dealers", { cookie: acc.cookie })).json.rows.length, 3, "accounts sees everything");
  assert.equal((await w.call("GET", "/api/dealers", { cookie: w.master })).json.rows.length, 3);
  assert.equal((await w.call("GET", "/api/dealers")).status, 401);
  assert.equal((await w.call("GET", "/api/ledger/" + idA)).status, 401);
});

test("taking a dealer away from a salesperson takes effect straight away", async () => {
  const w = await setup();
  await sync(w, [led("Alpha Traders")]);
  const rohit = await addUser(w, "rohit");
  const id = ledgerId("Alpha Traders");
  await w.call("PUT", "/api/mapping", { cookie: w.master, body: { assignments: { [id]: ["rohit"] } } });
  assert.equal((await w.call("GET", "/api/ledger/" + id, { cookie: rohit.cookie })).status, 200);
  await w.call("PUT", "/api/mapping", { cookie: w.master, body: { assignments: { [id]: [] } } });
  assert.equal((await w.call("GET", "/api/ledger/" + id, { cookie: rohit.cookie })).status, 404);
});

// ------------------------------------------------------------------ ageing and statements
test("ageing counts from the bill date and moves on as days pass", async () => {
  const w = await setup();
  await sync(w, [led("Alpha Traders")]);
  let d = (await w.call("GET", "/api/dealers", { cookie: w.master })).json;
  assert.equal(d.today, "2026-09-30");
  let row = d.rows[0];
  assert.deepEqual(row.buckets, { b0: 4000, b1: 6000, b2: 0, b3: 0, older: 0 }); // INV-2 is 29 days old, INV-1 is 60
  assert.equal(row.oldestDays, 60);
  w.clock.t = Date.parse("2026-11-20T06:00:00Z");
  const again = await w.call("POST", "/api/login", { body: { username: "lavesh", password: "Better-Pass-98765" } }); // the old session has expired
  d = (await w.call("GET", "/api/dealers", { cookie: again.cookie })).json;
  row = d.rows[0];
  assert.deepEqual(row.buckets, { b0: 0, b1: 0, b2: 4000, b3: 6000, older: 0 }, "same data, later date, older buckets");
  assert.equal(d.totals.receivable, 10000);
});

test("bills are rebuilt newest first when Tally gave no bill wise data, and the rest is 'older'", async () => {
  const f = deriveBillsFIFO(led("x").vouchers, "debtor", 7000);
  assert.deepEqual(f.bills.map((b) => [b.ref, b.pending]), [["INV-1", 3000], ["INV-2", 4000]]);
  assert.equal(f.older, 0);
  const g = deriveBillsFIFO(led("x").vouchers, "debtor", 12000);
  assert.equal(g.older, 2000);
  assert.deepEqual(deriveBillsFIFO([], "debtor", 500), { bills: [], older: 500 });
  assert.deepEqual(deriveBillsFIFO(led("x").vouchers, "debtor", 0).bills, []);
  assert.equal(bucketOf(0), "b0"); assert.equal(bucketOf(30), "b0"); assert.equal(bucketOf(31), "b1"); assert.equal(bucketOf(91), "b3");
  assert.equal(ageBills([{ date: "2026-09-30", pending: 5 }], 0, "2026-09-29").bills[0].days, 0, "never negative");
});

test("bill wise data from Tally is kept, and the tie out to the ledger balance is reported", async () => {
  const w = await setup();
  await sync(w, [led("Alpha Traders", { bills: [{ ref: "INV-2", date: "2026-09-01", pending: 4000 }, { ref: "INV-1", date: "2026-08-01", pending: 5000 }] })]);
  const id = ledgerId("Alpha Traders");
  const v = (await w.call("GET", "/api/ledger/" + id, { cookie: w.master })).json;
  assert.equal(v.ledger.billwise, true);
  assert.deepEqual(v.ledger.check, { billsTotal: 9000, outstanding: 10000, diff: 1000 });
  assert.equal(v.ledger.older, 1000, "the part that cannot be tied to a dated bill is shown as older");
  assert.equal(v.ledger.totals.total, 10000);
});

test("the statement carries a running balance and creditors and advances are handled", async () => {
  const w = await setup();
  await sync(w, [
    led("Alpha Traders", { opening: { amount: 1000, side: "Dr" }, closing: { amount: 9000, side: "Dr" },
      vouchers: [{ date: "2026-08-01", type: "Sales", number: "INV-1", particulars: "Sales", debit: 6000, credit: 0 }, { date: "2026-08-20", type: "Receipt", number: "R-1", particulars: "HDFC", debit: 0, credit: 2000 }, { date: "2026-09-01", type: "Sales", number: "INV-2", particulars: "Sales", debit: 4000, credit: 0 }] }),
    led("Advance Co", { closing: { amount: 300, side: "Cr" }, vouchers: [{ date: "2026-09-01", type: "Receipt", number: "R-9", particulars: "Advance", debit: 0, credit: 300 }] }),
  ]);
  const v = (await w.call("GET", "/api/ledger/" + ledgerId("Alpha Traders"), { cookie: w.master })).json;
  assert.deepEqual(v.statement.rows.map((r) => r.balance), [{ amount: 7000, side: "Dr" }, { amount: 5000, side: "Dr" }, { amount: 9000, side: "Dr" }]);
  assert.equal(v.statement.rows.at(-1).balance.amount, v.statement.closing.amount, "running balance ends at the ledger balance");
  const adv = (await w.call("GET", "/api/dealers", { cookie: w.master })).json.rows.find((r) => r.name === "Advance Co");
  assert.equal(adv.outstanding, 0, "a customer who paid in advance owes nothing");
});

test("utility functions", () => {
  assert.equal(istDate(Date.parse("2026-09-30T20:00:00Z")), "2026-10-01", "India is 5 and a half hours ahead");
  assert.notEqual(ledgerId("A & B"), ledgerId("A and B"));
  assert.equal(ledgerId("Same"), ledgerId("Same"));
});

test("the page has no inline scripts, which the security policy would block", () => {
  let html = ""; try { html = readFileSync(new URL("../site/index.html", import.meta.url), "utf8"); } catch { return; }
  const inline = [...html.matchAll(/<script\b([^>]*)>/gi)].filter((m) => !/\bsrc=/.test(m[1]));
  assert.equal(inline.length, 0, "inline <script> found");
  assert.ok(!/\son[a-z]+=/i.test(html), "inline event handler found");
});

test("a warning from the sync agent is kept and shown with the ledger", async () => {
  const w = await setup();
  await sync(w, [led("Alpha Traders", { warning: "Statement may be incomplete: entries do not add up to the Tally balance." })]);
  const v = (await w.call("GET", "/api/ledger/" + ledgerId("Alpha Traders"), { cookie: w.master })).json;
  assert.match(v.ledger.warning, /may be incomplete/);
});
