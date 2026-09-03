"""
Tests for scripts/probe_orb_scalping_stopout_spreads.py's pure helpers --
the trigger-decision rule and the fixed-strike chain lookup -- the parts
of the event-triggered spread probe that don't need a live broker.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.probe_orb_scalping_stopout_spreads import (  # noqa: E402
    _fetch_chain_row,
    _spread_fields,
    decide_trigger,
)


# ─── decide_trigger ──────────────────────────────────────────────────────

def test_no_trigger_when_nothing_fired():
    assert decide_trigger(index_triggered=False, candle_confirmed_stop=False,
                           premium_triggered=False, armed=True,
                           candle_exit_reason=None) is None


def test_index_level_ltp_cross_while_armed_is_trailing_stop():
    assert decide_trigger(index_triggered=True, candle_confirmed_stop=False,
                           premium_triggered=False, armed=True,
                           candle_exit_reason=None) == "trailing_stop"


def test_index_level_ltp_cross_while_not_armed_is_plain_stop():
    assert decide_trigger(index_triggered=True, candle_confirmed_stop=False,
                           premium_triggered=False, armed=False,
                           candle_exit_reason=None) == "stop"


def test_premium_only_trigger_is_premium_stop():
    assert decide_trigger(index_triggered=False, candle_confirmed_stop=False,
                           premium_triggered=True, armed=True,
                           candle_exit_reason=None) == "premium_stop"


def test_candle_close_fallback_used_when_ltp_missed_it():
    # A closed candle already crossed the stop (e.g. a missed fire) but
    # this fire's own live LTP read didn't itself confirm the cross --
    # falls back to the candle-close-confirmed reason.
    assert decide_trigger(index_triggered=False, candle_confirmed_stop=True,
                           premium_triggered=False, armed=True,
                           candle_exit_reason="trailing_stop") == "trailing_stop"


def test_index_side_wins_over_premium_when_both_fire_same_fire():
    # core/orb_scalping/premium.py's own tie-break is "premium stop wins on
    # the SAME candle" for the backtest's candle-by-candle walk; here, an
    # index-level cross is a real-time LTP observation (more certain than
    # the candle-close-only premium check), so it takes priority instead.
    assert decide_trigger(index_triggered=True, candle_confirmed_stop=False,
                           premium_triggered=True, armed=False,
                           candle_exit_reason=None) == "stop"


# ─── _fetch_chain_row ────────────────────────────────────────────────────

def _row(strike, option_type, bid=10.0, ask=11.0, ltp=10.5):
    return {"strike_price": strike, "option_type": option_type, "bid": bid, "ask": ask, "ltp": ltp}


class _FakeBroker:
    def __init__(self, rows):
        self._rows = rows

    def get_option_chain(self, underlying, expiry_epoch):
        return {"optionsChain": self._rows}


def test_fetch_chain_row_finds_exact_strike(monkeypatch):
    import scripts.probe_orb_scalping_stopout_spreads as mod
    monkeypatch.setattr(mod.sm, "get_expiry_epoch", lambda *a, **k: 123)
    rows = [_row(24000.0, "CE"), _row(24050.0, "CE"), _row(24050.0, "PE")]
    broker = _FakeBroker(rows)
    from datetime import date
    row = mod._fetch_chain_row(broker, "NIFTY", date(2026, 9, 4), 24050.0, "CE", 50.0)
    assert row["strike_price"] == 24050.0
    assert row["option_type"] == "CE"


def test_fetch_chain_row_returns_none_when_too_far_from_any_listed_strike(monkeypatch):
    import scripts.probe_orb_scalping_stopout_spreads as mod
    monkeypatch.setattr(mod.sm, "get_expiry_epoch", lambda *a, **k: 123)
    rows = [_row(23000.0, "CE")]  # 1050pt away -- nowhere near a 50pt-interval match
    broker = _FakeBroker(rows)
    from datetime import date
    row = mod._fetch_chain_row(broker, "NIFTY", date(2026, 9, 4), 24050.0, "CE", 50.0)
    assert row is None


def test_fetch_chain_row_returns_none_when_option_type_absent(monkeypatch):
    import scripts.probe_orb_scalping_stopout_spreads as mod
    monkeypatch.setattr(mod.sm, "get_expiry_epoch", lambda *a, **k: 123)
    rows = [_row(24050.0, "PE")]  # only PE listed, caller wants CE
    broker = _FakeBroker(rows)
    from datetime import date
    row = mod._fetch_chain_row(broker, "NIFTY", date(2026, 9, 4), 24050.0, "CE", 50.0)
    assert row is None


# ─── _spread_fields ──────────────────────────────────────────────────────

def test_spread_fields_computes_pct_of_mid():
    fields = _spread_fields({"bid": 10.0, "ask": 11.0, "ltp": 10.4})
    assert fields["spread_pct_of_mid"] == round((11.0 - 10.0) / 10.5 * 100, 3)


def test_spread_fields_blank_when_no_two_sided_quote():
    fields = _spread_fields({"bid": 0, "ask": 12.0, "ltp": 0})
    assert fields["spread_pct_of_mid"] == ""


# ─── End-to-end: probe_underlying() against a fake broker ──────────────────

class _FullFakeBroker:
    """Enough of BrokerAdapter's surface for probe_underlying(): candles
    that produce a known live_state, a movable spot LTP, and an option
    chain with one CE/PE pair at the ATM strike."""

    def __init__(self, candles, spot_ltp, chain_ltp):
        self._candles = candles
        self.spot_ltp = spot_ltp
        self.chain_ltp = chain_ltp

    def get_historical_data(self, symbol, timeframe, from_date, to_date):
        return [c for c in self._candles if c.timestamp <= to_date]

    def get_ltp(self, symbols):
        return {s: self.spot_ltp for s in symbols}

    def get_option_chain(self, underlying, expiry_epoch):
        return {"optionsChain": [
            {"strike_price": 24000.0, "option_type": "CE", "bid": self.chain_ltp - 0.5,
             "ask": self.chain_ltp + 0.5, "ltp": self.chain_ltp},
            {"strike_price": 24000.0, "option_type": "PE", "bid": self.chain_ltp - 0.5,
             "ask": self.chain_ltp + 0.5, "ltp": self.chain_ltp},
        ]}


def _make_day_candles():
    from datetime import datetime, timedelta, timezone
    from core.brokers.base import OHLCV
    start = datetime(2026, 9, 3, 3, 45, tzinfo=timezone.utc)  # 09:15 IST

    def bar(i, o, h, l, c):
        return OHLCV(timestamp=start + timedelta(minutes=5 * i), open=o, high=h, low=l, close=c, volume=1000)

    candles = [bar(i, 24000, 24001, 23999, 24000) for i in range(3)]  # opening range: 23999-24001
    candles[0] = bar(0, 24000, 24001, 23999, 24000)
    candles.append(bar(3, 24000, 24010, 23999, 24005))  # breakout close above 24001 -> CALL pending
    candles.append(bar(4, 24005, 24006, 24004, 24005))  # entry executes at this candle's open (24005)
    return candles, start


def _run(monkeypatch, tmp_path, broker, now_utc, event_writer_fields=None):
    import csv
    import scripts.probe_orb_scalping_stopout_spreads as mod
    log_path = tmp_path / "stopout.csv"
    monkeypatch.setattr(mod, "LOG_PATH", log_path)
    monkeypatch.setattr(mod, "datetime", _FrozenDatetime(now_utc))
    monkeypatch.setattr(mod.sm, "list_expiries", lambda underlying: [now_utc.date()])
    monkeypatch.setattr(mod.sm, "get_expiry_epoch", lambda *a, **k: 1)
    monkeypatch.setattr(mod, "select_expiry", lambda expiries, today, dte_floor_days: expiries[0])

    is_new = not log_path.exists()
    with log_path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=mod.LOG_FIELDS)
        if is_new:
            writer.writeheader()
        mod.probe_underlying(broker, "NIFTY", "NIFTY 50", 0, 50.0, writer)

    if log_path.exists():
        return list(csv.DictReader(log_path.open(newline="", encoding="utf-8")))
    return []


class _FrozenDatetime:
    """Stands in for the `datetime` class inside the probe module so
    datetime.now(timezone.utc) returns a fixed instant, while
    datetime.combine/fromisoformat still work (delegated to the real
    class) -- probe_underlying uses all three."""

    def __init__(self, frozen):
        self._frozen = frozen

    def now(self, tz=None):
        return self._frozen

    def combine(self, *a, **k):
        from datetime import datetime
        return datetime.combine(*a, **k)

    def fromisoformat(self, *a, **k):
        from datetime import datetime
        return datetime.fromisoformat(*a, **k)


def test_probe_underlying_captures_entry_then_exit_on_stop_cross(monkeypatch, tmp_path):
    from datetime import timedelta

    candles, start = _make_day_candles()
    # The entry candle (index 4) must itself be CLOSED before
    # compute_live_state() will report "in_position" -- i.e. wall-clock
    # must be past its own open time + 5 minutes.
    now_at_entry = candles[-1].timestamp + timedelta(minutes=5, seconds=30)

    broker = _FullFakeBroker(candles, spot_ltp=24005.0, chain_ltp=50.0)
    rows = _run(monkeypatch, tmp_path, broker, now_at_entry)
    assert len(rows) == 1
    assert rows[0]["event"] == "entry"
    assert rows[0]["direction"] == "CALL"
    assert float(rows[0]["entry_premium"]) == 50.0

    # Now the index LTP crosses below the initial stop (opening-range low,
    # 23999.0) -- next fire should capture the real-time stop-out spread.
    now_at_stop = now_at_entry + timedelta(minutes=1)
    broker.spot_ltp = 23990.0
    rows = _run(monkeypatch, tmp_path, broker, now_at_stop)
    assert len(rows) == 2
    assert rows[1]["event"] == "exit"
    assert rows[1]["trigger_reason"] == "stop"
    assert rows[1]["spread_pct_of_mid"] != ""

    # A third fire must NOT log a second exit for the same trade.
    now_later = now_at_stop + timedelta(minutes=1)
    rows = _run(monkeypatch, tmp_path, broker, now_later)
    assert len(rows) == 2
