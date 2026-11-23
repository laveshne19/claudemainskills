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


DEMO_COLS = ["Invoice Number", "Invoice Date", "Party Name", "GSTIN", "Bill To State", "Ship To State",
             "Item Description", "Quantity", "Rate", "Taxable Value", "Tax", "Total"]
DEMO_ROWS = [
    ["INV-2201", "2026-09-07", "SHARMA TELECOM", "04AAAAA1111A1Z5", "Chandigarh", "Chandigarh", "ACME AIRBUDS ACE BLACK", 2, 1288.14, 2576.28, 463.72, 4220.00],
    ["INV-2201", "2026-09-07", "SHARMA TELECOM", "04AAAAA1111A1Z5", "Chandigarh", "Chandigarh", "Pb331", 1, 1000.00, 1000.00, 180.00, 4220.00],
    ["INV-2202", "2026-09-07", "KAUR MOBILE SHOP", "", "Punjab", "Punjab", "Acme_Rocker Summit Classic Black", 10, 1694.92, 16949.20, 3050.86, 20000.06],
    ["INV-2203", "2026-09-08", "Rana Enterprise", "", "Punjab", "Punjab", "POWERBANK 20000 MAH WITH CABLE", 5, 1271.19, 6355.95, 1144.07, 7500.02],
    ["INV-2204", "2026-09-08", "ANKUR SRIVASTAV", "", "Chandigarh", "Chandigarh", "ACME AIRBUDS ACE BLACK", 3, 1694.92, 5084.76, 915.24, 6000.00],
    ["INV-2205", "2026-09-08", "BRIGHT & CLEAR ADVERTISING PVT LTD", "", "Haryana", "Haryana", "Coin 3-in-1 Charger", 4, 847.46, 3389.84, 610.16, 4000.00],
    ["INV-2206", "2026-09-06", "KAUR MOBILE SHOP", "", "Punjab", "Punjab", "ACME ROCKER SUMMIT BLACK", 10, 1694.92, 16949.20, 3050.86, 20000.06],
    ["INV-2207", "2026-09-09", "SHARMA TELECOM", "", "Chandigarh", "Chandigarh", "ACME ROCKER SUMMIT BLACK", 5, 1600.00, 8000.00, 1440.00, 8000.00],
    ["INV-2208", "2026-09-09", "ONLINE MARKETPLACE SALE", "", "Karnataka", "Karnataka", "ACME AIRBUDS ACE BLACK", 21, 767.51, 16117.71, 2901.19, 19018.90],
    ["INV-2209", "2026-09-10", "Rana Enterprises", "", "Punjab", "Haryana", "ACME ROCKER SUMMIT BLACK", 6, 1666.67, 10000.02, 1800.00, 11800.00],
]


def write_demo_sheet(path: str) -> str:
    """The sample batch used by the demo: ready, held, duplicate and error rows on purpose."""
    wb = Workbook()
    _sheet(wb.active, DEMO_COLS, DEMO_ROWS)
    wb.active.title = "Data"
    wb.save(path)
    return path


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
