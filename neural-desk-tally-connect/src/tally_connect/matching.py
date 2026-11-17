"""Name matching for parties and stock items.

Order of attack, learned from real data:
1. GSTIN match for parties (names differ, the tax number does not).
2. Saved mappings the user already approved (party_name_map.json, item_name_map.json).
3. Exact after normalising.
4. Substring in either direction ("BRIGHT" inside "BRIGHT AND INNOVATIVE ADVERTISING PVT LTD").
5. Token overlap, then difflib as the last resort.
Whole string similarity alone fails on short against long names, so it is never first.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

_SUFFIX = [
    (r"\bPRIVATE LIMITED\b", "PVT LTD"), (r"\bLIMITED\b", "LTD"),
    (r"\bM S\b", ""), (r"\bMS\b", ""),
]
COLOURS = {
    "BLACK", "BLK", "WHITE", "BLUE", "RED", "GREEN", "GREY", "GRAY", "SILVER", "GOLD", "PINK",
    "PURPLE", "ORANGE", "YELLOW", "BEIGE", "BROWN", "MIDNIGHT", "VELVET", "WINE", "ASH", "NAVY",
    "TEAL", "CLASSIC", "PREMIUM", "PLUS",
}


def norm(s: str) -> str:
    s = (s or "").upper().replace("&", " AND ")
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    for pat, rep in _SUFFIX:
        s = re.sub(pat, rep, s)
    return re.sub(r"\s+", " ", s).strip()


def strip_colours(s: str) -> str:
    toks = [t for t in norm(s).split() if t not in COLOURS]
    return " ".join(toks)


@dataclass
class Match:
    status: str                      # auto | ambiguous | none
    name: str | None = None
    score: float = 0.0
    how: str = ""
    candidates: list = field(default_factory=list)   # [(name, score)]


def _score(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if a in b or b in a:
        short, long_ = sorted((a, b), key=len)
        # a substring only counts when it covers a meaningful share of the longer name
        return 0.80 + 0.19 * (len(short) / len(long_)) if len(short) >= 4 else 0.0
    ta, tb = set(a.split()), set(b.split())
    if ta and tb:
        j = len(ta & tb) / len(ta | tb)
        if j >= 0.5:
            return 0.55 + 0.4 * j
    return difflib.SequenceMatcher(None, a, b).ratio() * 0.85


def best(query: str, names: list[str], *, ignore_colours=False, mapping: dict | None = None,
         floor: float = 0.62, gap: float = 0.08) -> Match:
    """Pick the single best name or say it is ambiguous. Never guess between different things."""
    if not query or not query.strip():
        return Match("none")
    if mapping:
        for k, v in mapping.items():
            if norm(k) == norm(query) and v in names:
                return Match("auto", v, 1.0, "saved mapping", [(v, 1.0)])
    prep = strip_colours if ignore_colours else norm
    q = prep(query)
    scored = sorted(((n, _score(q, prep(n))) for n in names), key=lambda x: -x[1])
    scored = [s for s in scored if s[1] >= floor][:6]
    if not scored:
        return Match("none")
    top = scored[0]
    if top[1] >= 0.995:
        return Match("auto", top[0], top[1], "exact", scored)
    if len(scored) == 1 or top[1] - scored[1][1] >= gap:
        return Match("auto", top[0], top[1], "best single hit", scored)
    return Match("ambiguous", None, top[1], "several close candidates", scored)


def by_gstin(gstin: str, ledgers: list[dict]) -> str | None:
    g = (gstin or "").strip().upper()
    if len(g) != 15:
        return None
    hits = [l["name"] for l in ledgers if (l.get("gstin") or "").strip().upper() == g]
    return hits[0] if len(hits) == 1 else None
