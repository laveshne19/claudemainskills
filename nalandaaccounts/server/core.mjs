// The whole API as one function: createApp({store, env}) -> async (Request) => Response.
// Netlify runs it behind netlify/functions/api.mjs. The tests and the local server call it directly.
import { ageBills, deriveBillsFIFO, withRunning } from "./ageing.mjs";
import { MIN_PASSWORD, SESSION_DAYS, hashPassword, parseCookies, passwordProblem, readSession, signSession, verifyPassword } from "./auth.mjs";
import { clip, istDate, isIsoDate, ledgerId, round2, safeEqual, tempPassword, validId } from "./util.mjs";

const COOKIE = "na_session";
const ROLES = ["master", "accounts", "sales"];
const KINDS = ["debtor", "creditor", "other"];
const LOCK_WINDOW_MS = 15 * 60 * 1000;
const MAX_USER_FAILS = 5;
const MAX_IP_FAILS = 40;
const MAX_JSON = 64 * 1024;
const MAX_SYNC = 5 * 1024 * 1024;
const USERNAME = /^[a-z0-9._-]{3,32}$/;

export function createApp({ store, env, now = () => Date.now(), secureCookie = true, log = console.error }) {
  const SESSION_SECRET = env.SESSION_SECRET || "";
  const SYNC_KEY = env.SYNC_KEY || "";
  const configured = SESSION_SECRET.length >= 32 && SYNC_KEY.length >= 32;

  // ---------------------------------------------------------------- responses
  const baseHeaders = {
    "content-type": "application/json; charset=utf-8",
    "cache-control": "no-store",
    "x-content-type-options": "nosniff",
    "referrer-policy": "no-referrer",
  };
  const json = (status, body, extra = {}) => new Response(JSON.stringify(body), { status, headers: { ...baseHeaders, ...extra } });
  const fail = (status, error, more = {}) => json(status, { ok: false, error, ...more });

  async function readJson(req, limit) {
    const len = Number(req.headers.get("content-length") || 0);
    if (len > limit) throw Object.assign(new Error("too large"), { status: 413 });
    const text = await req.text();
    if (text.length > limit) throw Object.assign(new Error("too large"), { status: 413 });
    try { return text ? JSON.parse(text) : {}; } catch { throw Object.assign(new Error("bad json"), { status: 400 }); }
  }

  const cookieHeader = (token, maxAge) =>
    `${COOKIE}=${encodeURIComponent(token)}; HttpOnly; ${secureCookie ? "Secure; " : ""}SameSite=Strict; Path=/; Max-Age=${maxAge}`;

  // ---------------------------------------------------------------- storage helpers
  const getUser = (u) => store.get(`user/${u}`);
  const publicUser = (u) => ({ username: u.username, name: u.name, role: u.role, active: u.active, mustChange: !!u.mustChange, createdAt: u.createdAt, lastLoginAt: u.lastLoginAt || null });

  async function currentUser(req) {
    const token = parseCookies(req.headers.get("cookie"))[COOKIE];
    const s = readSession(SESSION_SECRET, token, now());
    if (!s) return null;
    const u = await getUser(s.u);
    if (!u || !u.active || u.tokenVersion !== s.v) return null;
    return u;
  }

  function clientIp(req) {
    return (req.headers.get("x-nf-client-connection-ip") || (req.headers.get("x-forwarded-for") || "").split(",")[0] || "unknown").trim().slice(0, 64);
  }

  async function lockState(key) {
    const rec = (await store.get(`lock/${key}`)) || { n: 0, first: 0, until: 0 };
    if (now() - rec.first > LOCK_WINDOW_MS && rec.until < now()) return { n: 0, first: 0, until: 0 };
    return rec;
  }
  async function noteFailure(key, max) {
    const rec = await lockState(key);
    const t = now();
    const next = { n: rec.n + 1, first: rec.n ? rec.first : t, until: rec.until };
    if (next.n >= max) next.until = t + LOCK_WINDOW_MS;
    await store.set(`lock/${key}`, next);
  }

  const visibleTo = (user, row, mapping) =>
    user.role === "master" || user.role === "accounts" ? true : row.kind === "debtor" && (mapping[row.id] || []).includes(user.username);

  // ---------------------------------------------------------------- ledger ingest
  function checkMoney(m, label, problems) {
    if (!m || typeof m !== "object" || !Number.isFinite(Number(m.amount)) || Number(m.amount) < 0 || (m.side !== "Dr" && m.side !== "Cr")) {
      problems.push(`${label} must be {amount, side: Dr or Cr}`);
      return null;
    }
    return { amount: round2(m.amount), side: m.side };
  }

  function cleanLedger(raw, index) {
    const problems = [];
    const tag = `Ledger ${index + 1}`;
    if (!raw || typeof raw !== "object" || typeof raw.name !== "string" || !raw.name.trim() || raw.name.length > 160) {
      return { problems: [`${tag}: name is missing or too long`] };
    }
    const name = raw.name.trim();
    const kind = KINDS.includes(raw.kind) ? raw.kind : "other";
    const opening = checkMoney(raw.opening ?? { amount: 0, side: "Dr" }, `${tag} opening`, problems);
    const closing = checkMoney(raw.closing, `${tag} closing`, problems);
    const vouchers = [];
    if (!Array.isArray(raw.vouchers ?? [])) problems.push(`${tag}: vouchers must be a list`);
    for (const [i, v] of (Array.isArray(raw.vouchers) ? raw.vouchers : []).entries()) {
      if (i >= 20000) { problems.push(`${tag}: more than 20000 vouchers`); break; }
      if (!v || !isIsoDate(v.date) || !(Number(v.debit) >= 0) || !(Number(v.credit) >= 0)) { problems.push(`${tag}: voucher ${i + 1} is not valid`); break; }
      vouchers.push({ date: v.date, type: clip(v.type, 40), number: clip(v.number, 60), particulars: clip(v.particulars, 200), debit: round2(v.debit), credit: round2(v.credit) });
    }
    const bills = [];
    for (const [i, b] of (Array.isArray(raw.bills) ? raw.bills : []).entries()) {
      if (i >= 5000) { problems.push(`${tag}: more than 5000 bills`); break; }
      if (!b || !isIsoDate(b.date) || !(Number(b.pending) > 0)) { problems.push(`${tag}: bill ${i + 1} is not valid`); break; }
      bills.push({ ref: clip(b.ref, 60), date: b.date, original: round2(b.original ?? b.pending), pending: round2(b.pending) });
    }
    if (problems.length || !closing) return { problems };
    const doc = {
      name, id: ledgerId(name), group: clip(raw.group, 100), kind,
      phone: clip(raw.phone, 40), gstin: clip(raw.gstin, 20), city: clip(raw.city, 60), state: clip(raw.state, 40), address: clip(raw.address, 240), ...(raw.warning ? { warning: clip(raw.warning, 240) } : {}),
      opening, closing, vouchers, periodFrom: isIsoDate(raw.periodFrom) ? raw.periodFrom : null, periodTo: isIsoDate(raw.periodTo) ? raw.periodTo : null,
    };
    // outstanding is the amount owed on the side that matters for this kind of ledger
    const owedSide = kind === "creditor" ? "Cr" : "Dr";
    const outstanding = kind !== "other" && closing.side === owedSide ? closing.amount : 0;
    let billList = bills;
    let billwise = bills.length > 0;
    if (kind !== "other" && outstanding > 0 && !billwise) {
      billList = deriveBillsFIFO(vouchers, kind, outstanding).bills;
    }
    const billsTotal = round2(billList.reduce((a, b) => a + b.pending, 0));
    doc.bills = billList;
    doc.billwise = billwise;
    doc.outstanding = outstanding;
    doc.older = outstanding > billsTotal ? round2(outstanding - billsTotal) : 0;
    doc.check = { billsTotal, outstanding, diff: round2(outstanding - billsTotal) };
    return { doc };
  }

  const summarize = (doc, syncedAt) => ({
    id: doc.id, name: doc.name, group: doc.group, kind: doc.kind, city: doc.city, state: doc.state, phone: doc.phone, gstin: doc.gstin,
    closing: doc.closing, outstanding: doc.outstanding, older: doc.older, bills: doc.bills.map((b) => [b.date, b.pending]),
    lastVoucher: doc.vouchers.length ? doc.vouchers.reduce((m, v) => (v.date > m ? v.date : m), "") : null,
    voucherCount: doc.vouchers.length, syncedAt,
  });

  // ---------------------------------------------------------------- routes
  async function route(req, url) {
    const method = req.method;
    const path = url.pathname.replace(/\/+$/, "");

    if (path === "/api/health") return json(200, { ok: true, configured });
    if (!configured) return fail(503, "The portal is not configured yet.");

    // ---- sync agent and bootstrap: bearer key, no cookies, so no CSRF concern
    if (path.startsWith("/api/sync/") && path !== "/api/sync/status") return syncRoute(req, method, path);
    if (path === "/api/admin/bootstrap") return bootstrap(req, method);

    // ---- login does not need a session
    if (path === "/api/login" && method === "POST") return login(req);

    const user = await currentUser(req);
    if (path === "/api/logout" && method === "POST") return json(200, { ok: true }, { "set-cookie": cookieHeader("", 0) });
    if (!user) return fail(401, "Please sign in.");
    if (method !== "GET" && req.headers.get("x-requested-with") !== "nalanda") return fail(403, "Request not allowed.");

    if (path === "/api/me" && method === "GET") {
      const meta = (await store.get("meta")) || null;
      return json(200, { ok: true, user: publicUser(user), syncedAt: meta?.lastSyncAt || null, company: meta?.company || null });
    }
    if (path === "/api/change-password" && method === "POST") return changePassword(req, user);
    if (user.mustChange) return fail(403, "Please choose a new password first.", { mustChange: true });

    if (path === "/api/dealers" && method === "GET") return dealers(user);
    if (path.startsWith("/api/ledger/") && method === "GET") return ledgerView(user, path.slice("/api/ledger/".length), url);
    if (path === "/api/sync/status" && method === "GET") return syncStatus(user);

    if (path.startsWith("/api/users") || path === "/api/mapping") {
      if (user.role !== "master") return fail(403, "Only the master user can do this.");
      if (path === "/api/users" && method === "GET") return json(200, { ok: true, users: (await listUsers()).map(publicUser) });
      if (path === "/api/users" && method === "POST") return createUser(req);
      if (path.startsWith("/api/users/") && method === "PATCH") return patchUser(req, path.slice("/api/users/".length), user);
      if (path === "/api/mapping" && method === "GET") return json(200, { ok: true, mapping: (await store.get("mapping")) || {} });
      if (path === "/api/mapping" && method === "PUT") return putMapping(req);
    }
    return fail(404, "Not found.");
  }

  async function listUsers() {
    const keys = await store.list("user/");
    const out = [];
    for (const k of keys) { const u = await store.get(k); if (u) out.push(u); }
    return out.sort((a, b) => a.username.localeCompare(b.username));
  }

  // ---------------------------------------------------------------- auth routes
  async function login(req) {
    const body = await readJson(req, MAX_JSON);
    const username = typeof body.username === "string" ? body.username.trim().toLowerCase() : "";
    const password = typeof body.password === "string" ? body.password.slice(0, 200) : "";
    const generic = () => fail(401, "That user name or password is not right.");
    if (!USERNAME.test(username) || !password) return generic();
    const ip = clientIp(req);
    const [uLock, iLock] = await Promise.all([lockState(`user:${username}`), lockState(`ip:${ip}`)]);
    const t = now();
    if (uLock.until > t || iLock.until > t) {
      const wait = Math.ceil((Math.max(uLock.until, iLock.until) - t) / 1000);
      return fail(429, "Too many tries. Please wait a few minutes and try again.", { retryAfter: wait });
    }
    const user = await getUser(username);
    const ok = await verifyPassword(password, user?.password || null); // same work for unknown users
    if (!ok || !user.active) {
      await Promise.all([noteFailure(`user:${username}`, MAX_USER_FAILS), noteFailure(`ip:${ip}`, MAX_IP_FAILS)]);
      return generic();
    }
    await Promise.all([store.delete(`lock/user:${username}`)]);
    user.lastLoginAt = new Date(t).toISOString();
    await store.set(`user/${username}`, user);
    const token = signSession(SESSION_SECRET, { u: username, v: user.tokenVersion }, t);
    return json(200, { ok: true, user: publicUser(user) }, { "set-cookie": cookieHeader(token, SESSION_DAYS * 86400) });
  }

  async function changePassword(req, user) {
    const body = await readJson(req, MAX_JSON);
    if (!(await verifyPassword(String(body.current || ""), user.password))) return fail(400, "Your current password is not right.");
    const problem = passwordProblem(body.next, user.username);
    if (problem) return fail(400, problem);
    if (body.next === body.current) return fail(400, "Please choose a different password.");
    user.password = await hashPassword(body.next);
    user.mustChange = false;
    user.tokenVersion += 1; // signs out every other device
    await store.set(`user/${user.username}`, user);
    const token = signSession(SESSION_SECRET, { u: user.username, v: user.tokenVersion }, now());
    return json(200, { ok: true }, { "set-cookie": cookieHeader(token, SESSION_DAYS * 86400) });
  }

  async function bootstrap(req, method) {
    if (method !== "POST") return fail(405, "Use POST.");
    if (!safeEqual((req.headers.get("authorization") || "").replace(/^Bearer /, ""), SYNC_KEY)) return fail(401, "Not allowed.");
    if ((await store.list("user/")).length) return fail(409, "The portal already has users.");
    const body = await readJson(req, MAX_JSON);
    const username = String(body.username || "").trim().toLowerCase();
    if (!USERNAME.test(username)) return fail(400, "User name: 3 to 32 letters, numbers, dots, dashes.");
    const problem = passwordProblem(body.password, username);
    if (problem) return fail(400, problem);
    const u = { username, name: clip(body.name || username, 60), role: "master", active: true, mustChange: true, tokenVersion: 1, password: await hashPassword(body.password), createdAt: new Date(now()).toISOString() };
    await store.set(`user/${username}`, u);
    return json(201, { ok: true, user: publicUser(u) });
  }

  // ---------------------------------------------------------------- users (master only)
  async function createUser(req) {
    const b = await readJson(req, MAX_JSON);
    const username = String(b.username || "").trim().toLowerCase();
    if (!USERNAME.test(username)) return fail(400, "User name: 3 to 32 letters, numbers, dots, dashes.");
    if (!ROLES.includes(b.role)) return fail(400, "Role must be master, accounts or sales.");
    if (await getUser(username)) return fail(409, "That user name is taken.");
    let pw = b.password;
    let generated = false;
    if (!pw) { pw = tempPassword(12); generated = true; }
    const problem = passwordProblem(pw, username);
    if (problem) return fail(400, problem);
    const u = { username, name: clip(b.name || username, 60), role: b.role, active: true, mustChange: true, tokenVersion: 1, password: await hashPassword(pw), createdAt: new Date(now()).toISOString() };
    await store.set(`user/${username}`, u);
    return json(201, { ok: true, user: publicUser(u), ...(generated ? { tempPassword: pw } : {}) });
  }

  async function patchUser(req, username, me) {
    const target = await getUser(String(username).toLowerCase());
    if (!target) return fail(404, "No such user.");
    const b = await readJson(req, MAX_JSON);
    const all = await listUsers();
    const activeMasters = all.filter((u) => u.role === "master" && u.active);
    const wouldLoseMaster = (target.role === "master" && target.active) && activeMasters.length === 1 &&
      ((b.active === false) || (b.role && b.role !== "master"));
    if (wouldLoseMaster) return fail(400, "There must always be one active master user.");
    let revoke = false;
    if (typeof b.name === "string") target.name = clip(b.name, 60);
    if (b.role !== undefined) { if (!ROLES.includes(b.role)) return fail(400, "Role must be master, accounts or sales."); if (b.role !== target.role) { target.role = b.role; revoke = true; } }
    if (typeof b.active === "boolean" && b.active !== target.active) { target.active = b.active; revoke = true; }
    let temp;
    if (b.resetPassword === true) { temp = tempPassword(12); target.password = await hashPassword(temp); target.mustChange = true; revoke = true; }
    if (revoke) target.tokenVersion += 1;
    await store.set(`user/${target.username}`, target);
    return json(200, { ok: true, user: publicUser(target), ...(temp ? { tempPassword: temp } : {}) });
  }

  async function putMapping(req) {
    const b = await readJson(req, MAX_SYNC);
    const index = (await store.get("index")) || [];
    const known = new Set(index.filter((r) => r.kind === "debtor").map((r) => r.id));
    const users = new Set((await listUsers()).filter((u) => u.active).map((u) => u.username));
    const mode = b.mode === "replace" ? "replace" : "merge";
    const next = mode === "replace" ? {} : { ...((await store.get("mapping")) || {}) };
    let applied = 0;
    const skipped = [];
    for (const [id, list] of Object.entries(b.assignments || {})) {
      if (!known.has(id) || !Array.isArray(list)) { skipped.push(id); continue; }
      const names = [...new Set(list.map((x) => String(x).toLowerCase()).filter((x) => users.has(x)))];
      if (names.length) next[id] = names; else delete next[id];
      applied++;
    }
    await store.set("mapping", next);
    return json(200, { ok: true, applied, skipped: skipped.slice(0, 20), skippedCount: skipped.length });
  }

  // ---------------------------------------------------------------- reading data
  async function dealers(user) {
    const [index, mapping, meta] = await Promise.all([store.get("index"), store.get("mapping"), store.get("meta")]);
    const today = istDate(now());
    const rows = [];
    const totals = { receivable: 0, payable: 0, b0: 0, b1: 0, b2: 0, b3: 0, older: 0, dealers: 0 };
    for (const r of index || []) {
      if (!visibleTo(user, r, mapping || {})) continue;
      const aged = ageBills(r.bills.map(([date, pending]) => ({ date, pending })), r.older, today);
      rows.push({
        id: r.id, name: r.name, group: r.group, kind: r.kind, city: r.city, phone: r.phone, closing: r.closing, outstanding: r.outstanding,
        buckets: { b0: aged.totals.b0, b1: aged.totals.b1, b2: aged.totals.b2, b3: aged.totals.b3, older: aged.totals.older },
        oldestDays: aged.totals.oldestDays, billCount: r.bills.length, lastVoucher: r.lastVoucher,
        assigned: user.role === "master" ? (mapping || {})[r.id] || [] : undefined,
      });
      if (r.kind === "debtor") { totals.receivable = round2(totals.receivable + r.outstanding); totals.dealers++; }
      if (r.kind === "creditor") totals.payable = round2(totals.payable + r.outstanding);
      if (r.kind === "debtor") for (const k of ["b0", "b1", "b2", "b3", "older"]) totals[k] = round2(totals[k] + aged.totals[k]);
    }
    return json(200, { ok: true, today, syncedAt: meta?.lastSyncAt || null, company: meta?.company || null, totals, rows });
  }

  async function ledgerView(user, id, url) {
    if (!validId(id)) return fail(404, "Not found.");
    const [doc, mapping, meta] = await Promise.all([store.get(`ledger/${id}`), store.get("mapping"), store.get("meta")]);
    // the same answer for "does not exist" and "not yours", so ids cannot be probed
    if (!doc || !visibleTo(user, { id: doc.id, kind: doc.kind }, mapping || {})) return fail(404, "Not found.");
    const today = istDate(now());
    const aged = ageBills(doc.bills, doc.older, today);
    const from = isIsoDate(url.searchParams.get("from")) ? url.searchParams.get("from") : null;
    const to = isIsoDate(url.searchParams.get("to")) ? url.searchParams.get("to") : null;
    const rows = withRunning(doc.opening, doc.vouchers);
    return json(200, { ok: true, today, syncedAt: meta?.lastSyncAt || null, company: meta?.company || null, ledger: { ...doc, vouchers: undefined, bills: aged.bills, totals: aged.totals }, statement: { opening: doc.opening, closing: doc.closing, rows, from, to } });
  }

  async function syncStatus() {
    const meta = (await store.get("meta")) || null;
    return json(200, { ok: true, meta });
  }

  // ---------------------------------------------------------------- sync agent
  async function syncRoute(req, method, path) {
    if (method !== "POST") return fail(405, "Use POST.");
    if (!safeEqual((req.headers.get("authorization") || "").replace(/^Bearer /, ""), SYNC_KEY)) return fail(401, "Not allowed.");
    const b = await readJson(req, MAX_SYNC);
    const runId = String(b.runId || "");
    if (!/^[A-Za-z0-9_-]{6,64}$/.test(runId)) return fail(400, "runId is missing or not valid.");
    const key = `run/${runId}`;
    if (path === "/api/sync/start") {
      await store.set(key, { startedAt: new Date(now()).toISOString(), company: clip(b.company, 120), full: b.full !== false, summaries: [], ids: [] });
      return json(200, { ok: true });
    }
    const run = await store.get(key);
    if (!run) return fail(404, "Unknown sync run. Start a new one.");
    const syncedAt = new Date(now()).toISOString();
    if (path === "/api/sync/ledgers") {
      if (!Array.isArray(b.ledgers) || b.ledgers.length > 500) return fail(400, "Send between 1 and 500 ledgers at a time.");
      const problems = [];
      const docs = [];
      b.ledgers.forEach((raw, i) => { const r = cleanLedger(raw, i); if (r.problems) problems.push(...r.problems); else docs.push(r.doc); });
      if (problems.length) return fail(400, "Some ledgers are not valid.", { problems: problems.slice(0, 20) });
      for (const doc of docs) {
        if (run.ids.includes(doc.id)) continue;
        await store.set(`ledger/${doc.id}`, { ...doc, syncedAt });
        run.summaries.push(summarize(doc, syncedAt));
        run.ids.push(doc.id);
      }
      await store.set(key, run);
      return json(200, { ok: true, received: docs.length, total: run.ids.length });
    }
    if (path === "/api/sync/finish") {
      let index = run.summaries;
      if (!run.full) {
        const old = (await store.get("index")) || [];
        const fresh = new Set(run.ids);
        index = [...old.filter((r) => !fresh.has(r.id)), ...run.summaries];
      }
      index.sort((a, b2) => a.name.localeCompare(b2.name));
      await store.set("index", index);
      let removed = 0;
      if (run.full) {
        const keep = new Set(index.map((r) => r.id));
        for (const k of await store.list("ledger/")) if (!keep.has(k.slice("ledger/".length))) { await store.delete(k); removed++; }
      }
      const prev = (await store.get("meta")) || { history: [] };
      const entry = { at: syncedAt, startedAt: run.startedAt, ledgers: run.ids.length, removed, full: run.full };
      await store.set("meta", { company: run.company || prev.company || "", lastSyncAt: syncedAt, lastRun: entry, history: [entry, ...(prev.history || [])].slice(0, 30) });
      await store.delete(key);
      return json(200, { ok: true, ledgers: run.ids.length, removed });
    }
    return fail(404, "Not found.");
  }

  // ---------------------------------------------------------------- entry
  return async function handler(req) {
    try {
      const url = new URL(req.url);
      return await route(req, url);
    } catch (e) {
      if (e && e.status) return fail(e.status, e.status === 413 ? "That is too large." : "The request could not be read.");
      log("api error", e && e.stack ? e.stack : e);
      return fail(500, "Something went wrong on our side.");
    }
  };
}
