"""Plan a batch: decide for every document whether it is READY, HELD, a DUPLICATE or an ERROR.

Nothing is written here. Held items carry the exact question a human has to answer.
"""
from __future__ import annotations

import dataclasses
import json
import uuid
from dataclasses import dataclass, field

from . import importer as I, tax as T, vouchers as V
from .engine import Tally


@dataclass
class Row:
    doc: I.Doc
    status: str = "READY"                     # READY | HELD | DUPLICATE | ERROR
    reasons: list = field(default_factory=list)
    questions: list = field(default_factory=list)
    invoice: V.Invoice | None = None
    notes: list = field(default_factory=list)
    accounting: V.Accounting | None = None
    pay: object = None


def _held(row: Row, reason: str, question: str):
    row.status = "HELD" if row.status != "ERROR" else row.status
    row.reasons.append(reason)
    row.questions.append(question)


def build(t: Tally, d: I.Doc) -> Row:
    row = Row(d, notes=list(d.warnings))
    if d.voucher_type not in V.INVOICE_TYPES:
        row.status = "ERROR"
        row.reasons.append(f"Voucher type {d.voucher_type!r} is not an item invoice type")
        return row
    if not d.lines:
        row.status = "ERROR"
        row.reasons.append("No line items")
        return row
    cfg = t.cfg
    ledger_names = {l["name"] for l in t.ledgers()}

    # party
    pm = t.find_ledger(d.party, d.gstin)
    party_row = next((l for l in t.ledgers() if l["name"] == pm["name"]), None) if pm["name"] else None
    if pm["status"] == "none":
        _held(row, f"Party '{d.party}' has no ledger in Tally",
              f"Tally has no ledger for {d.party}. Create it as a new ledger, or is it an existing party under another name?")
    elif pm["status"] == "ambiguous":
        _held(row, f"Party '{d.party}' matches several ledgers",
              f"Which ledger is {d.party}? " + " / ".join(n for n, _ in pm["candidates"]))
    else:
        if pm["how"] not in ("exact", "GSTIN match", "saved mapping"):
            row.notes.append(f"Party '{d.party}' matched to '{pm['name']}' ({pm['how']})")

    # place of supply: ship to state, then bill to, then GSTIN code, then the ledger
    pos = d.ship_state or d.state or I.state_from_gstin(d.gstin) or (party_row or {}).get("state", "")
    party_state = d.state or I.state_from_gstin(d.gstin) or (party_row or {}).get("state", "") or pos
    if not pos:
        _held(row, "Place of supply unknown", f"What is the ship-to state for {d.number}? It decides IGST or CGST/SGST.")
    if not cfg.get("company_state"):
        _held(row, "Company state is not set", "Set company_state in the settings first.")

    # items
    items, taxable_sum = [], 0.0
    for ln in d.lines:
        im = t.find_item(ln.item)
        if im["status"] == "none":
            _held(row, f"Item '{ln.item}' not found",
                  f"No stock item matches '{ln.item}'. Map it to the closest item, or create it as a new item?")
            continue
        if im["status"] == "ambiguous":
            _held(row, f"Item '{ln.item}' is ambiguous",
                  f"Which stock item is '{ln.item}'? " + " / ".join(n for n, _ in im["candidates"]))
            continue
        if im["how"] not in ("exact", "saved mapping"):
            row.notes.append(f"Item '{ln.item}' matched to '{im['name']}'")
        line_tax = ln.tax or (ln.igst + ln.cgst + ln.sgst)
        rate = ln.gst_rate or (round(line_tax / ln.taxable * 100) if ln.taxable and line_tax else 0)
        rate = min((0, 5, 12, 18, 28), key=lambda r: abs(r - rate)) if rate else 0
        led = ln.ledger or (T.item_ledger(d.voucher_type, cfg["company_state"], pos, rate, cfg) if pos else "")
        if led and led not in ledger_names:
            _held(row, f"Ledger '{led}' not in Tally",
                  f"Which sales/purchase ledger should line '{ln.item}' use? '{led}' does not exist in Tally.")
        items.append(V.Item(im["name"], ln.qty, round(ln.rate, 2), round(ln.taxable, 2), ln.unit, led, rate, ln.hsn))
        taxable_sum += ln.taxable

    taxable, tax_total, total = I.doc_totals(d)
    if d.total is None and tax_total == 0:
        row.notes.append("No tax and no total in the sheet, so the invoice is posted at taxable value with no GST")
    tax_led = T.tax_ledgers(d.voucher_type, cfg["company_state"], pos, cfg) if (pos and cfg.get("company_state")) else []
    for tl in tax_led:
        if tl not in ledger_names:
            _held(row, f"Tax ledger '{tl}' not in Tally", f"The tax ledger '{tl}' is missing. Which ledger should GST go to?")
    tax_pairs = T.split(tax_total, tax_led) if (tax_led and tax_total) else []
    round_off = round(total - taxable - tax_total, 2)
    if abs(round_off) > 1.0:
        row.status = "ERROR"
        row.reasons.append(f"Items {taxable:.2f} + tax {tax_total:.2f} differ from the total {total:.2f} by {round_off:.2f}")
        if tax_total and abs(taxable - total) < 0.011:
            row.reasons.append("The taxable value equals the total, so the amount column may already include tax. "
                               "Check whether it is tax inclusive before posting.")
        return row
    if round_off and cfg["ledgers"]["round_off"] not in ledger_names:
        _held(row, "Round off ledger missing", "Which ledger takes the paise difference?")

    party_name = pm["name"] or d.party
    gst = V.Gst(d.gstin or (party_row or {}).get("gstin", ""), party_state, pos,
                bill_to=[], ship_to=[], company_gstin=cfg["company_gstin"], company_state=cfg["company_state"])
    row.invoice = V.Invoice(d.voucher_type, d.date, d.number, party_name, items, tax_pairs, round(total, 2), gst,
                            round_off, d.narration or f"{d.voucher_type} {d.number}", d.against_ref)
    if row.status == "READY":
        errs = V.validate_invoice(row.invoice)
        if errs:
            row.status, row.reasons = "ERROR", errs
    if row.status == "READY" and d.date:
        dup = t.find_duplicate(d.voucher_type, d.number, d.date)
        if dup:
            row.status = "DUPLICATE"
            row.reasons.append(dup)
    return row


