"""Ready to fill Excel templates, with a sample row and a short how-to sheet."""
from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

INV_COLS = ["Invoice Number", "Invoice Date", "Party Name", "GSTIN", "Bill To State", "Ship To State", "Item Description",
            "HSN", "Quantity", "Unit", "Rate", "Taxable Value", "GST Rate", "Tax", "Total", "Sale Ledger", "Narration"]
SAMPLE_SALES = [
    ["INV-1001", "2026-09-07", "SHARMA TELECOM", "04AAAAA1111A1Z5", "Chandigarh", "Chandigarh",
     "ACME AIRBUDS PROCLIP VELVET WINE", "85183011", 2, "PCS", 1288.14, 2576.28, 18, 463.72, 4220.00, "", "Sales to SHARMA"],
    ["INV-1001", "2026-09-07", "SHARMA TELECOM", "04AAAAA1111A1Z5", "Chandigarh", "Chandigarh",
     "Pb331", "85076000", 1, "PCS", 1000.00, 1000.00, 18, 180.00, 4220.00, "", "Sales to SHARMA"],
]
TEMPLATES = {
    "sales_invoices.xlsx": ("Sales", INV_COLS, SAMPLE_SALES),
    "purchase_bills.xlsx": ("Purchase", INV_COLS, []),
    "credit_notes.xlsx": ("Credit Note", INV_COLS[:-1] + ["Against Invoice"], []),
    "debit_notes.xlsx": ("Debit Note", INV_COLS[:-1] + ["Against Invoice"], []),
}
PAY_COLS = ["Date", "Party Name", "Amount", "Bank", "Reference", "Against Invoice", "Narration"]
HELP = {
    "Sales": ["One row per line item. Rows with the same Invoice Number become one invoice.",
              "Total is the invoice total AFTER tax. Never put the balance due here.",
              "Ship To State decides IGST or CGST+SGST. Leave it empty only if the GSTIN tells the state.",
              "Leave Sale Ledger empty and Tally Connect picks the ledger by state and rate.",
              "Dates: yyyy-mm-dd is safest. dd/mm/yyyy also works (Indian order)."],
}


def _sheet(ws, cols, rows):
    ws.append(cols)
    for r in rows:
        ws.append(r)
    for i, _ in enumerate(cols, 1):
        c = ws.cell(row=1, column=i)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1F3A5F")
        c.alignment = Alignment(wrap_text=True, vertical="center")
        ws.column_dimensions[get_column_letter(i)].width = max(14, min(36, len(cols[i - 1]) + 6))
    ws.freeze_panes = "A2"


def write_all(folder: str) -> list[str]:
    out = Path(folder)
    out.mkdir(parents=True, exist_ok=True)
    made = []
    for fname, (vt, cols, rows) in TEMPLATES.items():
        wb = Workbook()
        _sheet(wb.active, cols, rows)
        wb.active.title = "Data"
        h = wb.create_sheet("How to fill")
        for line in [f"{vt} template"] + HELP["Sales"]:
            h.append([line])
        h.column_dimensions["A"].width = 110
        wb.save(out / fname)
        made.append(str(out / fname))
    for fname, vt in (("receipts.xlsx", "Receipt"), ("payments.xlsx", "Payment")):
        wb = Workbook()
        _sheet(wb.active, PAY_COLS, [["2026-09-14", "Gill Communication" if vt == "Receipt" else "Prime Distribution Limited",
                                      11000, "HDFC BANK", "UTR123456", "", f"{vt} sample"]])
        wb.active.title = "Data"
        wb.save(out / fname)
        made.append(str(out / fname))
    return made
