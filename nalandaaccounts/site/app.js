/* Nalanda Accounts portal. No inline scripts (the security policy forbids them). Every piece of data shown goes through esc(). */
(function () {
"use strict";
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (n, d) => Number(n).toLocaleString("en-IN", { minimumFractionDigits: d, maximumFractionDigits: d });
const inr = (n, d = 0) => "₹" + fmt(n, d);
const inr2 = (n) => inr(n, 2);
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const dmy = (iso) => (iso ? `${iso.slice(8, 10)} ${MONTHS[+iso.slice(5, 7) - 1]} ${iso.slice(0, 4)}` : "");
const dayClass = (d) => (d <= 30 ? "d0" : d <= 60 ? "d1" : d <= 90 ? "d2" : "d3");
const signed = (b) => (b.side === "Dr" ? 1 : -1) * Number(b.amount);
const balText = (b, d = 2) => (!b || b.amount === 0 ? "Nil" : `${inr(b.amount, d)} ${b.side}`);
const BUCKETS = [["b0", "0 to 30 days", "s0"], ["b1", "31 to 60 days", "s1"], ["b2", "61 to 90 days", "s2"], ["b3", "Over 90 days", "s3"], ["older", "Older / opening", "s4"]];

function toast(m) { const t = $("#toast"); t.textContent = m; t.classList.add("on"); clearTimeout(toast.t); toast.t = setTimeout(() => t.classList.remove("on"), 3200); }

async function api(path, opts = {}) {
  let r;
  try {
    r = await fetch(path, { method: opts.method || "GET", headers: { "Content-Type": "application/json", "X-Requested-With": "nalanda" }, credentials: "same-origin", body: opts.body ? JSON.stringify(opts.body) : undefined });
  } catch (e) { return { ok: false, status: 0, error: "Could not reach the server. Check your internet and try again." }; }
  let j = {};
  try { j = await r.json(); } catch (e) { /* not json */ }
  if (r.status === 401 && S.user && !opts.quiet) { S.user = null; render(); }
  return { ok: false, ...j, status: r.status };
}

const S = { user: null, company: null, syncedAt: null, dealers: null, filter: "all", sort: "overdue", q: "", group: "", ledger: null, per: "fy", from: "", to: "", users: null, assignUser: "", assignQ: "", pending: {}, onlyUnassigned: false };

function can(role) { return S.user && (S.user.role === "master" || (role === "accounts" && S.user.role === "accounts")); }
const isSales = () => S.user && S.user.role === "sales";

/* ------------------------------------------------------------------ views: sign in */
function viewLogin(msg) {
  $("#root").innerHTML = `<div class="login"><div class="card"><div class="logo">N</div><h1>Nalanda Accounts</h1><p class="muted" style="margin:6px 0 0">Sign in to see your dealers and statements.</p>
  <form id="loginForm" autocomplete="on">${msg ? `<div class="banner bad" style="margin:0">${esc(msg)}</div>` : ""}
  <label class="f">User name<input type="text" id="u" autocomplete="username" autocapitalize="none" spellcheck="false" required></label>
  <label class="f">Password<input type="password" id="p" autocomplete="current-password" required></label>
  <button class="btn primary" type="submit" style="justify-content:center">Sign in</button>
  <p class="muted" style="font-size:13px;margin:0">Forgot your password? Ask the master user to reset it.</p></form></div></div>`;
  $("#loginForm").onsubmit = async (e) => {
    e.preventDefault();
    const btn = $("#loginForm button"); btn.disabled = true;
    const r = await api("/api/login", { method: "POST", body: { username: $("#u").value, password: $("#p").value }, quiet: true });
    btn.disabled = false;
    if (!r.ok) return viewLogin(r.error || "Could not sign in.");
    S.user = r.user; await boot(true);
  };
  $("#u").focus();
}

function viewChangePassword(forced, msg) {
  const body = `<h1 style="font-size:20px">${forced ? "Choose your own password" : "Change password"}</h1>
  <p class="muted" style="margin:6px 0 0">${forced ? "You signed in with a temporary password. Please choose a new one to continue." : "You will stay signed in here and be signed out on other devices."}</p>
  <form id="pwForm" style="display:grid;gap:14px;margin-top:16px">${msg ? `<div class="banner bad" style="margin:0">${esc(msg)}</div>` : ""}
  <label class="f">Current password<input type="password" id="cur" autocomplete="current-password" required></label>
  <label class="f">New password <span class="muted" style="font-weight:400">at least 10 characters</span><input type="password" id="nw" autocomplete="new-password" required></label>
  <label class="f">New password again<input type="password" id="nw2" autocomplete="new-password" required></label>
  <div class="row"><button class="btn primary" type="submit">Save password</button>${forced ? '<button class="btn ghost" type="button" data-act="logout">Sign out</button>' : '<a class="btn ghost" href="#/dealers">Cancel</a>'}</div></form>`;
  $("#root").innerHTML = forced ? `<div class="login"><div class="card">${body}</div></div>` : shell(`<div class="card pad" style="max-width:480px">${body}</div>`);
  $("#pwForm").onsubmit = async (e) => {
    e.preventDefault();
    if ($("#nw").value !== $("#nw2").value) return viewChangePassword(forced, "The two new passwords are different.");
    const r = await api("/api/change-password", { method: "POST", body: { current: $("#cur").value, next: $("#nw").value } });
    if (!r.ok) return viewChangePassword(forced, r.error);
    S.user.mustChange = false; toast("Password changed"); location.hash = "#/dealers"; await boot(true);
  };
}

/* ------------------------------------------------------------------ shell */
function tabs() {
  const t = [["#/dealers", "Dealers"]];
  if (can("accounts")) t.push(["#/payables", "Payables"]);
  if (S.user.role === "master") t.push(["#/assign", "Assign dealers"], ["#/users", "Users"]);
  if (can("accounts")) t.push(["#/sync", "Sync"]);
  return t;
}
function freshness() {
  if (!S.syncedAt) return '<span class="pill bad">No data yet</span>';
  const hrs = (Date.now() - Date.parse(S.syncedAt)) / 3600000;
  const when = new Date(S.syncedAt).toLocaleString("en-IN", { day: "2-digit", month: "short", hour: "numeric", minute: "2-digit", hour12: true, timeZone: "Asia/Kolkata" });
  return hrs > 10 ? `<span class="pill warn" title="Updates run 3 times a day">Data from ${esc(when)}, ${Math.floor(hrs)} hours ago</span>` : `<span class="pill ok">Updated ${esc(when)}</span>`;
}
function shell(inner) {
  const cur = location.hash.split("/")[1] || "dealers";
  const t = tabs();
  return `<header class="top"><div class="brand"><span class="logo">N</span>${esc(S.company || "Nalanda Accounts")}</div>
  <nav class="tabs" aria-label="Sections">${t.length > 1 ? t.map(([h, l]) => `<a href="${h}" class="${h === "#/" + cur || (cur === "dealer" && h === "#/dealers") ? "on" : ""}">${l}</a>`).join("") : ""}</nav>
  <span class="sp"></span>${freshness()}
  <span class="muted" style="font-size:13px">${esc(S.user.name)} <span class="pill dim">${esc(S.user.role)}</span></span>
  <a class="btn sm" href="#/password">Password</a><button class="btn sm ghost" data-act="logout">Sign out</button></header><main>${inner}</main>`;
}

/* ------------------------------------------------------------------ dealers and payables */
async function viewList(kind) {
  if (S.listKind !== kind) { S.listKind = kind; S.q = ""; S.filter = "all"; S.group = ""; } // each list starts fresh
  const r = await api("/api/dealers");
  if (!r.ok && r.status !== 401) { $("#root").innerHTML = shell(`<div class="banner bad">${esc(r.error || "Could not load.")}</div>`); return; }
  if (!r.rows) return;
  S.dealers = r; S.company = r.company || S.company; S.syncedAt = r.syncedAt;
  const rows = r.rows.filter((x) => (kind === "creditor" ? x.kind === "creditor" : x.kind === "debtor"));
  const groups = [...new Set(rows.map((x) => x.group).filter(Boolean))].sort();
  const T = r.totals;
  const kp = kind === "debtor"
    ? `<div class="kpi card"><div class="v">${inr(T.receivable)}</div><div class="l">Total receivable</div></div>
       <div class="kpi card"><div class="v">${inr(T.b0)}</div><div class="l">0 to 30 days</div></div><div class="kpi card"><div class="v">${inr(T.b1)}</div><div class="l">31 to 60 days</div></div>
       <div class="kpi card"><div class="v">${inr(T.b2)}</div><div class="l">61 to 90 days</div></div><div class="kpi card alert"><div class="v">${inr(T.b3)}</div><div class="l">Over 90 days</div></div>`
    : `<div class="kpi card"><div class="v">${inr(T.payable)}</div><div class="l">Total payable</div></div><div class="kpi card"><div class="v">${rows.length}</div><div class="l">Vendors</div></div>`;
  $("#root").innerHTML = shell(`${!S.syncedAt ? '<div class="banner warn">No data has been synced from Tally yet. Once the sync agent runs, your dealers appear here.</div>' : ""}
  ${isSales() && !rows.length && S.syncedAt ? '<div class="banner info">No dealers are assigned to you yet. Ask the master user to assign your dealers.</div>' : ""}
  <div class="kpis">${kp}</div>
  <div class="toolbar"><input type="search" id="q" placeholder="Search by name, city or phone" value="${esc(S.q)}" aria-label="Search">
   <select id="sort" aria-label="Sort"><option value="overdue">Most overdue first</option><option value="outstanding">Highest balance first</option><option value="name">Name A to Z</option><option value="oldest">Oldest bill first</option></select>
   ${groups.length > 1 ? `<select id="grp" aria-label="Group"><option value="">All groups</option>${groups.map((g) => `<option ${S.group === g ? "selected" : ""}>${esc(g)}</option>`).join("")}</select>` : ""}
   <div class="chips" id="chips">${[["all", "All"], ["owing", "With balance"], ["b3", "Over 90 days"], ["b2", "61 to 90 days"]].filter(([k]) => kind === "debtor" || k === "all" || k === "owing").map(([k, l]) => `<button class="chip ${S.filter === k ? "on" : ""}" data-f="${k}">${l}</button>`).join("")}</div></div>
  <div id="listBox"></div>`);
  $("#sort").value = S.sort;
  const paint = () => paintList(rows, kind);
  $("#q").oninput = (e) => { S.q = e.target.value; paint(); };
  $("#sort").onchange = (e) => { S.sort = e.target.value; paint(); };
  if ($("#grp")) $("#grp").onchange = (e) => { S.group = e.target.value; paint(); };
  $("#chips").onclick = (e) => { const b = e.target.closest("[data-f]"); if (!b) return; S.filter = b.dataset.f; $$("#chips .chip").forEach((c) => c.classList.toggle("on", c === b)); paint(); };
  paint();
}

function paintList(all, kind) {
  const q = S.q.trim().toLowerCase();
  let rows = all.filter((x) => (!q || `${x.name} ${x.city} ${x.phone}`.toLowerCase().includes(q)) && (!S.group || x.group === S.group));
  if (S.filter === "owing") rows = rows.filter((x) => x.outstanding > 0);
  if (S.filter === "b3") rows = rows.filter((x) => x.buckets.b3 > 0);
  if (S.filter === "b2") rows = rows.filter((x) => x.buckets.b2 > 0);
  const by = { overdue: (a, b) => b.buckets.b3 - a.buckets.b3 || b.buckets.b2 - a.buckets.b2 || b.buckets.b1 - a.buckets.b1 || b.outstanding - a.outstanding, outstanding: (a, b) => b.outstanding - a.outstanding, name: (a, b) => a.name.localeCompare(b.name), oldest: (a, b) => b.oldestDays - a.oldestDays };
  rows.sort(by[S.sort] || by.overdue);
  const shown = rows.slice(0, 400);
  const sum = shown.reduce((a, x) => a + x.outstanding, 0);
  const deb = kind === "debtor";
  $("#listBox").innerHTML = rows.length ? `
  <p class="muted" style="margin:0 0 8px;font-size:13px">${rows.length} ${deb ? "dealers" : "vendors"}${rows.length > 400 ? " (showing the first 400, narrow the search)" : ""} · ${inr(sum)}</p>
  <div class="tblwrap listy"><table><thead><tr><th>${deb ? "Dealer" : "Vendor"}</th><th>City</th><th class="r">Outstanding</th>${deb ? '<th class="r">0 to 30</th><th class="r">31 to 60</th><th class="r">61 to 90</th><th class="r">Over 90</th><th class="r">Oldest</th>' : ""}</tr></thead><tbody>
  ${shown.map((x) => `<tr class="link" data-id="${esc(x.id)}"><td><b>${esc(x.name)}</b>${x.group ? `<div class="muted" style="font-size:12px">${esc(x.group)}</div>` : ""}${S.user.role === "master" && deb && !(x.assigned || []).length ? ' <span class="pill warn">not assigned</span>' : ""}</td><td>${esc(x.city)}</td>
  <td class="r num"><b>${x.outstanding > 0 ? inr(x.outstanding) : x.closing.amount ? balText(x.closing, 0) : "Nil"}</b></td>
  ${deb ? `<td class="r num">${x.buckets.b0 ? inr(x.buckets.b0) : "-"}</td><td class="r num">${x.buckets.b1 ? inr(x.buckets.b1) : "-"}</td><td class="r num">${x.buckets.b2 ? inr(x.buckets.b2) : "-"}</td><td class="r num ${x.buckets.b3 ? "d3" : ""}">${x.buckets.b3 ? inr(x.buckets.b3) : "-"}</td><td class="r num ${x.billCount ? dayClass(x.oldestDays) : ""}">${x.billCount ? x.oldestDays + " days" : "-"}</td>` : ""}</tr>`).join("")}</tbody></table></div>
  <div class="cards">${shown.map((x) => `<div class="dcard" data-id="${esc(x.id)}" role="link" tabindex="0"><div class="t"><span>${esc(x.name)}</span><span class="num">${x.outstanding > 0 ? inr(x.outstanding) : "Nil"}</span></div>
   <div class="muted" style="font-size:13px">${esc(x.city)}${deb && x.billCount ? ` · oldest bill <span class="${dayClass(x.oldestDays)}">${x.oldestDays} days</span>` : ""}</div>${deb && x.outstanding > 0 ? agebar(x.buckets) : ""}</div>`).join("")}</div>`
    : `<div class="card pad muted">${all.length ? "Nobody matches this search." : "Nothing to show yet."}</div>`;
}

function agebar(b) {
  const tot = BUCKETS.reduce((a, [k]) => a + (b[k] || 0), 0) || 1;
  return `<div class="bar" aria-hidden="true">${BUCKETS.map(([k, , c]) => (b[k] ? `<i class="${c}" style="width:${(b[k] / tot) * 100}%"></i>` : "")).join("")}</div>`;
}

/* ------------------------------------------------------------------ one dealer */
function fyStart(today) { const y = +today.slice(0, 4); return (+today.slice(5, 7) >= 4 ? y : y - 1) + "-04-01"; }
function period(today) {
  if (S.per === "fy") return { from: fyStart(today), to: today, label: "This financial year" };
  if (S.per === "90") { const d = new Date(Date.parse(today + "T00:00:00Z") - 90 * 86400000); return { from: d.toISOString().slice(0, 10), to: today, label: "Last 90 days" }; }
  if (S.per === "custom" && S.from && S.to) return { from: S.from, to: S.to, label: "Custom period" };
  return { from: null, to: null, label: "All synced entries" };
}
function slice(st, p) {
  const rows = st.rows.filter((r) => (!p.from || r.date >= p.from) && (!p.to || r.date <= p.to));
  const before = p.from ? st.rows.filter((r) => r.date < p.from).at(-1) : null;
  const opening = p.from ? (before ? before.balance : st.opening) : st.opening;
  const sums = rows.reduce((a, r) => ({ dr: a.dr + r.debit, cr: a.cr + r.credit }), { dr: 0, cr: 0 });
  return { rows, opening, dr: sums.dr, cr: sums.cr, closing: rows.length ? rows.at(-1).balance : opening };
}

async function viewDealer(id) {
  const r = await api("/api/ledger/" + encodeURIComponent(id));
  if (!r.ledger) { if (r.status === 401) return; $("#root").innerHTML = shell(`<div class="banner bad">${esc(r.status === 404 ? "This dealer was not found, or is not assigned to you." : r.error || "Could not load.")}</div><a class="btn" href="#/dealers">Back to dealers</a>`); return; }
  S.ledger = r; S.company = r.company || S.company; S.syncedAt = r.syncedAt;
  paintDealer();
}
function paintDealer() {
  const r = S.ledger, L = r.ledger, T = L.totals, p = period(r.today), sl = slice(r.statement, p);
  const back = L.kind === "creditor" ? "#/payables" : "#/dealers";
  const phone = String(L.phone || "").replace(/[^0-9+]/g, "");
  const tie = L.check.diff === 0 ? '<span class="pill ok">Bills add up to the ledger balance</span>' : L.billwise ? `<span class="pill warn">${inr2(Math.abs(L.check.diff))} ${L.check.diff > 0 ? "of the balance is older than the bills Tally listed" : "more in bills than the balance"}</span>` : '<span class="pill info">Bills were rebuilt from the vouchers, newest first</span>';
  $("#root").innerHTML = shell(`<p class="noprint" style="margin:0 0 10px"><a href="${back}">&larr; Back</a></p>
  <div class="head"><div><h1>${esc(L.name)}</h1><div class="muted">${esc([L.group, L.city, L.state].filter(Boolean).join(" · "))}${phone ? ` · <a href="tel:${esc(phone)}">${esc(L.phone)}</a>` : ""}${L.gstin ? ` · GSTIN ${esc(L.gstin)}` : ""}</div></div>
   <span class="sp"></span><div class="row noprint"><button class="btn primary" data-act="pdf">Download PDF statement</button><button class="btn" data-act="print">Print</button></div></div>
  ${L.warning ? `<div class="banner warn">${esc(L.warning)}</div>` : ""}
  <div class="grid2"><div class="card pad"><h2>${L.kind === "creditor" ? "Payable" : "Outstanding"}</h2><div style="font-size:28px;font-weight:800">${L.outstanding > 0 ? inr2(L.outstanding) : balText(L.closing)}</div><div class="muted">${L.outstanding > 0 ? "as per Tally ledger" : L.closing.amount ? "Ledger balance (they have paid in advance)" : "Nothing outstanding"}</div>
   ${L.outstanding > 0 ? agebar(T) + `<div class="legend">${BUCKETS.filter(([k]) => T[k]).map(([k, l, c]) => `<span><i class="${c}"></i>${l} <b>${inr(T[k])}</b></span>`).join("")}</div>` : ""}<div style="margin-top:10px">${tie}</div></div>
   <div class="card pad"><h2>Unpaid bills</h2>${L.bills.length || L.older ? `<div class="tblwrap" style="border:0"><table><thead><tr><th>Bill</th><th>Date</th><th class="r">Pending</th><th class="r">Days</th></tr></thead><tbody>
   ${[...L.bills].reverse().map((b) => `<tr><td>${esc(b.ref || "-")}</td><td class="nw">${dmy(b.date)}</td><td class="r num">${inr2(b.pending)}</td><td class="r nw ${dayClass(b.days)}">${b.days} days</td></tr>`).join("")}
   ${L.older ? `<tr><td colspan="2" class="muted">Older balance, no bill date</td><td class="r num">${inr2(L.older)}</td><td></td></tr>` : ""}</tbody></table></div>` : '<p class="muted" style="margin:0">No unpaid bills.</p>'}</div></div>
  <div class="card pad" style="margin-top:14px"><div class="row noprint" style="margin-bottom:10px"><h2 style="margin:0">Statement</h2><span class="sp"></span>
   <select id="per" style="width:auto" aria-label="Period"><option value="fy">This financial year</option><option value="90">Last 90 days</option><option value="all">All synced entries</option><option value="custom">Choose dates</option></select>
   ${S.per === "custom" ? `<input type="date" id="pf" value="${esc(S.from)}" style="width:auto"><input type="date" id="pt" value="${esc(S.to)}" style="width:auto">` : ""}</div>
   <p class="muted" style="margin:0 0 8px;font-size:13px">${esc(p.label)}${p.from ? `: ${dmy(p.from)} to ${dmy(p.to)}` : ""} · Opening ${balText(sl.opening)} · Debit ${inr2(sl.dr)} · Credit ${inr2(sl.cr)} · Closing ${balText(sl.closing)}</p>
   <div class="tblwrap"><table><thead><tr><th>Date</th><th>Voucher</th><th>Particulars</th><th class="r">Debit</th><th class="r">Credit</th><th class="r">Balance</th></tr></thead><tbody>
   <tr><td colspan="5" class="muted">Opening balance</td><td class="r num">${balText(sl.opening)}</td></tr>
   ${sl.rows.map((x) => `<tr><td class="nw">${dmy(x.date)}</td><td>${esc(x.type)} ${esc(x.number)}</td><td>${esc(x.particulars)}</td><td class="r num">${x.debit ? fmt(x.debit, 2) : ""}</td><td class="r num">${x.credit ? fmt(x.credit, 2) : ""}</td><td class="r num nw">${balText(x.balance)}</td></tr>`).join("")}
   ${sl.rows.length ? "" : '<tr><td colspan="6" class="muted">No entries in this period.</td></tr>'}</tbody></table></div></div>`);
  $("#per").value = S.per;
  $("#per").onchange = (e) => { S.per = e.target.value; if (S.per === "custom" && !S.from) { S.from = fyStart(r.today); S.to = r.today; } paintDealer(); };
  if ($("#pf")) { $("#pf").onchange = (e) => { S.from = e.target.value; paintDealer(); }; $("#pt").onchange = (e) => { S.to = e.target.value; paintDealer(); }; }
}

/* ------------------------------------------------------------------ PDF statement */
function pdfNum(n) { return fmt(n, 2); }
function pdfBal(b) { return b.amount === 0 ? "Nil" : `${fmt(b.amount, 2)} ${b.side}`; }
function makePdf() {
  const r = S.ledger, L = r.ledger, p = period(r.today), sl = slice(r.statement, p), T = L.totals;
  if (!window.jspdf || !window.jspdf.jsPDF) { toast("The PDF tool did not load. Please refresh the page."); return; }
  const doc = new window.jspdf.jsPDF({ unit: "pt", format: "a4" });
  const W = doc.internal.pageSize.getWidth(), M = 40;
  let y = 46;
  doc.setFont("helvetica", "bold"); doc.setFontSize(15); doc.text(String(r.company || "Statement"), M, y);
  doc.setFontSize(10.5); doc.setFont("helvetica", "normal"); doc.text("Statement of Account", W - M, y, { align: "right" });
  y += 22; doc.setFont("helvetica", "bold"); doc.setFontSize(12); doc.text(L.name, M, y);
  doc.setFont("helvetica", "normal"); doc.setFontSize(9.5);
  const lines = [[L.address, [L.city, L.state].filter(Boolean).join(", ")].filter(Boolean).join(", "), L.gstin ? "GSTIN: " + L.gstin : "", L.phone ? "Phone: " + L.phone : ""].filter(Boolean);
  for (const t of lines) { y += 13; doc.text(doc.splitTextToSize(t, W - 2 * M), M, y); }
  y += 15; doc.text(`Period: ${p.from ? dmy(p.from) + " to " + dmy(p.to) : "all synced entries, up to " + dmy(r.today)}`, M, y);
  y += 8;
  doc.autoTable({ startY: y + 4, theme: "grid", styles: { fontSize: 9, cellPadding: 4 }, headStyles: { fillColor: [47, 69, 200] },
    head: [["Opening balance", "Total debit", "Total credit", "Closing balance"]], body: [[pdfBal(sl.opening), "Rs. " + pdfNum(sl.dr), "Rs. " + pdfNum(sl.cr), pdfBal(sl.closing)]], margin: { left: M, right: M } });
  const body = [["", "", "Opening balance", "", "", pdfBal(sl.opening)], ...sl.rows.map((x) => [dmy(x.date), `${x.type} ${x.number}`.trim(), x.particulars, x.debit ? pdfNum(x.debit) : "", x.credit ? pdfNum(x.credit) : "", pdfBal(x.balance)]), ["", "", "Closing balance", pdfNum(sl.dr), pdfNum(sl.cr), pdfBal(sl.closing)]];
  doc.autoTable({ startY: doc.lastAutoTable.finalY + 14, theme: "striped", margin: { left: M, right: M }, styles: { fontSize: 8.5, cellPadding: 3.5, overflow: "linebreak" },
    headStyles: { fillColor: [47, 69, 200] }, head: [["Date", "Voucher", "Particulars", "Debit", "Credit", "Balance"]], body,
    columnStyles: { 0: { cellWidth: 62 }, 1: { cellWidth: 88 }, 3: { halign: "right", cellWidth: 62 }, 4: { halign: "right", cellWidth: 62 }, 5: { halign: "right", cellWidth: 72 } },
    didParseCell: (d) => { if (d.section === "head" && d.column.index >= 3) d.cell.styles.halign = "right"; if (d.section === "body" && (d.row.index === 0 || d.row.index === body.length - 1)) d.cell.styles.fontStyle = "bold"; } });
  if (L.bills.length || L.older) {
    const need = 120; if (doc.lastAutoTable.finalY + need > doc.internal.pageSize.getHeight() - 60) doc.addPage();
    const sy = doc.lastAutoTable.finalY + 22 > doc.internal.pageSize.getHeight() - 90 ? 50 : doc.lastAutoTable.finalY + 22;
    doc.setFont("helvetica", "bold"); doc.setFontSize(10.5); doc.text("Unpaid bills as on " + dmy(r.today), M, sy);
    doc.autoTable({ startY: sy + 6, theme: "grid", margin: { left: M, right: M }, styles: { fontSize: 8.5, cellPadding: 3.5 }, headStyles: { fillColor: [90, 100, 120] },
      head: [["Bill", "Date", "Days", "Pending (Rs.)"]], body: [...L.bills].reverse().map((b) => [b.ref || "-", dmy(b.date), String(b.days), pdfNum(b.pending)]).concat(L.older ? [["Older balance, no bill date", "", "", pdfNum(L.older)]] : []).concat([["Total", "", "", pdfNum(T.total)]]),
      columnStyles: { 2: { halign: "right" }, 3: { halign: "right" } }, didParseCell: (d) => { if (d.section === "head" && d.column.index >= 2) d.cell.styles.halign = "right"; } });
    doc.setFont("helvetica", "normal"); doc.setFontSize(8.5);
    doc.text("Ageing: " + BUCKETS.filter(([k]) => T[k]).map(([k, l]) => `${l.replace(" days", "d")} Rs. ${pdfNum(T[k])}`).join("   "), M, doc.lastAutoTable.finalY + 14, { maxWidth: W - 2 * M });
  }
  const pages = doc.getNumberOfPages(), H = doc.internal.pageSize.getHeight();
  const stamp = r.syncedAt ? new Date(r.syncedAt).toLocaleString("en-IN", { day: "2-digit", month: "short", year: "numeric", hour: "numeric", minute: "2-digit", hour12: true, timeZone: "Asia/Kolkata" }) : "";
  for (let i = 1; i <= pages; i++) {
    doc.setPage(i); doc.setFontSize(7.5); doc.setTextColor(110);
    doc.text(`Computer generated statement from Tally data last updated ${stamp}. Please report differences within 7 days.`, M, H - 24);
    doc.text(`Page ${i} of ${pages}`, W - M, H - 24, { align: "right" });
  }
  const name = `Statement ${L.name} ${r.today}`.replace(/[^\w .-]+/g, "").replace(/\s+/g, " ").trim() + ".pdf";
  doc.save(name);
}

/* ------------------------------------------------------------------ users (master) */
async function viewUsers() {
  const r = await api("/api/users");
  if (!r.users) { if (r.status !== 401) $("#root").innerHTML = shell(`<div class="banner bad">${esc(r.error || "Not allowed.")}</div>`); return; }
  S.users = r.users;
  $("#root").innerHTML = shell(`<div class="head"><h1>Users</h1><span class="sp"></span><button class="btn primary" data-act="adduser">Add user</button></div>
  <p class="muted" style="margin:0 0 12px">Salespeople see only the dealers you assign to them, and never payables. "Accounts" users see every ledger but cannot change users. A new user gets a temporary password and must choose their own at first sign in.</p>
  <div class="tblwrap"><table><thead><tr><th>User name</th><th>Name</th><th>Role</th><th>Status</th><th>Last sign in</th><th></th></tr></thead><tbody>
  ${r.users.map((u) => `<tr><td><b>${esc(u.username)}</b></td><td>${esc(u.name)}</td><td>${esc(u.role)}</td><td>${u.active ? '<span class="pill ok">Active</span>' : '<span class="pill dim">Disabled</span>'}${u.mustChange ? ' <span class="pill warn">temporary password</span>' : ""}</td><td class="nw muted">${u.lastLoginAt ? esc(new Date(u.lastLoginAt).toLocaleString("en-IN", { day: "2-digit", month: "short", hour: "numeric", minute: "2-digit", timeZone: "Asia/Kolkata" })) : "never"}</td>
  <td class="r nw"><button class="btn sm" data-act="reset" data-u="${esc(u.username)}">Reset password</button> <button class="btn sm ${u.active ? "" : "primary"}" data-act="toggle" data-u="${esc(u.username)}" data-active="${u.active ? "1" : ""}">${u.active ? "Disable" : "Enable"}</button></td></tr>`).join("")}</tbody></table></div>`);
}
function dlg(html, mount) { $("#dlgBody").innerHTML = html; const d = $("#dlg"); if (!d.open) d.showModal(); if (mount) mount(d); }
function showSecret(title, user, pw) {
  dlg(`<h2 style="font-size:19px;margin:0">${esc(title)}</h2><p class="muted" style="margin:0">Give this temporary password to <b>${esc(user)}</b>. It is shown only now. They will choose their own when they sign in.</p><div class="secret" id="sec">${esc(pw)}</div>
  <div class="row" style="justify-content:flex-end"><button class="btn" data-act="copy" data-t="${esc(pw)}">Copy</button><button class="btn primary" data-act="closedlg">Done</button></div>`);
}
function addUserDialog(msg) {
  dlg(`<h2 style="font-size:19px;margin:0">Add a user</h2>${msg ? `<div class="banner bad" style="margin:0">${esc(msg)}</div>` : ""}
  <label class="f">User name <span class="muted" style="font-weight:400">letters, numbers, dot or dash, no spaces</span><input type="text" id="nu" autocapitalize="none" spellcheck="false"></label>
  <label class="f">Full name<input type="text" id="nn"></label>
  <label class="f">Role<select id="nr"><option value="sales">Salesperson (own dealers only)</option><option value="accounts">Accounts (all ledgers, read only)</option><option value="master">Master (everything)</option></select></label>
  <div class="row" style="justify-content:flex-end"><button class="btn" data-act="closedlg">Cancel</button><button class="btn primary" data-act="saveuser">Create user</button></div>`);
}

/* ------------------------------------------------------------------ assign dealers (master) */
async function viewAssign() {
  const [d, u] = await Promise.all([api("/api/dealers"), api("/api/users")]);
  if (!d.rows || !u.users) { if (d.status !== 401) $("#root").innerHTML = shell(`<div class="banner bad">${esc(d.error || u.error || "Not allowed.")}</div>`); return; }
  S.dealers = d; S.users = u.users; S.pending = {};
  const sales = u.users.filter((x) => x.role === "sales" && x.active);
  if (!S.assignUser || !sales.find((x) => x.username === S.assignUser)) S.assignUser = sales[0]?.username || "";
  paintAssign();
}
function currentAssign(row) { return S.pending[row.id] || row.assigned || []; }
function paintAssign() {
  const deb = S.dealers.rows.filter((x) => x.kind === "debtor");
  const sales = S.users.filter((x) => x.role === "sales" && x.active);
  const q = S.assignQ.trim().toLowerCase();
  const rows = deb.filter((x) => (!q || `${x.name} ${x.city}`.toLowerCase().includes(q)) && (!S.onlyUnassigned || !currentAssign(x).length));
  const mine = deb.filter((x) => currentAssign(x).includes(S.assignUser)).length;
  const pend = Object.keys(S.pending).length;
  $("#root").innerHTML = shell(`<div class="head"><h1>Assign dealers</h1></div>
  ${sales.length ? "" : '<div class="banner warn">Add a salesperson on the Users tab first.</div>'}
  <div class="grid2"><div class="card pad"><h2>One salesperson at a time</h2>
   <div class="toolbar"><select id="asu" aria-label="Salesperson">${sales.map((x) => `<option value="${esc(x.username)}" ${x.username === S.assignUser ? "selected" : ""}>${esc(x.name)} (${esc(x.username)})</option>`).join("")}</select>
   <span class="pill info">${mine} dealers</span></div>
   <div class="toolbar"><input type="search" id="asq" placeholder="Search dealers" value="${esc(S.assignQ)}"><label class="row" style="gap:6px"><input type="checkbox" id="asun" ${S.onlyUnassigned ? "checked" : ""}> only unassigned</label></div>
   <div class="row" style="margin-bottom:8px"><button class="btn sm" data-act="asall">Select all shown</button><button class="btn sm" data-act="asnone">Clear all shown</button><span class="sp"></span><button class="btn primary" data-act="assave" ${pend ? "" : "disabled"}>Save ${pend ? pend + " change" + (pend > 1 ? "s" : "") : ""}</button></div>
   <div class="tblwrap" style="max-height:480px"><table><tbody>${rows.slice(0, 500).map((x) => `<tr><td style="width:34px"><input type="checkbox" data-id="${esc(x.id)}" ${currentAssign(x).includes(S.assignUser) ? "checked" : ""} aria-label="Assign ${esc(x.name)}"></td><td>${esc(x.name)}<div class="muted" style="font-size:12px">${esc(x.city)} · ${inr(x.outstanding)}</div></td><td class="muted" style="font-size:12px">${esc(currentAssign(x).join(", ") || "not assigned")}</td></tr>`).join("") || '<tr><td class="muted">No dealers match.</td></tr>'}</tbody></table></div></div>
  <div class="card pad"><h2>Paste a list</h2><p class="muted" style="margin:0 0 8px;font-size:13px">One line per dealer: the dealer name, a comma, then the user name. For example from your dealer mapping sheet. Names must match Tally exactly.</p>
   <textarea id="csv" rows="9" placeholder="Alpha Traders, rohit&#10;Beta Traders, navneet"></textarea><div class="row" style="margin-top:8px"><button class="btn" data-act="csvcheck">Check the list</button></div><div id="csvOut" style="margin-top:10px"></div></div></div>`);
  $("#asu").onchange = (e) => { S.assignUser = e.target.value; paintAssign(); };
  $("#asq").oninput = (e) => { S.assignQ = e.target.value; const pos = e.target.selectionStart; paintAssign(); const el = $("#asq"); el.focus(); el.setSelectionRange(pos, pos); };
  $("#asun").onchange = (e) => { S.onlyUnassigned = e.target.checked; paintAssign(); };
  $$("[data-id]").forEach((c) => (c.onchange = () => { const row = deb.find((x) => x.id === c.dataset.id); toggleAssign(row, c.checked); paintAssign(); }));
}
function toggleAssign(row, on) {
  const set = new Set(currentAssign(row));
  if (on) set.add(S.assignUser); else set.delete(S.assignUser);
  S.pending[row.id] = [...set];
}
async function saveAssign(body) {
  const r = await api("/api/mapping", { method: "PUT", body });
  if (!r.ok) { toast(r.error || "Could not save."); return false; }
  toast(`Saved ${r.applied} dealer${r.applied === 1 ? "" : "s"}${r.skippedCount ? `, ${r.skippedCount} skipped` : ""}`);
  return true;
}
function csvPlan() {
  const deb = S.dealers.rows.filter((x) => x.kind === "debtor");
  const byName = new Map(); for (const x of deb) { const k = x.name.trim().toLowerCase(); byName.set(k, (byName.get(k) || []).concat(x)); }
  const users = new Set(S.users.filter((x) => x.active).map((x) => x.username));
  const out = { ok: [], missing: [], badUser: [], assignments: {} };
  for (const line of $("#csv").value.split(/\r?\n/)) {
    const t = line.split(/[,\t]/).map((s) => s.trim()); if (t.length < 2 || !t[0]) continue;
    const name = t.slice(0, -1).join(",").trim(), user = t.at(-1).toLowerCase();
    const hit = byName.get(name.toLowerCase());
    if (!users.has(user)) { out.badUser.push(line); continue; }
    if (!hit || hit.length !== 1) { out.missing.push(name); continue; }
    const row = hit[0]; const cur = new Set(out.assignments[row.id] || row.assigned || []); cur.add(user); out.assignments[row.id] = [...cur]; out.ok.push(name);
  }
  return out;
}

/* ------------------------------------------------------------------ sync status */
async function viewSync() {
  const r = await api("/api/sync/status");
  if (r.status === 401) return;
  const m = r.meta;
  const when = (iso) => new Date(iso).toLocaleString("en-IN", { day: "2-digit", month: "short", year: "numeric", hour: "numeric", minute: "2-digit", hour12: true, timeZone: "Asia/Kolkata" });
  $("#root").innerHTML = shell(`<div class="head"><h1>Sync from Tally</h1></div>
  ${m ? "" : '<div class="banner warn">Nothing has been synced yet. Install the sync agent on the PC that has Tally and run it once.</div>'}
  <div class="grid2"><div class="card pad"><h2>Last sync</h2>${m ? `<div style="font-size:22px;font-weight:800">${esc(when(m.lastSyncAt))}</div><p class="muted" style="margin:6px 0 0">${esc(m.company || "")} · ${m.lastRun.ledgers} ledgers${m.lastRun.removed ? `, ${m.lastRun.removed} removed` : ""}</p>${(Date.now() - Date.parse(m.lastSyncAt)) / 3600000 > 10 ? '<div class="banner warn" style="margin-top:10px">The data is more than 10 hours old. Check that the Tally PC is on and Tally is open.</div>' : '<div class="banner ok" style="margin-top:10px">Data is fresh.</div>'}` : '<p class="muted">No sync yet.</p>'}</div>
  <div class="card pad"><h2>How it updates</h2><p style="margin:0 0 8px">A small program on the Tally PC reads Tally three times a day and sends the ledgers here. The portal never connects into your PC.</p><p class="muted" style="margin:0">If Tally is closed at sync time, that run is skipped and the next one catches up. Ageing days always count from today, even between syncs.</p></div></div>
  ${m && m.history.length ? `<div class="card pad" style="margin-top:14px"><h2>Recent syncs</h2><div class="tblwrap"><table><thead><tr><th>When</th><th class="r">Ledgers</th><th>Type</th></tr></thead><tbody>${m.history.map((h) => `<tr><td>${esc(when(h.at))}</td><td class="r">${h.ledgers}</td><td>${h.full ? "Full" : "Partial"}${h.removed ? `, ${h.removed} removed` : ""}</td></tr>`).join("")}</tbody></table></div></div>` : ""}`);
}

/* ------------------------------------------------------------------ router and events */
async function render() {
  if (!S.user) return viewLogin();
  if (S.user.mustChange) return viewChangePassword(true);
  const h = location.hash || "#/dealers";
  const [, route, arg] = h.split("/");
  if (route === "password") return viewChangePassword(false);
  if (route === "dealer" && arg) return viewDealer(decodeURIComponent(arg));
  if (route === "payables" && can("accounts")) return viewList("creditor");
  if (route === "users" && S.user.role === "master") return viewUsers();
  if (route === "assign" && S.user.role === "master") return viewAssign();
  if (route === "sync" && can("accounts")) return viewSync();
  return viewList("debtor");
}
window.addEventListener("hashchange", render);

document.addEventListener("click", async (e) => {
  const row = e.target.closest("[data-id][role=link], tr.link");
  if (row && !e.target.closest("button,a,input")) { location.hash = "#/dealer/" + encodeURIComponent(row.dataset.id); return; }
  const el = e.target.closest("[data-act]"); if (!el) return;
  const a = el.dataset.act;
  if (a === "logout") { await api("/api/logout", { method: "POST", quiet: true }); S.user = null; S.dealers = null; location.hash = ""; render(); }
  else if (a === "pdf") makePdf();
  else if (a === "print") window.print();
  else if (a === "closedlg") $("#dlg").close();
  else if (a === "copy") { try { await navigator.clipboard.writeText(el.dataset.t); toast("Copied"); } catch (_) { toast("Select the password and copy it"); } }
  else if (a === "adduser") addUserDialog();
  else if (a === "saveuser") {
    const r = await api("/api/users", { method: "POST", body: { username: $("#nu").value, name: $("#nn").value, role: $("#nr").value } });
    if (!r.user) return addUserDialog(r.error || "Could not create the user.");
    showSecret("User created", r.user.username, r.tempPassword); viewUsers();
  } else if (a === "reset") {
    const r = await api("/api/users/" + encodeURIComponent(el.dataset.u), { method: "PATCH", body: { resetPassword: true } });
    if (!r.user) return toast(r.error || "Could not reset."); showSecret("Password reset", r.user.username, r.tempPassword); viewUsers();
  } else if (a === "toggle") {
    const r = await api("/api/users/" + encodeURIComponent(el.dataset.u), { method: "PATCH", body: { active: !el.dataset.active } });
    if (!r.user) return toast(r.error || "Could not change."); toast(r.user.active ? "User enabled" : "User disabled"); viewUsers();
  } else if (a === "asall" || a === "asnone") {
    const q = S.assignQ.trim().toLowerCase();
    S.dealers.rows.filter((x) => x.kind === "debtor" && (!q || `${x.name} ${x.city}`.toLowerCase().includes(q)) && (!S.onlyUnassigned || !currentAssign(x).length)).slice(0, 500).forEach((x) => toggleAssign(x, a === "asall"));
    paintAssign();
  } else if (a === "assave") { if (await saveAssign({ assignments: S.pending, mode: "merge" })) viewAssign(); }
  else if (a === "csvcheck") {
    const p = csvPlan(); S.csv = p;
    $("#csvOut").innerHTML = `<div class="banner ${p.ok.length ? "ok" : "warn"}" style="margin:0 0 8px">${p.ok.length} matched.${p.missing.length ? ` ${p.missing.length} dealer names not found.` : ""}${p.badUser.length ? ` ${p.badUser.length} lines with an unknown user.` : ""}</div>
    ${p.missing.length ? `<p class="muted" style="font-size:13px;margin:0 0 6px">Not found: ${esc(p.missing.slice(0, 8).join("; "))}${p.missing.length > 8 ? "..." : ""}</p>` : ""}${p.ok.length ? '<button class="btn primary" data-act="csvapply">Apply matched lines</button>' : ""}`;
  } else if (a === "csvapply") { if (S.csv && (await saveAssign({ assignments: S.csv.assignments, mode: "merge" }))) viewAssign(); }
});
document.addEventListener("keydown", (e) => { if (e.key === "Enter" && e.target.matches(".dcard")) e.target.click(); });

async function boot(again) {
  const r = await api("/api/me", { quiet: true });
  if (r.user) { S.user = r.user; S.company = r.company; S.syncedAt = r.syncedAt; } else { S.user = null; }
  render();
}
boot();
})();
