"""core/backtest/smc_ob_1h.py (docs/NIFTY_SMC_OB_1H_PREREG_2026-11-22.md §4). Synthetic bars only."""
from datetime import datetime, timedelta, time

import pytest

from core.backtest import smc_ob_1h as eng

SIG = {time(10, 15): "am", time(14, 15): "pm"}


def day_bars(d, ohlc):
    """7 bars on a 09:15 grid for one day; ohlc is a list of 7 (o,h,l,c)."""
    t0 = datetime(d.year, d.month, d.day, 9, 15)
    return [eng.Bar(t0 + timedelta(hours=i), *x) for i, x in enumerate(ohlc)]


def test_wilder_atr_seeds_with_mean_then_smooths():
    bars = [eng.Bar(datetime(2026, 1, 1, 9, 15) + timedelta(hours=i), 100, 102, 98, 100) for i in range(15)]
    a = eng.wilder_atr(bars, 14)
    assert a[12] is None and a[13] == pytest.approx(4.0) and a[14] == pytest.approx(4.0)


def build_setup():
    """Uptrend: a pivot high at 110, a bearish candle, a close above 110 (BOS, OB = that bearish candle),
    then a pullback bar into the OB at the 10:15 bar of the next day that closes up above the POC."""
    from datetime import date
    flat = [(100, 101, 99, 100)] * 7
    bars = []
    d = date(2026, 1, 5)
    for k in range(3):                                      # ATR warm-up, 21 flat bars
        bars += day_bars(d + timedelta(days=k), flat)
    # day 4: rise to a pivot high 110 at bar 2, fall away, then a bearish candle
    bars += day_bars(d + timedelta(days=3), [(100, 104, 99, 103), (103, 107, 102, 106), (106, 110, 105, 108),
                                             (108, 108, 103, 104), (104, 105, 102, 103), (103, 104, 101, 102),
                                             (102, 103, 100, 101)])
    # day 5: bars 0-1 low, bar 2 bearish (OB 103-106), bar 3 breaks 110 (BOS), then quiet
    bars += day_bars(d + timedelta(days=4), [(101, 102, 100, 101), (101, 103, 100, 102), (106, 106, 103, 104),
                                             (104, 112, 104, 111), (111, 112, 109, 110), (110, 111, 108, 109),
                                             (109, 110, 107, 108)])
    # day 6: 09:15 bar pulls back, 10:15 bar dips into the OB (low 105.5 <= 106) and closes up at 109
    bars += day_bars(d + timedelta(days=5), [(108, 109, 106, 107), (107, 109.5, 105.5, 109), (109, 112, 108, 111),
                                             (111, 113, 110, 112), (112, 114, 111, 113), (113, 115, 112, 114),
                                             (114, 116, 113, 115)])
    return bars


def test_signal_on_ob_retest_enters_next_open_and_consumes_the_ob():
    bars = build_setup()
    trades = eng.run(bars, lambda d: True, SIG)
    assert len(trades) == 1
    t = trades[0]
    assert t.signal_start.time() == time(10, 15) and t.entry_time.time() == time(11, 15) and t.entry == 109
    assert t.ob_bot == 103 and t.window == "am"
    lo, hi = eng.MIN_RISK * t.atr, eng.MAX_RISK * t.atr
    assert lo - 1e-9 <= t.risk <= hi + 1e-9 and t.target == pytest.approx(109 + 2 * t.risk)


def test_htf_filter_blocks_the_signal():
    assert eng.run(build_setup(), lambda d: False, SIG) == []


def test_wrong_window_blocks_the_signal():
    assert eng.run(build_setup(), lambda d: True, {time(13, 15): "pm"}) == []


def test_stop_taken_before_target_inside_one_5min_bar():
    bars = build_setup()
    k = next(i for i, b in enumerate(bars) if b.start == datetime(2026, 1, 10, 11, 15))
    b = bars[k]
    bars[k] = eng.Bar(b.start, 109, 200, 50, 109, ((b.start, 109, 200, 50, 109),))
    t = eng.run(bars, lambda d: True, SIG)[0]
    assert t.reason == "stop" and t.exit == pytest.approx(t.stop0) and t.bars_held == 1


def test_time_stop_at_the_close_of_bar_14():
    bars = build_setup()
    k = next(i for i, b in enumerate(bars) if b.start == datetime(2026, 1, 10, 11, 15))
    flat = [eng.Bar(bars[-1].start + timedelta(hours=h + 1), 109, 109.5, 108.5, 109) for h in range(20)]
    bars = bars[:k] + [eng.Bar(bars[k].start, 109, 109.5, 108.5, 109)] + flat
    t = eng.run(bars, lambda d: True, SIG)[0]
    assert t.reason == "time" and t.bars_held == eng.MAX_HOLD and t.exit == 109
