"""A small imitation of TallyPrime's XML gateway.

Purpose: automated tests, and a try-it-without-Tally demo (`tally-connect demo`).
It reproduces the behaviours that matter, including the nasty ones:
  * an invoice with stock items but no godown batch allocation fails with EXCEPTIONS:1 and no detail
  * missing GST identity fields fail the same silent way
  * unknown ledger or stock item names fail the same silent way
  * entries that do not add up to zero fail
  * the Day Book can lag behind real postings (lag=True)
  * connections can drop (drop_next)
It is NOT TallyPrime. Real Tally must be checked with `tally-connect doctor` and a first test entry.
"""
from __future__ import annotations

import re
import threading
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, HTTPServer
from xml.sax.saxutils import escape

DEMO_COMPANY = "Demo Traders Pvt Ltd"
REQUIRED_GST_TAGS = ("STATENAME", "PLACEOFSUPPLY", "GSTREGISTRATIONTYPE", "PARTYGSTIN", "CMPGSTIN",
                     "CMPGSTSTATE", "CLASSNAME")


def seed() -> dict:
    L = lambda n, p, g="", s="", b=0.0: {"name": n, "parent": p, "gstin": g, "state": s, "balance": b}
    return {
        "companies": [DEMO_COMPANY],
        "ledgers": {l["name"]: l for l in [
            L("SHARMA TELECOM", "Sundry Debtors", "04AAAAA1111A1Z5", "Chandigarh", -12000.0),
            L("KAUR MOBILE SHOP", "Sundry Debtors", "03AAAAA3333A1Z5", "Punjab", -4611.0),
            L("BRIGHT & CLEAR ADVERTISING PVT LTD", "Sundry Debtors", "06AAAAA2222B1Z9", "Haryana", 0.0),
            L("Rana Enterprises", "Sundry Debtors", "03BBBBB3333C1Z1", "Punjab", -25850.0),
            L("ONLINE MARKETPLACE SALE", "Sundry Debtors", "", "Karnataka", 0.0),
            L("NORTHERN ELECTRONICS", "Sundry Creditors", "04CCCCC4444D1Z2", "Chandigarh", 18500.0),
            L("Prime Distribution Limited", "Sundry Creditors", "27AAAAA2222A1Z5", "Maharashtra", 3340000.0),
            L("HDFC BANK", "Bank Accounts", "", "", 500000.0),
            L("CASH", "Cash-in-Hand", "", "", 20000.0),
            L("SALES LOCAL@ 18%", "Sales Accounts"), L("SALES IGST@18%", "Sales Accounts"),
            L("PURCHASE LOCAL@18%", "Purchase Accounts"), L("PURCHASE IGST@18%", "Purchase Accounts"),
            L("CGST OUTPUT", "Duties & Taxes"), L("SGST OUTPUT", "Duties & Taxes"),
            L("UTGST OUTPUT", "Duties & Taxes"), L("IGST OUTPUT", "Duties & Taxes"),
            L("CGST INPUT", "Duties & Taxes"), L("UTGST INPUT", "Duties & Taxes"),
            L("IGST INPUT", "Duties & Taxes"), L("ROUND OFF", "Indirect Expenses"),
        ]},
        "items": {n: {"name": n, "parent": "Primary", "unit": "PCS"} for n in [
            "ACME AIRBUDS ACE BLACK", "ACME AIRBUDS PROCLIP VELVET WINE", "ACME ROCKER SUMMIT BLACK",
            "POWERBANK 20000 MAH WITH CABLE", "Pb331", "CAR FM TRANSMITTER MP3"]},
        "vouchers": [],
    }


