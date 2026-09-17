"""
Tests for scripts/run_vault_daily_watch.py -- orchestration only (config
parsing, per-watch fetch, alert-on-PASS-only). core/vault/gates.py's own
fail-closed contract is covered by tests/unit/test_vault_gates.py; here
audit_gate and send_telegram are mocked so these tests stay about what this
script does with their results, not the audit logic itself.
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import scripts.run_vault_daily_watch as mod  # noqa: E402
from core.vault.models import GateDecision, Verdict  # noqa: E402


class _FakeBroker:
    def __init__(self, connects=True, candles=None, raise_on_fetch=False):
        self._connects = connects
        self._candles = candles or []
        self._raise_on_fetch = raise_on_fetch

    def connect(self):
        return self._connects

    def get_historical_data(self, symbol, timeframe, from_date, to_date):
        if self._raise_on_fetch:
            raise RuntimeError("boom")
        return self._candles


def _config(watch_enabled=True, watches=None):
    return {"vault": {"watch_enabled": watch_enabled, "watches": watches or []}}


def test_disabled_by_config_does_nothing(monkeypatch):
    monkeypatch.setattr(mod, "load_config", lambda path: _config(watch_enabled=False))
    with patch.object(mod, "audit_gate") as audit, patch.object(mod, "send_telegram") as tg:
        assert mod.main() == 0
    audit.assert_not_called()
    tg.assert_not_called()


def test_enabled_with_no_watches_does_nothing(monkeypatch):
    monkeypatch.setattr(mod, "load_config", lambda path: _config(watch_enabled=True, watches=[]))
    with patch.object(mod, "audit_gate") as audit, patch.object(mod, "send_telegram") as tg:
        assert mod.main() == 0
    audit.assert_not_called()
    tg.assert_not_called()


def test_broker_connect_failure_returns_error(monkeypatch):
    watches = [{"note": "n1", "symbol": "NIFTY 50", "label": "Test"}]
    monkeypatch.setattr(mod, "load_config", lambda path: _config(watches=watches))
    monkeypatch.setattr(mod, "get_broker", lambda config: _FakeBroker(connects=False))
    assert mod.main() == 1


def test_pass_sends_exactly_one_telegram_alert(monkeypatch):
    watches = [{"note": "n1", "symbol": "NIFTY 50", "label": "Test Watch"}]
    monkeypatch.setattr(mod, "load_config", lambda path: _config(watches=watches))
    monkeypatch.setattr(mod, "get_broker", lambda config: _FakeBroker())

    pass_decision = GateDecision(allowed=True, verdict=Verdict.PASS, reason="all rules passed")
    with patch.object(mod, "audit_gate", return_value=pass_decision) as audit, \
         patch.object(mod, "send_telegram", new_callable=AsyncMock, return_value=True) as tg:
        assert mod.main() == 0

    audit.assert_called_once()
    tg.assert_called_once()
    sent_message = tg.call_args[0][0]
    assert "Test Watch" in sent_message
    assert "NIFTY 50" in sent_message
    assert "n1" in sent_message


def test_fail_sends_no_alert(monkeypatch):
    watches = [{"note": "n1", "symbol": "NIFTY 50", "label": "Test"}]
    monkeypatch.setattr(mod, "load_config", lambda path: _config(watches=watches))
    monkeypatch.setattr(mod, "get_broker", lambda config: _FakeBroker())

    fail_decision = GateDecision(allowed=False, verdict=Verdict.FAIL, reason="rule 1 rejected")
    with patch.object(mod, "audit_gate", return_value=fail_decision), \
         patch.object(mod, "send_telegram", new_callable=AsyncMock) as tg:
        assert mod.main() == 0
    tg.assert_not_called()


def test_unavailable_sends_no_alert(monkeypatch):
    # allowed=False AND verdict != PASS is the fail-closed default for
    # anything that isn't a clean pass -- covers UNAVAILABLE/disabled/missing.
    watches = [{"note": "n1", "symbol": "NIFTY 50", "label": "Test"}]
    monkeypatch.setattr(mod, "load_config", lambda path: _config(watches=watches))
    monkeypatch.setattr(mod, "get_broker", lambda config: _FakeBroker())

    unavailable = GateDecision(allowed=False, verdict=Verdict.UNAVAILABLE, reason="vault not found")
    with patch.object(mod, "audit_gate", return_value=unavailable), \
         patch.object(mod, "send_telegram", new_callable=AsyncMock) as tg:
        assert mod.main() == 0
    tg.assert_not_called()


def test_malformed_watch_entry_is_skipped_not_fatal(monkeypatch):
    watches = [{"note": "n1"}, {"symbol": "NIFTY 50"}, {}]  # each missing a required field
    monkeypatch.setattr(mod, "load_config", lambda path: _config(watches=watches))
    monkeypatch.setattr(mod, "get_broker", lambda config: _FakeBroker())

    with patch.object(mod, "audit_gate") as audit, \
         patch.object(mod, "send_telegram", new_callable=AsyncMock) as tg:
        assert mod.main() == 0
    audit.assert_not_called()
    tg.assert_not_called()


def test_history_fetch_failure_is_self_healing_not_fatal(monkeypatch):
    watches = [
        {"note": "n1", "symbol": "BROKEN", "label": "Broken"},
        {"note": "n2", "symbol": "NIFTY 50", "label": "Fine"},
    ]
    monkeypatch.setattr(mod, "load_config", lambda path: _config(watches=watches))

    def _get_historical_data(symbol, timeframe, from_date, to_date):
        if symbol == "BROKEN":
            raise RuntimeError("boom")
        return []

    broker = _FakeBroker()
    broker.get_historical_data = _get_historical_data
    monkeypatch.setattr(mod, "get_broker", lambda config: broker)

    pass_decision = GateDecision(allowed=True, verdict=Verdict.PASS, reason="ok")
    with patch.object(mod, "audit_gate", return_value=pass_decision) as audit, \
         patch.object(mod, "send_telegram", new_callable=AsyncMock, return_value=True) as tg:
        assert mod.main() == 0

    # Only the second (healthy) watch reaches audit_gate; the broken one is
    # logged and skipped rather than aborting the whole run.
    audit.assert_called_once()
    tg.assert_called_once()


def test_telegram_delivery_failure_is_logged_not_fatal(monkeypatch):
    watches = [{"note": "n1", "symbol": "NIFTY 50", "label": "Test"}]
    monkeypatch.setattr(mod, "load_config", lambda path: _config(watches=watches))
    monkeypatch.setattr(mod, "get_broker", lambda config: _FakeBroker())

    pass_decision = GateDecision(allowed=True, verdict=Verdict.PASS, reason="ok")
    with patch.object(mod, "audit_gate", return_value=pass_decision), \
         patch.object(mod, "send_telegram", new_callable=AsyncMock, return_value=False):
        assert mod.main() == 0
