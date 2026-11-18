// Outstanding and ageing. Rules copied from the Nalanda reconciliation work:
//  * age is counted from the BILL date, never from a due date field
//  * newest bills are matched first against the ledger balance (FIFO from the top)
//  * the amount that cannot be matched to a dated bill is shown as "older / opening", with no date
//  * ledgers that are not bill wise are rebuilt from their own voucher history
import { daysBetween, round2 } from "./util.mjs";

export const BUCKETS = [
  { key: "b0", label: "0 to 30 days", from: 0, to: 30 },
  { key: "b1", label: "31 to 60 days", from: 31, to: 60 },
  { key: "b2", label: "61 to 90 days", from: 61, to: 90 },
  { key: "b3", label: "Over 90 days", from: 91, to: Infinity },
];

export function bucketOf(days) {
  for (const b of BUCKETS) if (days >= b.from && days <= b.to) return b.key;
  return "b3";
}

/**
 * Build dated bills from voucher history when Tally gave no bill wise data.
 * kind "debtor": invoices are debit entries. kind "creditor": bills are credit entries.
 * outstanding is the positive amount still owed on the right side (receivable or payable).
 */
export function deriveBillsFIFO(vouchers, kind, outstanding) {
  let remaining = round2(outstanding);
  const bills = [];
  if (remaining <= 0) return { bills, older: 0 };
  const key = kind === "creditor" ? "credit" : "debit";
  const rows = [...vouchers]
    .filter((v) => Number(v[key]) > 0)
    .sort((a, b) => (a.date < b.date ? 1 : a.date > b.date ? -1 : 0)); // newest first
  for (const v of rows) {
    if (remaining <= 0.004) break;
    const original = round2(v[key]);
    const pending = round2(Math.min(remaining, original));
    bills.push({ ref: String(v.number || ""), date: v.date, original, pending, derived: true });
    remaining = round2(remaining - pending);
  }
  bills.sort((a, b) => (a.date < b.date ? -1 : 1));
  return { bills, older: remaining > 0.004 ? remaining : 0 };
}

/** Add days and bucket to bills, and total them. today is yyyy-mm-dd. */
export function ageBills(bills, older, today) {
  const out = [];
  const totals = { b0: 0, b1: 0, b2: 0, b3: 0, older: round2(older || 0), total: 0, oldestDays: 0 };
  for (const b of bills || []) {
    const days = Math.max(0, daysBetween(b.date, today));
    const bucket = bucketOf(days);
    out.push({ ...b, days, bucket });
    totals[bucket] = round2(totals[bucket] + b.pending);
    totals.oldestDays = Math.max(totals.oldestDays, days);
  }
  totals.total = round2(totals.b0 + totals.b1 + totals.b2 + totals.b3 + totals.older);
  return { bills: out, totals };
}

/** Statement rows with a running balance. Dr is positive. opening is {amount, side}. */
export function withRunning(opening, vouchers) {
  let bal = (opening.side === "Cr" ? -1 : 1) * Number(opening.amount || 0);
  const rows = [];
  for (const v of [...vouchers].sort((a, b) => (a.date === b.date ? 0 : a.date < b.date ? -1 : 1))) {
    bal = round2(bal + Number(v.debit || 0) - Number(v.credit || 0));
    rows.push({ ...v, balance: { amount: Math.abs(bal), side: bal < 0 ? "Cr" : "Dr" } });
  }
  return rows;
}