@dataclass
class Plan:
    id: str
    rows: list
    notes: list

    def summary(self) -> dict:
        c = {"READY": 0, "HELD": 0, "DUPLICATE": 0, "ERROR": 0}
        for r in self.rows:
            c[r.status] += 1
        ready_total = round(sum((r.invoice.total if r.invoice else r.pay.amount) for r in self.rows if r.status == "READY"), 2)
        return {"plan_id": self.id, "counts": c, "ready_total": ready_total, "notes": self.notes,
                "series_gaps": series_gaps([r.doc.number for r in self.rows])}

    def table(self) -> list[dict]:
        out = []
        for r in self.rows:
            d = r.doc
            out.append({"type": d.voucher_type, "number": d.number, "date": d.date, "party": d.party,
                        "tally_party": (r.invoice.party_ledger if r.invoice else (r.accounting.party_ledger if r.accounting else "")),
                        "status": r.status,
                        "total": r.invoice.total if r.invoice else (r.pay.amount if r.pay else None),
                        "tax": [list(x) for x in r.invoice.tax] if r.invoice else [],
                        "reasons": r.reasons, "questions": r.questions, "notes": r.notes})
        return out


def series_gaps(numbers: list[str]) -> list[str]:
    """Report missing numbers inside a numeric invoice series. The series must stay complete."""
    import re
    groups: dict[str, list[int]] = {}
    for n in numbers:
        m = re.fullmatch(r"(.*?)(\d+)", n)
        if m:
            groups.setdefault(m[1], []).append(int(m[2]))
    gaps = []
    for pre, nums in groups.items():
        s = sorted(set(nums))
        if len(s) > 1 and s[-1] - s[0] < 5000:
            gaps += [f"{pre}{x}" for x in range(s[0], s[-1] + 1) if x not in set(s)]
    return gaps[:50]


