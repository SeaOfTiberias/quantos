"""
Trade watcher (stage 1, alerts only) — exit rules and position handling.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

from core.trade_watcher.rules import ExitRules, ManagedPosition, is_option_symbol, on_tick, rearm

REPO_ROOT = Path(__file__).resolve().parents[2]
SYM = "NSE:BANKNIFTY26OCT54900CE"
RULES = ExitRules(initial_stop_pct=15, breakeven_at_pct=10, trail_after_pct=15, trail_pct=10)


def _pos(entry=100.0, qty=30):
    return ManagedPosition.open(SYM, entry, qty, RULES)


def _kinds(events):
    return [e.kind for e in events]


class TestRules:
    def test_initial_stop(self):
        assert _pos().stop == 85.0

    def test_stop_hit_fires_exit_once(self):
        p = _pos()
        assert _kinds(on_tick(p, 85.0, RULES)) == ["exit"]
        assert on_tick(p, 80.0, RULES) == []          # no repeat; reminders are the runner's job

    def test_breakeven_then_trail_then_ratchet(self):
        p = _pos()
        assert _kinds(on_tick(p, 110.0, RULES)) == ["breakeven"]
        assert p.stop == 100.0
        ev = on_tick(p, 120.0, RULES)                 # +20%: trail on, stop 108
        assert _kinds(ev) == ["trail_on"] and ev[0].stop == 108.0
        assert _kinds(on_tick(p, 130.0, RULES)) == ["stop_raised"]
        assert p.stop == 117.0
        assert on_tick(p, 125.0, RULES) == []         # pullback above stop: nothing
        assert p.stop == 117.0                        # never moves down
        ev = on_tick(p, 116.5, RULES)
        assert _kinds(ev) == ["exit"] and ev[0].stop == 117.0

    def test_exit_checked_against_stop_before_the_tick_raises_it(self):
        p = _pos()
        on_tick(p, 130.0, RULES)                      # stop now 117
        assert _kinds(on_tick(p, 117.0, RULES)) == ["exit"]

    def test_breakeven_lock_protects_profit(self):
        rules = ExitRules(initial_stop_pct=10, breakeven_at_pct=10, breakeven_lock_pct=5,
                          trail_after_pct=15, trail_pct=10)
        p = ManagedPosition.open(SYM, 100.0, 30, rules)
        assert _kinds(on_tick(p, 110.0, rules)) == ["breakeven"] and p.stop == 105.0
        assert _kinds(on_tick(p, 115.0, rules)) == ["trail_on"]
        assert p.stop == 105.0                        # trail (103.5) below the lock: lock holds
        assert _kinds(on_tick(p, 120.0, rules)) == ["stop_raised"] and p.stop == 108.0
        assert _kinds(on_tick(p, 104.0, rules)) == ["exit"]

    def test_breakeven_off(self):
        rules = ExitRules(initial_stop_pct=15, breakeven_at_pct=0, trail_after_pct=50, trail_pct=10)
        p = ManagedPosition.open(SYM, 100.0, 30, rules)
        assert on_tick(p, 140.0, rules) == [] and p.stop == 85.0

    def test_rearm_after_trailed_exit_resets_high(self):
        p = _pos()
        on_tick(p, 130.0, RULES)                      # trailing, stop 117
        on_tick(p, 115.0, RULES)                      # exit alerted
        assert rearm(p, RULES) == 97.75               # 15% below 115
        assert p.high == 115.0 and not p.exit_alerted
        assert _kinds(on_tick(p, 118.0, RULES)) == ["stop_raised"]
        assert p.stop == 106.2                       # trails off the new high, not the old 130

    def test_rearm_needs_a_price(self):
        assert rearm(_pos(), RULES) is None

    def test_bad_ticks_ignored(self):
        p = _pos()
        assert on_tick(p, 0, RULES) == [] and on_tick(p, None, RULES) == []

    def test_state_round_trip(self):
        p = _pos()
        on_tick(p, 130.0, RULES)
        q = ManagedPosition.from_dict(p.to_dict())
        assert (q.stop, q.high, q.trail_on) == (117.0, 130.0, True)

    def test_config_defaults_and_overrides(self):
        r = ExitRules.from_config({"trail_pct": 8})
        assert r.trail_pct == 8.0 and r.initial_stop_pct == 15.0

    @pytest.mark.parametrize("sym, ok", [(SYM, True), ("NSE:KOTAKBANK26OCT430PE", True),
                                         ("NSE:KOTAKBANK-EQ", False), ("NSE:NIFTY26OCTFUT", False)])
    def test_option_symbols(self, sym, ok):
        assert is_option_symbol(sym) is ok


def _load_runner():
    spec = importlib.util.spec_from_file_location("run_trade_watcher", REPO_ROOT / "scripts" / "run_trade_watcher.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["run_trade_watcher"] = mod
    spec.loader.exec_module(mod)
    return mod


class _FakeNotifier:
    def __init__(self):
        self.sent = []

    def send(self, text):
        self.sent.append(text)


@pytest.fixture
def watcher(tmp_path):
    mod = _load_runner()
    n = _FakeNotifier()
    w = mod.Watcher(RULES, n, state_path=tmp_path / "state.json")
    return w, n, mod


class TestWatcher:
    def test_new_long_option_is_managed(self, watcher):
        w, n, _ = watcher
        w.on_position({"symbol": SYM, "netQty": 30, "netAvg": 100.0})
        assert SYM in w.positions
        assert "Managing" in n.sent[0] and "85.00" in n.sent[0]

    def test_equity_and_short_positions_not_managed(self, watcher):
        w, n, _ = watcher
        w.on_position({"symbol": "NSE:KOTAKBANK-EQ", "netQty": 10, "netAvg": 430})
        w.on_position({"symbol": SYM, "netQty": -30, "netAvg": 100.0})
        w.on_position({"symbol": SYM, "netQty": -30, "netAvg": 100.0})
        assert w.positions == {} and len(n.sent) == 1 and "not managed" in n.sent[0]

    def test_flat_position_closes_with_realized_pnl(self, watcher):
        w, n, _ = watcher
        w.on_position({"symbol": SYM, "netQty": 30, "netAvg": 100.0})
        w.on_position({"symbol": SYM, "netQty": 0, "realized_profit": 817.5})
        assert w.positions == {}
        assert "closed" in n.sent[-1] and "818" in n.sent[-1]

    def test_tick_exit_alert(self, watcher):
        w, n, _ = watcher
        w.on_position({"symbol": SYM, "netQty": 30, "netAvg": 100.0})
        w.on_tick(SYM, 84.0)
        assert "EXIT NOW" in n.sent[-1] and "-480" in n.sent[-1]

    def test_stop_raises_are_throttled_into_housekeeping(self, watcher, monkeypatch):
        w, n, mod = watcher
        w.on_position({"symbol": SYM, "netQty": 30, "netAvg": 100.0})
        w.on_tick(SYM, 120.0)                          # trail_on message sent now
        for px in (125.0, 130.0, 135.0):
            w.on_tick(SYM, px)
        before = len(n.sent)
        w.tick_housekeeping()                          # within 120 s of trail_on: held back
        assert len(n.sent) == before
        monkeypatch.setattr(mod, "RAISE_NOTIFY_EVERY_S", 0)
        w.tick_housekeeping()
        assert len(n.sent) == before + 1 and "121.50" in n.sent[-1]   # one message, latest stop

    def test_restart_resumes_saved_stop(self, watcher, tmp_path):
        w, n, mod = watcher
        w.on_position({"symbol": SYM, "netQty": 30, "netAvg": 100.0})
        w.on_tick(SYM, 130.0)
        w2 = mod.Watcher(RULES, _FakeNotifier(), state_path=tmp_path / "state.json")
        w2.on_position({"symbol": SYM, "netQty": 30, "netAvg": 100.0})
        assert w2.positions[SYM].stop == 117.0

    def test_ignored_exit_rearms_after_reminders(self, watcher, monkeypatch):
        w, n, mod = watcher
        monkeypatch.setattr(mod, "EXIT_REMINDER_EVERY_S", 0)
        w.on_position({"symbol": SYM, "netQty": 30, "netAvg": 100.0})
        w.on_tick(SYM, 84.0)                           # EXIT NOW at stop 85
        w.on_tick(SYM, 80.0)
        for _ in range(mod.EXIT_REMINDERS):
            w.tick_housekeeping()
        assert sum("Still open" in m for m in n.sent) == mod.EXIT_REMINDERS
        w.tick_housekeeping()                          # reminders spent: re-arm, not silence
        p = w.positions[SYM]
        assert "Fresh stop 68.00" in n.sent[-1] and p.stop == 68.0 and not p.exit_alerted
        assert SYM not in w.exit_reminders
        w.on_tick(SYM, 67.0)                           # the further fall is caught
        assert "EXIT NOW" in n.sent[-1] and "68.00" in n.sent[-1]

    def test_closed_during_reminders_drops_them(self, watcher, monkeypatch):
        w, n, mod = watcher
        monkeypatch.setattr(mod, "EXIT_REMINDER_EVERY_S", 0)
        w.on_position({"symbol": SYM, "netQty": 30, "netAvg": 100.0})
        w.on_tick(SYM, 84.0)
        w.on_position({"symbol": SYM, "netQty": 0, "realized_profit": -480})
        before = len(n.sent)
        w.tick_housekeeping()
        assert len(n.sent) == before and w.exit_reminders == {}

    def test_rest_session_gets_default_timeout(self, watcher):
        _, _, mod = watcher
        seen = {}

        class _Session:
            def request(self, method, url, **kw):
                seen.update(kw)

        s = mod.with_default_timeout(_Session(), 7)
        s.request("GET", "u")
        assert seen["timeout"] == 7
        s.request("GET", "u", timeout=1)
        assert seen["timeout"] == 1

    def test_unrelated_untracked_tick_ignored(self, watcher):
        w, n, _ = watcher
        w.on_tick("NSE:NIFTY26OCT25000CE", 50.0)
        assert n.sent == []


class TestQuantosTagSkip:
    def test_strategy_tagged_position_is_not_managed(self, watcher):
        w, n, _ = watcher
        w.tag_lookup = lambda s: "orbBANKNIFTY20261008"
        w.on_position({"symbol": SYM, "netQty": 30, "netAvg": 100.0})
        w.on_position({"symbol": SYM, "netQty": 30, "netAvg": 100.0})
        assert w.positions == {} and SYM in w.system_symbols and n.sent == []

    def test_manual_position_still_managed(self, watcher):
        w, n, _ = watcher
        w.tag_lookup = lambda s: None
        w.on_position({"symbol": SYM, "netQty": 30, "netAvg": 100.0})
        assert SYM in w.positions

    def test_lookup_failure_falls_back_to_managing(self, watcher):
        w, n, _ = watcher
        def boom(s):
            raise RuntimeError("tradebook down")
        w.tag_lookup = boom
        w.on_position({"symbol": SYM, "netQty": 30, "netAvg": 100.0})
        assert SYM in w.positions

    def test_tag_from_tradebook(self, watcher):
        _, _, mod = watcher
        trades = [
            {"symbol": SYM, "side": -1, "orderTag": "orbBANKNIFTYexit"},   # a sell: ignored
            {"symbol": "NSE:NIFTY26OCT25000CE", "side": 1, "orderTag": "orbNIFTY"},
            {"symbol": SYM, "side": 1, "orderTag": ""},                      # manual buy
        ]
        assert mod.tag_from_tradebook(trades, SYM) is None
        trades.append({"symbol": SYM, "side": 1, "orderTag": "darvasatrstopX"})
        assert mod.tag_from_tradebook(trades, SYM) == "darvasatrstopX"

    @pytest.mark.parametrize("tag, ok", [("quantos", True), ("ORBnifty", True), ("rotationpilot", True),
                                         ("", False), (None, False), ("TV12345", False)])
    def test_is_quantos_tag(self, watcher, tag, ok):
        _, _, mod = watcher
        assert mod.is_quantos_tag(tag) is ok
