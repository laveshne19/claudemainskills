"""Pending previews and the log of everything posted. Plain JSON, easy to inspect and back up."""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from . import config

PREVIEW_TTL = 30 * 60


class State:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else config.home() / "state.json"
        self.data = {"previews": {}, "posted": []}
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                pass

    def _save(self):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=1), encoding="utf-8")
        tmp.replace(self.path)

    def add_preview(self, kind: str, xml: str, summary: dict) -> str:
        now = time.time()
        for k in [k for k, v in self.data["previews"].items() if now - v["at"] > PREVIEW_TTL]:
            del self.data["previews"][k]
        pid = uuid.uuid4().hex[:10]
        self.data["previews"][pid] = {"kind": kind, "xml": xml, "summary": summary, "at": now}
        self._save()
        return pid

    def take_preview(self, pid: str) -> dict | None:
        """Single use: the preview is removed the moment it is taken."""
        p = self.data["previews"].pop(pid, None)
        self._save()
        if p and time.time() - p["at"] > PREVIEW_TTL:
            return None
        return p

    def log_posted(self, entry: dict):
        entry = {**entry, "at": time.strftime("%Y-%m-%d %H:%M:%S")}
        self.data["posted"].append(entry)
        self._save()

    def was_posted(self, vtype: str, number: str) -> dict | None:
        for e in self.data["posted"]:
            if e.get("voucher_type") == vtype and str(e.get("number")) == str(number) and e.get("ok"):
                return e
        return None

    def was_posted_key(self, key: str) -> bool:
        return any(e.get("key") == key and e.get("ok") for e in self.data["posted"])
