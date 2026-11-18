import base64, http.client, json, os, pathlib, sys, tempfile, unittest, urllib.request, urllib.error
os.environ["TALLY_CONNECT_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from openpyxl import Workbook
from tally_connect import config
from tally_connect.webapp import App, start_background


class Client:
    def __init__(self, url, token):
        self.url, self.token = url, token

    def post(self, name, body=None, token="default", host=None):
        tok = self.token if token == "default" else token
        host_h = host or self.url.replace("http://", "")
        h = host_h.split(":")
        real = self.url.replace("http://", "").split(":")
        conn = http.client.HTTPConnection(real[0], int(real[1]), timeout=60)   # always connect locally, only the Host header varies
        payload = json.dumps(body or {})
        headers = {"Content-Type": "application/json", "Host": host_h}
        if tok is not None:
            headers["X-Token"] = tok
        conn.request("POST", "/api/" + name, payload, headers)
        r = conn.getresponse()
        data = json.loads(r.read() or b"{}")
        conn.close()
        return r.status, data

    def ok(self, name, body=None):
        s, d = self.post(name, body)
        assert s == 200, (name, s, d)
        return d


class WebApp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cfg = config.load(path=pathlib.Path(tempfile.mkdtemp()) / "none.json")
        cls.app = App(cfg=cfg, demo=True)
        cls.srv, cls.url = start_background(cls.app)
        cls.c = Client(cls.url, cls.app.token)

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown(); cls.app.stop()

    # ---- security ----
    def test_01_token_and_host_are_required(self):
        self.assertEqual(self.c.post("status", token=None)[0], 403)
        self.assertEqual(self.c.post("status", token="wrong")[0], 403)
        self.assertEqual(self.c.post("status", host="evil.example.com")[0], 403)
        self.assertEqual(self.c.post("status", host="evil.example.com:80")[0], 403)
        self.assertEqual(self.c.post("status")[0], 200)

    def test_02_page_serves_with_token_and_headers(self):
        with urllib.request.urlopen(self.url + "/") as r:
            html = r.read().decode()
            self.assertIn(self.app.token, html); self.assertNotIn("__TOKEN__", html)
            self.assertEqual(r.headers["X-Content-Type-Options"], "nosniff")
            self.assertIn("default-src", r.headers["Content-Security-Policy"])

    def test_03_template_needs_token(self):
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(self.url + "/api/template?name=sales_invoices.xlsx")
        self.assertEqual(e.exception.code, 403)
        with urllib.request.urlopen(f"{self.url}/api/template?name=sales_invoices.xlsx&t={self.app.token}") as r:
            self.assertEqual(r.read(2), b"PK")
        with self.assertRaises(urllib.error.HTTPError):
            urllib.request.urlopen(f"{self.url}/api/template?name=../../etc/passwd&t={self.app.token}")

    # ---- upload validation ----
    def test_04_bad_uploads_are_refused_kindly(self):
        d = self.c.ok("plan", {"filename": "x.pdf", "data": "AAAA", "type": "Sales"})
        self.assertFalse(d["ok"]); self.assertIn("Claude", d["error"])
        d = self.c.ok("plan", {"filename": "x.exe", "data": "AAAA", "type": "Sales"})
        self.assertIn("Excel", d["error"])
        d = self.c.ok("plan", {"filename": "x.xlsx", "data": "***not base64***", "type": "Sales"})
        self.assertFalse(d["ok"])
        d = self.c.ok("plan", {"filename": "../../x.xlsx", "data": base64.b64encode(b"junk").decode(), "type": "Sales"})
        self.assertFalse(d["ok"])
        d = self.c.ok("plan", {"filename": "a.xlsx", "data": "AAAA", "type": "Bogus"})
        self.assertIn("Unknown document type", d["error"])

    # ---- the whole story, in order ----
    def test_10_full_flow(self):
        c = self.c
        st = c.ok("status")
        self.assertTrue(st["doctor"]["gateway_reachable"] and st["doctor"]["company_loaded"] and st["setup_complete"])

        p = c.ok("plan", {"sample": True})
        self.assertTrue(p["ok"])
        cnt = p["counts"]
        self.assertEqual((cnt["READY"], cnt["HELD"], cnt["DUPLICATE"], cnt["ERROR"]), (5, 2, 1, 1), cnt)
        pid = p["plan_id"]
        by = {r["number"]: r for r in p["rows"]}
        self.assertEqual(by["INV-2204"]["kinds"], ["party"])
        self.assertEqual(by["INV-2205"]["kinds"], ["item"])
        self.assertIn("amount column may already include tax", " ".join(by["INV-2207"]["reasons"]))
        self.assertEqual(by["INV-2202"]["tax"], [["IGST OUTPUT", 3050.86]])
        self.assertEqual([x[0] for x in by["INV-2201"]["tax"]], ["CGST OUTPUT", "UTGST OUTPUT"])

        # a missing party can never be force approved
        s, d = c.post("resolve", {"plan_id": pid, "row": by["INV-2204"]["i"], "action": "approve"})
        self.assertFalse(d["ok"])

        # create the ledger: incomplete details are flagged, complete ones go through
        pv = c.ok("ledger/preview", {"name": "ANKUR SRIVASTAV", "parent": "Sundry Debtors", "registration_type": "Unregistered"})
        self.assertTrue(pv["summary"]["missing_details"])
        pv = c.ok("ledger/preview", {"name": "ANKUR SRIVASTAV", "parent": "Sundry Debtors", "registration_type": "Unregistered",
                                     "state": "Chandigarh", "pincode": "160022", "address": ["Shop 12", "Sector 22"]})
        self.assertEqual(pv["summary"]["missing_details"], [])
        cf = c.ok("ledger/confirm", {"preview_id": pv["preview_id"], "plan_id": pid})
        self.assertTrue(cf["ok"])
        by = {r["number"]: r for r in cf["plan"]["rows"]}
        self.assertEqual(by["INV-2204"]["status"], "READY")
        # single use
        self.assertFalse(c.ok("ledger/confirm", {"preview_id": pv["preview_id"], "plan_id": pid})["ok"])

        # item: search, then map to an existing item, which is remembered
        names = c.ok("search", {"kind": "item", "q": "charger"})["names"]
        self.assertIsInstance(names, list)
        bad = c.ok("resolve", {"plan_id": pid, "row": by["INV-2205"]["i"], "action": "map_item", "source": "Coin 3-in-1 Charger", "tally_name": "NO SUCH ITEM"})
        self.assertFalse(bad["ok"])
        ok = c.ok("resolve", {"plan_id": pid, "row": by["INV-2205"]["i"], "action": "map_item", "source": "Coin 3-in-1 Charger", "tally_name": "Pb331"})
        by = {r["number"]: r for r in ok["rows"]}
        self.assertEqual(by["INV-2205"]["status"], "READY")
        self.assertEqual(ok["counts"]["READY"], 7)

        # skip one on purpose
        sk = c.ok("resolve", {"plan_id": pid, "row": by["INV-2209"]["i"], "action": "skip"})
        self.assertEqual(sk["counts"]["READY"], 6)

        # post every ready row, each proven by the party balance
        posted = []
        for r in sk["rows"]:
            if r["status"] == "READY":
                res = c.ok("post_row", {"plan_id": pid, "row": r["i"]})
                self.assertTrue(res["result"]["ok"], res)
                self.assertTrue(res["result"]["verified"])
                self.assertEqual(res["result"]["balance_delta"]["expected"], res["result"]["balance_delta"]["actual"])
                self.assertEqual(res["row"]["status"], "POSTED")
                posted.append(r["number"])
        self.assertEqual(len(posted), 6)
        # the same entry cannot be posted twice
        again = c.ok("post_row", {"plan_id": pid, "row": by["INV-2201"]["i"]})
        self.assertFalse(again["ok"])

        # the books really changed, in the simulator
        nums = [v["number"] for v in self.app.mock.db["vouchers"]]
        for n in posted:
            self.assertIn(n, nums)
        self.assertTrue(all(v["has_bill_alloc"] for v in self.app.mock.db["vouchers"]))

        # re-reading the same sheet now finds everything posted as duplicates
        p2 = c.ok("plan", {"sample": True})
        self.assertEqual(p2["counts"]["DUPLICATE"], 7, p2["counts"])
        self.assertEqual(p2["counts"]["READY"], 1)          # INV-2209 was skipped, so it is still new

        # history and diagnostics
        h = c.ok("history")["items"]
        self.assertGreaterEqual(len([x for x in h if x["voucher_type"] == "Sales" and x["ok"]]), 6)
        dg = c.ok("diagnostics")["text"]
        self.assertIn("Tally Connect 0.2.0", dg); self.assertIn("demo", dg)

    def test_20_read_only_blocks_posting(self):
        c = self.c
        c.ok("settings", {"changes": {"read_only": True}})
        try:
            p = c.ok("plan", {"sample": True})
            ready = [r for r in p["rows"] if r["status"] == "READY"]
            if ready:
                res = c.ok("post_row", {"plan_id": p["plan_id"], "row": ready[0]["i"]})
                self.assertFalse(res["result"]["ok"]); self.assertIn("Read only", " ".join(res["result"]["problems"]))
        finally:
            c.ok("settings", {"changes": {"read_only": False}})

    def test_21_settings_are_validated(self):
        s, d = self.c.post("settings", {"changes": {"host": "evil"}})
        self.assertFalse(d["ok"])
        s, d = self.c.post("settings", {"changes": {"ledgers": {"nope": "x"}}})
        self.assertFalse(d["ok"])
        d = self.c.ok("settings", {"changes": {"skip_number_prefixes": "DC-, DCCASH"}})
        self.assertEqual(d["settings"]["skip_number_prefixes"], ["DC-", "DCCASH"])
        self.c.ok("settings", {"changes": {"skip_number_prefixes": []}})
        s, d = self.c.post("settings", {"connection": {"host": "10.0.0.5", "port": 9000}})
        self.assertFalse(d["ok"])            # demo mode refuses to be pointed elsewhere

    def test_22_discover_finds_the_demo_ledgers(self):
        d = self.c.ok("discover")
        self.assertEqual(d["proposed_ledger_names"]["utgst_out"], "UTGST OUTPUT")
        self.assertIn("HDFC BANK", d["bank_and_cash"])

    def test_23_payments_through_the_app(self):
        wb = Workbook(); ws = wb.active
        ws.append(["Date", "Party Name", "Amount", "Bank"]); ws.append(["2026-09-14", "KAUR MOBILE SHOP", 3000, "HDFC BANK"])
        ws.append(["2026-09-14", "Nobody Known Ltd", 100, "HDFC BANK"])
        p = pathlib.Path(tempfile.mkdtemp()) / "r.xlsx"; wb.save(p)
        d = self.c.ok("plan", {"filename": "r.xlsx", "data": base64.b64encode(p.read_bytes()).decode(), "type": "Receipt"})
        self.assertEqual((d["counts"]["READY"], d["counts"]["HELD"]), (1, 1))
        res = self.c.ok("post_row", {"plan_id": d["plan_id"], "row": 0})
        self.assertTrue(res["result"]["ok"] and res["result"]["verified"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
