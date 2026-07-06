"""
US-02 Darvas Box Scanner — Unit Tests
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, AsyncMock, patch

from core.brokers.base import OHLCV
from core.darvas.box import (
    DarvasBox, DarvasSignal,
    detect_darvas_boxes, detect_breakout, score_confluence, next_trailing_stop,
    LOOKBACK_PERIOD, MIN_CONSOLIDATION, VOLUME_MULTIPLIER,
)
from core.darvas.scanner import DarvasScanner
from core.darvas.alerts import format_signal_alert, format_watchlist_summary


# ─── Fixtures ────────────────────────────────────────────────────────────────

def make_candle(
    close: float,
    high: float = None,
    low: float = None,
    volume: int = 100_000,
    offset_minutes: int = 0,
) -> OHLCV:
    return OHLCV(
        timestamp=datetime(2026, 1, 1, 9, 15, tzinfo=timezone.utc)
                  + timedelta(minutes=offset_minutes),
        open=close * 0.999,
        high=high if high is not None else close * 1.005,
        low=low if low is not None else close * 0.995,
        close=close,
        volume=volume,
    )


def make_candle_series(
    prices: list[float],
    volume: int = 100_000,
) -> list[OHLCV]:
    return [
        make_candle(p, volume=volume, offset_minutes=i * 15)
        for i, p in enumerate(prices)
    ]


def build_breakout_series() -> list[OHLCV]:
    """
    Build a candle series that contains a valid Darvas Box breakout.

    Structure:
    - 20 trending candles (establishes lookback high)
    - 5 consolidation candles (price holds below high)
    - 1 breakout candle (close above box top on high volume)
    """
    candles = []

    # Trending phase — gradually rising to establish a high
    for i in range(20):
        price = 1000 + i * 5   # 1000 → 1095
        candles.append(make_candle(price, volume=100_000, offset_minutes=i * 15))

    box_top = candles[-1].high  # ~1100

    # Consolidation — price drifts sideways below the high
    for i in range(5):
        price = 1080 - i * 2   # 1080, 1078, 1076, 1074, 1072
        candles.append(make_candle(
            price,
            high=box_top * 0.999,   # just below box top
            low=1060.0,
            volume=80_000,
            offset_minutes=(20 + i) * 15,
        ))

    # Breakout candle — close above box top on strong volume
    candles.append(make_candle(
        close=box_top * 1.01,   # 1% above box top
        high=box_top * 1.015,
        volume=250_000,          # 2.5× average
        offset_minutes=25 * 15,
    ))

    return candles


# ─── Box Detection Tests ──────────────────────────────────────────────────────

class TestDarvasBoxDetection:

    def test_detects_box_in_valid_series(self):
        candles = build_breakout_series()
        boxes = detect_darvas_boxes(candles[:-1], "TEST", "1h")
        assert len(boxes) >= 1

    def test_box_has_valid_top_and_bottom(self):
        candles = build_breakout_series()
        boxes = detect_darvas_boxes(candles[:-1], "TEST", "1h")
        box = boxes[-1]
        assert box.top > box.bottom
        assert box.top > 0
        assert box.bottom > 0

    def test_box_width_within_limit(self):
        candles = build_breakout_series()
        boxes = detect_darvas_boxes(candles[:-1], "TEST", "1h")
        for box in boxes:
            assert box.width_pct <= 8.0, f"Box too wide: {box.width_pct:.1f}%"

    def test_no_box_with_insufficient_candles(self):
        candles = make_candle_series([100.0] * 10)  # too few
        boxes = detect_darvas_boxes(candles, "TEST", "1h")
        assert boxes == []

    def test_tight_box_flag(self):
        box = DarvasBox(top=100.0, bottom=97.0, formed_at=5, candles_held=5, width_pct=3.0)
        assert box.is_tight is True

        wide_box = DarvasBox(top=100.0, bottom=94.0, formed_at=5, candles_held=5, width_pct=6.0)
        assert wide_box.is_tight is False

    def test_box_midpoint(self):
        box = DarvasBox(top=100.0, bottom=90.0, formed_at=5, candles_held=5, width_pct=10.0)
        assert box.midpoint == 95.0


# ─── Breakout Detection Tests ─────────────────────────────────────────────────

class TestBreakoutDetection:

    def test_detects_valid_breakout(self):
        candles = build_breakout_series()
        signal = detect_breakout(candles, "TEST", "1h")
        assert signal is not None
        assert signal.is_valid_breakout is True

    def test_no_breakout_without_volume(self):
        candles = build_breakout_series()
        # Weaken the breakout candle volume to below threshold
        last = candles[-1]
        candles[-1] = OHLCV(
            timestamp=last.timestamp,
            open=last.open, high=last.high, low=last.low, close=last.close,
            volume=50_000,  # well below avg
        )
        signal = detect_breakout(candles, "TEST", "1h")
        # Should either be None or have is_valid_breakout = False
        if signal is not None:
            assert signal.is_valid_breakout is False

    def test_no_breakout_when_price_inside_box(self):
        candles = build_breakout_series()
        # Replace breakout candle with a candle that stays inside the box
        last = candles[-1]
        candles[-1] = OHLCV(
            timestamp=last.timestamp,
            open=last.open,
            high=last.high * 0.98,
            low=last.low,
            close=last.close * 0.97,  # below box top
            volume=250_000,
        )
        signal = detect_breakout(candles, "TEST", "1h")
        assert signal is None

    def test_signal_has_correct_symbol_and_timeframe(self):
        candles = build_breakout_series()
        signal = detect_breakout(candles, "RELIANCE", "1d")
        assert signal is not None
        assert signal.symbol == "RELIANCE"
        assert signal.timeframe == "1d"

    def test_signal_quality_score_range(self):
        candles = build_breakout_series()
        signal = detect_breakout(candles, "TEST", "1h")
        if signal:
            assert 0 <= signal.quality_score <= 100

    def test_insufficient_candles_returns_none(self):
        candles = make_candle_series([100.0] * 15)
        result = detect_breakout(candles, "TEST", "1h")
        assert result is None


# ─── Confluence Scoring Tests ─────────────────────────────────────────────────

class TestConfluenceScoring:

    def _make_signal(self, timeframe: str, volume_ratio: float = 1.5, width_pct: float = 3.0) -> DarvasSignal:
        box = DarvasBox(top=100.0, bottom=100 - width_pct, formed_at=5,
                        candles_held=5, width_pct=width_pct)
        return DarvasSignal(
            timeframe=timeframe, symbol="TEST",
            breakout_price=101.0, box_top=100.0, box_bottom=97.0,
            box_width_pct=width_pct, volume_ratio=volume_ratio,
            candle_index=25, box=box, quality_score=75.0,
        )

    def test_empty_signals_returns_zero(self):
        result = score_confluence([])
        assert result.confluence_score == 0

    def test_single_daily_signal_gets_weight(self):
        result = score_confluence([self._make_signal("1d")])
        assert result.confluence_score >= 40   # daily weight

    def test_three_tf_confluence_higher_than_one(self):
        single = score_confluence([self._make_signal("1h")])
        triple = score_confluence([
            self._make_signal("1d"),
            self._make_signal("1h"),
            self._make_signal("15m"),
        ])
        assert triple.confluence_score > single.confluence_score

    def test_score_capped_at_100(self):
        signals = [
            self._make_signal("1d", volume_ratio=3.0, width_pct=1.5),
            self._make_signal("1h", volume_ratio=3.0, width_pct=1.5),
            self._make_signal("15m", volume_ratio=3.0, width_pct=1.5),
        ]
        result = score_confluence(signals)
        assert result.confluence_score <= 100.0

    def test_should_fire_above_70(self):
        signals = [
            self._make_signal("1d"),
            self._make_signal("1h"),
        ]
        result = score_confluence(signals)
        assert result.should_fire is True

    def test_should_not_fire_single_weak_signal(self):
        result = score_confluence([self._make_signal("15m", volume_ratio=1.3)])
        assert result.should_fire is False

    def test_primary_signal_is_highest_timeframe(self):
        signals = [self._make_signal("15m"), self._make_signal("1h")]
        result = score_confluence(signals)
        assert result.primary_signal.timeframe == "1h"

    def test_triggered_timeframes_recorded(self):
        signals = [self._make_signal("1d"), self._make_signal("15m")]
        result = score_confluence(signals)
        assert "1d" in result.timeframes_triggered
        assert "15m" in result.timeframes_triggered


# ─── Trailing Stop Tests (Task 4) ─────────────────────────────────────────────

class TestTrailingStop:

    def test_returns_none_when_no_box_formed(self):
        candles = make_candle_series([100.0] * 10)  # too few for a box
        assert next_trailing_stop(candles, current_stop=90.0) is None

    def test_returns_none_when_box_bottom_not_tighter(self):
        candles = build_breakout_series()[:-1]  # exclude the breakout candle
        box = detect_darvas_boxes(candles, "TEST", "1h")[-1]
        # current_stop already at (or above) the box bottom — nothing to trail
        assert next_trailing_stop(candles, current_stop=box.bottom + 1) is None

    def test_returns_tighter_stop_when_box_bottom_is_higher(self):
        candles = build_breakout_series()[:-1]
        box = detect_darvas_boxes(candles, "TEST", "1h")[-1]
        new_stop = next_trailing_stop(candles, current_stop=box.bottom - 1)
        assert new_stop == box.bottom


# ─── Alert Formatting Tests ───────────────────────────────────────────────────

class TestAlertFormatting:

    def _make_result(self, score: float = 85.0) -> "MultiTimeframeResult":
        from core.darvas.box import MultiTimeframeResult, DarvasSignal, DarvasBox
        box = DarvasBox(top=2950.0, bottom=2870.0, formed_at=5, candles_held=7, width_pct=2.8)
        signal = DarvasSignal(
            timeframe="1d", symbol="RELIANCE",
            breakout_price=2960.0, box_top=2950.0, box_bottom=2870.0,
            box_width_pct=2.8, volume_ratio=1.8, candle_index=25,
            box=box, quality_score=82.0,
        )
        return MultiTimeframeResult(
            symbol="RELIANCE",
            confluence_score=score,
            signals=[signal],
            timeframes_triggered=["1d", "1h"],
            primary_signal=signal,
            notes=["✅ 2-TF confluence: 1d + 1h"],
        )

    def test_alert_contains_symbol(self):
        result = self._make_result()
        msg = format_signal_alert(result)
        assert "RELIANCE" in msg

    def test_alert_contains_price(self):
        result = self._make_result()
        msg = format_signal_alert(result)
        assert "2,960.00" in msg

    def test_alert_contains_confluence_score(self):
        result = self._make_result(score=87.0)
        msg = format_signal_alert(result)
        assert "87" in msg

    def test_alert_contains_action_prompts(self):
        result = self._make_result()
        msg = format_signal_alert(result)
        assert "execute" in msg.lower()
        assert "skip" in msg.lower()

    def test_watchlist_summary_empty(self):
        msg = format_watchlist_summary([])
        assert "No Darvas breakouts" in msg

    def test_watchlist_summary_lists_symbols(self):
        results = [self._make_result(85), self._make_result(78)]
        results[1].symbol = "TCS"
        msg = format_watchlist_summary(results)
        assert "RELIANCE" in msg
        assert "TCS" in msg
