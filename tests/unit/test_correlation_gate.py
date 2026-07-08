"""S5-5 — agent-side correlation gate + cloud sync-for-display route."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import agent.main as agent_main
from core.risk.correlation import PortfolioCheckResult, CorrelationResult


# ── Fixtures / helpers ────────────────────────────────────────────────────────

class _FakeCorrService:
    """Stand-in for CorrelationPortfolioService with a preset result."""
    def __init__(self, result=None, raises=False):
        self._result = result
        self._raises = raises
        self.called_with = None

    async def check_candidate(self, symbol, open_symbols, threshold):
        self.called_with = (symbol, list(open_symbols), threshold)
        if self._raises:
            raise RuntimeError("history fetch blew up")
        return self._result


def _positions(*symbols):
    return {f"sig{i}": SimpleNamespace(symbol=s) for i, s in enumerate(symbols)}


def _blocked_result():
    return PortfolioCheckResult(
        candidate_symbol="HDFCBANK", is_blocked=True, max_correlation=0.82,
        correlated_with=[CorrelationResult("HDFCBANK", "ICICIBANK", 0.82, 40, True)],
    )


def _clear_result():
    return PortfolioCheckResult(
        candidate_symbol="TATASTEEL", is_blocked=False, max_correlation=0.21,
    )


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Stub the cloud sync POST so no real request goes out; capture calls."""
    post = MagicMock(return_value=MagicMock(raise_for_status=lambda: None))
    monkeypatch.setattr(agent_main.requests, "post", post)
    return post


# ── Agent gate decision (_correlation_refusal_reason) ─────────────────────────

def test_disabled_gate_returns_none(_no_network):
    assert agent_main._correlation_refusal_reason(
        None, "HDFCBANK", _positions("ICICIBANK"), 0.75, "http://c", {}) is None
    _no_network.assert_not_called()


def test_no_open_positions_skips_check(_no_network):
    svc = _FakeCorrService(_clear_result())
    assert agent_main._correlation_refusal_reason(
        svc, "HDFCBANK", {}, 0.75, "http://c", {}) is None
    assert svc.called_with is None       # never bothered the broker
    _no_network.assert_not_called()      # nothing to display


def test_blocked_entry_is_refused_and_synced(_no_network):
    svc = _FakeCorrService(_blocked_result())
    reason = agent_main._correlation_refusal_reason(
        svc, "HDFCBANK", _positions("ICICIBANK"), 0.75, "http://c", {"X": "1"})
    assert reason is not None
    assert reason.startswith("REFUSED by correlation gate")
    assert "ICICIBANK" in reason
    # candidate excludes itself already handled by the service; we passed it the
    # open symbols and the configured threshold.
    assert svc.called_with == ("HDFCBANK", ["ICICIBANK"], 0.75)
    # Decision was pushed to the cloud for display.
    url = _no_network.call_args[0][0]
    body = _no_network.call_args[1]["json"]
    assert url.endswith("/correlation/sync")
    assert body["is_blocked"] is True and body["candidate_symbol"] == "HDFCBANK"
    assert body["correlated_with"] == ["ICICIBANK"]


def test_uncorrelated_entry_allowed_but_still_synced(_no_network):
    svc = _FakeCorrService(_clear_result())
    reason = agent_main._correlation_refusal_reason(
        svc, "TATASTEEL", _positions("ICICIBANK"), 0.75, "http://c", {})
    assert reason is None
    _no_network.assert_called_once()                 # allowed decisions display too
    assert _no_network.call_args[1]["json"]["is_blocked"] is False


def test_check_error_fails_open(_no_network):
    svc = _FakeCorrService(raises=True)
    reason = agent_main._correlation_refusal_reason(
        svc, "HDFCBANK", _positions("ICICIBANK"), 0.75, "http://c", {})
    assert reason is None                             # allow, don't drop the trade
    _no_network.assert_not_called()                  # no result to sync


# ── Cloud sync/status route ───────────────────────────────────────────────────

@pytest.fixture
def client():
    from cloud.api.main import app
    from cloud.api import correlation_routes
    correlation_routes._reset()
    yield TestClient(app)
    correlation_routes._reset()


def _decision(symbol="HDFCBANK", blocked=True):
    return {
        "candidate_symbol": symbol, "is_blocked": blocked,
        "max_correlation": 0.82, "correlated_with": ["ICICIBANK"],
        "reason": "High correlation with: ICICIBANK (+0.82)",
        "checked_at": "2026-07-08T10:00:00+00:00",
    }


def test_status_empty(client):
    body = client.get("/correlation/status").json()
    assert body["decisions"] == []
    assert body["updated_at"] is None
    assert body["threshold"] == 0.75


def test_sync_then_status_roundtrip(client):
    assert client.post("/correlation/sync", json=_decision()).json() == {"synced": True}
    body = client.get("/correlation/status").json()
    assert len(body["decisions"]) == 1
    assert body["decisions"][0]["candidate_symbol"] == "HDFCBANK"
    assert body["decisions"][0]["is_blocked"] is True
    assert body["updated_at"] is not None


def test_status_feed_is_capped_newest_last(client):
    for i in range(25):
        client.post("/correlation/sync", json=_decision(symbol=f"SYM{i}"))
    decisions = client.get("/correlation/status").json()["decisions"]
    assert len(decisions) == 20                       # rolling window cap
    assert decisions[-1]["candidate_symbol"] == "SYM24"
    assert decisions[0]["candidate_symbol"] == "SYM5"
