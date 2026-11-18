// Made up dealers for tests and for the demo. No real names, numbers or GSTINs.
import { deriveBillsFIFO } from "../server/ageing.mjs";

const FIRST = ["Sharma", "Kaur", "Rana", "Gill", "Bansal", "Verma", "Singh", "Mehta", "Arora", "Kapoor", "Dhillon", "Sidhu", "Chopra", "Malik", "Garg", "Bedi", "Sethi", "Jain", "Khanna", "Bajwa"];
const KIND = ["Telecom", "Mobile Shop", "Electronics", "Communications", "Enterprises", "Traders", "Mobiles", "Digital Hub"];
const CITIES = ["Chandigarh", "Mohali", "Panchkula", "Zirakpur", "Kharar", "Ludhiana", "Ambala"];
const GROUPS = ["Sundry Debtors", "DEBTORS OF NORTH ZONE", "Sundry Debtors"];

function rng(seed) { let s = seed >>> 0; return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296); }
const iso = (today, daysAgo) => new Date(Date.parse(today + "T00:00:00Z") - daysAgo * 86400000).toISOString().slice(0, 10);

export function makeLedgers({ today = "2026-09-30", dealers = 40, vendors = 5, seed = 7 } = {}) {
  const r = rng(seed);
  const out = [];
  for (let i = 0; i < dealers; i++) {
    const name = `${FIRST[i % FIRST.length]} ${KIND[(i * 3) % KIND.length]}${i >= FIRST.length ? " " + (Math.floor(i / FIRST.length) + 1) : ""}`;
    const vouchers = [];
    let bal = 0;
    const n = 3 + Math.floor(r() * 5);
    for (let k = 0; k < n; k++) {
      const ago = 5 + Math.floor(r() * 190);
      const amt = Math.round((4000 + r() * 90000) / 10) * 10;
      vouchers.push({ date: iso(today, ago), type: "Sales", number: `INV-${1000 + i * 10 + k}`, particulars: "Goods sold", debit: amt, credit: 0 });
    }
    vouchers.sort((a, b) => (a.date < b.date ? -1 : 1));
    if (r() < 0.6) { // a receipt that clears about half of the older invoices
      const upto = vouchers[Math.floor(vouchers.length / 2)];
      const paid = Math.round(vouchers.slice(0, Math.ceil(vouchers.length / 2)).reduce((a, v) => a + v.debit, 0) * 0.9);
      vouchers.push({ date: iso(today, 3 + Math.floor(r() * 25)), type: "Receipt", number: `R-${i}`, particulars: "HDFC BANK", debit: 0, credit: paid });
    }
    vouchers.sort((a, b) => (a.date < b.date ? -1 : 1));
    bal = vouchers.reduce((a, v) => a + v.debit - v.credit, 0);
    const closing = { amount: Math.abs(bal), side: bal < 0 ? "Cr" : "Dr" };
    const doc = { name, group: GROUPS[i % GROUPS.length], kind: "debtor", city: CITIES[i % CITIES.length], state: "Chandigarh", phone: `98${String(10000000 + i * 137).slice(0, 8)}`,
      gstin: i % 3 === 0 ? "" : `04AAAAA${String(1000 + i).slice(-4)}A1Z5`, opening: { amount: 0, side: "Dr" }, closing, vouchers };
    if (i % 2 === 0 && closing.side === "Dr" && closing.amount > 0) { // bill wise ledger: Tally lists the bills
      doc.bills = deriveBillsFIFO(vouchers, "debtor", closing.amount).bills.map((b) => ({ ref: b.ref, date: b.date, original: b.original, pending: b.pending }));
    }
    out.push(doc);
  }
  for (let i = 0; i < vendors; i++) {
    const amt = 20000 + i * 15000;
    out.push({ name: `Prime Distribution ${i + 1} Limited`, group: "Sundry Creditors", kind: "creditor", city: "Mumbai", state: "Maharashtra", phone: "", gstin: "27AAAAA2222A1Z5",
      opening: { amount: 0, side: "Cr" }, closing: { amount: amt, side: "Cr" }, vouchers: [{ date: iso(today, 20 + i * 11), type: "Purchase", number: `P-${i + 1}`, particulars: "Goods purchased", debit: 0, credit: amt }] });
  }
  return out;
}

/** Push ledgers to a portal over its real sync API. */
export async function pushSync(baseUrl, key, ledgers, { company = "DEMO DATA (sample, not real)", full = true } = {}) {
  const run = "run-" + Math.random().toString(36).slice(2, 12);
  const post = async (path, body) => {
    const r = await fetch(baseUrl + path, { method: "POST", headers: { "content-type": "application/json", authorization: "Bearer " + key }, body: JSON.stringify(body) });
    const j = await r.json();
    if (!r.ok) throw new Error(`${path} ${r.status} ${JSON.stringify(j)}`);
    return j;
  };
  await post("/api/sync/start", { runId: run, company, full });
  for (let i = 0; i < ledgers.length; i += 100) await post("/api/sync/ledgers", { runId: run, ledgers: ledgers.slice(i, i + 100) });
  return post("/api/sync/finish", { runId: run });
}
