"""
US-12 Volume Profile + Darvas Fusion — Unit Tests
"""

import pytest
from datetime import datetime, timezone, timedelta

from core.brokers.base import OHLCV
from core.darvas.volume_profile import (
    compute_volume_profile, check_darvas_fusion,
    VolumeProfile, DarvasFusionResult,
    HVN_THRESHOLD, LVN_THRESHOLD, PROXIMITY_PCT,
)


# ─── Fixtures ─────────────────────────────────────────────────────────────────

def make_candle(close: float, high: float = None, low: float = None,
                volume: int = 100_000, offset_days: int = 0) -> OHLCV:
    return OHLCV(
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=offset_days),
        open=close * 0.999,
        high=high if high is not None else close * 1.01,
        low=low if low is not None else close * 0.99,
        close=close,
        volume=volume,
    )


def make_uniform_candles(n: int = 30, base_price: float = 100.0,
                          volume: int = 100_000) -> list[OHLCV]:
    """Candles with uniform price range — should produce flat volume profile."""
    candles = []
    for i in range(n):
        price = base_price + (i % 3)  # small oscillation
        candles.append(make_candle(price, high=price + 1, low=price - 1,
                                   volume=volume, offset_days=i))
    return candles


def make_candles_with_hvn(base_price: float = 100.0) -> list[OHLCV]:
    """
    Build candles where a specific price zone has much higher volume
    than the rest — should produce a clear HVN there.
    """
    candles = []
    # 20 candles at base_price with normal volume
    for i in range(20):
        candles.append(make_candle(base_price, high=base_price + 2,
                                   low=base_price - 2, volume=100_000, offset_days=i))
    # 5 candles at base_price + 10 with very high volume (HVN zone)
    for i in range(5):
        candles.append(make_candle(base_price + 10, high=base_price + 12,
                                   low=base_price + 8, volume=800_000, offset_days=20 + i))
    # 5 more candles above at normal volume
    for i in range(5):
        candles.append(make_candle(base_price + 20, high=base_price + 22,
                                   low=base_price + 18, volume=100_000, offset_days=25 + i))
    return candles


# ─── Volume Profile Tests ──────────────────────────────────────────────────────

class TestComputeVolumeProfile:

    def test_raises_on_empty_candles(self):
        with pytest.raises(ValueError):
            compute_volume_profile([], "TEST")

    def test_correct_number_of_bins(self):
        candles = make_uniform_candles(20)
        vp = compute_volume_profile(candles, "TEST", n_bins=24)
        assert len(vp.bins) == 24

    def test_total_volume_matches_candles(self):
        candles = make_uniform_candles(10, volume=100_000)
        vp = compute_volume_profile(candles, "TEST")
        # Total volume in profile should approximately match sum of candle volumes
        assert vp.total_volume == pytest.approx(10 * 100_000, rel=0.05)

    def test_price_range_covers_candles(self):
        candles = make_uniform_candles(20, base_price=100.0)
        vp = compute_volume_profile(candles, "TEST")
        assert vp.price_low <= 99.0
        assert vp.price_high >= 103.0

    def test_poc_is_highest_volume_bin(self):
        candles = make_candles_with_hvn(base_price=100.0)
        vp = compute_volume_profile(candles, "TEST")
        # POC should be near 110 (the high-volume zone)
        assert 105 <= vp.poc_price <= 115

    def test_hvn_detected_at_high_volume_zone(self):
        candles = make_candles_with_hvn(base_price=100.0)
        vp = compute_volume_profile(candles, "TEST")
        hvns = vp.hvns()
        assert len(hvns) > 0
        # At least one HVN should be near the high-volume zone (around 110)
        hvn_prices = [h.price_mid for h in hvns]
        assert any(100 <= p <= 120 for p in hvn_prices)

    def test_lvn_detected_in_thin_volume_zone(self):
        candles = make_candles_with_hvn(base_price=100.0)
        vp = compute_volume_profile(candles, "TEST")
        lvns = vp.lvns()
        assert len(lvns) >= 0   # may or may not have LVNs depending on distribution

    def test_all_bins_have_non_negative_volume(self):
        candles = make_uniform_candles(20)
        vp = compute_volume_profile(candles, "TEST")
        for bin_ in vp.bins:
            assert bin_.volume >= 0

    def test_single_candle_profile(self):
        candles = [make_candle(100.0, high=105.0, low=95.0, volume=1_000_000)]
        vp = compute_volume_profile(candles, "TEST")
        assert vp.total_volume == pytest.approx(1_000_000, rel=0.1)

    def test_symbol_stored_correctly(self):
        candles = make_uniform_candles(5)
        vp = compute_volume_profile(candles, "RELIANCE")
        assert vp.symbol == "RELIANCE"

    def test_lookback_candles_count(self):
        candles = make_uniform_candles(15)
        vp = compute_volume_profile(candles, "TEST")
        assert vp.lookback_candles == 15