class MockTally:
    def __init__(self, port=0, lag=False):
        self.db = seed()
        self.lag = lag
        self.drop_next = 0
        self.drop_reply_next = 0       # process the request, then drop the reply (a "cosmetic" timeout)
        self.calls = 0
        self._srv = HTTPServer(("127.0.0.1", port), self._handler())
        self.port = self._srv.server_address[1]
        self._t = threading.Thread(target=self._srv.serve_forever, daemon=True)

    def start(self):
        self._t.start()
        return self

    def stop(self):
        self._srv.shutdown()
        self._srv.server_close()

    # ------------------------------------------------------------------
    def _handler(self):
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                self._send("<RESPONSE>TallyPrime Server is Running</RESPONSE>")

            def do_POST(self):
                outer.calls += 1
                body = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode("utf-8")
                if outer.drop_next > 0:
                    outer.drop_next -= 1
                    self.close_connection = True
                    self.connection.close()
                    return
                reply = outer.handle(body)
                if outer.drop_reply_next > 0 and "Import Data" in body:
                    outer.drop_reply_next -= 1
                    self.close_connection = True
                    self.connection.close()
                    return
                self._send(reply)

            def _send(self, text):
                b = text.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/xml")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)
        return H

    # ------------------------------------------------------------------
    def handle(self, body: str) -> str:
        try:
            root = ET.fromstring(re.sub(r"<\?xml[^>]*\?>", "", body).strip())
        except ET.ParseError:
            return "<RESPONSE><LINEERROR>Bad XML</LINEERROR></RESPONSE>"
        treq = (root.findtext("./HEADER/TALLYREQUEST") or "").strip()
        if treq == "Import Data":
            return self._import(root)
        ident = (root.findtext("./HEADER/ID") or "").strip()
        if ident == "List of Companies":
            items = "".join(f'<COMPANY NAME="{escape(c)}"><NAME>{escape(c)}</NAME></COMPANY>' for c in self.db["companies"])
            return f"<ENVELOPE><BODY><DATA><COLLECTION>{items}</COLLECTION></DATA></BODY></ENVELOPE>"
        if ident == "Day Book":
            return self._daybook(root)
        if ident in ("NDLedgers", "NDBal"):
            flt = root.findtext(".//SYSTEM") or ""
            m = re.search(r'\$Name\s*=\s*"(.*)"', flt)
            out = ""
            for l in self.db["ledgers"].values():
                if m and l["name"] != m.group(1):
                    continue
                out += (f'<LEDGER NAME="{escape(l["name"], {chr(34): "&quot;"})}"><PARENT TYPE="String">{escape(l["parent"])}</PARENT>'
                        f'<PARTYGSTIN TYPE="String">{l["gstin"]}</PARTYGSTIN><LEDSTATENAME TYPE="String">{escape(l["state"])}</LEDSTATENAME>'
                        f'<CLOSINGBALANCE TYPE="Amount">{l["balance"]:.2f}</CLOSINGBALANCE></LEDGER>')
            return f"<ENVELOPE><BODY><DATA><COLLECTION>{out}</COLLECTION></DATA></BODY></ENVELOPE>"
        if ident == "NDItems":
            out = "".join(f'<STOCKITEM NAME="{escape(i["name"])}"><PARENT>{i["parent"]}</PARENT><BASEUNITS>{i["unit"]}</BASEUNITS></STOCKITEM>'
                          for i in self.db["items"].values())
            return f"<ENVELOPE><BODY><DATA><COLLECTION>{out}</COLLECTION></DATA></BODY></ENVELOPE>"
        return "<ENVELOPE></ENVELOPE>"

    def _daybook(self, root) -> str:
        d = root.findtext(".//SVFROMDATE") or ""
        if not (root.findtext(".//SVTODATE") and root.findtext(".//SVCURRENTDATE")):
            d = ""     # real Tally ignores the range unless all three are present
        vs = [] if self.lag else [v for v in self.db["vouchers"] if v["date"] == d]
        out = "".join(f"<VOUCHER><DATE>{v['date']}</DATE><VOUCHERTYPENAME>{escape(v['type'])}</VOUCHERTYPENAME>"
                      f"<VOUCHERNUMBER>{escape(v['number'])}</VOUCHERNUMBER><PARTYLEDGERNAME>{escape(v['party'])}</PARTYLEDGERNAME></VOUCHER>"
                      for v in vs)
        return f"<ENVELOPE><BODY><IMPORTDATA><REQUESTDATA><TALLYMESSAGE>{out}</TALLYMESSAGE></REQUESTDATA></IMPORTDATA></BODY></ENVELOPE>"

    # ------------------------------------------------------------------
    @staticmethod
    def _reply(created=0, errors=0, exceptions=0) -> str:
        return (f"<RESPONSE><CREATED>{created}</CREATED><ALTERED>0</ALTERED><ERRORS>{errors}</ERRORS>"
                f"<EXCEPTIONS>{exceptions}</EXCEPTIONS></RESPONSE>")

    def _import(self, root) -> str:
        report = root.findtext(".//REPORTNAME") or ""
        created = exc = 0
        for led in root.iter("LEDGER"):
            if report != "All Masters":
                continue
            name = led.findtext("NAME") or led.attrib.get("NAME", "")
            if not name or name in self.db["ledgers"] or not led.findtext("COUNTRYOFRESIDENCE"):
                exc += 1
                continue
            self.db["ledgers"][name] = {"name": name, "parent": led.findtext("PARENT") or "", "gstin": led.findtext("PARTYGSTIN") or "",
                                        "state": led.findtext("LEDSTATENAME") or "", "balance": 0.0}
            created += 1
        for v in root.iter("VOUCHER"):
            ok = self._post_voucher(v)
            created += 1 if ok else 0
            exc += 0 if ok else 1
        return self._reply(created, 0, exc)

    def _post_voucher(self, v) -> bool:
        entries = v.findall("LEDGERENTRIES.LIST") + v.findall("ALLLEDGERENTRIES.LIST")
        inv = v.findall("ALLINVENTORYENTRIES.LIST")
        if inv:
            for t in REQUIRED_GST_TAGS:
                if v.find(t) is None:
                    return False
            for it in inv:
                if it.find("BATCHALLOCATIONS.LIST/GODOWNNAME") is None:
                    return False
                if (it.findtext("STOCKITEMNAME") or "") not in self.db["items"]:
                    return False
        total = 0.0
        for e in entries:
            if (e.findtext("LEDGERNAME") or "") not in self.db["ledgers"]:
                return False
            total += float(e.findtext("AMOUNT") or 0)
        for it in inv:
            for a in it.findall("ACCOUNTINGALLOCATIONS.LIST"):
                if (a.findtext("LEDGERNAME") or "") not in self.db["ledgers"]:
                    return False
                total += float(a.findtext("AMOUNT") or 0)
        if abs(total) > 0.005 or not entries:
            return False
        for e in entries:
            self.db["ledgers"][e.findtext("LEDGERNAME")]["balance"] = round(
                self.db["ledgers"][e.findtext("LEDGERNAME")]["balance"] + float(e.findtext("AMOUNT") or 0), 2)
        self.db["vouchers"].append({"date": v.findtext("DATE") or "", "type": v.findtext("VOUCHERTYPENAME") or "",
                                    "number": v.findtext("VOUCHERNUMBER") or "", "party": v.findtext("PARTYLEDGERNAME") or "",
                                    "has_bill_alloc": v.find(".//BILLALLOCATIONS.LIST") is not None})
        return True
