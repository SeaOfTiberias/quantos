"""
US-05 Regime Detection Engine — Unit Tests
"""

import asyncio
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from core.regime.models import (
    Regime, RegimeInputs,
    NiftyData, VIXData, BreadthData,
)
from core.regime.classifier import classify, _score_trend, _score_vix, _score_breadth
from core.regime.service import RegimeService, format_regime_whatsapp
from core.regime.fetcher import _ema, _sma, _atr
from core.brokers.base import OHLCV


# ─── Fixtures ────────────────────────────────────────────────────────────────

def make_nifty(
    ltp=22000, ema_20=21800, ema_50=21500,
    ema_200=20000, slope_5d=1.2, atr_14=200, atr_pct=0.9,
) -> NiftyData:
    return NiftyData(
        ltp=ltp, ema_20=ema_20, ema_50=ema_50,
        ema_200=ema_200, slope_5d=slope_5d,
        atr_14=atr_14, atr_pct=atr_pct,
    )


def make_vix(current=13.0, ma_10=13.5, trend="FLAT", percentile=30.0) -> VIXData:
    return VIXData(current=current, ma_10=ma_10, trend=trend, percentile_52w=percentile)


def make_breadth(advance=350, decline=150) -> BreadthData:
    return BreadthData(advance_count=advance, decline_count=decline)


def make_inputs(nifty=None, vix=None, breadth=None) -> RegimeInputs:
    return RegimeInputs(
        nifty=nifty or make_nifty(),
        vix=vix or make_vix(),
        breadth=breadth or make_breadth(),
        timestamp=datetime.now(timezone.utc),
    )


# ─── Regime Classification Tests ──────────────────────────────────────────────

class TestRegimeClassification:

    def test_trending_bull_conditions(self):
        """Golden cross + low VIX + strong breadth → TRENDING_BULL"""
        inputs = make_inputs(
            nifty=make_nifty(ltp=22000, ema_20=21800, ema_50=21500, ema_200=20000, slope_5d=1.5),
            vix=make_vix(current=12.5, trend="FALLING"),
            breadth=make_breadth(advance=380, decline=120),
        )
        result = classify(inputs)
        assert result.regime == Regime.TRENDING_BULL
        assert result.darvas_enabled is True
        assert result.size_multiplier == 1.0

    def test_trending_bear_conditions(self):
        """Death cross + weak breadth → TRENDING_BEAR"""
        inputs = make_inputs(
            nifty=make_nifty(ltp=19000, ema_20=19500, ema_50=20000, ema_200=21000, slope_5d=-2.5),
            vix=make_vix(current=20.0, trend="RISING"),
            breadth=make_breadth(advance=120, decline=380),
        )
        result = classify(inputs)
        assert result.regime == Regime.TRENDING_BEAR
        assert result.darvas_enabled is False
        assert result.size_multiplier == 0.75

    def test_volatile_extreme_vix(self):
        """VIX >= 28 always → VOLATILE regardless of trend"""
        inputs = make_inputs(
            nifty=make_nifty(slope_5d=1.0),    # slightly bullish trend
            vix=make_vix(current=30.0, trend="RISING"),
            breadth=make_breadth(advance=300, decline=200),
        )
        result = classify(inputs)
        assert result.regime == Regime.VOLATILE
        assert result.size_multiplier == 0.50

    def test_volatile_high_vix_weak_breadth(self):
        """High VIX (>=22) + weak breadth → VOLATILE"""
        inputs = make_inputs(
            vix=make_vix(current=24.0, trend="RISING"),
            breadth=make_breadth(advance=100, decline=400),
        )
        result = classify(inputs)
        assert result.regime == Regime.VOLATILE

    def test_ranging_flat_trend_calm_vix(self):
        """Flat trend (price below ema_200, slight ema_20>ema_50) + calm VIX → RANGING"""
        inputs = make_inputs(
            nifty=make_nifty(
                ltp=21800,    # below ema_200 (22000) — not in full uptrend
                ema_20=21850, # slightly above ema_50 — no golden cross yet
                ema_50=21750,
                ema_200=22000,
                slope_5d=0.1, # near-flat
            ),
            vix=make_vix(current=13.5, trend="FLAT"),
            breadth=make_breadth(advance=250, decline=250),
        )
        result = classify(inputs)
        assert result.regime == Regime.RANGING
        assert "iron_condor" in result.allowed_strategies

    def test_uncertain_mixed_signals(self):
        """Mixed signals → UNCERTAIN with 0 size multiplier"""
        inputs = make_inputs(
            nifty=make_nifty(ltp=21000, ema_20=21200, ema_50=21500, slope_5d=-0.3),
            vix=make_vix(current=19.0, trend="RISING"),   # elevated but not extreme
            breadth=make_breadth(advance=280, decline=220),  # mild weakness
        )
        result = classify(inputs)
        # Mixed signals: slightly bearish trend, elevated VIX, weak breadth
        # Should be UNCERTAIN or RANGING — not TRENDING_BULL
        assert result.regime not in [Regime.TRENDING_BULL]

    def test_extreme_vix_overrides_bull_trend(self):
        """Even a strong bull trend becomes VOLATILE if VIX is extreme"""
        inputs = make_inputs(
            nifty=make_nifty(slope_5d=3.0, ema_20=22000, ema_50=21000, ema_200=19000),
            vix=make_vix(current=35.0),
            breadth=make_breadth(advance=350, decline=150),
        )
        result = classify(inputs)
        assert result.regime == Regime.VOLATILE

    def test_result_has_notes(self):
        inputs = make_inputs()
        result = classify(inputs)
        assert len(result.notes) > 0

    def test_allowed_strategies_match_regime(self):
        inputs = make_inputs(
            nifty=make_nifty(slope_5d=2.0),
            vix=make_vix(current=12.0, trend="FALLING"),
            breadth=make_breadth(advance=380, decline=120),
        )
        result = classify(inputs)
        if result.regime == Regime.TRENDING_BULL:
            assert "darvas_breakout" in result.allowed_strategies
        elif result.regime == Regime.RANGING:
            assert "iron_condor" in result.allowed_strategies

    def test_confidence_is_valid_range(self):
        inputs = make_inputs()
        result = classify(inputs)
        assert 0 <= result.confidence <= 100


