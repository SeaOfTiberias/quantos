"""
PEAD Gut-Check — Forward-Return Computation + Correlation — Unit Tests

Price series below are small constructed sequences (this tests the
lookup/return-arithmetic logic itself, not a data-integrity claim about
real prices -- unlike the bhavcopy/XBRL fixtures elsewhere in this suite,
which are trimmed real rows).
"""

from datetime import date, datetime

import pytest

from core.fundamentals.pead.eq_bhavcopy import EqCloseRow
from core.fundamentals.pead.gutcheck import (
    build_price_index,
    compute_forward_return,
    summarize,
)
from core.fundamentals.pead.pipeline import PeadSignalRow


def _signal_row(symbol, broadcast_date, yoy_pct):
    return PeadSignalRow(
        symbol=symbol, broadcast_date=datetime.combine(broadcast_date, datetime.min.time()),
        quarter_start=date(2024, 7, 1), quarter_end=date(2024, 9, 30),
        pat=0.0, pat_prior_year=0.0, yoy_surprise_pct=yoy_pct,
    )


class TestBuildPriceIndex:
    def test_groups_and_sorts_by_symbol(self):
        rows = [
            EqCloseRow(date(2024, 10, 2), "RELIANCE", 101.0),
            EqCloseRow(date(2024, 10, 1), "RELIANCE", 100.0),
            EqCloseRow(date(2024, 10, 1), "TCS", 200.0),
        ]
        idx = build_price_index(rows)
        assert idx["RELIANCE"] == [(date(2024, 10, 1), 100.0), (date(2024, 10, 2), 101.0)]
        assert idx["TCS"] == [(date(2024, 10, 1), 200.0)]


class TestComputeForwardReturn:
    def _index(self):
        # 10 consecutive trading days, RELIANCE only, deliberately simple
        # closes so returns are easy to hand-verify.
        rows = [EqCloseRow(date(2024, 10, 1 + i), "RELIANCE", 100.0 + i) for i in range(10)]
        return build_price_index(rows)

    def test_entry_is_first_trading_day_strictly_after_broadcast(self):
        idx = self._index()
        # broadcast on 2024-10-01 -> entry should be 2024-10-02 (close=101), not same-day.
        fr = compute_forward_return(idx, "RELIANCE", date(2024, 10, 1), horizon_trading_days=1)
        assert fr.entry_date == date(2024, 10, 2)
        assert fr.entry_close == 101.0

    def test_horizon_counts_trading_days_not_calendar_days(self):
        idx = self._index()
        fr = compute_forward_return(idx, "RELIANCE", date(2024, 10, 1), horizon_trading_days=3)
        # entry 10-02 (idx1, close 101) -> +3 trading days -> idx4 = 10-05 (close 104)
        assert fr.exit_date == date(2024, 10, 5)
        assert fr.return_pct == pytest.approx((104.0 - 101.0) / 101.0 * 100)

    def test_missing_symbol_returns_none(self):
        idx = self._index()
        assert compute_forward_return(idx, "UNKNOWN", date(2024, 10, 1), 5) is None

    def test_no_entry_day_available_returns_none(self):
        idx = self._index()  # last date is 2024-10-10
        assert compute_forward_return(idx, "RELIANCE", date(2024, 10, 15), 5) is None

    def test_horizon_runs_past_end_of_series_returns_none(self):
        idx = self._index()
        # entry near the end of the 10-day series, horizon overruns it.
        assert compute_forward_return(idx, "RELIANCE", date(2024, 10, 8), horizon_trading_days=5) is None


class TestSummarize:
    def test_splits_by_surprise_sign_and_correlates(self):
        # Two symbols: RELIANCE (positive surprise) trends up, TCS
        # (negative surprise) trends down -- a deliberately unambiguous
        # case so the correlation sign/magnitude is easy to hand-check.
        rows = (
            [EqCloseRow(date(2024, 10, 1 + i), "RELIANCE", 100.0 + i * 2) for i in range(10)]
            + [EqCloseRow(date(2024, 10, 1 + i), "TCS", 100.0 - i * 2) for i in range(10)]
        )
        idx = build_price_index(rows)
        signal_rows = [
            _signal_row("RELIANCE", date(2024, 10, 1), yoy_pct=25.0),
            _signal_row("TCS", date(2024, 10, 1), yoy_pct=-15.0),
        ]
        summaries = summarize(signal_rows, idx, horizons=(3,))
        s = summaries[0]
        assert s.n == 2
        assert s.correlation == pytest.approx(1.0)  # perfectly monotonic constructed case
        assert s.positive_surprise_n == 1
        assert s.positive_surprise_mean_return_pct > 0
        assert s.negative_surprise_n == 1
        assert s.negative_surprise_mean_return_pct < 0

    def test_no_matched_rows_gives_none_correlation(self):
        summaries = summarize([_signal_row("UNKNOWN", date(2024, 10, 1), 10.0)], {}, horizons=(5,))
        assert summaries[0].n == 0
        assert summaries[0].correlation is None

    def test_multiple_horizons_each_summarized(self):
        rows = [EqCloseRow(date(2024, 10, 1 + i), "RELIANCE", 100.0 + i) for i in range(20)]
        idx = build_price_index(rows)
        signal_rows = [_signal_row("RELIANCE", date(2024, 10, 1), yoy_pct=10.0)]
        summaries = summarize(signal_rows, idx, horizons=(3, 5, 10))
        assert [s.horizon_trading_days for s in summaries] == [3, 5, 10]
        assert all(s.n == 1 for s in summaries)

    def test_market_adjusted_strips_shared_move_both_groups_negative(self):
        # Both symbols drift DOWN in absolute terms (a shared bear-market
        # move), but RELIANCE (positive surprise) loses less than TCS
        # (negative surprise) -- exactly the "beta swamps a real relative
        # PEAD effect" scenario found in this session's live gut-check.
        # Market-adjusting should reveal RELIANCE beating the sample mean
        # and TCS trailing it, even though both are negative in raw terms.
        rows = (
            [EqCloseRow(date(2024, 10, 1 + i), "RELIANCE", 100.0 - i * 0.5) for i in range(10)]
            + [EqCloseRow(date(2024, 10, 1 + i), "TCS", 100.0 - i * 2.0) for i in range(10)]
        )
        idx = build_price_index(rows)
        signal_rows = [
            _signal_row("RELIANCE", date(2024, 10, 1), yoy_pct=25.0),
            _signal_row("TCS", date(2024, 10, 1), yoy_pct=-15.0),
        ]
        raw = summarize(signal_rows, idx, horizons=(5,), market_adjusted=False)[0]
        adjusted = summarize(signal_rows, idx, horizons=(5,), market_adjusted=True)[0]

        assert raw.positive_surprise_mean_return_pct < 0
        assert raw.negative_surprise_mean_return_pct < 0
        assert adjusted.market_return_pct is not None
        assert adjusted.positive_surprise_mean_return_pct > 0  # beats the sample mean
        assert adjusted.negative_surprise_mean_return_pct < 0  # trails the sample mean
        assert raw.market_return_pct is None  # not computed unless requested
