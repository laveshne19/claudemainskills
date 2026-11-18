"""The desktop app: a small local web server plus a browser screen, for people who prefer clicking to chatting.

Runs on the PC that has Tally. Binds to 127.0.0.1 only. Every request needs a random token that the page gets when it
is opened, and the Host header must be local, so a web page on the internet cannot talk to it (no cross site requests,
no DNS rebinding). Everything real goes through the same engine and the same safety chain as the Claude connector.
"""
from __future__ import annotations

import base64
import csv
import json
import platform
import re
import secrets
import sys
import tempfile
import threading
import webbrowser
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import __version__, config as cfgmod, importer as I, matching, pipeline, templates
from .engine import RefusedWrite, Tally
from .gateway import GatewayError, TallyGateway
from .state import State

MAX_BODY = 40 * 1024 * 1024
ALLOWED_EXT = {".xlsx", ".xls", ".csv"}
SAFE_APPROVE = {"large", "alias"}          # holds a person may approve anyway. Missing parties or items they may not.
TYPES = ["Sales", "Purchase", "Credit Note", "Debit Note", "Receipt", "Payment"]


class AppError(Exception):
    pass


class App:
    def __init__(self, cfg: dict | None = None, demo: bool = False, state_path: Path | None = None):
        self.demo = demo
        self.mock = None
        cfg = cfg or cfgmod.load()
        if demo:
            from .mocktally import DEMO_COMPANY, MockTally
            self.mock = MockTally(demo_history=True).start()
            cfg.update(host="127.0.0.1", port=self.mock.port, company=DEMO_COMPANY, company_gstin="04AAAAA0000A1Z5",
                       company_state="Chandigarh", freeze_before=None, read_only=False)
            state_path = state_path or Path(tempfile.mkdtemp()) / "state.json"
        self.t = Tally(cfg, state=State(state_path) if state_path else None)
        self.plans: dict[str, dict] = {}
        self.lock = threading.Lock()
        self.token = secrets.token_urlsafe(24)
        self.last_error = ""

    # ------------------------------------------------------------------ helpers
    def _plan(self, pid: str) -> dict:
        pm = self.plans.get(pid)
        if not pm:
            raise AppError("That file is no longer loaded. Read the file again.")
        return pm

    def _row(self, b: dict):
        pm = self._plan(b.get("plan_id", ""))
        try:
            return pm, pm["plan"].rows[int(b["row"])], int(b["row"])
        except (KeyError, ValueError, IndexError):
            raise AppError("Unknown row.")

    def _rebuild(self, pm: dict, i: int):
        r = pm["plan"].rows[i]
        if r.pay is not None:
            pm["plan"].rows[i] = pipeline.build_payment(self.t, r.pay, pm["bank"])
        else:
            pm["plan"].rows[i] = pipeline.build(self.t, r.doc)

    def _refresh_held(self, pm: dict):
        for i, r in enumerate(pm["plan"].rows):
            if r.status == "HELD" and any(k in ("party", "item", "bank", "ledger", "state", "setup") for k in r.kinds):
                self._rebuild(pm, i)

    def _row_json(self, pm: dict, i: int) -> dict:
        r = pm["plan"].rows[i]
        d = r.doc
        res = pm["results"].get(i)
        status = r.status
        if res:
            status = "POSTED" if res.get("ok") else ("DUPLICATE" if res.get("duplicate") else "FAILED")
        out = {"i": i, "status": status, "type": d.voucher_type, "number": d.number, "date": d.date, "party": d.party,
               "tally_party": (r.invoice.party_ledger if r.invoice else (r.accounting.party_ledger if r.accounting else "")),
               "total": r.invoice.total if r.invoice else (r.pay.amount if r.pay else None),
               "reasons": r.reasons, "questions": r.questions, "notes": r.notes, "kinds": r.kinds, "result": res,
               "can_approve": bool(r.status == "HELD" and r.kinds and set(r.kinds) <= SAFE_APPROVE and (r.invoice or r.accounting))}
        if r.pay is None:
            lines = []
            for ln in d.lines:
                im = self.t.find_item(ln.item)
                lines.append({"source": ln.item, "matched": im["name"], "status": im["status"], "how": im["how"],
                              "candidates": im["candidates"], "qty": ln.qty, "rate": round(ln.rate, 2), "taxable": round(ln.taxable, 2)})
            out["lines"] = lines
            if r.invoice:
                out.update(tax=[list(x) for x in r.invoice.tax], round_off=r.invoice.round_off,
                           taxable=round(sum(i.amount for i in r.invoice.items), 2),
                           place=r.invoice.gst.place_of_supply or r.invoice.gst.party_state)
            if "party" in r.kinds:
                pmx = self.t.find_ledger(d.party, d.gstin)
                out["party_candidates"] = pmx["candidates"]
        else:
            out["pay"] = {"bank": r.pay.bank, "reference": r.pay.reference, "narration": r.pay.narration}
        return out

    def _plan_json(self, pid: str) -> dict:
        pm = self._plan(pid)
        s = pm["plan"].summary()
        rows = [self._row_json(pm, i) for i in range(len(pm["plan"].rows))]
        counts = {k: 0 for k in ("READY", "HELD", "DUPLICATE", "SKIPPED", "ERROR", "POSTED", "FAILED")}
        for r in rows:
            counts[r["status"]] = counts.get(r["status"], 0) + 1
        ready = round(sum(r["total"] or 0 for r in rows if r["status"] == "READY"), 2)
        return {"ok": True, "plan_id": pid, "filename": pm["filename"], "type": pm["type"], "counts": counts,
                "ready_total": ready, "notes": s["notes"], "series_gaps": s["series_gaps"], "rows": rows}

    # ------------------------------------------------------------------ API
    def api_status(self, b):
        d = self.t.doctor()
        c = self.t.cfg
        return {"ok": True, "version": __version__, "demo": self.demo, "doctor": d, "types": TYPES,
                "setup_complete": bool(c.get("company_gstin") and c.get("company_state")),
                "settings": self._settings()}

    def _settings(self) -> dict:
        c = self.t.cfg
        keep = ("host", "port", "company", "company_gstin", "company_state", "default_godown", "default_batch", "class_name",
                "freeze_before", "read_only", "send_bill_allocations", "skip_number_prefixes", "skip_numbers",
                "ignore_trailing_colours", "large_amount_factor")
        return {**{k: c.get(k) for k in keep}, "ledgers": c["ledgers"]}

    def api_settings(self, b):
        conn = b.get("connection") or {}
        if conn:
            host, port = str(conn.get("host", "")).strip() or "localhost", int(conn.get("port") or 9000)
            if self.demo:
                raise AppError("Demo mode uses a built in simulated Tally. Close and start the normal app to connect to Tally.")
            self.t.cfg.update(host=host, port=port)
            self.t.gw = TallyGateway(host, port, self.t.cfg["timeout"], self.t.cfg["retries"])
            self.t._ledgers = self.t._items = None
            cfgmod.save(self.t.cfg)
        ch = b.get("changes") or {}
        if ch:
            for k in ("skip_number_prefixes", "skip_numbers"):
                if k in ch and isinstance(ch[k], str):
                    ch[k] = [x.strip() for x in ch[k].split(",") if x.strip()]
            res = self.t.update_settings(ch)
            if not res["ok"]:
                raise AppError("; ".join(res["problems"]))
        return {"ok": True, "settings": self._settings()}

    def api_discover(self, b):
        return {"ok": True, **self.t.discover_setup()}

    def api_search(self, b):
        kind, q = b.get("kind", "item"), (b.get("q") or "").strip()
        names = [x["name"] for x in (self.t.stock_items() if kind == "item" else self.t.ledgers())]
        toks = [t for t in matching.norm(q).split() if t]
        hits = [n for n in names if toks and all(t in matching.norm(n) for t in toks)][:12]
        if len(hits) < 5:
            m = matching.best(q, names, strict=False, floor=0.5)
            for n, _ in m.candidates:
                if n not in hits:
                    hits.append(n)
        return {"ok": True, "names": hits[:12]}

    def api_plan(self, b):
        typ = b.get("type") or "Sales"
        if typ not in TYPES:
            raise AppError("Unknown document type.")
        bank = (b.get("bank") or "").strip()
        tmp = Path(tempfile.mkdtemp(prefix="tcupload"))
        if b.get("sample"):
            if not self.demo:
                raise AppError("The sample file is only available in demo mode.")
            fname = "demo_sales.xlsx"
            templates.write_demo_sheet(str(tmp / fname))
            typ = "Sales"
        else:
            fname = Path(str(b.get("filename") or "")).name
            ext = Path(fname).suffix.lower()
            if ext == ".pdf" or ext in (".jpg", ".jpeg", ".png"):
                raise AppError("PDFs and photos are read by Claude, not by this screen. Use the Claude plugin for those, "
                               "or save the data as Excel and upload that here.")
            if ext not in ALLOWED_EXT:
                raise AppError("Please upload an Excel (.xlsx) or CSV file.")
            try:
                raw = base64.b64decode(b.get("data") or "", validate=True)
            except Exception:
                raise AppError("The file did not arrive intact. Try again.")
            if len(raw) > 25 * 1024 * 1024:
                raise AppError("That file is larger than 25 MB.")
            (tmp / fname).write_bytes(raw)
        try:
            plan = pipeline.make_plan(self.t, str(tmp / fname), typ, None, bank)
        except ValueError as e:
            raise AppError(str(e))
        except (zipfile.BadZipFile, UnicodeDecodeError, csv.Error, KeyError, OSError, EOFError) as e:
            raise AppError("Could not read that file. Is it a real Excel (.xlsx) or CSV file, and not open in another program?")
        except Exception as e:
            if type(e).__name__ in ("InvalidFileException", "InvalidXmlFileException"):
                raise AppError("Could not read that file. Please save it as .xlsx or .csv and try again.")
            raise
        pid = plan.id
        self.plans[pid] = {"plan": plan, "type": typ, "bank": bank, "filename": fname, "results": {}}
        return self._plan_json(pid)

    def api_plan_get(self, b):
        return self._plan_json(b.get("plan_id", ""))

    def api_resolve(self, b):
        pm, r, i = self._row(b)
        a = b.get("action")
        names_l = {x["name"] for x in self.t.ledgers()}
        if a == "map_party":
            name = b.get("tally_name", "")
            if name not in names_l:
                raise AppError("That ledger does not exist in Tally.")
            self.t.remember("party", r.doc.party, name)
        elif a == "map_item":
            name = b.get("tally_name", "")
            if name not in {x["name"] for x in self.t.stock_items()}:
                raise AppError("That stock item does not exist in Tally.")
            self.t.remember("item", b.get("source") or "", name)
        elif a == "set_bank":
            bank = (b.get("bank") or "").strip()
            if bank not in names_l:
                raise AppError("That bank or cash ledger does not exist in Tally.")
            if r.pay is not None:
                r.pay.bank = bank
        elif a == "recheck":
            self.t.ledgers(refresh=True)
            self.t.stock_items(refresh=True)
        elif a == "skip":
            r.status = "SKIPPED"
            r.reasons.append("Skipped by you. It stays out of this batch.")
            return {"ok": True, **self._plan_json(b["plan_id"])}
        elif a == "approve":
            if not (r.status == "HELD" and r.kinds and set(r.kinds) <= SAFE_APPROVE and (r.invoice or r.accounting)):
                raise AppError("This one cannot be approved from here. Fix the missing party or item first.")
            r.status = "READY"
            r.notes.append("You approved this after the warning: " + "; ".join(r.reasons))
            return {"ok": True, **self._plan_json(b["plan_id"])}
        else:
            raise AppError("Unknown action.")
        self._refresh_held(pm)
        return {"ok": True, **self._plan_json(b["plan_id"])}

    def api_ledger_preview(self, b):
        name = (b.get("name") or "").strip()
        if not name:
            raise AppError("The ledger needs a name.")
        addr = [l.strip() for l in (b.get("address") or []) if l.strip()]
        res = self.t.preview_ledger(name, b.get("parent") or "Sundry Debtors", gstin=(b.get("gstin") or "").strip().upper(),
                                    state=(b.get("state") or "").strip(), pincode=(b.get("pincode") or "").strip(),
                                    address=addr, registration_type=(b.get("registration_type") or "").strip())
        miss = res["summary"].get("missing_details", [])
        res["warnings"] = [w for w in res["warnings"] if not w.startswith("Incomplete.")]
        if miss:
            res["warnings"].append("Still needed before this ledger can be created: " + ", ".join(miss) +
                                   ". New ledgers are never created as a bare name. Walk in customers can stay Unregistered, "
                                   "but need an address, state and pincode.")
        return {"ok": True, **res}

    def api_ledger_confirm(self, b):
        res = self.t.confirm(b.get("preview_id", ""))
        if res.get("ok") and b.get("plan_id") in self.plans:
            self._refresh_held(self.plans[b["plan_id"]])
        out = {"ok": bool(res.get("ok")), "problems": res.get("problems", []), "import": res.get("import")}
        if b.get("plan_id") in self.plans:
            out["plan"] = self._plan_json(b["plan_id"])
        return out

    def api_post_row(self, b):
        pm, r, i = self._row(b)
        if r.status != "READY" or not (r.invoice or r.accounting):
            raise AppError("Only ready entries can be posted.")
        if i in pm["results"] and pm["results"][i].get("ok"):
            raise AppError("This entry was already posted.")
        res = pipeline.post_row(self.t, r)
        pm["results"][i] = res
        return {"ok": True, "result": res, "row": self._row_json(pm, i)}

    def api_history(self, b):
        return {"ok": True, "items": list(reversed(self.t.state.data["posted"][-300:]))}

    def api_diagnostics(self, b):
        d = self.t.doctor()
        lines = [f"Tally Connect {__version__} ({'demo' if self.demo else 'live'})", f"Python {sys.version.split()[0]} on {platform.platform()}",
                 f"Endpoint {self.t.gw.url}", f"Tally reachable: {d['gateway_reachable']}  company loaded: {d['company_loaded']}",
                 f"Companies: {', '.join(d['companies']) or '-'}", f"Problems: {'; '.join(d['problems']) or '-'}",
                 "Settings: " + json.dumps({k: v for k, v in self._settings().items() if k != "ledgers"}, default=str),
                 "Ledger names: " + json.dumps(self.t.cfg["ledgers"]),
                 "Last errors: " + (self.last_error or "-"), "Last posted:"]
        for e in self.t.state.data["posted"][-5:]:
            lines.append("  " + json.dumps({k: e.get(k) for k in ("at", "voucher_type", "number", "party", "total", "ok", "verified")}, default=str))
        return {"ok": True, "text": "\n".join(lines)}

    # ------------------------------------------------------------------ http
    def html(self) -> bytes:
        page = resources.files("tally_connect").joinpath("ui/app.html").read_text(encoding="utf-8")
        return page.replace("__TOKEN__", self.token).replace("__DEMO__", "true" if self.demo else "false").encode("utf-8")

    def template_bytes(self, name: str) -> tuple[bytes, str]:
        if not re.fullmatch(r"[a-z_]+\.xlsx", name or "") or name not in templates.TEMPLATES and name not in ("receipts.xlsx", "payments.xlsx"):
            raise AppError("Unknown template.")
        tmp = Path(tempfile.mkdtemp(prefix="tctpl"))
        templates.write_all(str(tmp))
        return (tmp / name).read_bytes(), name

    def stop(self):
        if self.mock:
            self.mock.stop()


