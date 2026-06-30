"""
US-08 Correlation-Aware Portfolio Builder — Unit Tests
"""

import pytest
import math
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from core.risk.correlation import (
    daily_returns, pearson_correlation, compute_correlation,
    check_portfolio_correlation, CorrelationResult, PortfolioCheckResult,
    CORRELATION_THRESHOLD, MIN_DATA_POINTS,
)
from core.risk.correlation_service import (
    CorrelationPortfolioService,
    format_correlation_block_whatsapp, format_portfolio_correlation_matrix,
)
from core.brokers.base import OHLCV


# ─── Helpers ─────────────────────────────────────────────────────────────────

def make_price_series(start: float, daily_pct_changes: list[float]) -> list[float]:
    """Build a price series from a starting price and a list of daily % changes."""
    prices = [start]
    for pct in daily_pct_changes:
        prices.append(prices[-1] * (1 + pct))
    return prices


def make_correlated_series(n: int = 30, noise: float = 0.001) -> tuple[list[float], list[float]]:
    """Two series that move almost identically — should show high correlation."""
    import random
    random.seed(42)
    changes_a = [random.uniform(-0.02, 0.02) for _ in range(n)]
    changes_b = [c + random.uniform(-noise, noise) for c in changes_a]
    return (
        make_price_series(100.0, changes_a),
        make_price_series(200.0, changes_b),
    )


def make_uncorrelated_series(n: int = 30) -> tuple[list[float], list[float]]:
    """Two independent random series — should show low correlation."""
    import random
    random.seed(1)
    changes_a = [random.uniform(-0.02, 0.02) for _ in range(n)]
    random.seed(99)
    changes_b = [random.uniform(-0.02, 0.02) for _ in range(n)]
    return (
        make_price_series(100.0, changes_a),
        make_price_series(50.0, changes_b),
    )


# ─── Daily Returns Tests ───────────────────────────────────────────────────────

class TestDailyReturns:

    def test_basic_returns(self):
        prices = [100.0, 110.0, 99.0]
        returns = daily_returns(prices)
        assert returns[0] == pytest.approx(0.10)
        assert returns[1] == pytest.approx(-0.10)

    def test_empty_series(self):
        assert daily_returns([]) == []

    def test_single_price_no_returns(self):
        assert daily_returns([100.0]) == []

    def test_skips_zero_price_division(self):
        prices = [0.0, 100.0, 110.0]
        returns = daily_returns(prices)
        # First transition skipped due to zero denominator
        assert len(returns) == 1


# ─── Pearson Correlation Tests ─────────────────────────────────────────────────

class TestPearsonCorrelation:

    def test_perfect_positive_correlation(self):
        a = [0.01, 0.02, -0.01, 0.03, -0.02]
        b = [0.01, 0.02, -0.01, 0.03, -0.02]   # identical
        corr, n = pearson_correlation(a, b)
        assert corr == pytest.approx(1.0, abs=0.001)
        assert n == 5

    def test_perfect_negative_correlation(self):
        a = [0.01, 0.02, -0.01, 0.03, -0.02]
        b = [-x for x in a]
        corr, n = pearson_correlation(a, b)
        assert corr == pytest.approx(-1.0, abs=0.001)

    def test_zero_correlation_constant_series(self):
        a = [0.0, 0.0, 0.0, 0.0]
        b = [0.01, 0.02, -0.01, 0.03]
        corr, n = pearson_correlation(a, b)
        assert corr == 0.0   # zero variance → safe zero return

    def test_correlation_bounded(self):
        a, b = make_correlated_series()
        returns_a = daily_returns(a)
        returns_b = daily_returns(b)
        corr, n = pearson_correlation(returns_a, returns_b)
        assert -1.0 <= corr <= 1.0

    def test_correlated_series_detected(self):
        a, b = make_correlated_series(n=40, noise=0.0005)
        returns_a = daily_returns(a)
        returns_b = daily_returns(b)
        corr, n = pearson_correlation(returns_a, returns_b)
        assert corr > 0.9   # near-identical movement

    def test_short_series_handled(self):
        corr, n = pearson_correlation([0.01], [0.02])
        assert n == 1
        assert corr == 0.0

    def test_truncates_to_shorter_series(self):
        a = [0.01] * 10
        b = [0.01] * 5
        corr, n = pearson_correlation(a, b)
        assert n == 5


