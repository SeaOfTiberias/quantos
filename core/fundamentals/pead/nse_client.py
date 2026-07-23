"""
QuantOS — PEAD Phase 1: NSE Corporate-Financial-Results Client
────────────────────────────────────────────────────────────────
Thin client for the two NSE endpoints the PEAD data pipeline needs (see
memory: quantos-pead-earnings-feasibility for the original feasibility
check, confirmed live 2026-07-23, not assumed from docs):

  - GET /api/corporates-financial-results -- filing METADATA (broadcast/
    disclosure date, the quarter covered, consolidated/audited flags, and
    an `xbrl` link). No PAT figure here. Works with or without a `symbol`
    filter -- omitting it returns every NSE-listed company's filings
    broadcast in the date window (confirmed: a 2-month window returned
    ~3,700 rows / ~2,100 symbols, no truncation), which is what
    core.fundamentals.pead.pipeline uses for bulk discovery instead of
    500 sequential per-symbol pulls.
  - The `xbrl` link itself -- a directly fetchable XML file (once
    `format == "New"`; `"Old"` rows have a dead placeholder link and
    carry no extractable PAT). See core.fundamentals.pead.xbrl for parsing.

NSE sits behind Akamai bot protection: a bare request 403s even with a
full browser User-Agent. The fix (confirmed live) is mundane -- load the
actual corporate-filings page with a realistic header set to get a real
session cookie, then reuse that cookie + a matching Referer on the API
calls. No login, no API key, no captcha involved.
"""

from __future__ import annotations

import logging
import time
from datetime import date
from typing import Any, Callable, Optional

import requests

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

_BASE_URL = "https://www.nseindia.com"
_FILINGS_PAGE_URL = f"{_BASE_URL}/companies-listing/corporate-filings-financial-results"
_RESULTS_API_URL = f"{_BASE_URL}/api/corporates-financial-results"

# The page-load response's Set-Cookie carries a ~2hr Max-Age (nsit cookie);
# refresh proactively rather than waiting for a 401/403 mid-run so a long
# bulk-discovery pass (see pipeline.py) doesn't stall on an expired session.
SESSION_MAX_AGE_SECONDS = 5400  # 90 min, under the observed 2hr cookie TTL

_PAGE_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "none",
    "Upgrade-Insecure-Requests": "1",
}

_API_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json, text/plain, */*",
    "Referer": _FILINGS_PAGE_URL,
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
}


class NseSessionError(Exception):
    """Raised when NSE won't hand out a working session (Akamai block,
    network failure) after retries -- distinct from a normal empty result."""


class NseSession:
    """A bootstrapped requests.Session against nseindia.com, with
    proactive self-refresh. Callers should hold one instance across a
    whole pipeline run rather than re-bootstrapping per request."""

    def __init__(self, _session_factory: Callable[[], Any] = requests.Session) -> None:
        # _session_factory is DI for tests only (see tests/unit/test_pead_nse_client.py)
        # -- production code always uses the default requests.Session.
        self._session_factory = _session_factory
        self._session: Optional[requests.Session] = None
        self._bootstrapped_at: float = 0.0

    def _bootstrap(self, max_retries: int = 3) -> requests.Session:
        last_exc: Optional[Exception] = None
        for attempt in range(max_retries):
            sess = self._session_factory()
            try:
                resp = sess.get(_FILINGS_PAGE_URL, headers=_PAGE_HEADERS, timeout=30)
            except requests.RequestException as e:
                last_exc = e
                time.sleep(1.5 * (attempt + 1))
                continue
            if resp.status_code == 200 and sess.cookies:
                self._bootstrapped_at = time.monotonic()
                return sess
            last_exc = RuntimeError(
                f"session bootstrap -> HTTP {resp.status_code}, "
                f"{len(sess.cookies)} cookies"
            )
            time.sleep(1.5 * (attempt + 1))
        raise NseSessionError(f"could not bootstrap NSE session after {max_retries} attempts: {last_exc}")

    def get(self) -> requests.Session:
        stale = (
            self._session is None
            or time.monotonic() - self._bootstrapped_at > SESSION_MAX_AGE_SECONDS
        )
        if stale:
            self._session = self._bootstrap()
        return self._session

    def force_refresh(self) -> requests.Session:
        self._session = self._bootstrap()
        return self._session


def _get_json(
    nse: NseSession, url: str, params: dict[str, Any], *, max_retries: int = 3,
) -> Any:
    last_exc: Optional[Exception] = None
    for attempt in range(max_retries):
        sess = nse.get()
        try:
            resp = sess.get(url, params=params, headers=_API_HEADERS, timeout=30)
        except requests.RequestException as e:
            last_exc = e
            time.sleep(1.5 * (attempt + 1))
            continue
        if resp.status_code in (401, 403):
            # Session likely expired/blocked mid-run; force one fresh
            # bootstrap and retry rather than burning all attempts on a
            # dead cookie.
            nse.force_refresh()
            last_exc = RuntimeError(f"{url} -> HTTP {resp.status_code} (session refreshed, retrying)")
            time.sleep(1.5 * (attempt + 1))
            continue
        if resp.status_code != 200:
            last_exc = RuntimeError(f"{url} -> HTTP {resp.status_code}")
            time.sleep(1.5 * (attempt + 1))
            continue
        return resp.json()
    raise NseSessionError(f"failed to fetch {url} after {max_retries} attempts: {last_exc}")


def fetch_financial_results_metadata(
    nse: NseSession,
    from_date: date,
    to_date: date,
    *,
    symbol: Optional[str] = None,
    segment: str = "equities",
    period: str = "Quarterly",
) -> list[dict[str, Any]]:
    """One page of filing-metadata rows broadcast in [from_date, to_date].

    Omitting `symbol` returns every NSE-listed company's filings in the
    window (confirmed: no pagination/truncation up to a 2-month window in
    this session's testing) -- callers doing bulk discovery across years
    should chunk by date, not by symbol, and should keep chunks to roughly
    a month or less until a real production run has confirmed a bigger
    window is still complete.
    """
    params = {
        "index": segment,
        "period": period,
        "from_date": from_date.strftime("%d-%m-%Y"),
        "to_date": to_date.strftime("%d-%m-%Y"),
    }
    if symbol:
        params["symbol"] = symbol.upper()
    result = _get_json(nse, _RESULTS_API_URL, params)
    return result if isinstance(result, list) else []


def fetch_xbrl(nse: NseSession, xbrl_url: str, *, max_retries: int = 3) -> bytes:
    """Fetch one filing's raw XBRL XML. Raises NseSessionError if the URL
    is unreachable after retries -- callers should treat a bad/placeholder
    URL (see core.fundamentals.pead.xbrl) as a separate, expected case,
    not something that should reach this function at all."""
    last_exc: Optional[Exception] = None
    for attempt in range(max_retries):
        sess = nse.get()
        try:
            resp = sess.get(xbrl_url, headers=_API_HEADERS, timeout=30)
        except requests.RequestException as e:
            last_exc = e
            time.sleep(1.5 * (attempt + 1))
            continue
        if resp.status_code in (401, 403):
            nse.force_refresh()
            last_exc = RuntimeError(f"{xbrl_url} -> HTTP {resp.status_code} (session refreshed, retrying)")
            time.sleep(1.5 * (attempt + 1))
            continue
        if resp.status_code != 200:
            last_exc = RuntimeError(f"{xbrl_url} -> HTTP {resp.status_code}")
            time.sleep(1.5 * (attempt + 1))
            continue
        return resp.content
    raise NseSessionError(f"failed to fetch {xbrl_url} after {max_retries} attempts: {last_exc}")
