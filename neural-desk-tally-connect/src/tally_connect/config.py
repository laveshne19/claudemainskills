"""Settings. Everything company specific lives here, nothing is hard coded in the engine."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path

DEFAULTS: dict = {
    "host": "localhost",
    "port": 9000,
    "company": None,                 # None = whichever single company is open in Tally
    "company_gstin": "",
    "company_state": "",
    "company_gst_type": "Regular",
    "country": "India",
    "default_godown": "Main Location",
    "default_batch": "Primary Batch",
    "class_name": "DefaultVoucherClass",
    "freeze_before": None,           # ISO date. Vouchers dated before this are refused.
    "read_only": False,              # True = every write is refused
    "allow_ledger_creation": False,  # ledger previews are still possible, but flagged
    "ignore_trailing_colours": True, # stock not tracked colour wise
    "ledgers": {
        "cgst_out": "CGST OUTPUT", "sgst_out": "SGST OUTPUT",
        "utgst_out": "UTGST OUTPUT", "igst_out": "IGST OUTPUT",
        "cgst_in": "CGST INPUT", "sgst_in": "SGST INPUT",
        "utgst_in": "UTGST INPUT", "igst_in": "IGST INPUT",
        "round_off": "ROUND OFF",
        "sales_local": "SALES LOCAL@ {rate}%",
        "sales_igst": "SALES IGST@{rate}%",
        "purchase_local": "PURCHASE LOCAL@{rate}%",
        "purchase_igst": "PURCHASE IGST@{rate}%",
    },
    # Union territories without a legislature charge UTGST instead of SGST.
    "utgst_states": [
        "Chandigarh", "Ladakh", "Lakshadweep",
        "Andaman and Nicobar Islands", "Dadra and Nagar Haveli and Daman and Diu",
    ],
    "timeout": 30,
    "retries": 4,
}


def home() -> Path:
    p = Path(os.environ.get("TALLY_CONNECT_HOME") or Path.home() / ".tally-connect")
    p.mkdir(parents=True, exist_ok=True)
    return p


def _merge(base: dict, extra: dict) -> dict:
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v
    return base


def load(path: str | os.PathLike | None = None) -> dict:
    cfg = copy.deepcopy(DEFAULTS)
    p = Path(path) if path else home() / "config.json"
    if p.exists():
        _merge(cfg, json.loads(p.read_text(encoding="utf-8-sig")))
    if os.environ.get("TALLY_HOST"):
        cfg["host"] = os.environ["TALLY_HOST"]
    if os.environ.get("TALLY_PORT"):
        cfg["port"] = int(os.environ["TALLY_PORT"])
    return cfg


def save(cfg: dict, path: str | os.PathLike | None = None) -> Path:
    p = Path(path) if path else home() / "config.json"
    p.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return p