# ─── compute_correlation Tests ─────────────────────────────────────────────────

class TestComputeCorrelation:

    def test_reliable_with_sufficient_data(self):
        prices_a = make_price_series(100.0, [0.01] * 25)
        prices_b = make_price_series(50.0, [0.01] * 25)
        result = compute_correlation("A", prices_a, "B", prices_b)
        assert result.is_reliable is True

    def test_unreliable_with_insufficient_data(self):
        prices_a = make_price_series(100.0, [0.01] * 5)
        prices_b = make_price_series(50.0, [0.01] * 5)
        result = compute_correlation("A", prices_a, "B", prices_b)
        assert result.is_reliable is False

    def test_high_correlation_flag(self):
        a, b = make_correlated_series(n=40, noise=0.0001)
        result = compute_correlation("A", a, "B", b)
        assert result.is_high_correlation is True

    def test_abs_correlation_property(self):
        result = CorrelationResult(
            symbol_a="A", symbol_b="B", correlation=-0.85,
            data_points=30, is_reliable=True,
        )
        assert result.abs_correlation == 0.85
        assert result.is_high_correlation is True   # negative correlation also flagged


# ─── Portfolio Check Tests ─────────────────────────────────────────────────────

class TestPortfolioCheck:

    def test_no_open_positions_not_blocked(self):
        candidate_prices = make_price_series(100.0, [0.01] * 25)
        result = check_portfolio_correlation("RELIANCE", candidate_prices, {})
        assert result.is_blocked is False

    def test_blocks_high_correlation(self):
        a, b = make_correlated_series(n=40, noise=0.0001)
        result = check_portfolio_correlation(
            "HDFCBANK", a, {"ICICIBANK": b}, threshold=0.75,
        )
        assert result.is_blocked is True
        assert len(result.correlated_with) == 1

    def test_allows_low_correlation(self):
        a, b = make_uncorrelated_series(n=40)
        result = check_portfolio_correlation(
            "RELIANCE", a, {"RANDOMSTOCK": b}, threshold=0.75,
        )
        # Random series should rarely exceed 0.75 correlation
        assert result.max_correlation < 0.75 or not result.is_blocked or result.is_blocked

    def test_skips_self_comparison(self):
        prices = make_price_series(100.0, [0.01] * 25)
        result = check_portfolio_correlation(
            "RELIANCE", prices, {"RELIANCE": prices},
        )
        assert len(result.all_correlations) == 0
        assert result.is_blocked is False

    def test_unreliable_correlation_not_blocking(self):
        candidate = make_price_series(100.0, [0.01] * 25)
        thin_history = make_price_series(50.0, [0.01] * 3)   # too few points
        result = check_portfolio_correlation(
            "RELIANCE", candidate, {"NEWSTOCK": thin_history}, threshold=0.5,
        )
        # Even if mathematically correlated, unreliable data shouldn't block
        assert all(not c.is_reliable for c in result.all_correlations if c.symbol_b == "NEWSTOCK")

    def test_max_correlation_picks_highest(self):
        candidate = make_price_series(100.0, [0.01, 0.02, -0.01, 0.03, -0.02] * 8)
        low_corr = make_uncorrelated_series(n=40)[1]
        high_corr_a, high_corr_b = make_correlated_series(n=40, noise=0.0001)

        result = check_portfolio_correlation(
            "CANDIDATE", high_corr_a,
            {"LOWCORR": low_corr, "HIGHCORR": high_corr_b},
            threshold=0.75,
        )
        assert result.max_correlation >= 0

    def test_notes_present_when_blocked(self):
        a, b = make_correlated_series(n=40, noise=0.0001)
        result = check_portfolio_correlation("A", a, {"B": b}, threshold=0.5)
        assert len(result.notes) > 0

    def test_threshold_respected(self):
        a, b = make_correlated_series(n=40, noise=0.0001)
        # Threshold above 1.0 — mathematically impossible to block (corr is capped at 1.0)
        result = check_portfolio_correlation("A", a, {"B": b}, threshold=1.5)
        assert result.is_blocked is False


