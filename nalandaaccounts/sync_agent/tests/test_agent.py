"""End to end: fictional ledgers -> fake Tally -> sync agent -> the REAL portal code -> checked through the portal API.
Run from nalandaaccounts/:  PYTHONPATH=. python -m unittest discover -s sync_agent/tests -v
Needs: node, and the tally_connect package (pip install the wheel from the Tally Connect desktop zip, or set PYTHONPATH to its src)."""
import copy
import datetime as dt
import http.cookiejar
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fake_tally import FakeTally  # noqa: E402
from sync_agent import agent  # noqa: E402

KEY = "k" * 48
TODAY = dt.date(2026, 9, 30)


def load_fixture():
    out = subprocess.run(["node", str(ROOT / "tests" / "dump_fixtures.mjs")], capture_output=True, check=True, text=True).stdout
    return json.loads(out)


class Portal:
    """The real portal server (server/local.mjs, in memory), plus a signed in master session."""
    def __init__(self):
        self.port = 18000 + (os.getpid() % 1000)
        env = {**os.environ, "SESSION_SECRET": "s" * 48, "SYNC_KEY": KEY, "PORT": str(self.port)}
        self.proc = subprocess.Popen(["node", str(ROOT / "server" / "local.mjs")], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        self.proc.stdout.readline()  # "Local portal on ..."
        self.url = f"http://127.0.0.1:{self.port}"
        self.jar = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.call("POST", "/api/admin/bootstrap", {"username": "lavesh", "name": "L", "password": "Temp-Pass-12345"}, bearer=KEY)
        self.call("POST", "/api/login", {"username": "lavesh", "password": "Temp-Pass-12345"})
        self.call("POST", "/api/change-password", {"current": "Temp-Pass-12345", "next": "Better-Pass-98765"})

    def call(self, method, path, body=None, bearer=None):
        req = urllib.request.Request(self.url + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json", "X-Requested-With": "nalanda", **({"Authorization": "Bearer " + bearer} if bearer else {})})
        try:
            with self.op.open(req, timeout=30) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            return {"status": e.code, **json.loads(e.read() or b"{}")}

    def stop(self):
        self.proc.terminate()


def cfg_for(portal, tally, **over):
    c = dict(agent.DEFAULTS)
    c.update(portal_url=portal.url, sync_key=KEY, tally_host="127.0.0.1", tally_port=tally.port, statement_from="", pause_seconds=0, batch_size=7)
    c.update(over)
    return c


class AgentEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = load_fixture()
        cls.portal = Portal()

    @classmethod
    def tearDownClass(cls):
        cls.portal.stop()

    def setUp(self):
        self.tally = FakeTally(copy.deepcopy(self.fixture))
        self.lock = Path(tempfile.mkdtemp()) / "sync.lock"

    def tearDown(self):
        self.tally.stop()

    def run_agent(self, **kw):
        return agent.run(cfg_for(self.portal, self.tally, **kw.pop("cfg", {})), today=TODAY, lock_path=self.lock, **kw)

    # ---- the happy path
    def test_01_sync_reaches_the_portal_with_the_right_numbers(self):
        res = self.run_agent()
        owing = [l for l in self.fixture if l["closing"]["amount"] > 0]
        self.assertEqual(res["sent"], len(owing))
        self.assertEqual(res["warned"], 0, "every statement ties to the Tally balance")
        d = self.portal.call("GET", "/api/dealers")
        self.assertEqual(len(d["rows"]), len(owing))
        want = round(sum(l["closing"]["amount"] for l in owing if l["kind"] == "debtor" and l["closing"]["side"] == "Dr"), 2)
        self.assertEqual(d["totals"]["receivable"], want, "total receivable equals the sum of the Tally balances")
        self.assertEqual(d["company"], "FAKE TRADERS PVT LTD")
        # a bill wise dealer: the bills Tally listed are kept and tie to the ledger balance
        bw = next(l for l in owing if l.get("bills") and l["kind"] == "debtor" and l["closing"]["side"] == "Dr")
        row = next(r for r in d["rows"] if r["name"] == bw["name"])
        v = self.portal.call("GET", "/api/ledger/" + row["id"])
        self.assertTrue(v["ledger"]["billwise"])
        self.assertEqual(v["ledger"]["check"]["diff"], 0)
        self.assertEqual(sum(b["pending"] for b in v["ledger"]["bills"]), bw["closing"]["amount"])
        self.assertNotIn("warning", v["ledger"])
        self.assertTrue(row["city"] or True)
        self.assertEqual(next(r for r in d["rows"] if r["name"] == bw["name"])["city"], "Chandigarh", "city comes from the last address line")
        # the statement ends exactly where Tally says the balance is
        self.assertEqual(v["statement"]["rows"][-1]["balance"], v["statement"]["closing"])
        self.assertEqual(v["statement"]["closing"], bw["closing"])
        # a ledger that is not bill wise has its bills rebuilt from the statement
        nb = next(l for l in owing if not l.get("bills") and l["kind"] == "debtor" and l["closing"]["side"] == "Dr")
        row = next(r for r in d["rows"] if r["name"] == nb["name"])
        v = self.portal.call("GET", "/api/ledger/" + row["id"])
        self.assertFalse(v["ledger"]["billwise"])
        self.assertEqual(v["ledger"]["totals"]["total"], nb["closing"]["amount"])

    def test_02_sub_groups_and_kinds_are_understood(self):
        self.run_agent()
        d = self.portal.call("GET", "/api/dealers")
        north = [r for r in d["rows"] if r["group"] == "DEBTORS OF NORTH ZONE"]
        self.assertTrue(north, "a dealer in a sub group of Sundry Debtors is still a dealer")
        self.assertTrue(all(r["kind"] == "debtor" for r in north))
        self.assertEqual(len([r for r in d["rows"] if r["kind"] == "creditor"]), 5)

    def test_03_options(self):
        r = self.run_agent(limit=4)
        self.assertEqual(r["sent"], 4)
        r = self.run_agent(cfg={"kinds": ["creditor"]})
        self.assertEqual(r["sent"], 5)
        d = self.portal.call("GET", "/api/dealers")
        self.assertEqual({x["kind"] for x in d["rows"]}, {"creditor"}, "a full sync replaces what was there")
        r = self.run_agent(only="Sharma")
        self.assertTrue(0 < r["sent"] < 10)

    def test_04_dry_run_sends_nothing(self):
        before = self.portal.call("GET", "/api/sync/status")["meta"]
        r = self.run_agent(dry_run=True, limit=3)
        self.assertTrue(r["dry_run"]); self.assertEqual(r["ledgers"], 3)
        self.assertEqual(self.portal.call("GET", "/api/sync/status")["meta"], before)

    def test_05_debug_dump_saves_raw_replies(self):
        dump = Path(tempfile.mkdtemp()) / "dump"
        self.run_agent(dry_run=True, limit=3, dump=dump)
        files = sorted(p.name for p in dump.iterdir())
        self.assertEqual(len(files), 6); self.assertTrue(any(f.endswith(".bills.xml") for f in files))

    # ---- the safety checks
    def test_10_a_missing_entry_is_flagged_not_hidden(self):
        victim = next(l for l in self.fixture if l["kind"] == "debtor" and l["closing"]["amount"] > 0 and any(v["date"] >= "2026-04-01" for v in l["vouchers"]))
        self.tally.drop_voucher = victim["name"]
        r = self.run_agent()
        self.assertEqual(r["warned"], 1)
        d = self.portal.call("GET", "/api/dealers")
        row = next(x for x in d["rows"] if x["name"] == victim["name"])
        v = self.portal.call("GET", "/api/ledger/" + row["id"])
        self.assertIn("do not add up to the Tally balance", v["ledger"]["warning"])
        self.assertEqual(v["ledger"]["closing"], victim["closing"], "the balance shown is still Tally's own")

    def test_11_tally_closed_is_a_clean_skip_not_a_crash(self):
        cfg = cfg_for(self.portal, self.tally, tally_port=1)
        with self.assertRaises(agent.SyncError) as e:
            agent.run(cfg, today=TODAY, lock_path=self.lock)
        self.assertEqual(e.exception.code, 2); self.assertIn("TallyPrime open", str(e.exception))

    def test_12_two_open_companies_needs_a_choice(self):
        self.tally.stop()
        self.tally = FakeTally(copy.deepcopy(self.fixture), extra_company="OTHER CO")
        with self.assertRaises(agent.SyncError) as e:
            self.run_agent()
        self.assertEqual(e.exception.code, 2); self.assertIn("More than one company", str(e.exception))
        self.assertEqual(self.run_agent(cfg={"company": "FAKE TRADERS PVT LTD"}, limit=2)["sent"], 2)
        with self.assertRaises(agent.SyncError):
            self.run_agent(cfg={"company": "NOT OPEN"})

    def test_13_wrong_key_or_address(self):
        with self.assertRaises(agent.SyncError) as e:
            self.run_agent(cfg={"sync_key": "x" * 48})
        self.assertEqual(e.exception.code, 3)
        with self.assertRaises(agent.SyncError) as e:
            self.run_agent(cfg={"sync_key": ""})
        self.assertEqual(e.exception.code, 3); self.assertIn("sync_key", str(e.exception))

    def test_14_only_one_sync_at_a_time(self):
        with agent.Lock(self.lock):
            with self.assertRaises(agent.SyncError) as e:
                self.run_agent()
            self.assertEqual(e.exception.code, 4)
        self.assertFalse(self.lock.exists(), "the lock is released")
        self.lock.write_text("1"); old = time.time() - 3 * 3600; os.utime(self.lock, (old, old))
        self.assertEqual(self.run_agent(limit=1)["sent"], 1, "a stale lock from a crashed run is cleared")

    def test_15_a_custom_start_date_works_out_the_opening_balance(self):
        r = self.run_agent(cfg={"statement_from": "2026-07-01"}, limit=8)
        self.assertEqual(r["warned"], 0, "no tie out warning is raised when the start date is not the financial year start")
        d = self.portal.call("GET", "/api/dealers")
        v = self.portal.call("GET", "/api/ledger/" + d["rows"][0]["id"])
        self.assertEqual(v["statement"]["rows"][-1]["balance"], v["statement"]["closing"])


    # ---- history for named ledgers
    def _with_history_ledgers(self):
        """Two ledgers with 2024 entries: one still owing, one fully settled (zero balance)."""
        base = {"group": "Sundry Debtors", "kind": "debtor", "city": "Ludhiana", "state": "Punjab", "phone": "", "gstin": "", "bills": []}
        spon = {**base, "name": "Spontaneous Traders", "vouchers": [
            {"date": "2024-05-10", "type": "Sales", "number": "S-1", "particulars": "Goods", "debit": 50000, "credit": 0},
            {"date": "2024-06-01", "type": "Receipt", "number": "R-1", "particulars": "Bank", "debit": 0, "credit": 20000},
            {"date": "2026-05-02", "type": "Sales", "number": "S-9", "particulars": "Goods", "debit": 12000, "credit": 0}],
            "closing": {"amount": 42000, "side": "Dr"}}
        nar = {**base, "name": "Narang  Enterprises", "vouchers": [
            {"date": "2024-04-15", "type": "Sales", "number": "N-1", "particulars": "Goods", "debit": 30000, "credit": 0},
            {"date": "2024-08-01", "type": "Receipt", "number": "R-2", "particulars": "Bank", "debit": 0, "credit": 30000}],
            "closing": {"amount": 0, "side": "Dr"}}
        self.tally.ledgers[spon["name"]] = spon
        self.tally.ledgers[nar["name"]] = nar

    def test_16_history_rules_go_back_in_time_and_keep_zero_balance_ledgers(self):
        self._with_history_ledgers()
        hist = [{"match": "spontan", "from": "2024-04-01"}, {"match": "narang enterprises", "from": "2024-04-01"}]
        r = self.run_agent(cfg={"history": hist})
        self.assertEqual(r["unmatched"], [])
        self.assertEqual(r["history"]["narang enterprises"]["ledgers"], ["Narang  Enterprises"], "spacing in the Tally name does not stop the match")
        d = self.portal.call("GET", "/api/dealers")
        names = [x["name"] for x in d["rows"]]
        self.assertIn("Spontaneous Traders", names)
        self.assertIn("Narang  Enterprises", names, "a zero balance ledger is kept because it has a history rule")
        row = next(x for x in d["rows"] if x["name"] == "Spontaneous Traders")
        v = self.portal.call("GET", "/api/ledger/" + row["id"])
        self.assertEqual([x["date"] for x in v["statement"]["rows"]][0], "2024-05-10", "statement starts in 2024")
        self.assertEqual(len(v["statement"]["rows"]), 3)
        self.assertEqual(v["statement"]["rows"][-1]["balance"], {"amount": 42000, "side": "Dr"})
        nrow = next(x for x in d["rows"] if x["name"] == "Narang  Enterprises")
        nv = self.portal.call("GET", "/api/ledger/" + nrow["id"])
        self.assertEqual(len(nv["statement"]["rows"]), 2)
        self.assertEqual(nv["statement"]["closing"]["amount"], 0)

    def test_17_a_partial_run_keeps_the_rest_of_the_portal(self):
        self._with_history_ledgers()
        self.run_agent(cfg={"kinds": ["creditor"]})
        before = len(self.portal.call("GET", "/api/dealers")["rows"])
        self.assertEqual(before, 5)
        r = self.run_agent(only=["spontan", "narang enterprises"], cfg={"history": [
            {"match": "spontan", "from": "2024-04-01"}, {"match": "narang enterprises", "from": "2024-04-01"}]})
        self.assertTrue(r["partial"])
        self.assertEqual(r["sent"], 2)
        d = self.portal.call("GET", "/api/dealers")
        self.assertEqual(len(d["rows"]), before + 2, "the five creditors already there are still there")

    def test_18_a_rule_that_matches_nothing_is_reported(self):
        self._with_history_ledgers()
        r = self.run_agent(cfg={"history": [{"match": "no such party", "from": "2024-04-01"}]}, limit=2)
        self.assertEqual(r["unmatched"], ["no such party (from 2024-04-01)"])

    def test_19_bad_history_rule_is_refused_clearly(self):
        with self.assertRaises(agent.SyncError):
            self.run_agent(cfg={"history": [{"match": "x", "from": "not a date"}]})

    def test_20_cli_from_needs_only(self):
        self.assertEqual(agent.main(["--config", "/nonexistent.json", "--from", "2024-04-01", "--dry-run"]), 1)


class Parsers(unittest.TestCase):
    def test_dates(self):
        for text in ("20260401", "01-Apr-2026", "1-Apr-26", "01/04/2026", "2026-04-01"):
            self.assertEqual(agent.parse_date(text), "2026-04-01", text)
        self.assertIsNone(agent.parse_date("nonsense"))

    def test_money_and_sign(self):
        self.assertEqual(agent.money("-1,234.50"), {"amount": 1234.5, "side": "Dr"})
        self.assertEqual(agent.money("99"), {"amount": 99.0, "side": "Cr"})
        self.assertEqual(agent.money(""), {"amount": 0.0, "side": "Cr"})

    def test_vouchers_tolerate_missing_pieces(self):
        xml = ("<ENVELOPE><DSPVCHDATE>01-Apr-2026</DSPVCHDATE><DSPVCHLEDACCOUNT>Sales</DSPVCHLEDACCOUNT><DSPVCHTYPE>Sales</DSPVCHTYPE><DSPVCHDRAMT>100.00</DSPVCHDRAMT>"
               "<DSPVCHDATE>02-Apr-2026</DSPVCHDATE><DSPVCHTYPE>Receipt</DSPVCHTYPE><DSPVCHCRAMT>40.00</DSPVCHCRAMT>"
               "<DSPVCHDATE>bad</DSPVCHDATE><DSPVCHDRAMT>9</DSPVCHDRAMT></ENVELOPE>")
        rows = agent.parse_vouchers(xml)
        self.assertEqual([(r["date"], r["debit"], r["credit"], r["number"]) for r in rows], [("2026-04-01", 100.0, 0.0, ""), ("2026-04-02", 0.0, 40.0, "")])

    def test_bills_pair_the_reference_with_the_pending_amount(self):
        xml = ("<ENVELOPE><BILLFIXED><BILLDATE>05-Apr-2026</BILLDATE><BILLREF>INV-1</BILLREF></BILLFIXED><BILLCL>-500.00</BILLCL>"
               "<BILLFIXED><BILLDATE>06-Apr-2026</BILLDATE><BILLREF>INV-2</BILLREF></BILLFIXED><BILLCL>0.00</BILLCL></ENVELOPE>")
        self.assertEqual(agent.parse_bills(xml), [{"date": "2026-04-05", "ref": "INV-1", "pending": 500.0}])

    def test_group_chain_and_financial_year(self):
        groups = {"DEBTORS OF NORTH ZONE": "Sundry Debtors", "Sundry Debtors": "Current Assets"}
        self.assertEqual(agent.kind_of("DEBTORS OF NORTH ZONE", groups, agent.DEFAULTS), "debtor")
        self.assertEqual(agent.kind_of("Bank Accounts", groups, agent.DEFAULTS), "other")
        self.assertEqual(agent.kind_of("A", {"A": "B", "B": "A"}, agent.DEFAULTS), "other", "a loop in the group tree cannot hang the agent")
        self.assertEqual(agent.fy_start(dt.date(2026, 3, 31)), "2025-04-01"); self.assertEqual(agent.fy_start(dt.date(2026, 4, 1)), "2026-04-01")


if __name__ == "__main__":
    unittest.main(verbosity=1)
