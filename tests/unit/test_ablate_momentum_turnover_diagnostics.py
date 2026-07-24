"""
scripts/ablate_momentum_turnover_diagnostics.py — pure-logic unit tests for
_pooled_trade_stats() and half_split_diagnostic(). The coverage-clean and
full-window simulation paths reuse core/rotation/equity_curve.py's already-
tested simulate_portfolio() unchanged, so those aren't retested here.
"""

from datetime import datetime, timezone

from scripts.ablate_momentum_turnover_diagnostics import (
    _pooled_trade_stats, half_split_diagnostic,
)


class _Trade:
    def __init__(self, entry_date, entry_price, exit_price):
        self.entry_date = entry_date
        self.entry_price = entry_price
        self.exit_price = exit_price


def _d(day: int) -> datetime:
    return datetime(2024, 1, day, tzinfo=timezone.utc)


class TestPooledTradeStats:

    def test_empty_returns_zero(self):
        stats = _pooled_trade_stats([])
        assert stats == {"n": 0, "profit_factor": 0.0, "sharpe": 0.0}

    def test_all_winners_infinite_pf(self):
        trades = [_Trade(_d(1), 100, 110), _Trade(_d(2), 100, 105)]
        stats = _pooled_trade_stats(trades)
        assert stats["profit_factor"] == float("inf")
        assert stats["n"] == 2

    def test_mixed_winners_losers(self):
        # +10%, -5% -> gains=10, losses=5 -> PF=2.0
        trades = [_Trade(_d(1), 100, 110), _Trade(_d(2), 100, 95)]
        stats = _pooled_trade_stats(trades)
        assert stats["profit_factor"] == 2.0

    def test_single_trade_zero_sharpe(self):
        trades = [_Trade(_d(1), 100, 110)]
        stats = _pooled_trade_stats(trades)
        assert stats["sharpe"] == 0.0   # n<2, no variance defined


class TestHalfSplitDiagnostic:

    def test_splits_chronologically_by_entry_date(self):
        # Deliberately out of order in the input list -- must sort by entry_date.
        trades = [
            _Trade(_d(3), 100, 90),    # loser, should land in first half after sort
            _Trade(_d(1), 100, 110),   # winner, first half
            _Trade(_d(4), 100, 90),    # loser, second half
            _Trade(_d(2), 100, 110),   # winner, first half... wait sorted order: 1,2,3,4
        ]
        result = half_split_diagnostic(trades)
        # sorted by entry_date: d1(win), d2(win), d3(loss), d4(loss) -> mid=2
        # first_half = [d1, d2] both winners -> PF inf
        # second_half = [d3, d4] both losers -> PF 0.0
        assert result["first_half"]["n"] == 2
        assert result["second_half"]["n"] == 2
        assert result["first_half"]["profit_factor"] == float("inf")
        assert result["second_half"]["profit_factor"] == 0.0

    def test_degradation_flag_set_when_first_half_much_better(self):
        # First half: small, mildly-varying winners (positive, stable Sharpe).
        # Second half: noisy mixed results straddling zero (near-zero/negative Sharpe).
        first = [_Trade(_d(i), 100, 100 + 1 + (i % 3) * 0.1) for i in range(1, 11)]
        second = [_Trade(_d(20 + i), 100, 100 + (5 if i % 2 == 0 else -5)) for i in range(10)]
        result = half_split_diagnostic(first + second)
        assert result["degradation_flag"] is True

    def test_no_degradation_flag_when_stable(self):
        trades = [_Trade(_d(i), 100, 102) for i in range(1, 21)]
        result = half_split_diagnostic(trades)
        assert result["degradation_flag"] is False

    def test_empty_trades(self):
        result = half_split_diagnostic([])
        assert result["first_half"]["n"] == 0
        assert result["second_half"]["n"] == 0
        assert result["degradation_flag"] is False
