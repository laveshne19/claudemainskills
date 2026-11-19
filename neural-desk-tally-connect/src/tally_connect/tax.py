"""GST ledger choice and split.

Place of supply is the SHIP TO state. Intra state uses CGST plus SGST, or CGST plus UTGST when the
company state is a union territory without a legislature. Inter state uses IGST.
"""
from __future__ import annotations


def _eq(a: str, b: str) -> bool:
    return (a or "").strip().lower().replace("&", "and") == (b or "").strip().lower().replace("&", "and")


def is_intra(company_state: str, place_of_supply: str) -> bool:
    return bool(company_state) and _eq(company_state, place_of_supply)


def tax_ledgers(voucher_type: str, company_state: str, place_of_supply: str, cfg: dict) -> list[str]:
    side = "in" if voucher_type in ("Purchase", "Debit Note") else "out"
    L = cfg["ledgers"]
    if not is_intra(company_state, place_of_supply):
        return [L[f"igst_{side}"]]
    uts = any(_eq(company_state, s) for s in cfg.get("utgst_states", []))
    return [L[f"cgst_{side}"], L[f"utgst_{side}" if uts else f"sgst_{side}"]]


def split(tax_amount: float, ledgers: list[str]) -> list[tuple[str, float]]:
    """Split a tax total across ledgers. Any odd paisa goes to the first ledger."""
    if len(ledgers) == 1:
        return [(ledgers[0], round(tax_amount, 2))]
    half = round(tax_amount / 2, 2)
    return [(ledgers[0], round(tax_amount - half, 2)), (ledgers[1], half)]


def item_ledger(voucher_type: str, company_state: str, place_of_supply: str, rate: float, cfg: dict) -> str:
    kind = "purchase" if voucher_type in ("Purchase", "Debit Note") else "sales"
    key = f"{kind}_{'local' if is_intra(company_state, place_of_supply) else 'igst'}"
    r = f"{rate:g}"
    return cfg["ledgers"][key].format(rate=r)
