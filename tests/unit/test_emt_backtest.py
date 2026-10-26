"""core/emt/backtest.py -- hand-built 5-minute days, one rule per test."""

from datetime import datetime, timezone

from core.brokers.base import OHLCV
from core.emt.backtest import IST, Bar, build_bars, metrics, run_day


def t(hh, mm):
    return datetime(2026, 10, 26, hh, mm, tzinfo=IST)


def bar(hh, mm, o, h, l, c, vwap=100.0, ema9=105.0, atr=10.0):
    return Bar(t(hh, mm), o, h, l, c, vwap, ema9, atr)


def stretch_then_turn(start=(10, 0), after=None):
    """Flat at the mean, a stretch up to 121 (2 ATR), then a bar closing lower = short signal."""
    hh, mm = start
    day = [bar(hh, mm, 100, 101, 99, 100),
           bar(hh, mm + 5, 100, 121, 100, 120),
           bar(hh, mm + 10, 120, 122, 115, 116)]
    return day + ([bar(hh, mm + 15, *after)] if after else [])


def test_vwap_is_ohlc4_weighted_by_futures_volume():
    ts = [datetime(2026, 10, 26, 3, 45, tzinfo=timezone.utc), datetime(2026, 10, 26, 3, 50, tzinfo=timezone.utc)]
    idx = [OHLCV(ts[0], 10, 10, 10, 10, 0), OHLCV(ts[1], 20, 20, 20, 20, 0)]
    fut = [OHLCV(ts[0], 0, 0, 0, 0, 1), OHLCV(ts[1], 0, 0, 0, 0, 3)]
    assert build_bars(idx, fut)[-1].vwap == 17.5


def test_short_after_stretch_exits_at_the_mean():
    trades = run_day(stretch_then_turn(after=(116, 118, 99, 101)), k=1.0)
    assert len(trades) == 1
    tr = trades[0]
    assert (tr.side, tr.entry, tr.stop, tr.exit, tr.reason) == (-1, 116, 122, 100, "target")
    assert tr.points == 16


def test_stop_wins_when_both_levels_are_in_one_bar():
    tr = run_day(stretch_then_turn(after=(116, 123, 99, 101)), k=1.0)[0]
    assert (tr.exit, tr.reason, tr.points) == (122, "stop", -6)


def test_no_stretch_below_k():
    assert run_day(stretch_then_turn(after=(116, 118, 99, 101)), k=2.5) == []


def test_ema_confirmation_blocks_the_vwap_ema_variant_only():
    day = [bar(b.t.hour, b.t.minute, b.o, b.h, b.l, b.c, ema9=125.0)
           for b in stretch_then_turn(after=(116, 118, 99, 101))]
    assert run_day(day, k=1.0, mode="vwap_ema") == []
    assert len(run_day(day, k=1.0, mode="vwap")) == 1


def test_no_entry_after_1430():
    assert run_day(stretch_then_turn(start=(14, 20), after=(116, 118, 99, 101)), k=1.0) == []


def test_flat_at_1515():
    day = stretch_then_turn(start=(14, 0), after=(116, 118, 110, 112))
    day.append(bar(15, 15, 111, 112, 109, 110))
    tr = run_day(day, k=1.0)[0]
    assert (tr.reason, tr.exit) == ("eod", 111)


def test_side_filter():
    day = stretch_then_turn(after=(116, 118, 99, 101))
    assert len(run_day(day, k=1.0, side=-1)) == 1
    assert run_day(day, k=1.0, side=1) == []


def test_metrics_net_of_cost():
    trades = run_day(stretch_then_turn(after=(116, 118, 99, 101)), k=1.0)
    m = metrics(trades, cost=2.0)
    assert (m["n"], m["mean_net"], m["reasons"]) == (1, 14.0, {"target": 1})
