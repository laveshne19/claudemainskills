"""The engine: read from Tally, preview, confirm, verify."""
from __future__ import annotations

import json
from datetime import date

from . import config as cfgmod
from . import matching, vouchers as V, xmlkit as X
from .gateway import GatewayError, TallyGateway
from .state import State


class RefusedWrite(RuntimeError):
    pass


class Tally:
    def __init__(self, cfg: dict | None = None, gateway: TallyGateway | None = None, state: State | None = None):
        self.cfg = cfg or cfgmod.load()
        self.gw = gateway or TallyGateway(self.cfg["host"], self.cfg["port"],
                                          self.cfg["timeout"], self.cfg["retries"])
        self.state = state or State()
        self._ledgers: list[dict] | None = None
        self._items: list[dict] | None = None

    # ------------------------------------------------------------------ connection
    @property
    def company(self) -> str | None:
        return self.cfg.get("company")

    def doctor(self) -> dict:
        out = {"endpoint": self.gw.url, "gateway_reachable": False, "company_loaded": False,
               "companies": [], "problems": [], "next_steps": []}
        if not self.gw.ping():
            out["problems"].append("TallyPrime did not answer on " + self.gw.url)
            out["next_steps"] = [
                "Open TallyPrime and load the company you want to work in.",
                "Press F1 (Help) > Settings > Connectivity > Client/Server configuration.",
                "Set 'TallyPrime acts as' to Server or Both, port 9000, then restart Tally.",
                "If Tally is on another PC, allow tally.exe through the Windows firewall for the "
                "Domain, Private and Public profiles.",
                "Press Esc until you are on the Gateway of Tally. An open dialog blocks the connection."]
            return out
        out["gateway_reachable"] = True
        try:
            out["companies"] = self.companies()
        except Exception as e:
            out["problems"].append(f"Tally answered but the company list failed: {e}")
        out["company_loaded"] = bool(out["companies"])
        if not out["company_loaded"]:
            out["problems"].append("No company is open in Tally.")
            out["next_steps"].append("Open a company in TallyPrime, then run the check again.")
        if len(out["companies"]) > 1 and not self.company:
            out["problems"].append("More than one company is open. Set the company name so entries go to the right books.")
        out["write_mode"] = "READ ONLY" if self.cfg["read_only"] else "writes allowed after preview and confirm"
        out["checklist"] = ["Use TallyPrime Silver or Gold. The Educational edition silently truncates date ranges."]
        return out

    def companies(self) -> list[str]:
        xml = self.gw.post(X.company_list_request())
        return [r["NAME"] for r in X.rows(xml, "COMPANY") if r.get("NAME")]

    # ------------------------------------------------------------------ masters
    def ledgers(self, refresh=False) -> list[dict]:
        if self._ledgers is None or refresh:
            xml = self.gw.post(X.collection_request(
                "NDLedgers", "Ledger", "Name,Parent,PartyGSTIN,ClosingBalance,LedStateName", self.company))
            self._ledgers = [{"name": r["NAME"], "parent": r.get("PARENT", ""), "gstin": r.get("PARTYGSTIN", ""),
                              "state": r.get("LEDSTATENAME", ""), "balance": X.num(r.get("CLOSINGBALANCE"))}
                             for r in X.rows(xml, "LEDGER") if r.get("NAME")]
        return self._ledgers

    def stock_items(self, refresh=False) -> list[dict]:
        if self._items is None or refresh:
            xml = self.gw.post(X.collection_request(
                "NDItems", "StockItem", "Name,Parent,BaseUnits", self.company))
            self._items = [{"name": r["NAME"], "parent": r.get("PARENT", ""), "unit": r.get("BASEUNITS", "")}
                           for r in X.rows(xml, "STOCKITEM") if r.get("NAME")]
        return self._items

    def find_ledger(self, text: str, gstin: str = "") -> dict:
        leds = self.ledgers()
        hit = matching.by_gstin(gstin, leds)
        if hit:
            return {"status": "auto", "name": hit, "how": "GSTIN match", "candidates": [[hit, 1.0]]}
        m = matching.best(text, [l["name"] for l in leds], mapping=self.mapping("party"))
        return {"status": m.status, "name": m.name, "how": m.how, "candidates": [[n, round(s, 2)] for n, s in m.candidates]}

    def find_item(self, text: str) -> dict:
        m = matching.best(text, [i["name"] for i in self.stock_items()],
                          ignore_colours=self.cfg["ignore_trailing_colours"], mapping=self.mapping("item"))
        return {"status": m.status, "name": m.name, "how": m.how, "candidates": [[n, round(s, 2)] for n, s in m.candidates]}

    def balance(self, ledger: str) -> float | None:
        xml = self.gw.post(X.collection_request(
            "NDBal", "Ledger", "Name,ClosingBalance", self.company, filter_formula=f'$Name = "{ledger}"'))
        rows = [r for r in X.rows(xml, "LEDGER") if r.get("NAME") == ledger]
        return X.num(rows[0].get("CLOSINGBALANCE")) if rows else None

    # ------------------------------------------------------------------ onboarding
    def discover_setup(self) -> dict:
        """Look at the company's own ledgers and propose the GST / sales / purchase ledger names.
        Every company names these differently, so the user confirms the proposal once."""
        leds = self.ledgers(refresh=True)
        names = [l["name"] for l in leds]

        def pick(words, parents=()):
            cand = [l["name"] for l in leds if all(w in l["name"].upper() for w in words)
                    and (not parents or l["parent"] in parents)]
            return cand[0] if cand else None

        duties = ("Duties & Taxes",)
        prop = {
            "cgst_out": pick(["CGST", "OUT"], duties), "sgst_out": pick(["SGST", "OUT"], duties) if True else None,
            "utgst_out": pick(["UTGST", "OUT"], duties), "igst_out": pick(["IGST", "OUT"], duties),
            "cgst_in": pick(["CGST", "IN"], duties), "sgst_in": pick(["SGST", "IN"], duties),
            "utgst_in": pick(["UTGST", "IN"], duties), "igst_in": pick(["IGST", "IN"], duties),
            "round_off": pick(["ROUND"]),
        }
        # "SGST OUT" also matches "UTGST OUT"; prefer the plain one
        if prop["sgst_out"] and "UTGST" in prop["sgst_out"].upper():
            prop["sgst_out"] = next((l["name"] for l in leds if "SGST" in l["name"].upper() and "UTGST" not in l["name"].upper()
                                     and "OUT" in l["name"].upper() and l["parent"] in duties), None)
        if prop["sgst_in"] and "UTGST" in prop["sgst_in"].upper():
            prop["sgst_in"] = next((l["name"] for l in leds if "SGST" in l["name"].upper() and "UTGST" not in l["name"].upper()
                                    and " IN" in l["name"].upper() and l["parent"] in duties), None)
        found = {k: v for k, v in prop.items() if v}
        by_parent = lambda p: [l["name"] for l in leds if l["parent"] == p]
        return {"proposed_ledger_names": found, "not_found": [k for k, v in prop.items() if not v],
                "sales_ledgers": by_parent("Sales Accounts"), "purchase_ledgers": by_parent("Purchase Accounts"),
                "bank_and_cash": by_parent("Bank Accounts") + by_parent("Cash-in-Hand"),
                "counts": {"ledgers": len(names), "stock_items": len(self.stock_items(refresh=True))},
                "next": "Show this to the user, confirm each name, then save with update_settings. For the sales and "
                        "purchase ledgers, set the pattern with {rate} where the GST rate appears in the name."}

    ALLOWED_SETTINGS = {"company", "company_gstin", "company_state", "company_gst_type", "default_godown", "default_batch",
                        "class_name", "freeze_before", "read_only", "allow_ledger_creation", "ignore_trailing_colours",
                        "ledgers", "utgst_states"}

    def update_settings(self, changes: dict) -> dict:
        bad = [k for k in changes if k not in self.ALLOWED_SETTINGS]
        if bad:
            return {"ok": False, "problems": [f"Not a setting you can change: {', '.join(bad)}"]}
        for k, v in changes.items():
            if k == "ledgers":
                unknown = [x for x in v if x not in self.cfg["ledgers"]]
                if unknown:
                    return {"ok": False, "problems": [f"Unknown ledger setting: {', '.join(unknown)}"]}
                self.cfg["ledgers"].update(v)
            else:
                self.cfg[k] = v
        cfgmod.save(self.cfg)
        self._ledgers = self._items = None
        return {"ok": True, "saved": changes}

    # ------------------------------------------------------------------ saved mappings
    def _map_path(self, kind: str):
        return cfgmod.home() / f"{kind}_name_map.json"

    def mapping(self, kind: str) -> dict:
        p = self._map_path(kind)
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

    def remember(self, kind: str, source_name: str, tally_name: str):
        m = self.mapping(kind)
        m[source_name] = tally_name
        self._map_path(kind).write_text(json.dumps(m, indent=1, ensure_ascii=False), encoding="utf-8")

    # ------------------------------------------------------------------ duplicates
    def day_vouchers(self, iso_day: str) -> list[dict]:
        xml = self.gw.post(X.daybook_request(iso_day, iso_day, self.company))
        out = []
        for r in X.rows(xml, "VOUCHER"):
            out.append({"type": r.get("VOUCHERTYPENAME", ""), "number": r.get("VOUCHERNUMBER", ""),
                        "party": r.get("PARTYLEDGERNAME", ""), "date": iso_day})
        return out

    def find_duplicate(self, vtype: str, number: str, iso_day: str) -> str | None:
        """Two independent layers: our own posted log, then a live Day Book lookup for that day."""
        if number and self.state.was_posted(vtype, number):
            return "already posted by Tally Connect"
        if number:
            for v in self.day_vouchers(iso_day):
                if v["type"].lower() == vtype.lower() and str(v["number"]) == str(number):
                    return "already in Tally on that date"
        return None

    # ------------------------------------------------------------------ guards
    def _guard(self, iso_day: str):
        if self.cfg["read_only"]:
            raise RefusedWrite("Read only mode is on. Writes are disabled in the settings.")
        fz = self.cfg.get("freeze_before")
        if fz and date.fromisoformat(iso_day) < date.fromisoformat(fz):
            raise RefusedWrite(f"{iso_day} is before the freeze date {fz}. Old entries are not touched.")

    # ------------------------------------------------------------------ preview
    def preview_invoice(self, inv: V.Invoice) -> dict:
        self._guard(inv.date)
        errs = V.validate_invoice(inv)
        if errs:
            return {"ok": False, "problems": errs}
        dup = self.find_duplicate(inv.voucher_type, inv.number, inv.date)
        if dup:
            return {"ok": False, "duplicate": True, "problems": [f"{inv.voucher_type} {inv.number}: {dup}. Nothing created."]}
        xml = X.import_envelope(V.invoice_xml(inv, self.cfg), self.company)
        before = self.balance(inv.party_ledger)
        s = V.SIGN[inv.voucher_type]
        summary = {"voucher_type": inv.voucher_type, "number": inv.number, "date": inv.date,
                   "party": inv.party_ledger, "total": inv.total,
                   "taxable": round(sum(i.amount for i in inv.items), 2), "tax": inv.tax,
                   "round_off": inv.round_off, "lines": len(inv.items),
                   "party_balance_before": before, "expected_delta": round(-s * inv.total, 2),
                   "place_of_supply": inv.gst.place_of_supply or inv.gst.party_state}
        pid = self.state.add_preview("invoice", xml, summary)
        return {"ok": True, "preview_id": pid, "summary": summary}

    def preview_accounting(self, v: V.Accounting) -> dict:
        self._guard(v.date)
        errs = V.validate_accounting(v)
        if errs:
            return {"ok": False, "problems": errs}
        amt = abs(next((a for l, a in v.entries if l == v.party_ledger), v.entries[0][1]))
        key = f"{v.voucher_type}|{v.date}|{v.party_ledger}|{amt:.2f}"
        if self.state.was_posted_key(key):
            return {"ok": False, "duplicate": True, "problems": [f"{v.voucher_type} of {amt:,.2f} for {v.party_ledger} on {v.date} was already posted."]}
        if v.number:
            dup = self.find_duplicate(v.voucher_type, v.number, v.date)
            if dup:
                return {"ok": False, "duplicate": True, "problems": [f"{v.voucher_type} {v.number}: {dup}."]}
        xml = X.import_envelope(V.accounting_xml(v, self.cfg), self.company)
        before = self.balance(v.party_ledger) if v.party_ledger else None
        delta = next((a for l, a in v.entries if l == v.party_ledger), None) if v.party_ledger else None
        summary = {"voucher_type": v.voucher_type, "number": v.number, "date": v.date, "key": key,
                   "party": v.party_ledger, "entries": v.entries, "narration": v.narration,
                   "party_balance_before": before, "expected_delta": delta}
        pid = self.state.add_preview("accounting", xml, summary)
        return {"ok": True, "preview_id": pid, "summary": summary}

    def preview_ledger(self, name: str, parent="Sundry Debtors", **kw) -> dict:
        if self.cfg["read_only"]:
            raise RefusedWrite("Read only mode is on.")
        existing = matching.best(name, [l["name"] for l in self.ledgers()])
        warn = []
        if existing.name:
            warn.append(f"A similar ledger already exists: {existing.name}. Use it instead unless the user says it is a different party.")
        if existing.status == "ambiguous":
            warn.append("Several similar ledgers exist: " + ", ".join(n for n, _ in existing.candidates))
        if kw.get("gstin"):
            g = matching.by_gstin(kw["gstin"], self.ledgers())
            if g:
                warn.append(f"This GSTIN already belongs to ledger {g}.")
        missing = [k for k, label in (("address", "address"), ("state", "state"), ("pincode", "6 digit pincode")) if not kw.get(k)]
        if parent in ("Sundry Debtors", "Sundry Creditors") and not kw.get("gstin") and not kw.get("registration_type"):
            missing.append("GSTIN or an explicit Unregistered status")
        if missing:
            warn.append("Incomplete. New ledgers are created complete: still needed " + ", ".join(missing) +
                        ". Ask the user, or say clearly that the source has none (walk in customers are Unregistered).")
        xml = X.import_envelope(V.ledger_xml(name, parent, self.cfg, **kw), self.company, report="All Masters")
        summary = {"ledger": name, "parent": parent, **kw, "warnings": warn, "missing_details": missing,
                   "needs_explicit_user_approval": True}
        pid = self.state.add_preview("ledger", xml, summary)
        return {"ok": True, "preview_id": pid, "summary": summary, "warnings": warn}

    # ------------------------------------------------------------------ confirm and verify
    def confirm(self, preview_id: str) -> dict:
        p = self.state.take_preview(preview_id)
        if not p:
            return {"ok": False, "problems": ["Unknown or expired preview. Previews are single use, preview again."]}
        sm = p["summary"]
        if p["kind"] != "ledger":
            self._guard(sm["date"])
        out = {"kind": p["kind"], "summary": sm}
        try:
            reply = self.gw.post(p["xml"], retry=False)        # never auto retry a write
            res = X.import_result(reply)
        except GatewayError as err:
            # A timeout is often cosmetic: Tally may have posted and only the reply was lost.
            # Never retry blindly. Decide from the party balance, which is the only trustworthy signal.
            res = {"ok": False, "created": 0, "errors": 0, "exceptions": 0, "line_error": "", "timeout": True}
            before, exp = sm.get("party_balance_before"), sm.get("expected_delta")
            if p["kind"] != "ledger" and sm.get("party") and before is not None and exp is not None:
                try:
                    got = round((self.balance(sm["party"]) or 0.0) - before, 2)
                except GatewayError:
                    got = None
                if got is not None and abs(got - exp) < 0.011:
                    out.update(**{"import": res}, ok=True, verified=True, balance_delta={"expected": exp, "actual": got},
                               note="Tally timed out on the reply but the entry did post. Verified by the party balance.")
                    self.state.log_posted({**self._key(p), "ok": True, "verified": True, "timeout": True})
                    return out
                out.update(ok=False, **{"import": res}, problems=[
                    "Tally did not answer. The party balance has not moved, so the entry was NOT posted. "
                    "It is safe to preview and confirm again once Tally responds. Check there is no dialog box open in Tally."])
                return out
            out.update(ok=False, **{"import": res}, problems=[f"Tally did not answer: {err}"])
            return out
        out["import"] = res
        if not res["ok"]:
            out["ok"] = False
            out["problems"] = [
                "Tally did not accept the entry. Nothing was posted.",
                "Tally gives no error text. The usual causes are: a ledger or stock item name that does "
                "not exist exactly as written, a missing godown on a stock entry, or a dialog box open in Tally."]
            self.state.log_posted({**self._key(p), "ok": False})
            return out
        if p["kind"] == "ledger":
            self._ledgers = None
            out["ok"] = True
            self.state.log_posted({"voucher_type": "Ledger", "number": sm["ledger"], "ok": True})
            return out
        # Seed our log immediately, then prove it with the party balance delta.
        after = self.balance(sm["party"]) if sm.get("party") else None
        before, exp = sm.get("party_balance_before"), sm.get("expected_delta")
        verified = None
        if before is not None and after is not None and exp is not None:
            got = round(after - before, 2)
            verified = abs(got - exp) < 0.011
            out["balance_delta"] = {"expected": exp, "actual": got}
        out["verified"] = verified
        out["ok"] = verified is not False
        if verified is False:
            out["problems"] = ["The party balance did not move by the expected amount. Stop and check this "
                               "voucher in Tally before posting anything else."]
        self.state.log_posted({**self._key(p), "ok": True, "verified": verified})
        return out

    @staticmethod
    def _key(p):
        s = p["summary"]
        return {"voucher_type": s.get("voucher_type", ""), "number": s.get("number", ""),
                "party": s.get("party", ""), "total": s.get("total"), "key": s.get("key", "")}