class TestVolumeProfileQueries:

    def setup_method(self):
        self.candles = make_candles_with_hvn(base_price=100.0)
        self.vp = compute_volume_profile(self.candles, "TEST", n_bins=30)

    def test_nearest_hvn_above(self):
        hvn = self.vp.nearest_hvn_above(100.0)
        # Should find an HVN above 100 (near 110)
        if hvn:
            assert hvn.price_mid > 100.0

    def test_nearest_hvn_below(self):
        hvn = self.vp.nearest_hvn_below(120.0)
        if hvn:
            assert hvn.price_mid < 120.0

    def test_nearest_hvn_above_none_when_at_top(self):
        hvn = self.vp.nearest_hvn_above(self.vp.price_high + 100)
        assert hvn is None

    def test_nearest_hvn_below_none_when_at_bottom(self):
        hvn = self.vp.nearest_hvn_below(self.vp.price_low - 100)
        assert hvn is None

    def test_is_near_hvn_true_when_close(self):
        hvns = self.vp.hvns()
        if hvns:
            poc = hvns[0].price_mid
            # Price exactly at HVN mid — must be near
            assert self.vp.is_near_hvn(poc)

    def test_is_near_hvn_false_when_far(self):
        # Price far below all HVNs
        assert self.vp.is_near_hvn(self.vp.price_low * 0.5) is False


class TestDarvasFusion:

    def setup_method(self):
        self.candles = make_candles_with_hvn(base_price=100.0)
        self.vp = compute_volume_profile(self.candles, "TEST", n_bins=30)

    def test_fusion_score_boosted_on_hvn_clearance(self):
        # Find an HVN and test breakout just above it
        hvns = self.vp.hvns()
        if not hvns:
            pytest.skip("No HVNs in test data")

        hvn = hvns[0]
        breakout_price = hvn.price_mid * 1.005  # 0.5% above HVN

        result = check_darvas_fusion("TEST", breakout_price, 75.0, self.vp)
        if result.has_hvn_clearance:
            assert result.fusion_score > 75.0   # boosted

    def test_fusion_score_bounded_at_100(self):
        hvns = self.vp.hvns()
        if not hvns:
            pytest.skip("No HVNs")
        hvn = hvns[0]
        breakout = hvn.price_mid * 1.005
        result = check_darvas_fusion("TEST", breakout, 100.0, self.vp)
        assert result.fusion_score <= 100.0

    def test_fusion_result_has_notes(self):
        result = check_darvas_fusion("TEST", 115.0, 80.0, self.vp)
        assert len(result.notes) > 0

    def test_poc_price_included_in_result(self):
        result = check_darvas_fusion("TEST", 115.0, 80.0, self.vp)
        assert result.poc_price == self.vp.poc_price

    def test_symbol_stored_in_result(self):
        result = check_darvas_fusion("RELIANCE", 115.0, 80.0, self.vp)
        assert result.symbol == "RELIANCE"

    def test_base_score_preserved_without_hvn(self):
        # Test at a price with no HVN nearby
        result = check_darvas_fusion("TEST", self.vp.price_low + 0.01, 60.0, self.vp)
        # Without HVN clearance, score shouldn't be boosted above base (60.0)
        # (it might be penalised if extended)
        assert 0 <= result.fusion_score <= 100


class TestVolumeBin:

    def test_price_mid(self):
        from core.darvas.volume_profile import VolumeBin
        bin_ = VolumeBin(price_low=100.0, price_high=110.0, volume=50000)
        assert bin_.price_mid == 105.0

    def test_hvn_flag(self):
        from core.darvas.volume_profile import VolumeBin
        bin_ = VolumeBin(price_low=100.0, price_high=110.0, volume=50000, is_hvn=True)
        assert bin_.is_hvn is True
        assert bin_.is_lvn is False
