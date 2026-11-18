"""Nalanda Accounts sync agent. Runs on the PC that has TallyPrime.

Reads the party ledgers (customers and vendors), their unpaid bills and their statements from Tally,
checks that every statement adds up to Tally's own closing balance, and sends them to the portal over HTTPS.
It only ever reads from Tally. It never writes to Tally. The portal never connects into this PC.

Run:   python -m sync_agent --config agent.json
Check: python -m sync_agent --config agent.json --dry-run --limit 5 --debug-dump dump
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import re
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from tally_connect import xmlkit as X
from tally_connect.gateway import GatewayError, TallyGateway

log = logging.getLogger("sync_agent")
HOME = Path(os.environ.get("NALANDA_AGENT_HOME") or Path.home() / ".nalandaaccounts")

DEFAULTS = {
    "portal_url": "",
    "sync_key": "",                    # or set NALANDA_SYNC_KEY in the environment
    "tally_host": "localhost",
    "tally_port": 9000,
    "company": "",                     # exact company name in Tally, empty = the one that is open
    "company_title": "",               # name shown on the portal and on PDFs, empty = the company name
    "kinds": ["debtor", "creditor"],
    "skip_zero_balance": True,         # only ledgers that owe or are owed
    "statement_from": "",              # yyyy-mm-dd, empty = start of the current financial year
    "batch_size": 20,
    "pause_seconds": 0.15,             # be gentle, Tally slows down under load
    "max_ledgers": 0,                  # 0 = no limit
    "debtor_groups": ["Sundry Debtors"],
    "creditor_groups": ["Sundry Creditors"],
}


class SyncError(Exception):
    def __init__(self, msg, code=1):
        super().__init__(msg)
        self.code = code


# ------------------------------------------------------------------ small parsers
def parse_date(text) -> str | None:
    t = (text or "").strip()
    for fmt in ("%Y%m%d", "%d-%b-%Y", "%d-%b-%y", "%d-%B-%Y", "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(t, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def money(text) -> dict:
    """Tally: debit is negative, credit is positive. Portal: an amount and a side."""
    v = X.num(text)
    return {"amount": round(abs(v), 2), "side": "Dr" if v < 0 else "Cr"}


def signed(m: dict) -> float:
    return (1 if m["side"] == "Dr" else -1) * m["amount"]


def fy_start(today: dt.date) -> str:
    y = today.year if today.month >= 4 else today.year - 1
    return f"{y}-04-01"


def guess_city(lines: list[str]) -> str:
    """The last address line is usually the city. Only trust it when it looks like a place name."""
    for line in reversed([l.strip() for l in lines if l and l.strip()]):
        return line if len(line) <= 30 and not any(c.isdigit() for c in line) else ""
    return ""


def _t(el):
    return (el.text or "").strip() if el is not None else ""


def parse_vouchers(xml: str) -> list[dict]:
    """Rows of a 'Ledger Vouchers' report. A new row starts at every voucher date."""
    root = X.parse(xml)
    rows, cur = [], None
    for el in root.iter():
        tag = el.tag.upper()
        if tag == "DSPVCHDATE":
            cur = {"date": parse_date(_t(el)), "type": "", "number": "", "particulars": "", "debit": 0.0, "credit": 0.0}
            rows.append(cur)
        elif cur is None:
            continue
        elif tag == "DSPVCHTYPE":
            cur["type"] = _t(el)
        elif tag in ("DSPVCHNUMBER", "VOUCHERNUMBER", "VCHNUMBER"):
            cur["number"] = _t(el)
        elif tag == "DSPVCHLEDACCOUNT":
            cur["particulars"] = _t(el)
        elif tag == "NARRATION" and not cur["particulars"]:
            cur["particulars"] = _t(el)
        elif tag == "DSPVCHDRAMT":
            cur["debit"] = round(abs(X.num(_t(el))), 2)
        elif tag == "DSPVCHCRAMT":
            cur["credit"] = round(abs(X.num(_t(el))), 2)
    return [r for r in rows if r["date"] and (r["debit"] or r["credit"])]


def parse_bills(xml: str) -> list[dict]:
    """Unpaid bills of a 'Ledger Outstandings' report: BILLFIXED (date, reference) then BILLCL (pending)."""
    root = X.parse(xml)
    bills, cur = [], None
    for el in root.iter():
        tag = el.tag.upper()
        if tag == "BILLFIXED":
            cur = {"date": parse_date(_t(el.find("BILLDATE"))), "ref": _t(el.find("BILLREF")), "pending": None}
            bills.append(cur)
        elif tag == "BILLCL" and cur is not None and cur["pending"] is None:
            cur["pending"] = round(abs(X.num(_t(el))), 2)
    return [b for b in bills if b["date"] and b["pending"]]


# ------------------------------------------------------------------ reading from Tally
class TallyReader:
    def __init__(self, cfg: dict, gw: TallyGateway | None = None):
        self.cfg = cfg
        self.gw = gw or TallyGateway(cfg["tally_host"], cfg["tally_port"], timeout=60, retries=4)
        self.company = cfg["company"] or None

    def check(self) -> str:
        if not self.gw.ping():
            raise SyncError("Tally did not answer. Is TallyPrime open with the company loaded, and set to Server mode on port "
                            f"{self.cfg['tally_port']}?", code=2)
        names = [r["NAME"] for r in X.rows(self.gw.post(X.company_list_request()), "COMPANY") if r.get("NAME")]
        if not names:
            raise SyncError("Tally is running but no company is open.", code=2)
        if self.company and self.company not in names:
            raise SyncError(f"The company '{self.company}' is not open in Tally. Open companies: {', '.join(names)}", code=2)
        if not self.company and len(names) > 1:
            raise SyncError("More than one company is open in Tally. Set \"company\" in the agent settings so the right one is read.", code=2)
        self.company = self.company or names[0]
        return self.company

    def groups(self) -> dict[str, str]:
        xml = self.gw.post(X.collection_request("NAGroups", "Group", "Name,Parent", self.company))
        return {r["NAME"]: r.get("PARENT", "") for r in X.rows(xml, "GROUP") if r.get("NAME")}

    def ledgers(self) -> list[dict]:
        xml = self.gw.post(X.collection_request(
            "NALedgers", "Ledger", "Name,Parent,ClosingBalance,OpeningBalance,PartyGSTIN,LedStateName,LedgerPhone,LedgerMobile,Address,Pincode", self.company))
        out = []
        for el in X.parse(xml).iter():
            if el.tag.upper() != "LEDGER" or not el.attrib.get("NAME"):
                continue
            kid = {c.tag.upper(): c for c in el}
            addr = [_t(a) for a in (kid["ADDRESS.LIST"].iter("ADDRESS") if "ADDRESS.LIST" in kid else [])]
            out.append({"name": el.attrib["NAME"], "parent": _t(kid.get("PARENT")), "closing": money(_t(kid.get("CLOSINGBALANCE"))),
                        "opening": money(_t(kid.get("OPENINGBALANCE"))), "gstin": _t(kid.get("PARTYGSTIN")), "state": _t(kid.get("LEDSTATENAME")),
                        "phone": _t(kid.get("LEDGERMOBILE")) or _t(kid.get("LEDGERPHONE")), "address": ", ".join(a for a in addr if a),
                        "pincode": _t(kid.get("PINCODE")), "city": guess_city(addr)})
        return out

    def _report(self, report_id: str, ledger: str, d_from: str, d_to: str) -> str:
        extra = (f"<LEDGERNAME>{X.esc(ledger)}</LEDGERNAME><SVFROMDATE>{X.tdate(d_from)}</SVFROMDATE>"
                 f"<SVTODATE>{X.tdate(d_to)}</SVTODATE><SVCURRENTDATE>{X.tdate(d_to)}</SVCURRENTDATE>")
        comp = f"<SVCURRENTCOMPANY>{X.esc(self.company)}</SVCURRENTCOMPANY>" if self.company else ""
        return self.gw.post(
            "<ENVELOPE><HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Data</TYPE>"
            f"<ID>{X.esc(report_id)}</ID></HEADER><BODY><DESC><STATICVARIABLES><SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>"
            f"{extra}{comp}</STATICVARIABLES></DESC></BODY></ENVELOPE>")

    def vouchers_xml(self, ledger, d_from, d_to):
        return self._report("Ledger Vouchers", ledger, d_from, d_to)

    def bills_xml(self, ledger, d_from, d_to):
        return self._report("Ledger Outstandings", ledger, d_from, d_to)


# ------------------------------------------------------------------ building the documents
def kind_of(parent: str, groups: dict[str, str], cfg: dict) -> str:
    deb = {g.lower() for g in cfg["debtor_groups"]}
    cre = {g.lower() for g in cfg["creditor_groups"]}
    seen, g = set(), parent
    while g and g not in seen:
        seen.add(g)
        if g.lower() in deb:
            return "debtor"
        if g.lower() in cre:
            return "creditor"
        g = groups.get(g, "")
    return "other"


def build_doc(led: dict, kind: str, vouchers: list[dict], bills: list[dict], d_from: str, d_to: str, fy: str | None = None) -> dict:
    net = round(sum(v["debit"] for v in vouchers) - sum(v["credit"] for v in vouchers), 2)
    opening = led["opening"]
    checked = fy is None or d_from == fy
    if not checked:
        # Tally's opening balance is for the start of the financial year. For any other start date work the
        # opening out from the closing balance. That cannot be cross checked, so no tie out warning is raised.
        bal = round(signed(led["closing"]) - net, 2)
        opening = {"amount": abs(bal), "side": "Dr" if bal >= 0 else "Cr"}
    doc = {"name": led["name"], "group": led["parent"], "kind": kind, "gstin": led["gstin"], "state": led["state"], "phone": led["phone"], "city": led.get("city", ""),
           "address": ", ".join(x for x in (led["address"], led["pincode"]) if x), "opening": opening, "closing": led["closing"],
           "vouchers": vouchers, "bills": bills, "periodFrom": d_from, "periodTo": d_to}
    # The check that matters: opening plus debits minus credits must equal Tally's own closing balance.
    calc = round(signed(opening) + net, 2)
    if checked and abs(calc - signed(led["closing"])) > 0.01:
        doc["warning"] = ("The entries listed do not add up to the Tally balance (difference "
                          f"{abs(calc - signed(led['closing'])):,.2f}). Treat the statement as incomplete and check in Tally.")
    return doc


def collect(reader: TallyReader, cfg: dict, only: str = "", limit: int = 0, dump: Path | None = None, today: dt.date | None = None):
    today = today or dt.date.today()
    d_from = cfg["statement_from"] or fy_start(today)
    d_to = today.isoformat()
    groups = reader.groups()
    rows = reader.ledgers()
    picked = []
    for led in rows:
        k = kind_of(led["parent"], groups, cfg)
        if k not in cfg["kinds"] or (only and only.lower() not in led["name"].lower()):
            continue
        if cfg["skip_zero_balance"] and led["closing"]["amount"] == 0:
            continue
        picked.append((led, k))
    cap = limit or cfg["max_ledgers"]
    if cap:
        picked = picked[:cap]
    log.info("%d ledgers read from Tally, %d to send", len(rows), len(picked))
    docs, warned = [], 0
    for i, (led, k) in enumerate(picked, 1):
        vx = reader.vouchers_xml(led["name"], d_from, d_to)
        bx = reader.bills_xml(led["name"], d_from, d_to) if k in ("debtor", "creditor") else ""
        if dump and i <= 3:
            dump.mkdir(parents=True, exist_ok=True)
            safe = re.sub(r"[^A-Za-z0-9]+", "_", led["name"])[:40]
            (dump / f"{safe}.vouchers.xml").write_text(vx, encoding="utf-8")
            (dump / f"{safe}.bills.xml").write_text(bx, encoding="utf-8")
        doc = build_doc(led, k, parse_vouchers(vx), parse_bills(bx) if bx else [], d_from, d_to, fy_start(today))
        warned += 1 if doc.get("warning") else 0
        docs.append(doc)
        if i % 25 == 0:
            log.info("read %d of %d", i, len(picked))
        time.sleep(cfg["pause_seconds"])
    return docs, {"company": reader.company, "from": d_from, "to": d_to, "warned": warned}


# ------------------------------------------------------------------ sending to the portal
class Portal:
    def __init__(self, url: str, key: str):
        self.url, self.key = url.rstrip("/"), key

    def post(self, path: str, body: dict) -> dict:
        data = json.dumps(body).encode("utf-8")
        last = None
        for attempt in range(4):
            req = urllib.request.Request(self.url + path, data=data, method="POST",
                                         headers={"Content-Type": "application/json", "Authorization": "Bearer " + self.key, "User-Agent": "nalanda-sync-agent"})
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    return json.loads(r.read() or b"{}")
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", "replace")[:300]
                if e.code < 500:
                    raise SyncError(f"The portal refused {path}: {e.code} {detail}", code=3)
                last = f"{e.code} {detail}"
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
                last = str(e)
            time.sleep(2 * (attempt + 1))
        raise SyncError(f"Could not reach the portal ({last}). Check the internet connection and the address.", code=3)


def push(portal: Portal, docs: list[dict], meta: dict, cfg: dict) -> dict:
    run = "run-" + uuid.uuid4().hex[:16]
    portal.post("/api/sync/start", {"runId": run, "company": cfg["company_title"] or meta["company"], "full": True})
    n = cfg["batch_size"]
    for i in range(0, len(docs), n):
        portal.post("/api/sync/ledgers", {"runId": run, "ledgers": docs[i:i + n]})
    return portal.post("/api/sync/finish", {"runId": run})


# ------------------------------------------------------------------ run
class Lock:
    """One sync at a time, even if a scheduled run overlaps a manual one."""
    def __init__(self, path: Path):
        self.path = path

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists() and time.time() - self.path.stat().st_mtime > 2 * 3600:
            self.path.unlink()
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            raise SyncError("Another sync is already running. This run is skipped.", code=4)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return self

    def __exit__(self, *a):
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


def load_config(path: str | None) -> dict:
    cfg = dict(DEFAULTS)
    p = Path(path) if path else HOME / "agent.json"
    if p.exists():
        cfg.update(json.loads(p.read_text(encoding="utf-8-sig")))
    cfg["sync_key"] = os.environ.get("NALANDA_SYNC_KEY") or cfg["sync_key"]
    return cfg


def run(cfg: dict, *, dry_run=False, limit=0, only="", dump: Path | None = None, today=None, lock_path: Path | None = None) -> dict:
    if not dry_run and (not cfg["portal_url"] or not cfg["sync_key"]):
        raise SyncError("Set portal_url and sync_key in the agent settings first.", code=3)
    with Lock(lock_path or HOME / "sync.lock"):
        reader = TallyReader(cfg)
        company = reader.check()
        log.info("Reading company: %s", company)
        docs, meta = collect(reader, cfg, only=only, limit=limit, dump=dump, today=today)
        if meta["warned"]:
            log.warning("%d statements do not add up to Tally's balance. They are sent with a warning.", meta["warned"])
        if dry_run:
            return {"dry_run": True, "ledgers": len(docs), **meta}
        res = push(Portal(cfg["portal_url"], cfg["sync_key"]), docs, meta, cfg)
        log.info("Sent %s ledgers to the portal.", res.get("ledgers"))
        return {"sent": res.get("ledgers"), "removed": res.get("removed"), **meta}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="sync_agent", description=__doc__.split("\n")[0])
    ap.add_argument("--config")
    ap.add_argument("--dry-run", action="store_true", help="read from Tally and check, send nothing")
    ap.add_argument("--limit", type=int, default=0, help="only the first N ledgers, for a quick test")
    ap.add_argument("--only", default="", help="only ledgers whose name contains this text")
    ap.add_argument("--debug-dump", help="folder to save the raw Tally replies for the first 3 ledgers")
    ap.add_argument("--verbose", "-v", action="store_true")
    a = ap.parse_args(argv)
    HOME.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.StreamHandler(), logging.FileHandler(HOME / "sync_agent.log", encoding="utf-8")])
    try:
        res = run(load_config(a.config), dry_run=a.dry_run, limit=a.limit, only=a.only, dump=Path(a.debug_dump) if a.debug_dump else None)
        print(json.dumps(res, indent=1))
        return 0
    except SyncError as e:
        log.error("%s", e)
        return e.code
    except GatewayError as e:
        log.error("%s", e)
        return 2
    except Exception:
        log.exception("The sync stopped unexpectedly")
        return 1


if __name__ == "__main__":
    sys.exit(main())
