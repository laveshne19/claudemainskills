"""MCP server. Works on both the 1.x (FastMCP) and 2.x (MCPServer) Python SDKs.

The previous community connector crashed on startup when mcp 2.x was installed. This one adapts.
"""
from __future__ import annotations

import functools
import inspect
import json

from . import __version__, config as cfgmod, pipeline
from . import vouchers as V
from .engine import RefusedWrite, Tally

try:                                        # SDK 1.x
    from mcp.server.fastmcp import FastMCP as _Server
except Exception:                           # SDK 2.x
    from mcp.server.mcpserver import MCPServer as _Server        # type: ignore

INSTRUCTIONS = (
    "Tally Connect posts entries into TallyPrime. Always start with tally_doctor. Writes are two steps: "
    "a preview, then confirm_import after the user says yes. Never create a ledger or stock item without the "
    "user's explicit approval. Never post to Tally without showing the batch table first. After every confirm, "
    "report the balance check result. Held items must be put to the user as the exact question from the plan.")

mcp = _Server("tally-connect", instructions=INSTRUCTIONS)
_t: Tally | None = None
_plans: dict[str, pipeline.Plan] = {}


def T() -> Tally:
    global _t
    if _t is None:
        _t = Tally()
    return _t


def _j(x) -> str:
    return json.dumps(x, indent=1, ensure_ascii=False, default=str)


def _safe(fn):
    @functools.wraps(fn)
    def wrap(*a, **k):
        try:
            return _j(fn(*a, **k))
        except RefusedWrite as e:
            return _j({"ok": False, "refused": str(e)})
        except Exception as e:
            return _j({"ok": False, "error": f"{type(e).__name__}: {e}"})
    # Keep the real parameter list so Claude sees proper argument names, but advertise a text result.
    wrap.__signature__ = inspect.signature(fn).replace(return_annotation=str)
    wrap.__annotations__ = {**fn.__annotations__, "return": str}
    return wrap


def tool(fn):
    return mcp.tool()(_safe(fn))


@tool
def tally_doctor() -> dict:
    """Check the connection to TallyPrime and say what to fix. Run this first, every session."""
    return {"version": __version__, **T().doctor()}


@tool
def list_companies() -> list:
    """Companies currently open in TallyPrime."""
    return T().companies()


@tool
def set_company(name: str, gstin: str = "", state: str = "") -> dict:
    """Choose the company entries go to. Optionally set the company GSTIN and state, which drive GST."""
    T().cfg["company"] = name
    if gstin:
        T().cfg["company_gstin"] = gstin
    if state:
        T().cfg["company_state"] = state
    cfgmod.save(T().cfg)
    T()._ledgers = T()._items = None
    return {"company": name, "gstin": T().cfg["company_gstin"], "state": T().cfg["company_state"]}


@tool
def discover_setup() -> dict:
    """Scan the open company and propose the GST, sales, purchase, round off and bank ledger names. Use once per company."""
    return T().discover_setup()


@tool
def update_settings(changes: dict) -> dict:
    """Change settings after the user agreed, for example {"default_godown": "Main Location"} or
    {"ledgers": {"igst_out": "IGST OUTPUT 18%"}}. Use this when a screenshot or error shows a name differs."""
    return T().update_settings(changes)


@tool
def find_ledger(name: str, gstin: str = "") -> dict:
    """Find the Tally ledger for a party name (GSTIN match first). Returns auto, ambiguous or none."""
    return T().find_ledger(name, gstin)


@tool
def find_stock_item(name: str) -> dict:
    """Find the Tally stock item for an item description."""
    return T().find_item(name)


@tool
def ledger_balance(ledger: str) -> dict:
    """Closing balance of a ledger. Tally convention: debit is negative, credit is positive."""
    return {"ledger": ledger, "balance": T().balance(ledger)}


@tool
def day_book(date: str) -> list:
    """Vouchers on one day (yyyy-mm-dd). The Day Book can lag, so it is not used to prove a posting."""
    return T().day_vouchers(date)


@tool
def plan_import(path: str, voucher_type: str = "Sales", sheet: str = "", default_bank: str = "") -> dict:
    """Read an Excel/CSV of invoices, bills, credit/debit notes (or Receipt/Payment rows), match parties and items, and sort every document into READY, HELD, DUPLICATE or ERROR.
    Writes nothing. Show the returned table to the user and ask the held questions before posting."""
    p = pipeline.make_plan(T(), path, voucher_type, sheet or None, default_bank)
    _plans[p.id] = p
    return {**p.summary(), "table": p.table()}


