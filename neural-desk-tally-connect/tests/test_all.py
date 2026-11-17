import os, sys, tempfile, unittest, pathlib, datetime
os.environ["TALLY_CONNECT_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from openpyxl import Workbook
from tally_connect import config, importer as I, matching, pipeline, tax, vouchers as V, xmlkit as X
from tally_connect.engine import RefusedWrite, Tally
from tally_connect.gateway import GatewayError, TallyGateway
from tally_connect.mocktally import MockTally
from tally_connect.state import State


def make(mock, **over):
    cfg = config.load(path=pathlib.Path(tempfile.mkdtemp()) / "none.json")
    cfg.update(port=mock.port, host="127.0.0.1", company_gstin="04AAAAA0000A1Z5", company_state="Chandigarh", retries=3)
    cfg.update(over)
    return Tally(cfg, state=State(pathlib.Path(tempfile.mkdtemp()) / "s.json"))


def sheet(rows, cols=None):
    cols = cols or ["Invoice Number", "Invoice Date", "Party Name", "GSTIN", "Ship To State", "Item Description",
                    "Quantity", "Rate", "Taxable Value", "Tax", "Total"]
    wb = Workbook(); ws = wb.active; ws.append(cols)
    for r in rows: ws.append(r)
    p = pathlib.Path(tempfile.mkdtemp()) / "x.xlsx"; wb.save(p); return str(p)


class Matching(unittest.TestCase):
    P = ["BRIGHT & CLEAR ADVERTISING PVT LTD", "KAUR MOBILE SHOP", "Prime Distribution Limited", "SHARMA TELECOM"]
    def test_short_in_long(self): self.assertEqual(matching.best("BRIGHT", self.P).name, self.P[0])
    def test_suffix_variants(self):
        self.assertEqual(matching.best("Prime Distribution Pvt Ltd", self.P).name, "Prime Distribution Limited")
        self.assertEqual(matching.best("Bright and Clear Advertising Private Limited", self.P).name, self.P[0])
    def test_none(self): self.assertEqual(matching.best("Zzz Traders", self.P).status, "none")
    def test_colour_ignored(self):
        it = ["ACME ROCKER SUMMIT BLACK", "ACME AIRBUDS ACE BLACK"]
        self.assertEqual(matching.best("Acme_Rocker Summit Classic Black", it, ignore_colours=True).name, it[0])
    def test_ambiguous(self):
        m = matching.best("Sharma Traders", ["Sharma Traders Delhi", "Sharma Traders Noida"])
        self.assertEqual(m.status, "ambiguous")
    def test_saved_mapping_wins(self):
        self.assertEqual(matching.best("Kaur Mob", self.P, mapping={"Kaur Mob": "KAUR MOBILE SHOP"}).name, "KAUR MOBILE SHOP")


class Vouchers(unittest.TestCase):
    cfg = config.DEFAULTS
    def inv(self, vt="Sales"):
        return V.Invoice(vt, "2026-09-07", "17607", "SHARMA TELECOM",
                         [V.Item("ACME AIRBUDS PROCLIP VELVET WINE", 2, 1288.14, 2576.28, ledger="SALES LOCAL@ 18%")],
                         [("CGST OUTPUT", 231.86), ("UTGST OUTPUT", 231.86)], 3040.00)
    def test_valid(self): self.assertEqual(V.validate_invoice(self.inv()), [])
    def test_total_mismatch_caught(self):
        i = self.inv(); i.total = 3000
        self.assertTrue(V.validate_invoice(i))
    def test_xml_required_pieces(self):
        x = V.invoice_xml(self.inv(), self.cfg)
        for needle in ("<ISINVOICE>Yes</ISINVOICE>", "BATCHALLOCATIONS.LIST", "<GODOWNNAME>Main Location",
                       "<BILLTYPE>New Ref</BILLTYPE>", "<NAME>17607</NAME>", "COUNTRYOFRESIDENCE>India", "LEDGERENTRIES.LIST",
                       "<CLASSNAME>DefaultVoucherClass", "PLACEOFSUPPLY"):
            self.assertIn(needle, x)
        self.assertNotIn("ALLLEDGERENTRIES.LIST", x)       # invoice view uses LEDGERENTRIES.LIST
    def test_sign_table(self):
        for vt, party_sign in (("Sales", -1), ("Purchase", 1), ("Credit Note", 1), ("Debit Note", -1)):
            x = V.invoice_xml(self.inv(vt), self.cfg)
            self.assertIn(f"<AMOUNT>{party_sign * 3040:.2f}</AMOUNT>", x, vt)
    def test_credit_note_against_ref(self):
        i = self.inv("Credit Note"); i.against_ref = "17500"
        x = V.invoice_xml(i, self.cfg)
        self.assertIn("<BILLTYPE>Agst Ref</BILLTYPE>", x); self.assertIn("<NAME>17500</NAME>", x)
    def test_accounting_uses_all_ledger_entries(self):
        a = V.Accounting("Receipt", "2026-09-14", "", [("HDFC BANK", -100.0), ("KAUR MOBILE SHOP", 100.0)], "KAUR MOBILE SHOP")
        self.assertEqual(V.validate_accounting(a), [])
        x = V.accounting_xml(a, self.cfg)
        self.assertIn("ALLLEDGERENTRIES.LIST", x); self.assertIn("<ISINVOICE>No</ISINVOICE>", x)
    def test_unbalanced_accounting(self):
        self.assertTrue(V.validate_accounting(V.Accounting("Journal", "2026-09-14", "", [("A", -1.0), ("B", 2.0)])))
    def test_ledger_never_sends_opening_balance(self):
        self.assertNotIn("OPENINGBALANCE", V.ledger_xml("X", "Sundry Debtors", self.cfg))
        self.assertIn("COUNTRYOFRESIDENCE>India", V.ledger_xml("X", "Sundry Debtors", self.cfg))


class Tax(unittest.TestCase):
    cfg = config.DEFAULTS
    def test_ut_intra(self): self.assertEqual(tax.tax_ledgers("Sales", "Chandigarh", "chandigarh", self.cfg), ["CGST OUTPUT", "UTGST OUTPUT"])
    def test_state_intra(self): self.assertEqual(tax.tax_ledgers("Sales", "Punjab", "Punjab", self.cfg), ["CGST OUTPUT", "SGST OUTPUT"])
    def test_inter(self): self.assertEqual(tax.tax_ledgers("Sales", "Chandigarh", "Punjab", self.cfg), ["IGST OUTPUT"])
    def test_purchase_input(self): self.assertEqual(tax.tax_ledgers("Purchase", "Chandigarh", "Punjab", self.cfg), ["IGST INPUT"])
    def test_split_odd_paisa(self):
        s = tax.split(0.03, ["A", "B"]); self.assertAlmostEqual(sum(a for _, a in s), 0.03)
    def test_item_ledger(self): self.assertEqual(tax.item_ledger("Sales", "Chandigarh", "Punjab", 18, self.cfg), "SALES IGST@18%")


class Importer(unittest.TestCase):
    def test_dates(self):
        w = []
        self.assertEqual(I.to_iso(46265.0), "2026-08-31")
        self.assertEqual(I.to_iso("07/09/2026", w), "2026-09-07"); self.assertTrue(w)
        self.assertEqual(I.to_iso("31-Aug-2026"), "2026-08-31")
        self.assertEqual(I.to_iso(datetime.datetime(2026, 9, 7)), "2026-09-07")
    def test_group_by_invoice(self):
        p = sheet([["A1", "2026-09-07", "SHARMA TELECOM", "", "Chandigarh", "X", 1, 100, 100, 18, 118],
                   ["A1", "2026-09-07", "SHARMA TELECOM", "", "Chandigarh", "Y", 1, 200, 200, 36, 354]])
        docs, _ = I.parse(p); self.assertEqual(len(docs), 1); self.assertEqual(len(docs[0].lines), 2)
    def test_missing_header(self):
        with self.assertRaises(ValueError): I.parse(sheet([[1, 2]], ["foo", "bar"]))
    def test_state_from_gstin(self): self.assertEqual(I.state_from_gstin("04AAAAA1111A1Z5"), "Chandigarh")
    def test_series_gaps(self): self.assertEqual(pipeline.series_gaps(["17601", "17602", "17604"]), ["17603"])


class Engine(unittest.TestCase):
    def setUp(self): self.m = MockTally().start()
    def tearDown(self): self.m.stop()

    def good(self, n="1001", party="SHARMA TELECOM"):
        return V.Invoice("Sales", "2026-09-07", n, party,
                         [V.Item("ACME AIRBUDS ACE BLACK", 1, 1000.0, 1000.0, ledger="SALES LOCAL@ 18%")],
                         [("CGST OUTPUT", 90.0), ("UTGST OUTPUT", 90.0)], 1180.0,
                         V.Gst("04AAAAA1111A1Z5", "Chandigarh", "Chandigarh"))

    def test_post_verify_and_balance(self):
        t = make(self.m); before = t.balance("SHARMA TELECOM")
        r = t.confirm(t.preview_invoice(self.good())["preview_id"])
        self.assertTrue(r["ok"] and r["verified"])
        self.assertAlmostEqual(t.balance("SHARMA TELECOM"), before - 1180.0)
        self.assertTrue(self.m.db["vouchers"][-1]["has_bill_alloc"])

    def test_preview_is_single_use(self):
        t = make(self.m); pid = t.preview_invoice(self.good())["preview_id"]
        self.assertTrue(t.confirm(pid)["ok"]); self.assertFalse(t.confirm(pid)["ok"])

    def test_nothing_written_on_preview(self):
        t = make(self.m); t.preview_invoice(self.good()); self.assertEqual(self.m.db["vouchers"], [])

    def test_duplicate_refused_from_log(self):
        t = make(self.m); t.confirm(t.preview_invoice(self.good())["preview_id"])
        r = t.preview_invoice(self.good()); self.assertFalse(r["ok"]); self.assertTrue(r["duplicate"])

    def test_duplicate_caught_by_daybook_when_log_empty(self):
        t = make(self.m); t.confirm(t.preview_invoice(self.good())["preview_id"])
        t2 = make(self.m)        # fresh state, simulates another PC or a wiped log
        self.assertTrue(t2.preview_invoice(self.good())["duplicate"])

    def test_lagging_daybook_still_safe_via_log_and_delta(self):
        self.m.lag = True; t = make(self.m)
        r = t.confirm(t.preview_invoice(self.good())["preview_id"]); self.assertTrue(r["verified"])
        self.assertTrue(t.preview_invoice(self.good())["duplicate"])

    def test_missing_godown_fails_silently_like_tally(self):
        t = make(self.m); pid = t.preview_invoice(self.good())["preview_id"]
        t.state.data["previews"][pid]["xml"] = t.state.data["previews"][pid]["xml"].replace("BATCHALLOCATIONS.LIST", "XX")
        r = t.confirm(pid); self.assertFalse(r["ok"]); self.assertEqual(self.m.db["vouchers"], [])

    def test_unknown_ledger_fails_and_nothing_posted(self):
        t = make(self.m); r = t.confirm(t.preview_invoice(self.good(party="NO SUCH PARTY"))["preview_id"])
        self.assertFalse(r["ok"]); self.assertEqual(self.m.db["vouchers"], [])

    def test_write_is_never_retried(self):
        t = make(self.m); pid = t.preview_invoice(self.good())["preview_id"]
        self.m.drop_next = 1; calls = self.m.calls
        t.confirm(pid)
        self.assertEqual(self.m.db["vouchers"], [])       # one attempt only, no blind retry
        self.assertLessEqual(self.m.calls - calls, 3)      # the write itself was sent once, plus balance reads

    def test_dropped_write_before_processing_reports_not_posted(self):
        t = make(self.m); pid = t.preview_invoice(self.good())["preview_id"]; self.m.drop_next = 1
        r = t.confirm(pid); self.assertFalse(r["ok"]); self.assertIn("NOT posted", r["problems"][0]); self.assertEqual(self.m.db["vouchers"], [])

    def test_cosmetic_timeout_is_detected_by_balance_and_not_reposted(self):
        t = make(self.m); pid = t.preview_invoice(self.good())["preview_id"]; self.m.drop_reply_next = 1
        r = t.confirm(pid); self.assertTrue(r["ok"] and r["verified"]); self.assertEqual(len(self.m.db["vouchers"]), 1)
        self.assertTrue(t.preview_invoice(self.good())["duplicate"])

    def test_incomplete_ledger_is_flagged(self):
        t = make(self.m); r = t.preview_ledger("ANKUR SRIVASTAV")
        self.assertIn("pincode", " ".join(r["warnings"]))

    def test_reads_are_retried(self):
        t = make(self.m); self.m.drop_next = 2
        self.assertTrue(t.companies())

    def test_freeze_and_read_only(self):
        with self.assertRaises(RefusedWrite): make(self.m, freeze_before="2026-10-01").preview_invoice(self.good())
        with self.assertRaises(RefusedWrite): make(self.m, read_only=True).preview_invoice(self.good())

    def test_ledger_preview_warns_on_similar_and_gstin(self):
        t = make(self.m); r = t.preview_ledger("SHARMA TELECO", gstin="04AAAAA1111A1Z5")
        self.assertTrue(r["warnings"]); self.assertTrue(r["summary"]["needs_explicit_user_approval"])

    def test_ledger_create_then_visible(self):
        t = make(self.m); r = t.confirm(t.preview_ledger("VIKRANT", "Sundry Debtors", state="Chandigarh")["preview_id"])
        self.assertTrue(r["ok"]); self.assertIn("VIKRANT", [l["name"] for l in t.ledgers(refresh=True)])

    def test_receipt_flow(self):
        t = make(self.m); b = t.balance("KAUR MOBILE SHOP")
        a = V.Accounting("Receipt", "2026-09-14", "", [("HDFC BANK", -4611.0), ("KAUR MOBILE SHOP", 4611.0)], "KAUR MOBILE SHOP")
        r = t.confirm(t.preview_accounting(a)["preview_id"]); self.assertTrue(r["verified"])
        self.assertAlmostEqual(t.balance("KAUR MOBILE SHOP"), b + 4611.0)
        self.assertTrue(t.preview_accounting(a)["duplicate"])

    def test_doctor_without_tally(self):
        cfg = config.load(path=pathlib.Path(tempfile.mkdtemp()) / "n.json"); cfg.update(port=1, retries=1, timeout=1)
        d = Tally(cfg, state=State(pathlib.Path(tempfile.mkdtemp()) / "s.json")).doctor()
        self.assertFalse(d["gateway_reachable"]); self.assertTrue(d["next_steps"])


class Pipeline(unittest.TestCase):
    def setUp(self): self.m = MockTally().start(); self.t = make(self.m)
    def tearDown(self): self.m.stop()

    def test_ready_held_duplicate_sorting(self):
        rows = [["S1", "2026-09-07", "SHARMA TELECOM", "04AAAAA1111A1Z5", "Chandigarh", "ACME AIRBUDS ACE BLACK", 1, 1000, 1000, 180, 1180],
                ["S2", "2026-09-07", "ANKUR SRIVASTAV", "", "Chandigarh", "ACME AIRBUDS ACE BLACK", 1, 5000, 5000, 900, 5900],
                ["S3", "2026-09-07", "KAUR MOBILE SHOP", "", "Punjab", "Coin 3-in-1 Charger", 1, 100, 100, 18, 118],
                ["S4", "2026-09-07", "Rana Enterprises", "", "Punjab", "Pb331", 2, 500, 1000, 180, 1180]]
        p = pipeline.make_plan(self.t, sheet(rows))
        st = {r["number"]: r for r in p.table()}
        self.assertEqual(st["S1"]["status"], "READY"); self.assertEqual(st["S4"]["status"], "READY")
        self.assertEqual(st["S2"]["status"], "HELD"); self.assertIn("new ledger", st["S2"]["questions"][0])
        self.assertEqual(st["S3"]["status"], "HELD"); self.assertIn("stock item", st["S3"]["questions"][0])
        self.assertEqual(st["S4"]["tax"], [["IGST OUTPUT", 180.0]])          # Punjab buyer: IGST
        self.assertEqual(st["S1"]["tax"], [["CGST OUTPUT", 90.0], ["UTGST OUTPUT", 90.0]])
        res = pipeline.post_plan(self.t, p); self.assertTrue(all(r.get("ok") for r in res))
        p2 = pipeline.make_plan(self.t, sheet(rows)); self.assertEqual(p2.summary()["counts"]["DUPLICATE"], 2)

    def test_total_mismatch_is_error_not_posted(self):
        p = pipeline.make_plan(self.t, sheet([["S9", "2026-09-07", "SHARMA TELECOM", "", "Chandigarh", "Pb331", 1, 100, 100, 18, 500]]))
        self.assertEqual(p.table()[0]["status"], "ERROR"); self.assertEqual(pipeline.post_plan(self.t, p), [])

    def test_round_off_paise(self):
        p = pipeline.make_plan(self.t, sheet([["S8", "2026-09-07", "SHARMA TELECOM", "", "Chandigarh", "Pb331", 1, 100.30, 100.30, 18.05, 118.0]]))
        r = p.rows[0]; self.assertEqual(r.status, "READY"); self.assertAlmostEqual(r.invoice.round_off, -0.35, places=2)
        res = pipeline.post_plan(self.t, p); self.assertTrue(res[0]["ok"])

    def test_payments_sheet(self):
        p = pipeline.make_plan(self.t, sheet([["2026-09-14", "KAUR MOBILE SHOP", 4611, "HDFC BANK", "UTR1", "", "note"]],
                                             ["Date", "Party Name", "Amount", "Bank", "Reference", "Against Invoice", "Narration"]), "Receipt")
        self.assertEqual(p.rows[0].status, "READY"); self.assertTrue(pipeline.post_plan(self.t, p)[0]["ok"])
        self.assertEqual(pipeline.make_plan(self.t, sheet([["2026-09-14", "KAUR MOBILE SHOP", 4611, "HDFC BANK", "UTR1", "", "note"]],
                         ["Date", "Party Name", "Amount", "Bank", "Reference", "Against Invoice", "Narration"]), "Receipt").rows[0].status, "DUPLICATE")

    def test_payment_without_bank_is_held(self):
        p = pipeline.make_plan(self.t, sheet([["2026-09-14", "KAUR MOBILE SHOP", 100]], ["Date", "Party Name", "Amount"]), "Receipt")
        self.assertEqual(p.rows[0].status, "HELD")

    def test_stops_at_first_failure(self):
        rows = [["T1", "2026-09-07", "SHARMA TELECOM", "", "Chandigarh", "Pb331", 1, 100, 100, 18, 118],
                ["T2", "2026-09-07", "SHARMA TELECOM", "", "Chandigarh", "Pb331", 1, 100, 100, 18, 118]]
        p = pipeline.make_plan(self.t, sheet(rows)); self.m.db["items"].pop("Pb331")    # item vanishes between plan and post
        res = pipeline.post_plan(self.t, p); self.assertFalse(res[0]["ok"]); self.assertIn("stopped", res[-1])


class Onboarding(unittest.TestCase):
    def setUp(self): self.m = MockTally().start(); self.t = make(self.m)
    def tearDown(self): self.m.stop()
    def test_discover(self):
        d = self.t.discover_setup()
        self.assertEqual(d["proposed_ledger_names"]["utgst_out"], "UTGST OUTPUT")
        self.assertEqual(d["proposed_ledger_names"]["sgst_out"], "SGST OUTPUT")
        self.assertIn("HDFC BANK", d["bank_and_cash"]); self.assertIn("SALES LOCAL@ 18%", d["sales_ledgers"])
    def test_update_settings_validates(self):
        self.assertFalse(self.t.update_settings({"host": "evil"})["ok"])
        self.assertFalse(self.t.update_settings({"ledgers": {"nope": "x"}})["ok"])
        self.assertTrue(self.t.update_settings({"ledgers": {"igst_out": "IGST OUTPUT"}, "default_godown": "Shop"})["ok"])
        self.assertEqual(self.t.cfg["default_godown"], "Shop")


class Xml(unittest.TestCase):
    def test_num(self):
        self.assertEqual(X.num("-1,234.50"), -1234.5); self.assertEqual(X.num("500 Dr"), -500.0); self.assertEqual(X.num(""), 0.0)
    def test_control_chars_cleaned(self):
        from tally_connect.gateway import clean
        self.assertEqual(clean("a&#4;b\x01c"), "abc")
    def test_daybook_has_all_three_dates(self):
        x = X.daybook_request("2026-09-07", "2026-09-07")
        for t in ("SVFROMDATE", "SVTODATE", "SVCURRENTDATE"): self.assertIn(t, x)
    def test_company_tag_is_svcurrentcompany(self):
        self.assertIn("SVCURRENTCOMPANY", X.import_envelope("", "ACME")); self.assertNotIn("<SVCOMPANY>", X.import_envelope("", "ACME"))


if __name__ == "__main__":
    unittest.main(verbosity=1)
