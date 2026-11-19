"""HTTP/XML gateway to TallyPrime (default localhost:9000).

Rules learned the hard way:
* Reads may be retried. Imports must NEVER be retried automatically, a retry after a
  dropped connection can create a duplicate voucher.
* Tally drops connections under load (WinError 10054). Callers ask for one day or one
  ledger at a time and the reads here retry with backoff.
"""
from __future__ import annotations

import re
import time
import urllib.error
import urllib.request

_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]|&#(?:[0-8]|1[1-2]|1[4-9]|2[0-9]|3[0-1]);")


class GatewayError(RuntimeError):
    pass


def clean(xml: str) -> str:
    """Tally sometimes emits control characters that break XML parsers."""
    return _CTRL.sub("", xml)


class TallyGateway:
    def __init__(self, host="localhost", port=9000, timeout=30, retries=4, backoff=1.5):
        self.host, self.port = host, int(port)
        self.timeout, self.retries, self.backoff = timeout, retries, backoff

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def ping(self) -> bool:
        try:
            with urllib.request.urlopen(self.url, timeout=min(self.timeout, 8)) as r:
                return "tally" in r.read().decode("utf-8", "replace").lower()
        except Exception:
            return False

    def post(self, xml: str, *, retry: bool = True) -> str:
        data = xml.encode("utf-8")
        attempts = self.retries if retry else 1
        last: Exception | None = None
        for i in range(attempts):
            try:
                req = urllib.request.Request(
                    self.url, data=data, headers={"Content-Type": "text/xml; charset=utf-8"})
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    return clean(r.read().decode("utf-8", "replace"))
            except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as e:
                last = e
                if i + 1 < attempts:
                    time.sleep(self.backoff * (i + 1))
        raise GatewayError(
            f"Could not reach TallyPrime at {self.url} ({last}). Check that Tally is open, a company "
            "is loaded, no dialog box is waiting for a key press, and F1 > Settings > Connectivity "
            "is set to Server or Both on this port.")
