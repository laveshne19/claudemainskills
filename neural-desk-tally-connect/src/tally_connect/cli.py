"""tally-connect command line."""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from . import __version__, config as cfgmod, pipeline, templates
from .engine import Tally


def _print_plan(p: pipeline.Plan):
    s = p.summary()
    print(f"Plan {s['plan_id']}: {s['counts']}  ready total {s['ready_total']:,.2f}")
    for n in s["notes"]:
        print("  note:", n)
    if s["series_gaps"]:
        print("  series gaps:", ", ".join(s["series_gaps"]))
    for r in p.table():
        flag = {"READY": "[ok]  ", "HELD": "[held]", "DUPLICATE": "[dup] ", "SKIPPED": "[skip]", "ERROR": "[err] "}[r["status"]]
        tot = f"{r['total']:>12,.2f}" if r["total"] is not None else " " * 12
        print(f"  {flag} {r['type']:<11} {r['number']:<14} {r['date']}  {r['party'][:30]:<30} {tot}")
        for q in r["questions"] or r["reasons"]:
            print("           ->", q)


def cmd_doctor(a):
    d = Tally().doctor()
    print(json.dumps(d, indent=2))
    return 0 if d["gateway_reachable"] and d["company_loaded"] else 1


def cmd_setup(a):
    cfg = cfgmod.load()
    for k in ("company", "company_gstin", "company_state", "host", "port", "freeze_before"):
        v = getattr(a, k, None)
        if v:
            cfg[k] = v
    if a.read_only is not None:
        cfg["read_only"] = a.read_only
    print("Saved", cfgmod.save(cfg))
    return 0


def cmd_plan(a):
    t = Tally()
    p = pipeline.make_plan(t, a.file, a.type, a.sheet, a.bank or "")
    _print_plan(p)
    if a.post:
        print("\nPosting READY rows...")
        for r in pipeline.post_plan(t, p):
            print(" ", r)
    return 0


def cmd_templates(a):
    for f in templates.write_all(a.folder):
        print("wrote", f)
    return 0


def cmd_mock(a):
    from .mocktally import MockTally
    m = MockTally(port=a.port).start()
    print(f"Simulated TallyPrime ({'Demo Traders Pvt Ltd'}) running on port {m.port}. This is NOT real Tally.")
    print("Set company_gstin 04AAAAA0000A1Z5 and company_state Chandigarh to try the sample sheets. Ctrl+C to stop.")
    try:
        m._t.join()
    except KeyboardInterrupt:
        m.stop()
    return 0


def cmd_demo(a):
    from .mocktally import MockTally
    from .state import State
    m = MockTally().start()
    tmp = Path(tempfile.mkdtemp())
    cfg = cfgmod.load()
    cfg.update(port=m.port, host="127.0.0.1", company_gstin="04AAAAA0000A1Z5", company_state="Chandigarh")
    t = Tally(cfg, state=State(tmp / "state.json"))
    templates.write_all(str(tmp))
    print("Simulated Tally started (not real Tally). Doctor:", t.doctor()["company_loaded"])
    p = pipeline.make_plan(t, str(tmp / "sales_invoices.xlsx"))
    _print_plan(p)
    print("\nPosting READY rows:")
    for r in pipeline.post_plan(t, p):
        print(" ", r)
    m.stop()
    return 0


def cmd_app(a):
    from .webapp import serve
    return serve(port=a.port, demo=a.demo, open_browser=not a.no_browser)


def cmd_serve(a):
    from .server import main as serve
    serve()
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="tally-connect", description="Neural Desk Tally Connect " + __version__)
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("doctor", help="check the connection to TallyPrime").set_defaults(fn=cmd_doctor)
    s = sp.add_parser("setup", help="save company settings")
    for k in ("company", "company_gstin", "company_state", "host", "port", "freeze_before"):
        s.add_argument("--" + k.replace("_", "-"), dest=k)
    s.add_argument("--read-only", dest="read_only", action="store_true", default=None)
    s.set_defaults(fn=cmd_setup)
    pl = sp.add_parser("plan", help="read an Excel/CSV and show what is ready, held or duplicate")
    pl.add_argument("file")
    pl.add_argument("--type", default="Sales", choices=["Sales", "Purchase", "Credit Note", "Debit Note", "Receipt", "Payment"])
    pl.add_argument("--sheet")
    pl.add_argument("--bank", help="default bank/cash ledger for receipts and payments")
    pl.add_argument("--post", action="store_true", help="post the READY rows (previews and verifies each one)")
    pl.set_defaults(fn=cmd_plan)
    tp = sp.add_parser("templates", help="write blank Excel templates")
    tp.add_argument("folder", nargs="?", default="templates")
    tp.set_defaults(fn=cmd_templates)
    mk = sp.add_parser("mock", help="run a simulated Tally so you can try everything without Tally")
    mk.add_argument("--port", type=int, default=9000)
    mk.set_defaults(fn=cmd_mock)
    sp.add_parser("demo", help="run a full self contained demo").set_defaults(fn=cmd_demo)
    ap2 = sp.add_parser("app", help="open the desktop app in your browser (run this on the PC that has Tally)")
    ap2.add_argument("--demo", action="store_true", help="use a built in simulated Tally, no Tally needed")
    ap2.add_argument("--port", type=int, default=8765)
    ap2.add_argument("--no-browser", action="store_true")
    ap2.set_defaults(fn=cmd_app)
    sp.add_parser("serve", help="start the MCP server for Claude").set_defaults(fn=cmd_serve)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
