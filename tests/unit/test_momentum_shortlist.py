"""
core/discovery/momentum_shortlist.py — combines the 52-week-high-proximity
momentum ranking (core/rotation/ranker.py) with the Darvas weekly base
classification (core/darvas/weekly_discovery.py) into a discretionary
review shortlist. analyse_symbol() itself is already exhaustively tested in
test_weekly_discovery.py, so it's mocked here — these tests only cover
build_shortlist's own logic: momentum ranking/tiering, bucket assignment,
and sort order.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from core.brokers.base import OHLCV
from core.darvas.weekly_discovery import DiscoveryResult
from core.discovery.momentum_shortlist import (
    _bucket, _has_tight_base, _momentum_tier, build_shortlist,
)

EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _candle(day: int, close: float) -> OHLCV:
    return OHLCV(timestamp=EPOCH + timedelta(days=day),
                 open=close, high=close, low=close, close=close, volume=100_000)


def _series(closes: list[float]) -> list[OHLCV]:
    return [_candle(i, c) for i, c in enumerate(closes)]


def _tight_base(width_pct: float = 2.0) -> DiscoveryResult:
    return DiscoveryResult(symbol="X", status="APPROACHING", box_width_pct=width_pct)


def _wide_or_forming_base() -> DiscoveryResult:
    return DiscoveryResult(symbol="X", status="BOX FORMING")


class TestMomentumTier:

    def test_top_tercile_is_leader(self):
        assert _momentum_tier(rank=1, total=6) == "LEADER"
        assert _momentum_tier(rank=2, total=6) == "LEADER"

    def test_middle_tercile_is_midpack(self):
        assert _momentum_tier(rank=3, total=6) == "MIDPACK"
        assert _momentum_tier(rank=4, total=6) == "MIDPACK"

    def test_bottom_tercile_is_laggard(self):
        assert _momentum_tier(rank=5, total=6) == "LAGGARD"
        assert _momentum_tier(rank=6, total=6) == "LAGGARD"

    def test_single_symbol_universe_is_leader(self):
        assert _momentum_tier(rank=1, total=1) == "LEADER"


class TestHasTightBase:

    def test_none_base_is_not_tight(self):
        assert _has_tight_base(None) is False

    def test_box_forming_is_not_tight_even_without_width(self):
        assert _has_tight_base(_wide_or_forming_base()) is False

    def test_live_status_under_threshold_is_tight(self):
        assert _has_tight_base(_tight_base(3.9)) is True

    def test_live_status_at_or_over_threshold_is_not_tight(self):
        assert _has_tight_base(_tight_base(4.0)) is False
        assert _has_tight_base(_tight_base(10.0)) is False


class TestBucket:

    def test_leader_with_tight_base(self):
        assert _bucket("LEADER", True) == "LEADER_TIGHT_BASE"

    def test_leader_without_tight_base(self):
        assert _bucket("LEADER", False) == "LEADER_EXTENDED"

    def test_non_leader_with_tight_base(self):
        assert _bucket("MIDPACK", True) == "BUILDING_BASE"
        assert _bucket("LAGGARD", True) == "BUILDING_BASE"

    def test_non_leader_without_tight_base(self):
        assert _bucket("MIDPACK", False) == "WATCH"
        assert _bucket("LAGGARD", False) == "WATCH"


class TestBuildShortlist:

    def _daily_by_symbol(self):
        # window=5 (passed explicitly below): momentum score looks at the
        # rolling max of each symbol's last 5 closes.
        return {
            "L1": _series([50, 50, 60, 70, 80, 90, 100]),   # last5 max=100, close=100 -> 100.0%
            "L2": _series([50, 50, 60, 70, 80, 90, 95]),     # last5 max=95, close=95 -> 100.0%
            "M1": _series([50, 50, 90, 60, 70, 50, 60]),     # last5 max=90, close=60 -> 66.7%
            "M2": _series([50, 50, 90, 55, 65, 50, 50]),     # last5 max=90, close=50 -> 55.6%
            "G1": _series([50, 50, 90, 40, 30, 20, 10]),     # last5 max=90, close=10 -> 11.1%
            "G2": _series([50, 50, 90, 30, 20, 10, 5]),      # last5 max=90, close=5 -> 5.6%
        }

    def _mock_base(self, symbol: str):
        return {
            "L1": _tight_base(2.0),
            "L2": _wide_or_forming_base(),
            "M1": _tight_base(3.5),
            "M2": _wide_or_forming_base(),
            "G1": _tight_base(1.0),
            "G2": _wide_or_forming_base(),
        }[symbol]

    def test_buckets_assigned_per_symbol(self):
        daily = self._daily_by_symbol()
        as_of = EPOCH + timedelta(days=6)
        with patch("core.discovery.momentum_shortlist.analyse_symbol",
                   side_effect=lambda symbol, d, cfg=None: self._mock_base(symbol)):
            entries = build_shortlist(daily, as_of, momentum_window=5)

        by_symbol = {e.symbol: e for e in entries}
        assert by_symbol["L1"].momentum_tier == "LEADER"
        assert by_symbol["L1"].bucket == "LEADER_TIGHT_BASE"
        assert by_symbol["L2"].momentum_tier == "LEADER"
        assert by_symbol["L2"].bucket == "LEADER_EXTENDED"
        assert by_symbol["M1"].momentum_tier == "MIDPACK"
        assert by_symbol["M1"].bucket == "BUILDING_BASE"
        assert by_symbol["M2"].momentum_tier == "MIDPACK"
        assert by_symbol["M2"].bucket == "WATCH"
        assert by_symbol["G1"].momentum_tier == "LAGGARD"
        assert by_symbol["G1"].bucket == "BUILDING_BASE"
        assert by_symbol["G2"].momentum_tier == "LAGGARD"
        assert by_symbol["G2"].bucket == "WATCH"

    def test_sort_order_groups_by_bucket_then_momentum_desc(self):
        daily = self._daily_by_symbol()
        as_of = EPOCH + timedelta(days=6)
        with patch("core.discovery.momentum_shortlist.analyse_symbol",
                   side_effect=lambda symbol, d, cfg=None: self._mock_base(symbol)):
            entries = build_shortlist(daily, as_of, momentum_window=5)

        assert [e.bucket for e in entries] == [
            "LEADER_TIGHT_BASE", "LEADER_EXTENDED",
            "BUILDING_BASE", "BUILDING_BASE",
            "WATCH", "WATCH",
        ]
        # Within BUILDING_BASE, M1 (66.7%) outranks G1 (11.1%).
        building = [e for e in entries if e.bucket == "BUILDING_BASE"]
        assert [e.symbol for e in building] == ["M1", "G1"]
        # Within WATCH, M2 (55.6%) outranks G2 (5.6%).
        watch = [e for e in entries if e.bucket == "WATCH"]
        assert [e.symbol for e in watch] == ["M2", "G2"]

    def test_excludes_symbols_without_enough_momentum_history(self):
        daily = {
            "READY": _series([50, 60, 70, 80, 90]),       # exactly window=5 bars
            "TOO_SHORT": _series([50, 60, 70, 80]),        # only 4 bars, never warms up
        }
        as_of = EPOCH + timedelta(days=4)
        with patch("core.discovery.momentum_shortlist.analyse_symbol",
                   return_value=None):
            entries = build_shortlist(daily, as_of, momentum_window=5)

        assert [e.symbol for e in entries] == ["READY"]

    def test_no_base_result_fills_honest_defaults(self):
        daily = {"SOLO": _series([50, 60, 70, 80, 90])}
        as_of = EPOCH + timedelta(days=4)
        with patch("core.discovery.momentum_shortlist.analyse_symbol",
                   return_value=None):
            entries = build_shortlist(daily, as_of, momentum_window=5)

        entry = entries[0]
        assert entry.base_status == "NO BASE"
        assert entry.box_width_pct is None
        assert entry.dist_to_ceil is None
        assert entry.rr_ratio is None
        assert entry.vol_ratio == 0.0
        # Sole symbol in the universe -> top (and only) tercile -> LEADER,
        # but with no confirmed base it's "extended" not "in a base".
        assert entry.momentum_tier == "LEADER"
        assert entry.bucket == "LEADER_EXTENDED"
