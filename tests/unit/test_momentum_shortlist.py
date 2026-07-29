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
    _bucket, _ema_series, _is_uptrend, _momentum_tier, _tight_base_symbols, build_shortlist,
)

EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _candle(day: int, close: float) -> OHLCV:
    return OHLCV(timestamp=EPOCH + timedelta(days=day),
                 open=close, high=close, low=close, close=close, volume=100_000)


def _series(closes: list[float]) -> list[OHLCV]:
    return [_candle(i, c) for i, c in enumerate(closes)]


def _live_base(width_pct: float) -> DiscoveryResult:
    return DiscoveryResult(symbol="X", status="APPROACHING", box_width_pct=width_pct)


def _forming_base() -> DiscoveryResult:
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


class TestTightBaseSymbols:
    """"Tight" is the narrowest third of box widths among symbols with a
    currently-live base — a relative ranking, not a fixed percentage (see
    TIGHT_BASE_TERCILE's docstring for why: a fixed 4% cutoff borrowed from
    a different Darvas engine never matched this one's real-world widths,
    which ran 8%-34% live against Nifty Alpha 50 on 2026-07-29)."""

    def test_empty_dict_yields_no_tight_symbols(self):
        assert _tight_base_symbols({}) == set()

    def test_none_and_forming_bases_never_count_as_live(self):
        result = _tight_base_symbols({"A": None, "B": _forming_base()})
        assert result == set()

    def test_narrowest_third_among_live_bases_is_tight(self):
        bases = {
            "NARROW": _live_base(2.0),
            "MID":    _live_base(10.0),
            "WIDE":   _live_base(20.0),
        }
        # 3 live bases -> tercile_size = max(1, round(3/3)) = 1: only the
        # single narrowest one qualifies.
        assert _tight_base_symbols(bases) == {"NARROW"}

    def test_forming_or_missing_bases_excluded_even_if_others_are_wide(self):
        bases = {
            "NARROW": _live_base(2.0),
            "FORMING": _forming_base(),
            "MISSING": None,
        }
        assert _tight_base_symbols(bases) == {"NARROW"}


class TestEmaSeries:

    def test_none_before_warmed_up(self):
        assert _ema_series([10.0, 20.0], period=3) == [None, None]

    def test_seeds_with_sma_then_smooths(self):
        # period=3, k=0.5: seed = avg(10,20,30) = 20; next = 40*0.5+20*0.5 = 30.
        result = _ema_series([10.0, 20.0, 30.0, 40.0], period=3)
        assert result[:2] == [None, None]
        assert result[2] == 20.0
        assert result[3] == 30.0


