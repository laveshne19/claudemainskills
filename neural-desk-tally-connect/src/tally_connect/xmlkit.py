"""Builders for Tally export requests and parsers for the replies."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape


def esc(s) -> str:
    return escape(str(s if s is not None else ""), {'"': "&quot;"})


def tdate(iso: str) -> str:
    """2026-09-07 -> 20260907"""
    return iso.replace("-", "")


def _static(company: str | None, extra: str = "") -> str:
    comp = f"<SVCURRENTCOMPANY>{esc(company)}</SVCURRENTCOMPANY>" if company else ""
    return f"<STATICVARIABLES><SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>{comp}{extra}</STATICVARIABLES>"


def collection_request(name: str, ttype: str, fetch: str, company: str | None = None,
                       filter_formula: str | None = None) -> str:
    filt = ""
    sysdef = ""
    if filter_formula:
        filt = "<FILTERS>NDFilter</FILTERS>"
        sysdef = f'<SYSTEM TYPE="Formulae" NAME="NDFilter">{esc(filter_formula)}</SYSTEM>'
    return (
        "<ENVELOPE><HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST>"
        f"<TYPE>Collection</TYPE><ID>{esc(name)}</ID></HEADER><BODY><DESC>{_static(company)}"
        f'<TDL><TDLMESSAGE><COLLECTION NAME="{esc(name)}" ISMODIFY="No"><TYPE>{esc(ttype)}</TYPE>'
        f"<FETCH>{esc(fetch)}</FETCH>{filt}</COLLECTION>{sysdef}</TDLMESSAGE></TDL></DESC></BODY></ENVELOPE>"
    )


def company_list_request() -> str:
    return collection_request("List of Companies", "Company", "Name,StartingFrom,Books")


def daybook_request(iso_from: str, iso_to: str, company: str | None = None) -> str:
    d1, d2 = tdate(iso_from), tdate(iso_to)
    # SVFROMDATE, SVTODATE and SVCURRENTDATE must all be present or Tally ignores the range.
    extra = f"<SVFROMDATE>{d1}</SVFROMDATE><SVTODATE>{d2}</SVTODATE><SVCURRENTDATE>{d2}</SVCURRENTDATE>"
    return (
        "<ENVELOPE><HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Data</TYPE>"
        f"<ID>Day Book</ID></HEADER><BODY><DESC>{_static(company, extra)}</DESC></BODY></ENVELOPE>"
    )


def import_envelope(messages: str, company: str | None, report: str = "Vouchers") -> str:
    comp = f"<SVCURRENTCOMPANY>{esc(company)}</SVCURRENTCOMPANY>" if company else ""
    return (
        "<ENVELOPE><HEADER><TALLYREQUEST>Import Data</TALLYREQUEST></HEADER><BODY><IMPORTDATA>"
        f"<REQUESTDESC><REPORTNAME>{esc(report)}</REPORTNAME><STATICVARIABLES>{comp}</STATICVARIABLES>"
        f'</REQUESTDESC><REQUESTDATA><TALLYMESSAGE xmlns:UDF="TallyUDF">{messages}</TALLYMESSAGE>'
        "</REQUESTDATA></IMPORTDATA></BODY></ENVELOPE>"
    )


def parse(xml: str) -> ET.Element:
    xml = re.sub(r"<\?xml[^>]*\?>", "", xml).strip()
    return ET.fromstring(xml)


def num(text) -> float:
    """Tally amounts: '-1,234.50', '1234.5 Dr', '' -> float. Dr is negative, Cr is positive."""
    if text is None:
        return 0.0
    t = str(text).strip().replace(",", "")
    if not t:
        return 0.0
    sign = 1.0
    if t.upper().endswith("DR"):
        sign, t = -1.0, t[:-2].strip()
    elif t.upper().endswith("CR"):
        t = t[:-2].strip()
    try:
        return round(sign * float(t), 2)
    except ValueError:
        m = re.search(r"-?\d+(?:\.\d+)?", t)
        return round(sign * float(m.group()), 2) if m else 0.0


def rows(xml: str, tag: str) -> list[dict]:
    """Flatten <TAG NAME="x"><FIELD>v</FIELD>...</TAG> elements into dicts."""
    root = parse(xml)
    out = []
    for el in root.iter():
        if el.tag.upper() == tag.upper():
            d = {"NAME": el.attrib.get("NAME", "")}
            for ch in el:
                if len(ch) == 0:
                    d[ch.tag.upper()] = (ch.text or "").strip()
            out.append(d)
    return out


def import_result(xml: str) -> dict:
    """Pull CREATED / ALTERED / ERRORS / EXCEPTIONS counters out of an import reply."""
    def grab(name):
        m = re.search(rf"<{name}>\s*(-?\d+)\s*</{name}>", xml, re.I)
        return int(m.group(1)) if m else 0
    res = {k.lower(): grab(k) for k in ("CREATED", "ALTERED", "ERRORS", "EXCEPTIONS")}
    m = re.search(r"<LINEERROR>(.*?)</LINEERROR>", xml, re.I | re.S)
    res["line_error"] = m.group(1).strip() if m else ""
    res["ok"] = (res["created"] + res["altered"]) >= 1 and res["errors"] == 0 and res["exceptions"] == 0
    return res