@tool
def post_plan(plan_id: str, only: list[str] | None = None) -> dict:
    """Post the READY rows of a plan, one at a time, each preview then confirm then balance check.
    Call this only after the user has seen the table and said go. Stops at the first failure."""
    p = _plans.get(plan_id)
    if not p:
        return {"ok": False, "error": "Unknown plan. Run plan_import again."}
    return {"results": pipeline.post_plan(T(), p, only)}


@tool
def preview_invoice(voucher_type: str, date: str, number: str, party_ledger: str, items: list, tax: list,
                    total: float, party_gstin: str = "", party_state: str = "", place_of_supply: str = "",
                    round_off: float = 0.0, narration: str = "", against_ref: str = "",
                    bill_to: list | None = None, ship_to: list | None = None) -> dict:
    """Preview one Sales/Purchase/Credit Note/Debit Note. items: [{stock_item, qty, rate, amount, ledger, unit}],
    tax: [[ledger, amount]]. All numbers positive. total is the invoice total after tax (never balance due)."""
    cfg = T().cfg
    inv = V.Invoice(voucher_type, date, number, party_ledger, [V.Item(**i) for i in items],
                    [tuple(x) for x in tax], total,
                    V.Gst(party_gstin, party_state, place_of_supply, bill_to=bill_to or [], ship_to=ship_to or [],
                          company_gstin=cfg["company_gstin"], company_state=cfg["company_state"]),
                    round_off, narration, against_ref)
    return T().preview_invoice(inv)


@tool
def preview_payment_or_receipt(voucher_type: str, date: str, party_ledger: str, bank_or_cash_ledger: str,
                               amount: float, narration: str = "", number: str = "",
                               settles_invoices: list | None = None) -> dict:
    """Preview a Receipt (money in from a customer) or Payment (money out to a vendor). amount is positive.
    settles_invoices: [[invoice_no, amount]] to tie it to bills, otherwise it is booked On Account."""
    if voucher_type == "Receipt":
        entries = [(bank_or_cash_ledger, -amount), (party_ledger, amount)]
    else:
        entries = [(party_ledger, -amount), (bank_or_cash_ledger, amount)]
    return T().preview_accounting(V.Accounting(voucher_type, date, number, entries, party_ledger, narration,
                                               [tuple(x) for x in (settles_invoices or [])]))


@tool
def preview_ledger(name: str, parent: str = "Sundry Debtors", gstin: str = "", state: str = "",
                   pincode: str = "", address: list | None = None, mobile: str = "") -> dict:
    """Preview a NEW party ledger. Only after the user has explicitly approved creating it."""
    return T().preview_ledger(name, parent, gstin=gstin, state=state, pincode=pincode, address=address, mobile=mobile)


@tool
def confirm_import(preview_id: str) -> dict:
    """Write a previewed entry to Tally, then prove it by checking the party balance moved by the right amount.
    Single use. Call only after the user said yes to this preview."""
    return T().confirm(preview_id)


@tool
def remember_mapping(kind: str, source_name: str, tally_name: str) -> dict:
    """Save an approved name mapping so the same name is matched automatically next time. kind: party or item."""
    T().remember(kind, source_name, tally_name)
    return {"saved": True, "kind": kind, source_name: tally_name}


@tool
def get_rules() -> dict:
    """The standing safety rules and current settings."""
    return {"settings": {k: v for k, v in T().cfg.items() if k != "ledgers"}, "ledger_names": T().cfg["ledgers"],
            "rules": RULES}


RULES = [
    "Tally is the master. Documents are entered into Tally, ledgers and items already exist there.",
    "Never write without showing the preview and getting an explicit yes.",
    "Never create a ledger or stock item without explicit approval. Look for an existing match first (GSTIN, address, similar name).",
    "Check for an existing entry before creating one. Duplicates are never fixed by reversals, they are listed for the user to delete in Tally.",
    "Use Total Amount After Tax, never Balance Due.",
    "Place of supply is the ship to state.",
    "After every confirm, prove it with the party balance delta. The Day Book can lag.",
    "Do not touch entries before the freeze date.",
    "Keep invoice number series complete and report gaps.",
    "Never test post in live books."]


def main():
    mcp.run()


if __name__ == "__main__":
    main()
