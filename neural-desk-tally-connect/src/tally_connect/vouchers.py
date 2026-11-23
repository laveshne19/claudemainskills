"""Voucher models and the XML shapes proven against a real TallyPrime installation.

Sign convention (Tally data convention): debit is negative, credit is positive.

  Voucher        items / tax   party
  Sales          +  credit     -  debit
  Purchase       -  debit      +  credit
  Credit Note    -  debit      +  credit   (sales return)
  Debit Note     +  credit     -  debit    (purchase return)

Callers give natural positive numbers. Signs are applied here so nobody has to think about them.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from .xmlkit import esc, tdate

SIGN = {"Sales": 1, "Debit Note": 1, "Purchase": -1, "Credit Note": -1}   # sign of items and tax
INVOICE_TYPES = tuple(SIGN)
ACCOUNTING_TYPES = ("Receipt", "Payment", "Contra", "Journal")
PARTY_SIDE = {"Sales": "Dr", "Debit Note": "Dr", "Purchase": "Cr", "Credit Note": "Cr"}


@dataclass
class Item:
    stock_item: str
    qty: float
    rate: float
    amount: float                    # taxable amount of the line, positive
    unit: str = "PCS"
    ledger: str = ""                 # sales / purchase ledger for this line
    gst_rate: float | None = None
    hsn: str = ""
    godown: str = ""
    batch: str = ""


@dataclass
class Gst:
    party_gstin: str = ""
    party_state: str = ""
    place_of_supply: str = ""        # the SHIP TO state, not blindly the bill to state
    registration_type: str = ""      # Regular / Unregistered / Composition ...
    bill_to: list = field(default_factory=list)     # address lines, each <= 60 chars
    ship_to: list = field(default_factory=list)
    company_gstin: str = ""
    company_state: str = ""
    company_gst_type: str = "Regular"


@dataclass
class Invoice:
    voucher_type: str                # Sales | Purchase | Credit Note | Debit Note
    date: str                        # ISO yyyy-mm-dd
    number: str
    party_ledger: str
    items: list
    tax: list                        # [(ledger_name, positive_amount)]
    total: float                     # "Total Amount After Tax", never "Balance Due"
    gst: Gst = field(default_factory=Gst)
    round_off: float = 0.0           # signed in natural terms: +ve adds to the invoice total
    narration: str = ""
    against_ref: str = ""            # for credit / debit notes: the original invoice number
    reference: str = ""


@dataclass
class Accounting:
    voucher_type: str                # Receipt | Payment | Contra | Journal
    date: str
    number: str
    entries: list                    # [(ledger, signed_amount)] debit negative, sum must be zero
    party_ledger: str = ""
    narration: str = ""
    bill_refs: list = field(default_factory=list)   # [(invoice_ref, amount)] to settle bills


def _amt(x: float) -> str:
    return f"{x:.2f}"


def _deemed(amount: float) -> str:
    return "Yes" if amount < 0 else "No"


def validate_invoice(inv: Invoice) -> list[str]:
    """Return a list of problems. Empty list means the voucher is arithmetically sound."""
    errs = []
    if inv.voucher_type not in INVOICE_TYPES:
        errs.append(f"Unknown voucher type {inv.voucher_type!r}")
    try:
        date.fromisoformat(inv.date)
    except ValueError:
        errs.append(f"Date {inv.date!r} is not in yyyy-mm-dd form")
    if not inv.number:
        errs.append("Invoice number is missing")
    if not inv.party_ledger:
        errs.append("Party ledger is missing")
    if not inv.items:
        errs.append("No line items")
    for i, it in enumerate(inv.items, 1):
        if not it.stock_item:
            errs.append(f"Line {i}: item name is missing")
        if not it.ledger:
            errs.append(f"Line {i}: sales/purchase ledger is missing")
        if it.qty <= 0:
            errs.append(f"Line {i}: quantity must be above zero")
    taxable = sum(i.amount for i in inv.items)
    tax = sum(a for _, a in inv.tax)
    calc = round(taxable + tax + inv.round_off, 2)
    if abs(calc - inv.total) > 0.011:
        errs.append(f"Items {taxable:.2f} + tax {tax:.2f} + round off {inv.round_off:.2f} = {calc:.2f}, "
                    f"but the invoice total is {inv.total:.2f}")
    if abs(inv.round_off) > 1.0:
        errs.append(f"Round off {inv.round_off:.2f} is larger than 1 rupee, check the source")
    return errs


def _addr(tag: str, lines: list) -> str:
    if not lines:
        return ""
    body = "".join(f"<{tag}>{esc(l[:60])}</{tag}>" for l in lines if l)
    return f"<{tag}.LIST>{body}</{tag}.LIST>"


def invoice_xml(inv: Invoice, cfg: dict) -> str:
    """Item wise Invoice view voucher (Sales, Purchase, Credit Note, Debit Note)."""
    s = SIGN[inv.voucher_type]
    g = inv.gst
    pos = g.place_of_supply or g.party_state
    cname = cfg.get("class_name", "DefaultVoucherClass")
    party_amt = -s * inv.total                       # opposite sign to the items
    ref_type = "Agst Ref" if inv.against_ref else "New Ref"
    ref_name = inv.against_ref or inv.number

    inv_entries = []
    for it in inv.items:
        amt = s * it.amount
        godown = it.godown or cfg.get("default_godown", "Main Location")
        batch = it.batch or cfg.get("default_batch", "Primary Batch")
        qty = f"{it.qty:g} {it.unit}"
        inv_entries.append(
            "<ALLINVENTORYENTRIES.LIST>"
            f"<STOCKITEMNAME>{esc(it.stock_item)}</STOCKITEMNAME>"
            f"<ISDEEMEDPOSITIVE>{_deemed(amt)}</ISDEEMEDPOSITIVE>"
            f"<RATE>{it.rate:.2f}/{esc(it.unit)}</RATE><AMOUNT>{_amt(amt)}</AMOUNT>"
            f"<ACTUALQTY> {esc(qty)}</ACTUALQTY><BILLEDQTY> {esc(qty)}</BILLEDQTY>"
            "<BATCHALLOCATIONS.LIST>"
            f"<GODOWNNAME>{esc(godown)}</GODOWNNAME><BATCHNAME>{esc(batch)}</BATCHNAME>"
            f"<DESTINATIONGODOWNNAME>{esc(godown)}</DESTINATIONGODOWNNAME>"
            f"<AMOUNT>{_amt(amt)}</AMOUNT><ACTUALQTY> {esc(qty)}</ACTUALQTY><BILLEDQTY> {esc(qty)}</BILLEDQTY>"
            "</BATCHALLOCATIONS.LIST>"
            "<ACCOUNTINGALLOCATIONS.LIST>"
            f"<LEDGERNAME>{esc(it.ledger)}</LEDGERNAME><ISDEEMEDPOSITIVE>{_deemed(amt)}</ISDEEMEDPOSITIVE>"
            f"<AMOUNT>{_amt(amt)}</AMOUNT></ACCOUNTINGALLOCATIONS.LIST>"
            + (f"<HSNCODE>{esc(it.hsn)}</HSNCODE>" if it.hsn else "")
            + "</ALLINVENTORYENTRIES.LIST>")

    led = [
        "<LEDGERENTRIES.LIST>"                          # party first, like real vouchers
        f"<LEDGERNAME>{esc(inv.party_ledger)}</LEDGERNAME><ISDEEMEDPOSITIVE>{_deemed(party_amt)}</ISDEEMEDPOSITIVE>"
        f"<ISPARTYLEDGER>Yes</ISPARTYLEDGER><AMOUNT>{_amt(party_amt)}</AMOUNT>"
        # Carry a bill allocation with the real invoice number. Without it some installations file the
        # voucher as "On Account" dated the day it was posted and Tally's own ageing breaks.
        # Switch off with send_bill_allocations=false if a company behaves differently (confirm on the first test).
        + ((f"<BILLALLOCATIONS.LIST><NAME>{esc(ref_name)}</NAME><BILLTYPE>{ref_type}</BILLTYPE>"
            f"<AMOUNT>{_amt(party_amt)}</AMOUNT></BILLALLOCATIONS.LIST>") if cfg.get("send_bill_allocations", True) else "")
        + "</LEDGERENTRIES.LIST>"
    ]
    for ledger, a in inv.tax:
        amt = s * a
        led.append(f"<LEDGERENTRIES.LIST><LEDGERNAME>{esc(ledger)}</LEDGERNAME>"
                   f"<ISDEEMEDPOSITIVE>{_deemed(amt)}</ISDEEMEDPOSITIVE><AMOUNT>{_amt(amt)}</AMOUNT></LEDGERENTRIES.LIST>")
    if abs(inv.round_off) >= 0.005:
        amt = s * inv.round_off
        led.append(f"<LEDGERENTRIES.LIST><LEDGERNAME>{esc(cfg['ledgers']['round_off'])}</LEDGERNAME>"
                   f"<ISDEEMEDPOSITIVE>{_deemed(amt)}</ISDEEMEDPOSITIVE><AMOUNT>{_amt(amt)}</AMOUNT></LEDGERENTRIES.LIST>")

    country = cfg.get("country", "India")
    return (
        f'<VOUCHER VCHTYPE="{esc(inv.voucher_type)}" ACTION="Create" OBJVIEW="Invoice Voucher View">'
        f"<DATE>{tdate(inv.date)}</DATE><VOUCHERTYPENAME>{esc(inv.voucher_type)}</VOUCHERTYPENAME>"
        f"<VOUCHERNUMBER>{esc(inv.number)}</VOUCHERNUMBER>"
        + (f"<REFERENCE>{esc(inv.reference)}</REFERENCE>" if inv.reference else "")
        + f"<PARTYLEDGERNAME>{esc(inv.party_ledger)}</PARTYLEDGERNAME><PARTYNAME>{esc(inv.party_ledger)}</PARTYNAME>"
        f"<BASICBUYERNAME>{esc(inv.party_ledger)}</BASICBUYERNAME><PARTYMAILINGNAME>{esc(inv.party_ledger)}</PARTYMAILINGNAME>"
        "<PERSISTEDVIEW>Invoice Voucher View</PERSISTEDVIEW><ISINVOICE>Yes</ISINVOICE>"
        f"<CLASSNAME>{esc(cname)}</CLASSNAME><NUMBERINGSTYLE>Manual</NUMBERINGSTYLE>"
        f"<STATENAME>{esc(g.party_state)}</STATENAME><COUNTRYOFRESIDENCE>{esc(country)}</COUNTRYOFRESIDENCE>"
        f"<PLACEOFSUPPLY>{esc(pos)}</PLACEOFSUPPLY>"
        f"<GSTREGISTRATIONTYPE>{esc(g.registration_type or ('Regular' if g.party_gstin else 'Unregistered'))}</GSTREGISTRATIONTYPE>"
        f"<PARTYGSTIN>{esc(g.party_gstin)}</PARTYGSTIN><CMPGSTIN>{esc(g.company_gstin or cfg.get('company_gstin',''))}</CMPGSTIN>"
        f"<CMPGSTREGISTRATIONTYPE>{esc(g.company_gst_type or cfg.get('company_gst_type','Regular'))}</CMPGSTREGISTRATIONTYPE>"
        f"<CMPGSTSTATE>{esc(g.company_state or cfg.get('company_state',''))}</CMPGSTSTATE>"
        f"<DISPATCHFROMSTATENAME>{esc(g.company_state or cfg.get('company_state',''))}</DISPATCHFROMSTATENAME>"
        f"<BILLTOPLACE>{esc(g.party_state)}</BILLTOPLACE><SHIPTOPLACE>{esc(pos)}</SHIPTOPLACE>"
        f"<NARRATION>{esc(inv.narration)}</NARRATION>"
        + _addr("BASICBUYERADDRESS", g.bill_to) + _addr("BASICSHIPPINGADDRESS", g.ship_to or g.bill_to)
        + "".join(led) + "".join(inv_entries) + "</VOUCHER>"
    )


def validate_accounting(v: Accounting) -> list[str]:
    errs = []
    if v.voucher_type not in ACCOUNTING_TYPES:
        errs.append(f"Unknown voucher type {v.voucher_type!r}")
    try:
        date.fromisoformat(v.date)
    except ValueError:
        errs.append(f"Date {v.date!r} is not in yyyy-mm-dd form")
    if len(v.entries) < 2:
        errs.append("A voucher needs at least two ledger entries")
    if abs(sum(a for _, a in v.entries)) > 0.005:
        errs.append(f"Entries do not balance, they add up to {sum(a for _, a in v.entries):.2f}")
    if any(not l for l, _ in v.entries):
        errs.append("A ledger name is empty")
    return errs


def accounting_xml(v: Accounting, cfg: dict) -> str:
    """Receipt, Payment, Contra, Journal. These use ALLLEDGERENTRIES.LIST, the opposite of invoices."""
    ents = []
    for ledger, amt in v.entries:
        bills = ""
        if v.party_ledger and ledger == v.party_ledger:
            if v.bill_refs:
                bills = "".join(
                    f"<BILLALLOCATIONS.LIST><NAME>{esc(r)}</NAME><BILLTYPE>Agst Ref</BILLTYPE>"
                    f"<AMOUNT>{_amt(abs(a) if amt > 0 else -abs(a))}</AMOUNT></BILLALLOCATIONS.LIST>"
                    for r, a in v.bill_refs)
            else:
                bills = (f"<BILLALLOCATIONS.LIST><NAME>On Account</NAME><BILLTYPE>On Account</BILLTYPE>"
                         f"<AMOUNT>{_amt(amt)}</AMOUNT></BILLALLOCATIONS.LIST>")
        ents.append(
            f"<ALLLEDGERENTRIES.LIST><LEDGERNAME>{esc(ledger)}</LEDGERNAME>"
            f"<ISDEEMEDPOSITIVE>{_deemed(amt)}</ISDEEMEDPOSITIVE>"
            + (f"<ISPARTYLEDGER>Yes</ISPARTYLEDGER>" if ledger == v.party_ledger else "")
            + f"<AMOUNT>{_amt(amt)}</AMOUNT>{bills}</ALLLEDGERENTRIES.LIST>")
    return (
        f'<VOUCHER VCHTYPE="{esc(v.voucher_type)}" ACTION="Create" OBJVIEW="Accounting Voucher View">'
        f"<DATE>{tdate(v.date)}</DATE><VOUCHERTYPENAME>{esc(v.voucher_type)}</VOUCHERTYPENAME>"
        + (f"<VOUCHERNUMBER>{esc(v.number)}</VOUCHERNUMBER>" if v.number else "")
        + (f"<PARTYLEDGERNAME>{esc(v.party_ledger)}</PARTYLEDGERNAME>" if v.party_ledger else "")
        + f"<ISINVOICE>No</ISINVOICE><NARRATION>{esc(v.narration)}</NARRATION>" + "".join(ents) + "</VOUCHER>"
    )


def ledger_xml(name: str, parent: str, cfg: dict, *, gstin="", state="", pincode="",
               address=None, registration_type="", mobile="") -> str:
    """Create a party ledger. Never sends an opening balance: bulk alters that did so corrupted balances."""
    addr = "".join(f"<ADDRESS>{esc(l[:60])}</ADDRESS>" for l in (address or [])[:4] if l)
    return (
        f'<LEDGER NAME="{esc(name)}" ACTION="Create"><NAME>{esc(name)}</NAME><PARENT>{esc(parent)}</PARENT>'
        f"<COUNTRYOFRESIDENCE>{esc(cfg.get('country','India'))}</COUNTRYOFRESIDENCE>"
        + (f"<LEDSTATENAME>{esc(state)}</LEDSTATENAME>" if state else "")
        + (f"<PINCODE>{esc(pincode)}</PINCODE>" if pincode else "")
        + (f"<PARTYGSTIN>{esc(gstin)}</PARTYGSTIN>" if gstin else "")
        + f"<GSTREGISTRATIONTYPE>{esc(registration_type or ('Regular' if gstin else 'Unregistered'))}</GSTREGISTRATIONTYPE>"
        + (f"<LEDGERMOBILE>{esc(mobile)}</LEDGERMOBILE>" if mobile else "")
        + (f"<ADDRESS.LIST>{addr}</ADDRESS.LIST>" if addr else "")
        + "<ISBILLWISEON>Yes</ISBILLWISEON></LEDGER>"
    )