def make_handler(app: App, port_getter):
    def host_ok(h: str) -> bool:
        p = port_getter()
        return (h or "") in (f"127.0.0.1:{p}", f"localhost:{p}")

    class H(BaseHTTPRequestHandler):
        server_version = "TallyConnect"

        def log_message(self, *a):
            pass

        def _send(self, code, body: bytes, ctype="application/json", extra=None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self' 'unsafe-inline' data: blob:")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code, obj):
            self._send(code, json.dumps(obj, default=str).encode("utf-8"))

        def _guard(self) -> bool:
            if not host_ok(self.headers.get("Host", "")):
                self._json(403, {"ok": False, "error": "Not allowed."})
                return False
            return True

        def do_GET(self):
            if not self._guard():
                return
            u = urlparse(self.path)
            if u.path == "/":
                return self._send(200, app.html(), "text/html; charset=utf-8")
            q = parse_qs(u.query)
            if u.path == "/api/template":
                if (q.get("t") or [""])[0] != app.token:
                    return self._json(403, {"ok": False, "error": "Not allowed."})
                try:
                    data, name = app.template_bytes((q.get("name") or [""])[0])
                except AppError as e:
                    return self._json(400, {"ok": False, "error": str(e)})
                return self._send(200, data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                  {"Content-Disposition": f'attachment; filename="{name}"'})
            self._json(404, {"ok": False, "error": "Not found."})

        def do_POST(self):
            if not self._guard():
                return
            if not self.path.startswith("/api/"):
                return self._json(404, {"ok": False, "error": "Not found."})
            if self.headers.get("X-Token") != app.token:
                return self._json(403, {"ok": False, "error": "Not allowed. Reload the page."})
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_BODY:
                return self._json(413, {"ok": False, "error": "Too large."})
            try:
                body = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                return self._json(400, {"ok": False, "error": "Bad request."})
            fn = getattr(app, "api_" + self.path[5:].replace("/", "_"), None)
            if not fn:
                return self._json(404, {"ok": False, "error": "Unknown action."})
            with app.lock:
                try:
                    return self._json(200, fn(body))
                except AppError as e:
                    return self._json(200, {"ok": False, "error": str(e)})
                except RefusedWrite as e:
                    return self._json(200, {"ok": False, "error": str(e), "refused": True})
                except GatewayError as e:
                    app.last_error = str(e)
                    return self._json(200, {"ok": False, "error": str(e), "tally_unreachable": True})
                except Exception as e:      # never leak a stack trace to the page, keep it for diagnostics
                    app.last_error = f"{type(e).__name__}: {e}"
                    return self._json(500, {"ok": False, "error": "Something went wrong: " + app.last_error})
    return H


def serve(port: int = 8765, demo: bool = False, open_browser: bool = True, app: App | None = None):
    app = app or App(demo=demo)
    srv = ThreadingHTTPServer(("127.0.0.1", port), lambda *a, **k: None)
    srv.RequestHandlerClass = make_handler(app, lambda: srv.server_address[1])
    real = srv.server_address[1]
    url = f"http://127.0.0.1:{real}/"
    print(f"Tally Connect {__version__} {'(DEMO, simulated Tally) ' if demo else ''}is running at {url}")
    print("Keep this window open while you work. Press Ctrl+C to stop.")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
        app.stop()
    return 0


def start_background(app: App, port: int = 0):
    """For tests: run on a free port in a thread, return (server, url)."""
    srv = ThreadingHTTPServer(("127.0.0.1", port), lambda *a, **k: None)
    srv.RequestHandlerClass = make_handler(app, lambda: srv.server_address[1])
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"