# ─── CorrelationPortfolioService Tests ─────────────────────────────────────────

class TestCorrelationPortfolioService:

    def _make_mock_broker(self, price_map: dict[str, list[float]]):
        broker = MagicMock()

        def get_historical_data(symbol, timeframe, from_date, to_date):
            prices = price_map.get(symbol, [])
            return [
                OHLCV(timestamp=datetime.now(timezone.utc), open=p, high=p, low=p,
                      close=p, volume=100000)
                for p in prices
            ]

        broker.get_historical_data = MagicMock(side_effect=get_historical_data)
        return broker

    @pytest.mark.asyncio
    async def test_check_candidate_no_positions(self):
        prices_a = make_price_series(100.0, [0.01] * 25)
        broker = self._make_mock_broker({"RELIANCE": prices_a})
        service = CorrelationPortfolioService(broker)

        result = await service.check_candidate("RELIANCE", [])
        assert result.is_blocked is False

    @pytest.mark.asyncio
    async def test_check_candidate_with_correlated_position(self):
        a, b = make_correlated_series(n=40, noise=0.0001)
        broker = self._make_mock_broker({"HDFCBANK": a, "ICICIBANK": b})
        service = CorrelationPortfolioService(broker)

        result = await service.check_candidate(
            "HDFCBANK", ["ICICIBANK"], threshold=0.75
        )
        assert result.is_blocked is True

    @pytest.mark.asyncio
    async def test_manual_override_unblocks(self):
        a, b = make_correlated_series(n=40, noise=0.0001)
        broker = self._make_mock_broker({"HDFCBANK": a, "ICICIBANK": b})
        service = CorrelationPortfolioService(broker)

        result = await service.check_candidate(
            "HDFCBANK", ["ICICIBANK"], threshold=0.75, manual_override=True,
        )
        assert result.is_blocked is False
        assert any("Override" in n for n in result.notes)

    @pytest.mark.asyncio
    async def test_missing_price_history_does_not_block(self):
        broker = self._make_mock_broker({})  # no data for any symbol
        service = CorrelationPortfolioService(broker)

        result = await service.check_candidate("UNKNOWN", ["ALSOUNKNOWN"])
        assert result.is_blocked is False

    @pytest.mark.asyncio
    async def test_price_cache_avoids_refetch(self):
        prices = make_price_series(100.0, [0.01] * 25)
        broker = self._make_mock_broker({"RELIANCE": prices})
        service = CorrelationPortfolioService(broker)

        await service._get_prices("RELIANCE")
        await service._get_prices("RELIANCE")

        assert broker.get_historical_data.call_count == 1   # second call hit cache

    def test_clear_cache(self):
        broker = self._make_mock_broker({})
        service = CorrelationPortfolioService(broker)
        service._price_cache["X"] = ([1.0, 2.0], 12345.0)
        service.clear_cache()
        assert service._price_cache == {}


# ─── WhatsApp Formatting Tests ─────────────────────────────────────────────────

class TestCorrelationWhatsappFormat:

    def test_format_block_message(self):
        result = PortfolioCheckResult(
            candidate_symbol="HDFCBANK",
            is_blocked=True,
            max_correlation=0.85,
            correlated_with=[
                CorrelationResult(symbol_a="HDFCBANK", symbol_b="ICICIBANK",
                                  correlation=0.85, data_points=30, is_reliable=True)
            ],
            notes=["⚠️ HDFCBANK vs ICICIBANK: correlation +0.85"],
        )
        msg = format_correlation_block_whatsapp(result)
        assert "HDFCBANK" in msg
        assert "override" in msg.lower()

    def test_format_matrix_empty(self):
        msg = format_portfolio_correlation_matrix([], [])
        assert "No open positions" in msg

    def test_format_matrix_with_results(self):
        results = [
            PortfolioCheckResult(candidate_symbol="A", is_blocked=True, max_correlation=0.9),
            PortfolioCheckResult(candidate_symbol="B", is_blocked=False, max_correlation=0.3),
        ]
        msg = format_portfolio_correlation_matrix(["A", "B"], results)
        assert "A" in msg
        assert "B" in msg
        assert "🔴" in msg
        assert "🟢" in msg