def build_payment(t: Tally, d: I.PayDoc, default_bank: str = "") -> Row:
    shell = I.Doc(d.voucher_type, d.reference or f"{d.date}|{d.party}|{d.amount:.2f}", d.date, d.party,
                  warnings=list(d.warnings))
    row = Row(shell, notes=list(d.warnings))
    row.pay = d
    if d.voucher_type not in ("Receipt", "Payment"):
        row.status = "ERROR"
        row.reasons.append(f"Voucher type {d.voucher_type!r} is not a Receipt or Payment")
        return row
    if not d.date or d.amount <= 0:
        row.status = "ERROR"
        row.reasons.append("Missing date or amount")
        return row
    pm = t.find_ledger(d.party)
    if pm["status"] == "none":
        _held(row, f"Party '{d.party}' has no ledger in Tally", f"No ledger for {d.party}. Which ledger is this payment for?")
    elif pm["status"] == "ambiguous":
        _held(row, f"Party '{d.party}' matches several ledgers",
              f"Which ledger is {d.party}? " + " / ".join(n for n, _ in pm["candidates"]))
    bank = d.bank or default_bank
    names = {l["name"] for l in t.ledgers()}
    bm = t.find_ledger(bank) if bank else {"status": "none", "name": None}
    if bm["status"] != "auto":
        _held(row, "Bank or cash ledger unclear", f"Which bank or cash ledger took this {d.voucher_type.lower()} of {d.amount:,.2f}?")
    if row.status == "READY":
        party, bnk = pm["name"], bm["name"]
        entries = [(bnk, -d.amount), (party, d.amount)] if d.voucher_type == "Receipt" else [(party, -d.amount), (bnk, d.amount)]
        row.accounting = V.Accounting(d.voucher_type, d.date, d.reference, entries, party, d.narration,
                                      [(r, d.amount / max(len(d.invoices), 1)) for r in d.invoices] if len(d.invoices) == 1 else [])
        key = f"{d.voucher_type}|{d.date}|{party}|{d.amount:.2f}"
        if t.state.was_posted_key(key):
            row.status = "DUPLICATE"
            row.reasons.append("already posted by Tally Connect (same date, party and amount)")
    return row


def make_plan(t: Tally, path: str, default_type="Sales", sheet=None, default_bank: str = "") -> Plan:
    if default_type in ("Receipt", "Payment"):
        docs, notes = I.parse_payments(path, default_type, sheet)
        rows = [build_payment(t, d, default_bank) for d in docs]
        return Plan(uuid.uuid4().hex[:8], rows, notes)
    docs, notes = I.parse(path, default_type, sheet)
    rows = [build(t, d) for d in docs]
    return Plan(uuid.uuid4().hex[:8], rows, notes)


def post_plan(t: Tally, plan: Plan, only: list[str] | None = None) -> list[dict]:
    """Post READY rows one by one. Stops at the first row that fails or fails verification."""
    results = []
    for r in plan.rows:
        if r.status != "READY" or (only and r.doc.number not in only) or not (r.invoice or r.accounting):
            continue
        pv = t.preview_invoice(r.invoice) if r.invoice else t.preview_accounting(r.accounting)
        if not pv["ok"]:
            results.append({"number": r.doc.number, "ok": False, "problems": pv["problems"]})
            continue
        cf = t.confirm(pv["preview_id"])
        results.append({"number": r.doc.number, "ok": cf["ok"], "verified": cf.get("verified"),
                        "balance_delta": cf.get("balance_delta"), "problems": cf.get("problems", [])})
        if not cf["ok"]:
            results.append({"stopped": "Stopped after the first failure so nothing else is posted on top of a problem."})
            break
    return results