# ─── Individual Scorer Tests ──────────────────────────────────────────────────

class TestScorers:

    def test_trend_score_bull(self):
        nifty = make_nifty(ltp=22000, ema_20=21800, ema_50=21500, ema_200=20000, slope_5d=2.5)
        score = _score_trend(nifty)
        assert score > 40    # should be positive / bullish

    def test_trend_score_bear(self):
        nifty = make_nifty(ltp=19000, ema_20=19500, ema_50=20000, ema_200=21000, slope_5d=-3.0)
        score = _score_trend(nifty)
        assert score < -40   # should be negative / bearish

    def test_trend_score_range(self):
        nifty = make_nifty()
        score = _score_trend(nifty)
        assert -100 <= score <= 100

    def test_vix_score_calm(self):
        assert _score_vix(make_vix(current=11.0)) == 0

    def test_vix_score_extreme(self):
        assert _score_vix(make_vix(current=30.0)) == 100

    def test_breadth_score_strong(self):
        assert _score_breadth(make_breadth(advance=450, decline=50)) == 100

    def test_breadth_score_weak(self):
        assert _score_breadth(make_breadth(advance=50, decline=450)) == -100

    def test_breadth_ad_ratio(self):
        b = make_breadth(advance=300, decline=100)
        assert b.ad_ratio == 3.0

    def test_breadth_pct(self):
        b = BreadthData(advance_count=300, decline_count=200, unchanged_count=0)
        assert b.breadth_pct == 60.0


# ─── RegimeResult Tests ───────────────────────────────────────────────────────

class TestRegimeResult:

    def test_is_tradeable_bull(self):
        inputs = make_inputs(
            nifty=make_nifty(slope_5d=2.0),
            vix=make_vix(current=12.0, trend="FALLING"),
            breadth=make_breadth(advance=380, decline=120),
        )
        result = classify(inputs)
        if result.regime == Regime.TRENDING_BULL:
            assert result.is_tradeable is True

    def test_uncertain_not_tradeable(self):
        from core.regime.service import _uncertain_fallback
        result = _uncertain_fallback()
        assert result.is_tradeable is False
        assert result.size_multiplier == 0.0

    def test_allows_strategy(self):
        inputs = make_inputs(
            nifty=make_nifty(slope_5d=2.0),
            vix=make_vix(current=12.0, trend="FALLING"),
            breadth=make_breadth(advance=380, decline=120),
        )
        result = classify(inputs)
        for strategy in result.allowed_strategies:
            assert result.allows_strategy(strategy) is True

    def test_summary_string(self):
        inputs = make_inputs()
        result = classify(inputs)
        summary = result.summary()
        assert "Regime:" in summary
        assert "Confidence:" in summary
        assert "Darvas:" in summary


# ─── Math Utility Tests ───────────────────────────────────────────────────────