class TestIsUptrend:

    def test_false_when_not_enough_history_for_slow_ema(self):
        daily = _series([10, 11, 12])
        assert _is_uptrend(daily, EPOCH + timedelta(days=2), fast=2, slow=5) is False

    def test_true_when_fast_ema_above_slow_ema(self):
        # Steady climb -> the faster EMA (2) sits above the slower one (3).
        daily = _series([50, 55, 60, 70, 85, 100])
        as_of = EPOCH + timedelta(days=5)
        assert _is_uptrend(daily, as_of, fast=2, slow=3) is True

    def test_false_when_fast_ema_below_slow_ema(self):
        # Steady decline -> the faster EMA reacts down quicker than the slow one.
        daily = _series([100, 85, 70, 60, 55, 50])
        as_of = EPOCH + timedelta(days=5)
        assert _is_uptrend(daily, as_of, fast=2, slow=3) is False

    def test_respects_as_of_date_ignoring_later_bars(self):
        # As of day 2 (still climbing to 60), later decline days shouldn't
        # be visible yet.
        daily = _series([50, 55, 60, 40, 30, 20])
        as_of = EPOCH + timedelta(days=2)
        assert _is_uptrend(daily, as_of, fast=2, slow=3) is True


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
        # window=5, ema_fast=2, ema_slow=3 (all passed explicitly below).
        # Momentum (last-5-close-window proximity) descends cleanly
        # L1 > L2 > M1 > M2 > G1 > G2; trend (EMA2 vs EMA3) is up for
        # L1/L2/M1 and down for M2/G1/G2 — chosen independently of momentum
        # so the two dimensions can be tested in combination.
        return {
            "L1": _series([50, 50, 55, 60, 70, 85, 100]),  # momentum=100.0%, uptrend
            "L2": _series([50, 50, 60, 80, 95, 98, 95]),   # momentum=96.9%,  uptrend
            "M1": _series([50, 52, 58, 66, 74, 80, 72]),   # momentum=90.0%,  uptrend
            "M2": _series([50, 60, 70, 65, 60, 55, 50]),   # momentum=71.4%,  DOWNTREND
            "G1": _series([50, 60, 70, 50, 40, 35, 30]),   # momentum=42.9%,  downtrend
            "G2": _series([50, 55, 60, 40, 30, 20, 10]),   # momentum=16.7%,  downtrend
        }

    def _mock_base(self, symbol: str):
        # M2 is deliberately given the single NARROWEST width of all six
        # (1.0) but is in a downtrend — the exact GLENMARK case (2026-07-29
        # live run): a tight weekly box that's actually rolling over must
        # NOT count as a constructive base. Only L1/L2/M1 are uptrend, so
        # only they compete for "tight"; among those three M1 (3.0) is
        # narrowest and wins it despite not being the narrowest overall.
        return {
            "L1": _live_base(15.0),
            "L2": _live_base(20.0),
            "M1": _live_base(3.0),
            "M2": _live_base(1.0),
            "G1": _live_base(25.0),
            "G2": _live_base(30.0),
        }[symbol]

    def _build(self, daily, as_of):
        with patch("core.discovery.momentum_shortlist.analyse_symbol",
                   side_effect=lambda symbol, d, cfg=None: self._mock_base(symbol)):
            return build_shortlist(daily, as_of, momentum_window=5, ema_fast=2, ema_slow=3)

    def test_buckets_assigned_per_symbol(self):
        daily = self._daily_by_symbol()
        as_of = EPOCH + timedelta(days=6)
        entries = self._build(daily, as_of)

        by_symbol = {e.symbol: e for e in entries}
        assert by_symbol["L1"].momentum_tier == "LEADER"
        assert by_symbol["L1"].bucket == "LEADER_EXTENDED"     # leader, uptrend, but not narrowest of the uptrenders
        assert by_symbol["L2"].momentum_tier == "LEADER"
        assert by_symbol["L2"].bucket == "LEADER_EXTENDED"     # leader, uptrend, wider still
        assert by_symbol["M1"].momentum_tier == "MIDPACK"
        assert by_symbol["M1"].trend_up is True
        assert by_symbol["M1"].bucket == "BUILDING_BASE"       # non-leader, uptrend, narrowest among uptrenders
        assert by_symbol["M2"].momentum_tier == "MIDPACK"
        assert by_symbol["M2"].trend_up is False
        assert by_symbol["M2"].bucket == "WATCH"               # narrowest width of ALL six, but downtrend -> not tight
        assert by_symbol["G1"].momentum_tier == "LAGGARD"
        assert by_symbol["G1"].bucket == "WATCH"               # non-leader, downtrend
        assert by_symbol["G2"].momentum_tier == "LAGGARD"
        assert by_symbol["G2"].bucket == "WATCH"               # non-leader, downtrend, widest of all

    def test_sort_order_groups_by_bucket_then_momentum_desc(self):
        daily = self._daily_by_symbol()
        as_of = EPOCH + timedelta(days=6)
        entries = self._build(daily, as_of)

        assert [e.bucket for e in entries] == [
            "LEADER_EXTENDED", "LEADER_EXTENDED",
            "BUILDING_BASE",
            "WATCH", "WATCH", "WATCH",
        ]
        # Within LEADER_EXTENDED, momentum descending: L1 (100.0%) > L2 (96.9%).
        leaders = [e for e in entries if e.bucket == "LEADER_EXTENDED"]
        assert [e.symbol for e in leaders] == ["L1", "L2"]
        # Within WATCH, momentum descending: M2 (71.4%) > G1 (42.9%) > G2 (16.7%).
        watch = [e for e in entries if e.bucket == "WATCH"]
        assert [e.symbol for e in watch] == ["M2", "G1", "G2"]

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
