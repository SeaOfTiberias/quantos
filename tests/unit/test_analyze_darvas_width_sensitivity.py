"""
Tests for scripts/analyze_darvas_width_sensitivity.py --
docs/DARVAS_BOX_WIDTH_SENSITIVITY_METHODOLOGY.md's unbiased gut-check.
No network/broker; synthetic daily candles constructed to actually clear
core/darvas/weekly_discovery.py's real box/breakout logic.
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.brokers.base import OHLCV  # noqa: E402
from scripts.analyze_darvas_width_sensitivity import (  # noqa: E402
    BUCKETS,
    EXCLUDED_BUCKET,
    all_events,
    bucket_stats,
    find_breakouts,
    sample_universe,
)

START = datetime(2024, 1, 1, tzinfo=timezone.utc)


def bar(i: int, o: float, h: float, l: float, c: float, v: int = 100000) -> OHLCV:
    return OHLCV(timestamp=START + timedelta(days=i), open=o, high=h, low=l, close=c, volume=v)


def flat(n: int, price: float = 100.0, start_i: int = 0) -> list[OHLCV]:
    return [bar(start_i + i, price, price + 0.5, price - 0.5, price) for i in range(n)]


def build_breakout_series(box_low: float, box_high: float, breakout_close: float,
                          weeks_in_box: int = 10, tail_days: int = 90) -> list[OHLCV]:
    """A flat run (warms up the box), a tight range for `weeks_in_box`
    weeks (confirms ceiling/floor), then a high-volume breakout candle,
    then a flat tail so forward-return horizons have something to read."""
    candles = flat(70, price=(box_low + box_high) / 2)  # warm-up, outside the box window
    day = len(candles)
    mid = (box_low + box_high) / 2
    for w in range(weeks_in_box):
        for d in range(5):
            candles.append(bar(day, mid, box_high - 0.1, box_low + 0.1, mid, v=100000))
            day += 1
    # Breakout candle: big volume, closes above the box ceiling.
    candles.append(bar(day, box_high, breakout_close + 1, box_high - 0.1, breakout_close, v=500000))
    day += 1
    # Tail: drifts a known amount so the forward-return math is checkable.
    for i in range(tail_days):
        price = breakout_close * (1 + 0.001 * i)
        candles.append(bar(day, price, price + 0.5, price - 0.5, price, v=100000))
        day += 1
    return candles


# ─── sample_universe ────────────────────────────────────────────────────────

def test_sample_universe_takes_every_7th_line(tmp_path):
    f = tmp_path / "universe.txt"
    f.write_text("\n".join(f"SYM{i}" for i in range(21)))
    sampled = sample_universe(f)
    assert sampled == ["SYM0", "SYM7", "SYM14"]


def test_sample_universe_ignores_blank_lines(tmp_path):
    f = tmp_path / "universe.txt"
    f.write_text("A\n\nB\n\nC\n\nD\n\nE\n\nF\n\nG\n\nH\n")
    sampled = sample_universe(f)
    assert sampled[0] == "A"


# ─── find_breakouts ─────────────────────────────────────────────────────────

def test_find_breakouts_records_a_real_breakout_with_correct_entry_and_return():
    daily = build_breakout_series(box_low=95.0, box_high=105.0, breakout_close=110.0)
    events = find_breakouts("TEST", daily)
    assert len(events) >= 1
    e = events[0]
    assert e["symbol"] == "TEST"
    assert e["width_pct"] > 0
    # Entry is the NEXT day's open, not the breakout candle's own close.
    breakout_i = next(i for i, c in enumerate(daily) if c.close == 110.0)
    assert e["entry_price"] == daily[breakout_i + 1].open


def test_find_breakouts_reports_no_events_for_a_flat_series():
    daily = flat(200, price=100.0)
    assert find_breakouts("FLAT", daily) == []


def test_find_breakouts_captures_a_wide_box_the_live_default_would_exclude():
    """The whole point of using WIDE_CFG: a box the live 35% default would
    silently drop must still show up here, with its real width recorded."""
    daily = build_breakout_series(box_low=60.0, box_high=100.0, breakout_close=110.0)  # ~67% wide
    events = find_breakouts("WIDE", daily)
    assert len(events) >= 1
    assert events[0]["width_pct"] > 35.0


def test_find_breakouts_skips_a_breakout_with_no_next_day_bar():
    daily = build_breakout_series(box_low=95.0, box_high=105.0, breakout_close=110.0, tail_days=0)
    # The breakout is the very last candle -- no next-day open to enter on.
    events = find_breakouts("NOTAIL", daily)
    assert events == []


# ─── bucket_stats / all_events ──────────────────────────────────────────────

def _fake_results(widths_and_returns):
    """widths_and_returns: list of (width_pct, return_pct)."""
    return {"SYM": {"events": [
        {"symbol": "SYM", "date": "2026-01-01", "width_pct": w,
         "entry_price": 100.0, "returns": {"4w": r}}
        for w, r in widths_and_returns
    ]}}


def test_bucket_stats_reports_insufficient_below_min_sample():
    results = _fake_results([(20.0, 5.0)] * 5)  # only 5 events, need 10
    events = all_events(results)
    stats = bucket_stats(events, BUCKETS[0][1], "4w")
    assert stats["insufficient"] is True
    assert stats["n"] == 5


def test_bucket_stats_computes_mean_median_hit_rate_once_enough_samples():
    returns = [10.0] * 6 + [-5.0] * 4   # 10 events, 6 positive
    results = _fake_results([(20.0, r) for r in returns])
    events = all_events(results)
    stats = bucket_stats(events, BUCKETS[0][1], "4w")
    assert stats["insufficient"] is False
    assert stats["n"] == 10
    assert stats["hit_rate_pct"] == 60.0


def test_buckets_partition_by_width_correctly():
    control, mid, wide = BUCKETS
    assert control[1](35.0) is True and control[1](35.1) is False
    assert mid[1](35.0) is False and mid[1](36.0) is True and mid[1](50.0) is True
    assert wide[1](50.1) is True and wide[1](100.0) is True and wide[1](100.1) is False
    assert EXCLUDED_BUCKET[1](100.1) is True and EXCLUDED_BUCKET[1](100.0) is False


def test_events_from_different_widths_land_in_different_buckets():
    results = _fake_results([(20.0, 5.0)] * 10 + [(40.0, 3.0)] * 10 + [(150.0, 99.0)] * 10)
    events = all_events(results)
    assert bucket_stats(events, BUCKETS[0][1], "4w")["n"] == 10
    assert bucket_stats(events, BUCKETS[1][1], "4w")["n"] == 10
    assert bucket_stats(events, EXCLUDED_BUCKET[1], "4w")["n"] == 10