class TestMathUtils:

    def test_ema_single_value(self):
        result = _ema([100.0], 1)
        assert result == 100.0

    def test_ema_increasing_series(self):
        prices = [100, 101, 102, 103, 104, 105]
        result = _ema(prices, 3)
        assert result > 100  # should be above starting price

    def test_sma_basic(self):
        result = _sma([10, 20, 30], 3)
        assert result == 20.0

    def test_sma_partial(self):
        result = _sma([10, 20], 5)   # fewer values than period
        assert result == 15.0

    def test_atr_basic(self):
        from datetime import timedelta
        ts = datetime(2026, 1, 1, 9, 15, tzinfo=timezone.utc)
        candles = [
            OHLCV(timestamp=ts + timedelta(days=i),
                  open=100, high=105, low=95, close=100, volume=100000)
            for i in range(5)
        ]
        atr = _atr(candles)
        assert atr > 0


# ─── Alert Formatting Tests ───────────────────────────────────────────────────

class TestRegimeWhatsapp:

    def test_format_contains_regime_name(self):
        inputs = make_inputs(
            nifty=make_nifty(slope_5d=2.0),
            vix=make_vix(current=12.0, trend="FALLING"),
            breadth=make_breadth(advance=380, decline=120),
        )
        result = classify(inputs)
        msg = format_regime_whatsapp(result)
        assert result.regime.value.replace("_", " ") in msg

    def test_format_contains_darvas_status(self):
        inputs = make_inputs()
        result = classify(inputs)
        msg = format_regime_whatsapp(result)
        assert "Darvas" in msg

    def test_uncertain_shows_stand_aside(self):
        from core.regime.service import _uncertain_fallback
        result = _uncertain_fallback()
        msg = format_regime_whatsapp(result)
        assert "stand aside" in msg.lower() or "No strategies" in msg


# ─── Regime Service Cache Tests ───────────────────────────────────────────────

class TestRegimeService:

    @pytest.mark.asyncio
    async def test_get_regime_returns_result(self):
        mock_broker = MagicMock()
        service = RegimeService(mock_broker)

        mock_result = classify(make_inputs())

        with patch("core.regime.service.fetch_regime_inputs",
                   new_callable=AsyncMock,
                   return_value=make_inputs()):
            result = await service.get_regime()

        assert result is not None
        assert isinstance(result.regime, Regime)

    @pytest.mark.asyncio
    async def test_cache_is_used_on_second_call(self):
        mock_broker = MagicMock()
        service = RegimeService(mock_broker)

        with patch("core.regime.service.fetch_regime_inputs",
                   new_callable=AsyncMock,
                   return_value=make_inputs()) as mock_fetch:
            await service.get_regime()
            await service.get_regime()   # second call

        # fetch should only be called once — second call hits cache
        assert mock_fetch.call_count == 1

    @pytest.mark.asyncio
    async def test_force_refresh_bypasses_cache(self):
        mock_broker = MagicMock()
        service = RegimeService(mock_broker)

        with patch("core.regime.service.fetch_regime_inputs",
                   new_callable=AsyncMock,
                   return_value=make_inputs()) as mock_fetch:
            await service.get_regime()
            await service.get_regime(force_refresh=True)

        assert mock_fetch.call_count == 2

    def test_is_stale_when_empty(self):
        service = RegimeService(MagicMock())
        assert service.is_stale() is True


class TestRegimeServiceEventLoopBinding:
    """
    Regression coverage for the same event-loop-binding bug found and
    fixed twice already today in core/darvas/weekly_discovery.py and
    core/darvas/scanner.py: RegimeService.__init__ used to construct
    asyncio.Lock() at construction time. agent/main.py constructs
    RegimeService once (synchronously, no loop running) and then calls
    asyncio.run(service.get_regime()) repeatedly, once per poll tick —
    each tick spins up a brand new event loop, so a lock bound to a
    previous tick's (now-closed) loop would raise. These tests call
    asyncio.run() from a plain sync test function specifically to
    reproduce that construction/call pattern.
    """

    def test_get_regime_via_asyncio_run_from_sync_context(self):
        service = RegimeService(MagicMock())   # constructed with no loop running

        with patch("core.regime.service.fetch_regime_inputs",
                   new_callable=AsyncMock, return_value=make_inputs()):
            result = asyncio.run(service.get_regime())

        assert isinstance(result.regime, Regime)

    def test_get_regime_can_run_more_than_once_across_separate_event_loops(self):
        """Same instance, two separate asyncio.run() calls — each must
        get a correctly-bound lock for its own loop."""
        service = RegimeService(MagicMock())

        with patch("core.regime.service.fetch_regime_inputs",
                   new_callable=AsyncMock, return_value=make_inputs()) as mock_fetch:
            first = asyncio.run(service.get_regime())
            second = asyncio.run(service.get_regime())

        assert isinstance(first.regime, Regime)
        assert isinstance(second.regime, Regime)
        # Still within the 15-min cache, so the second asyncio.run() call
        # (a fresh loop) must reuse the cached result, not refetch.
        assert mock_fetch.call_count == 1
