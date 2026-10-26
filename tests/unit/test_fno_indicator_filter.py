"""scripts/backtest_fno_indicator_filter.py -- indicator states on hand-built daily bars."""

from datetime import date, timedelta

from scripts.backtest_fno_indicator_filter import agrees, indicator_states


def bars(closes):
    d0 = date(2025, 1, 1)
    return {d0 + timedelta(days=i): (c, c + 1, c - 1, c) for i, c in enumerate(closes)}


def test_warm_up_needs_cci_34_plus_ema_52():
    st = indicator_states(bars([100.0] * 200))
    assert min(st) == date(2025, 1, 1) + timedelta(days=34 - 1 + 52 - 1)


def test_a_late_rally_is_bullish_on_both():
    st = indicator_states(bars([100.0] * 120 + [100.0 + 2 * i for i in range(1, 11)]))
    last = st[max(st)]
    assert last == (1, 1)
    assert agrees("both", last, 1) and not agrees("both", last, -1)


def test_a_late_drop_is_bearish_on_both():
    st = indicator_states(bars([100.0] * 120 + [100.0 - 2 * i for i in range(1, 11)]))
    assert st[max(st)] == (-1, -1)


def test_flat_market_reads_neither_side():
    st = indicator_states(bars([100.0] * 200))
    cci, sma = st[max(st)]
    assert (cci, sma) == (0, 0)
    assert not agrees("cci", (cci, sma), 1) and not agrees("sma", (cci, sma), -1)
