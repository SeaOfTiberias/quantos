"""
PEAD Phase 1 — NSE Session/Fetch Client — Unit Tests

No real network calls here (see scripts/fetch_pead_fundamentals.py for the
live-tested driver) -- NseSession's session_factory is dependency-injected
with a fake requests.Session-alike, same pattern
tests/unit/test_vrp_bhavcopy.py uses for fetch_raw(session=...).
"""

from datetime import date

import pytest

from core.fundamentals.pead.nse_client import (
    NseSession,
    NseSessionError,
    fetch_financial_results_metadata,
    fetch_xbrl,
)


class _FakeResponse:
    def __init__(self, status_code, content=b"", json_data=None):
        self.status_code = status_code
        self.content = content
        self._json = json_data

    def json(self):
        return self._json


class _FakeRequestsSession:
    """One instance = one simulated requests.Session. `responses` is
    consumed in order across ALL .get() calls on this instance (page load
    first, then API calls)."""
    def __init__(self, responses):
        self._responses = list(responses)
        self.cookies = {}
        self.calls = []

    def get(self, url, headers=None, params=None, timeout=None):
        self.calls.append((url, params))
        resp = self._responses.pop(0)
        if resp.status_code == 200:
            self.cookies = {"nsit": "fake-session-cookie"}
        return resp


def _factory_returning(*sessions):
    """A session_factory that hands out pre-built fake sessions in order,
    one per bootstrap attempt -- mirrors NseSession calling
    self._session_factory() fresh on every retry."""
    it = iter(sessions)
    return lambda: next(it)


class TestBootstrap:
    def test_lazy_bootstrap_on_first_get(self):
        fake = _FakeRequestsSession([_FakeResponse(200)])
        nse = NseSession(_session_factory=_factory_returning(fake))
        sess = nse.get()
        assert sess is fake
        assert len(fake.calls) == 1

    def test_reuses_session_within_max_age(self):
        fake = _FakeRequestsSession([_FakeResponse(200)])
        nse = NseSession(_session_factory=_factory_returning(fake))
        nse.get()
        nse.get()
        # Only one page-load call even though .get() was called twice --
        # a second bootstrap would raise StopIteration on the exhausted
        # factory iterator.
        assert len(fake.calls) == 1

    def test_bootstrap_retries_on_non_200(self, monkeypatch):
        monkeypatch.setattr("core.fundamentals.pead.nse_client.time.sleep", lambda *_: None)
        bad = _FakeRequestsSession([_FakeResponse(403)])
        good = _FakeRequestsSession([_FakeResponse(200)])
        nse = NseSession(_session_factory=_factory_returning(bad, good))
        sess = nse.get()
        assert sess is good

    def test_bootstrap_gives_up_after_max_retries(self, monkeypatch):
        monkeypatch.setattr("core.fundamentals.pead.nse_client.time.sleep", lambda *_: None)
        sessions = [_FakeRequestsSession([_FakeResponse(403)]) for _ in range(3)]
        nse = NseSession(_session_factory=_factory_returning(*sessions))
        with pytest.raises(NseSessionError):
            nse.get()

    def test_force_refresh_bootstraps_again(self):
        first = _FakeRequestsSession([_FakeResponse(200)])
        second = _FakeRequestsSession([_FakeResponse(200)])
        nse = NseSession(_session_factory=_factory_returning(first, second))
        nse.get()
        refreshed = nse.force_refresh()
        assert refreshed is second


class TestFetchFinancialResultsMetadata:
    def test_returns_rows_on_success(self):
        page = _FakeRequestsSession([_FakeResponse(200)])
        rows = [{"symbol": "RELIANCE"}]
        page._responses.append(_FakeResponse(200, json_data=rows))
        nse = NseSession(_session_factory=_factory_returning(page))
        result = fetch_financial_results_metadata(nse, date(2024, 1, 1), date(2024, 1, 31))
        assert result == rows

    def test_symbol_param_uppercased(self):
        page = _FakeRequestsSession([_FakeResponse(200), _FakeResponse(200, json_data=[])])
        nse = NseSession(_session_factory=_factory_returning(page))
        fetch_financial_results_metadata(nse, date(2024, 1, 1), date(2024, 1, 31), symbol="reliance")
        api_call_params = page.calls[-1][1]
        assert api_call_params["symbol"] == "RELIANCE"

    def test_date_params_formatted_dd_mm_yyyy(self):
        page = _FakeRequestsSession([_FakeResponse(200), _FakeResponse(200, json_data=[])])
        nse = NseSession(_session_factory=_factory_returning(page))
        fetch_financial_results_metadata(nse, date(2024, 3, 5), date(2024, 3, 31))
        api_call_params = page.calls[-1][1]
        assert api_call_params["from_date"] == "05-03-2024"
        assert api_call_params["to_date"] == "31-03-2024"

    def test_non_list_response_returns_empty(self):
        page = _FakeRequestsSession([_FakeResponse(200), _FakeResponse(200, json_data={})])
        nse = NseSession(_session_factory=_factory_returning(page))
        result = fetch_financial_results_metadata(nse, date(2024, 1, 1), date(2024, 1, 31))
        assert result == []

    def test_401_forces_session_refresh_then_retries(self, monkeypatch):
        monkeypatch.setattr("core.fundamentals.pead.nse_client.time.sleep", lambda *_: None)
        stale_page = _FakeRequestsSession([_FakeResponse(200), _FakeResponse(401)])
        fresh_page = _FakeRequestsSession([_FakeResponse(200), _FakeResponse(200, json_data=[{"ok": 1}])])
        nse = NseSession(_session_factory=_factory_returning(stale_page, fresh_page))
        result = fetch_financial_results_metadata(nse, date(2024, 1, 1), date(2024, 1, 31))
        assert result == [{"ok": 1}]


class TestFetchXbrl:
    def test_returns_raw_bytes_on_success(self):
        page = _FakeRequestsSession([_FakeResponse(200), _FakeResponse(200, content=b"<xbrl/>")])
        nse = NseSession(_session_factory=_factory_returning(page))
        result = fetch_xbrl(nse, "https://nsearchives.nseindia.com/corporate/xbrl/x.xml")
        assert result == b"<xbrl/>"

    def test_raises_after_exhausting_retries(self, monkeypatch):
        monkeypatch.setattr("core.fundamentals.pead.nse_client.time.sleep", lambda *_: None)
        page = _FakeRequestsSession(
            [_FakeResponse(200)] + [_FakeResponse(500)] * 3
        )
        nse = NseSession(_session_factory=_factory_returning(page, page, page))
        with pytest.raises(NseSessionError):
            fetch_xbrl(nse, "https://nsearchives.nseindia.com/corporate/xbrl/x.xml", max_retries=3)
