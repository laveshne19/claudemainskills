"""A pretend Tally gateway that serves fictional ledgers in the report shapes the agent expects.
It is NOT TallyPrime. It lets the agent be tested end to end; the real report shapes are confirmed on the first run."""
import datetime as dt
import re
import threading
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, HTTPServer
from xml.sax.saxutils import escape

FY_START = "2026-04-01"
GROUPS = [("Sundry Debtors", "Current Assets"), ("Sundry Creditors", "Current Liabilities"), ("DEBTORS OF NORTH ZONE", "Sundry Debtors"), ("Bank Accounts", "Current Assets")]


def tally_amount(side, amount):
    return f"{(-1 if side == 'Dr' else 1) * amount:.2f}"


def ddmmmyyyy(iso):
    d = dt.date.fromisoformat(iso)
    return d.strftime("%d-%b-%Y")


class FakeTally:
    def __init__(self, ledgers, company="FAKE TRADERS PVT LTD", extra_company=None):
        self.ledgers = {l["name"]: l for l in ledgers}
        self.company = company
        self.extra_company = extra_company
        self.calls = []
        self.drop_voucher = None            # (ledger name) one voucher removed, to test the tie out warning
        self.srv = HTTPServer(("127.0.0.1", 0), self._handler())
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def stop(self):
        self.srv.shutdown(); self.srv.server_close()

    def _opening(self, l):
        # Tally's opening balance is the balance at the start of the financial year
        bal = sum(v["debit"] - v["credit"] for v in l["vouchers"] if v["date"] < FY_START)
        return ("Dr" if bal >= 0 else "Cr", abs(bal))

    def _vouchers(self, l, d_from, d_to):
        rows = [v for v in l["vouchers"] if d_from <= v["date"] <= d_to]
        if self.drop_voucher == l["name"] and rows:
            rows = rows[1:]
        return rows

    def _handler(self):
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass

            def do_GET(self):
                self._send("<RESPONSE>TallyPrime Server is Running</RESPONSE>")

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode("utf-8")
                outer.calls.append(body[:400])
                self._send(outer.handle(body))

            def _send(self, text):
                b = text.encode("utf-8")
                self.send_response(200); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
        return H

    def handle(self, body):
        root = ET.fromstring(re.sub(r"<\?xml[^>]*\?>", "", body).strip())
        ident = (root.findtext("./HEADER/ID") or "").strip()
        sv = lambda n: (root.findtext(f".//{n}") or "")
        if ident == "List of Companies":
            names = [self.company] + ([self.extra_company] if self.extra_company else [])
            return "<ENVELOPE><BODY><DATA><COLLECTION>" + "".join(f'<COMPANY NAME="{escape(n)}"><NAME>{escape(n)}</NAME></COMPANY>' for n in names) + "</COLLECTION></DATA></BODY></ENVELOPE>"
        if ident == "NAGroups":
            return "<ENVELOPE><BODY><DATA><COLLECTION>" + "".join(f'<GROUP NAME="{escape(n)}"><PARENT>{escape(p)}</PARENT></GROUP>' for n, p in GROUPS) + "</COLLECTION></DATA></BODY></ENVELOPE>"
        if ident == "NALedgers":
            out = ""
            for l in self.ledgers.values():
                os_, oa = self._opening(l)
                out += (f'<LEDGER NAME="{escape(l["name"], {chr(34): "&quot;"})}"><PARENT TYPE="String">{escape(l["group"])}</PARENT>'
                        f'<CLOSINGBALANCE TYPE="Amount">{tally_amount(l["closing"]["side"], l["closing"]["amount"])}</CLOSINGBALANCE>'
                        f'<OPENINGBALANCE TYPE="Amount">{tally_amount(os_, oa)}</OPENINGBALANCE><PARTYGSTIN>{l.get("gstin","")}</PARTYGSTIN>'
                        f'<LEDSTATENAME>{escape(l.get("state",""))}</LEDSTATENAME><LEDGERMOBILE>{l.get("phone","")}</LEDGERMOBILE>'
                        f'<ADDRESS.LIST><ADDRESS>Shop 1, Main Market</ADDRESS><ADDRESS>{escape(l.get("city",""))}</ADDRESS></ADDRESS.LIST><PINCODE>160022</PINCODE></LEDGER>')
            return f"<ENVELOPE><BODY><DATA><COLLECTION>{out}</COLLECTION></DATA></BODY></ENVELOPE>"
        name = sv("LEDGERNAME")
        l = self.ledgers.get(name)
        if ident == "Ledger Vouchers" and l:
            d1 = dt.datetime.strptime(sv("SVFROMDATE"), "%Y%m%d").date().isoformat()
            d2 = dt.datetime.strptime(sv("SVTODATE"), "%Y%m%d").date().isoformat()
            out = ""
            for v in self._vouchers(l, d1, d2):
                out += (f"<DSPVCHDATE>{ddmmmyyyy(v['date'])}</DSPVCHDATE><DSPVCHLEDACCOUNT>{escape(v['particulars'])}</DSPVCHLEDACCOUNT>"
                        f"<DSPVCHTYPE>{escape(v['type'])}</DSPVCHTYPE><DSPVCHNUMBER>{escape(v['number'])}</DSPVCHNUMBER>"
                        f"<DSPVCHDRAMT>{v['debit']:.2f}</DSPVCHDRAMT><DSPVCHCRAMT>{v['credit']:.2f}</DSPVCHCRAMT>")
            return f"<ENVELOPE><BODY><DATA>{out}</DATA></BODY></ENVELOPE>"
        if ident == "Ledger Outstandings" and l:
            out = ""
            for b in l.get("bills", []):
                out += (f"<BILLFIXED><BILLDATE>{ddmmmyyyy(b['date'])}</BILLDATE><BILLREF>{escape(b['ref'])}</BILLREF><BILLPARTY>{escape(name)}</BILLPARTY></BILLFIXED>"
                        f"<BILLCL>{tally_amount('Dr' if l['kind'] == 'debtor' else 'Cr', b['pending'])}</BILLCL><BILLDUE>{ddmmmyyyy(b['date'])}</BILLDUE><BILLOVERDUE>10</BILLOVERDUE>")
            return f"<ENVELOPE><BODY><DATA>{out}</DATA></BODY></ENVELOPE>"
        return "<ENVELOPE></ENVELOPE>"
