"""Turn a messy Excel or CSV into clean documents.

This is the deterministic half of the sorting. Claude does the judgement half (reading PDFs and
images, deciding what an odd column means). Everything here is checked arithmetic.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

SYNONYMS = {
    "invoice_no": ["invoice number", "invoice no", "invoice no.", "inv no", "bill no", "bill number", "voucher no",
                   "voucher number", "document no", "doc no", "invoice"],
    "date": ["invoice date", "date", "bill date", "voucher date", "doc date"],
    "party": ["party account name", "party name", "party", "customer", "customer name", "buyer name", "buyer",
              "vendor", "vendor name", "supplier", "ledger name", "account name"],
    "gstin": ["gstin", "gstin/uin", "gst no", "gst number", "party gstin", "customer gstin", "buyer gstin"],
    "state": ["state", "bill to state", "buyer state", "state buyer", "party state"],
    "ship_state": ["ship to state", "place of supply", "shipping state", "delivery state"],
    "item": ["item description", "item", "item name", "product", "product name", "description", "stock item"],
    "qty": ["quantity", "qty", "qty.", "units"],
    "unit": ["unit", "uom"],
    "rate": ["rate", "price", "unit price", "rate per unit"],
    "taxable": ["taxable value", "taxable amount", "taxable", "amount before tax", "net amount", "basic value", "amount"],
    "tax": ["tax", "gst", "gst amount", "tax amount", "total tax"],
    "igst": ["igst", "igst amount"], "cgst": ["cgst", "cgst amount"],
    "sgst": ["sgst", "sgst amount", "utgst", "sgst/utgst"],
    "gst_rate": ["gst rate", "tax rate", "gst %", "tax %", "rate of tax"],
    "total": ["total", "invoice total", "total amount", "total amount after tax", "invoice value", "grand total"],
    "hsn": ["hsn", "hsn code", "hsn/sac", "hsn sac"],
    "ledger": ["sale ledger", "sales ledger", "purchase ledger", "ledger"],
    "voucher_type": ["voucher type", "type", "document type"],
    "narration": ["narration", "remarks", "note", "notes"],
    "against_ref": ["against invoice", "original invoice", "against ref", "reference invoice", "original invoice no"],
}
_STATE_CODES = {
    "01": "Jammu and Kashmir", "02": "Himachal Pradesh", "03": "Punjab", "04": "Chandigarh", "05": "Uttarakhand",
    "06": "Haryana", "07": "Delhi", "08": "Rajasthan", "09": "Uttar Pradesh", "10": "Bihar", "11": "Sikkim",
    "12": "Arunachal Pradesh", "13": "Nagaland", "14": "Manipur", "15": "Mizoram", "16": "Tripura",
    "17": "Meghalaya", "18": "Assam", "19": "West Bengal", "20": "Jharkhand", "21": "Odisha", "22": "Chhattisgarh",
    "23": "Madhya Pradesh", "24": "Gujarat", "26": "Dadra and Nagar Haveli and Daman and Diu", "27": "Maharashtra",
    "29": "Karnataka", "30": "Goa", "31": "Lakshadweep", "32": "Kerala", "33": "Tamil Nadu", "34": "Puducherry",
    "35": "Andaman and Nicobar Islands", "36": "Telangana", "37": "Andhra Pradesh", "38": "Ladakh",
}


def state_from_gstin(g: str) -> str:
    g = (g or "").strip()
    return _STATE_CODES.get(g[:2], "") if len(g) == 15 else ""


def _key(h) -> str:
    return re.sub(r"\s+", " ", str(h or "").strip().lower())


def map_headers(headers: list) -> dict:
    """canonical name -> column index. Exact synonym beats partial."""
    found: dict[str, int] = {}
    keys = [_key(h) for h in headers]
    for canon, syns in SYNONYMS.items():
        for s in syns:
            if s in keys:
                found.setdefault(canon, keys.index(s))
                break
    return found


def read_table(path: str, sheet: str | None = None) -> tuple[list[list], str]:
    p = Path(path)
    if p.suffix.lower() == ".csv":
        with open(p, newline="", encoding="utf-8-sig") as f:
            return [r for r in csv.reader(f)], "csv"
    if p.suffix.lower() == ".xls":
        try:
            import xlrd  # type: ignore
        except ImportError as e:
            raise RuntimeError("Old .xls files need 'pip install xlrd', or save the file as .xlsx first.") from e
        wb = xlrd.open_workbook(str(p))
        ws = wb.sheet_by_name(sheet) if sheet else wb.sheet_by_index(0)
        return [[ws.cell_value(r, c) for c in range(ws.ncols)] for r in range(ws.nrows)], ws.name
    import openpyxl
    wb = openpyxl.load_workbook(p, data_only=True, read_only=True)
    ws = wb[sheet] if sheet else wb.worksheets[0]
    return [list(r) for r in ws.iter_rows(values_only=True)], ws.title


def to_iso(v, warnings: list | None = None) -> str:
    if v is None or v == "":
        return ""
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, (int, float)) and 20000 < float(v) < 80000:      # Excel serial
        return (date(1899, 12, 30) + timedelta(days=int(float(v)))).isoformat()
    s = str(v).strip()
    m = re.fullmatch(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", s)
    if m:
        return date(int(m[1]), int(m[2]), int(m[3])).isoformat()
    m = re.fullmatch(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})", s)
    if m:
        d, mo, y = int(m[1]), int(m[2]), int(m[3])
        y += 2000 if y < 100 else 0
        if d <= 12 and mo <= 12 and d != mo and warnings is not None:
            warnings.append(f"Date {s} read as day/month/year (Indian format). Check it.")
        return date(y, mo, d).isoformat()
    for fmt in ("%d-%b-%Y", "%d %b %Y", "%d-%B-%Y", "%b %d, %Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    raise ValueError(f"Cannot read the date {s!r}")


def f(v) -> float:
    if v is None or v == "":
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = re.sub(r"[^0-9.\-]", "", str(v).replace(",", ""))
    return float(s) if s not in ("", "-", ".") else 0.0


@dataclass
class DocLine:
    item: str
    qty: float
    rate: float
    taxable: float
    tax: float = 0.0
    igst: float = 0.0
    cgst: float = 0.0
    sgst: float = 0.0
    gst_rate: float | None = None
    unit: str = "PCS"
    hsn: str = ""
    ledger: str = ""


@dataclass
class Doc:
    voucher_type: str
    number: str
    date: str
    party: str
    gstin: str = ""
    state: str = ""
    ship_state: str = ""
    lines: list = field(default_factory=list)
    total: float | None = None
    narration: str = ""
    against_ref: str = ""
    warnings: list = field(default_factory=list)
    source_rows: list = field(default_factory=list)


def parse(path: str, default_type: str = "Sales", sheet: str | None = None) -> tuple[list[Doc], list[str]]:
    table, sheetname = read_table(path, sheet)
    notes: list[str] = []
    hdr_i = None
    for i, row in enumerate(table[:30]):
        mp = map_headers(row)
        if len(mp) >= 4 and "item" in mp or len(mp) >= 5:
            hdr_i, cols = i, mp
            break
    if hdr_i is None:
        raise ValueError("Could not find a header row. The sheet needs columns like Invoice Number, Date, "
                         "Party, Item, Quantity, Rate, Taxable Value, Tax.")
    missing = [c for c in ("invoice_no", "date", "party") if c not in cols]
    if missing:
        raise ValueError("Missing required columns: " + ", ".join(missing))
    notes.append(f"Sheet '{sheetname}', header on row {hdr_i + 1}, columns found: " + ", ".join(sorted(cols)))
    docs: dict[tuple, Doc] = {}
    order = []
    get = lambda row, k: row[cols[k]] if k in cols and cols[k] < len(row) else None
    for ri, row in enumerate(table[hdr_i + 1:], start=hdr_i + 2):
        if not any(c not in (None, "") for c in row):
            continue
        no = str(get(row, "invoice_no") or "").strip()
        if no.endswith(".0"):
            no = no[:-2]
        if not no:
            continue
        vt = str(get(row, "voucher_type") or default_type).strip().title()
        vt = {"Sale": "Sales", "Sales Invoice": "Sales", "Purchase Invoice": "Purchase", "Bill": "Purchase",
              "Credit Memo": "Credit Note", "Debit Memo": "Debit Note"}.get(vt, vt)
        key = (vt, no)
        if key not in docs:
            warns: list = []
            try:
                iso = to_iso(get(row, "date"), warns)
            except ValueError as e:
                iso = ""
                warns.append(str(e))
            docs[key] = Doc(vt, no, iso, str(get(row, "party") or "").strip(),
                            str(get(row, "gstin") or "").strip().upper(),
                            str(get(row, "state") or "").strip(), str(get(row, "ship_state") or "").strip(),
                            narration=str(get(row, "narration") or "").strip(),
                            against_ref=str(get(row, "against_ref") or "").strip(), warnings=warns)
            order.append(key)
        d = docs[key]
        d.source_rows.append(ri)
        qty, rate = f(get(row, "qty")), f(get(row, "rate"))
        taxable = f(get(row, "taxable")) or round(qty * rate, 2)
        item = str(get(row, "item") or "").strip()
        if item or taxable:
            d.lines.append(DocLine(item, qty or 1.0, rate or (round(taxable / qty, 2) if qty else taxable), taxable,
                                   f(get(row, "tax")), f(get(row, "igst")), f(get(row, "cgst")), f(get(row, "sgst")),
                                   f(get(row, "gst_rate")) or None, str(get(row, "unit") or "PCS").strip() or "PCS",
                                   str(get(row, "hsn") or "").strip(), str(get(row, "ledger") or "").strip()))
        t = f(get(row, "total"))
        if t and "total" in cols and (d.total is None or t > d.total):
            d.total = t
    out = [docs[k] for k in order]
    for d in out:
        if not d.date:
            d.warnings.append("No usable date")
    return out, notes


def doc_totals(d: Doc) -> tuple[float, float, float]:
    taxable = round(sum(l.taxable for l in d.lines), 2)
    tax = round(sum((l.tax or (l.igst + l.cgst + l.sgst)) for l in d.lines), 2)
    total = d.total if d.total else round(taxable + tax, 2)
    return taxable, tax, total


PAY_SYNONYMS = {
    "date": ["date", "payment date", "receipt date", "voucher date", "txn date", "transaction date"],
    "party": ["party", "party name", "customer", "vendor", "name", "ledger", "account name", "received from", "paid to"],
    "amount": ["amount", "receipt amount", "payment amount", "total", "credit", "paid", "received"],
    "bank": ["bank", "bank ledger", "bank/cash", "deposit to", "paid from", "mode", "account"],
    "reference": ["reference", "ref no", "ref", "utr", "cheque no", "transaction id", "voucher no"],
    "narration": ["narration", "remarks", "note", "notes", "description"],
    "invoices": ["against invoice", "invoice no", "invoices", "invoice number", "bill no"],
    "voucher_type": ["voucher type", "type"],
}


@dataclass
class PayDoc:
    voucher_type: str          # Receipt | Payment
    date: str
    party: str
    amount: float
    bank: str = ""
    reference: str = ""
    narration: str = ""
    invoices: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    source_row: int = 0


def parse_payments(path: str, default_type: str = "Receipt", sheet: str | None = None) -> tuple[list[PayDoc], list[str]]:
    table, sheetname = read_table(path, sheet)
    hdr_i, cols = None, {}
    for i, row in enumerate(table[:30]):
        keys = [_key(h) for h in row]
        mp = {}
        for canon, syns in PAY_SYNONYMS.items():
            for s in syns:
                if s in keys:
                    mp.setdefault(canon, keys.index(s))
                    break
        if {"date", "party", "amount"} <= set(mp):
            hdr_i, cols = i, mp
            break
    if hdr_i is None:
        raise ValueError("Could not find a header row with Date, Party and Amount columns.")
    out, get = [], lambda row, k: row[cols[k]] if k in cols and cols[k] < len(row) else None
    for ri, row in enumerate(table[hdr_i + 1:], start=hdr_i + 2):
        if not any(c not in (None, "") for c in row):
            continue
        warns: list = []
        try:
            iso = to_iso(get(row, "date"), warns)
        except ValueError as e:
            iso = ""
            warns.append(str(e))
        vt = str(get(row, "voucher_type") or default_type).strip().title()
        inv = [x.strip() for x in re.split(r"[,;/]", str(get(row, "invoices") or "")) if x.strip()]
        out.append(PayDoc(vt, iso, str(get(row, "party") or "").strip(), abs(f(get(row, "amount"))),
                          str(get(row, "bank") or "").strip(), str(get(row, "reference") or "").strip(),
                          str(get(row, "narration") or "").strip(), inv, warns, ri))
    return out, [f"Sheet '{sheetname}', header on row {hdr_i + 1}, columns found: " + ", ".join(sorted(cols))]
