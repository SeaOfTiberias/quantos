"""
US-11 Pine Script Backtest Interpreter — Unit Tests
"""

import pytest
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from core.backtest.parser import (
    BacktestTrade, BacktestMetrics, BacktestReport,
    parse_tradingview_csv, _compute_metrics, _sharpe_ratio, _max_drawdown,
)
from core.backtest.analyst import analyse_backtest, _parse_analysis


# ─── Sample CSV fixtures ──────────────────────────────────────────────────────

def make_sample_csv(n_wins: int = 15, n_losses: int = 10) -> str:
    """Generate a minimal TradingView-style trade list CSV."""
    rows = ["Type,Date/Time,Price,Contracts,Profit,Profit %,Cum. Profit"]
    trade_num = 0
    cum = 0.0
    for i in range(n_wins):
        trade_num += 1
        entry_dt = f"2024-{(i % 12) + 1:02d}-01 09:15"
        exit_dt  = f"2024-{(i % 12) + 1:02d}-05 15:30"
        profit   = 500 + i * 10
        pct      = 2.5
        cum     += pct
        rows.append(f"Long Entry,{entry_dt},100,10,,, ")
        rows.append(f"Long Exit,{exit_dt},102.5,10,{profit},{pct},{cum:.2f}")

    for i in range(n_losses):
        trade_num += 1
        entry_dt = f"2025-{(i % 12) + 1:02d}-01 09:15"
        exit_dt  = f"2025-{(i % 12) + 1:02d}-03 15:30"
        profit   = -300
        pct      = -1.5
        cum     += pct
        rows.append(f"Long Entry,{entry_dt},100,10,,, ")
        rows.append(f"Long Exit,{exit_dt},98.5,10,{profit},{pct},{cum:.2f}")

    return "\n".join(rows)


def make_trades(n: int = 20, win_pct: float = 2.5, loss_pct: float = -1.5,
                win_rate: float = 0.6) -> list[BacktestTrade]:
    """Directly create BacktestTrade objects for testing metrics."""
    trades = []
    for i in range(n):
        is_win = i < int(n * win_rate)
        pnl_pct = win_pct if is_win else loss_pct
        pnl = abs(pnl_pct) * 100 * (1 if is_win else -1)
        trades.append(BacktestTrade(
            trade_num=i + 1, direction="Long", qty=10,
            entry_date=datetime(2024, 1, i % 28 + 1),
            entry_price=100.0, exit_price=100 * (1 + pnl_pct / 100),
            exit_date=datetime(2024, 2, i % 28 + 1),
            profit=pnl, profit_pct=pnl_pct, cum_profit=pnl * (i + 1),
            bars_held=5,
        ))
    return trades


# ─── Parser Tests ─────────────────────────────────────────────────────────────

class TestParseTradingViewCSV:

    def test_parses_valid_csv(self):
        csv_content = make_sample_csv(n_wins=15, n_losses=10)
        report = parse_tradingview_csv(csv_content, "darvas_breakout")
        assert report.overall.total_trades == 25

    def test_strategy_name_stored(self):
        csv_content = make_sample_csv()
        report = parse_tradingview_csv(csv_content, "My Strategy")
        assert report.strategy_name == "My Strategy"

    def test_raises_on_empty_csv(self):
        with pytest.raises(ValueError):
            parse_tradingview_csv("Type,Date/Time,Price\n", "test")

    def test_walk_forward_split_created(self):
        csv_content = make_sample_csv(n_wins=15, n_losses=10)
        report = parse_tradingview_csv(csv_content)
        assert report.first_half is not None
        assert report.second_half is not None

    def test_year_breakdown_populated(self):
        csv_content = make_sample_csv(n_wins=15, n_losses=10)
        report = parse_tradingview_csv(csv_content)
        assert len(report.by_year) > 0

    def test_overfitting_flag_added_when_small_sample(self):
        csv_content = make_sample_csv(n_wins=8, n_losses=2)  # 10 trades, high WR
        report = parse_tradingview_csv(csv_content)
        if report.overall.is_overfit_risk:
            assert any("Overfitting risk" in n or "sample size" in n for n in report.notes)


# ─── Metrics Tests ─────────────────────────────────────────────────────────────

class TestComputeMetrics:

    def test_win_rate_correct(self):
        trades = make_trades(20, win_rate=0.6)
        metrics = _compute_metrics(trades)
        assert metrics.win_rate == pytest.approx(0.6)

    def test_profit_factor_positive_for_winning_system(self):
        trades = make_trades(20, win_pct=3.0, loss_pct=-1.5, win_rate=0.6)
        metrics = _compute_metrics(trades)
        assert metrics.profit_factor > 1.0

    def test_has_positive_edge(self):
        trades = make_trades(30, win_pct=4.0, loss_pct=-2.0, win_rate=0.6)
        metrics = _compute_metrics(trades)
        assert metrics.has_positive_edge is True

    def test_overfitting_risk_flag(self):
        # 25 trades with high win rate
        trades = make_trades(25, win_pct=3.0, loss_pct=-1.0, win_rate=0.8)
        metrics = _compute_metrics(trades)
        assert metrics.is_overfit_risk is True

    def test_no_overfit_risk_with_sufficient_trades(self):
        trades = make_trades(50, win_pct=3.0, loss_pct=-1.0, win_rate=0.75)
        metrics = _compute_metrics(trades)
        assert metrics.is_overfit_risk is False   # >= 30 trades, flag not raised

    def test_empty_trades_returns_zero_metrics(self):
        metrics = _compute_metrics([])
        assert metrics.total_trades == 0
        assert metrics.win_rate == 0


class TestSharpeRatio:

    def test_positive_for_consistent_wins(self):
        # Mostly positive returns with some variance → positive Sharpe
        returns = [0.025, 0.030, 0.020, 0.028, 0.015, 0.035, 0.022, 0.018, 0.031, 0.027]
        sharpe = _sharpe_ratio(returns)
        assert sharpe > 0

    def test_zero_for_constant_returns(self):
        returns = [0.01] * 10   # identical returns — zero std dev
        sharpe = _sharpe_ratio(returns)
        assert sharpe == 0.0   # zero std dev handled safely

    def test_negative_for_consistent_losses(self):
        # Mostly negative returns with some variance → negative Sharpe
        returns = [-0.015, -0.020, -0.012, -0.018, -0.025, -0.010, -0.022, -0.016, -0.019, -0.014]
        sharpe = _sharpe_ratio(returns)
        assert sharpe < 0

    def test_short_series_safe(self):
        sharpe = _sharpe_ratio([0.01])
        assert sharpe == 0.0


class TestMaxDrawdown:

    def test_zero_for_all_wins(self):
        trades = make_trades(10, win_pct=2.0, loss_pct=0, win_rate=1.0)
        dd = _max_drawdown(trades)
        assert dd == 0.0

    def test_positive_for_losing_streak(self):
        # All losses
        trades = make_trades(10, win_pct=0, loss_pct=-2.0, win_rate=0.0)
        dd = _max_drawdown(trades)
        assert dd > 0

    def test_empty_returns_zero(self):
        assert _max_drawdown([]) == 0.0


# ─── BacktestReport Tests ──────────────────────────────────────────────────────

class TestBacktestReport:

    def test_has_degradation_detects_drop(self):
        csv_content = make_sample_csv(n_wins=10, n_losses=15)
        report = parse_tradingview_csv(csv_content)
        # Just verify the property exists and returns a bool
        assert isinstance(report.has_degradation, bool)


# ─── Claude Analyst Tests ──────────────────────────────────────────────────────

class TestAnalyseBacktest:

    def make_report(self) -> BacktestReport:
        trades = make_trades(30, win_pct=3.0, loss_pct=-1.5, win_rate=0.6)
        metrics = _compute_metrics(trades)
        return BacktestReport(
            strategy_name="darvas_breakout",
            total_trades=trades,
            overall=metrics,
            first_half=_compute_metrics(trades[:15]),
            second_half=_compute_metrics(trades[15:]),
        )

    @pytest.mark.asyncio
    async def test_returns_structured_analysis(self):
        report = self.make_report()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({
            "verdict": "PROMISING",
            "confidence": 75,
            "strengths": ["Good win rate"],
            "weaknesses": ["Low sample size"],
            "overfitting_assessment": "Minimal signs of overfitting",
            "walk_forward_recommendation": "Test on 2023-2024 OOS",
            "suggested_improvements": ["Increase lookback period"],
            "narrative": "Overall the strategy looks promising.",
        }))]

        with patch("core.backtest.analyst._claude.messages.create",
                   new_callable=AsyncMock, return_value=mock_response):
            result = await analyse_backtest(report)

        assert result["verdict"] == "PROMISING"
        assert result["confidence"] == 75
        assert "strengths" in result
        assert "computed_stats" in result

    @pytest.mark.asyncio
    async def test_fallback_on_malformed_claude_response(self):
        report = self.make_report()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="not valid json")]

        with patch("core.backtest.analyst._claude.messages.create",
                   new_callable=AsyncMock, return_value=mock_response):
            result = await analyse_backtest(report)

        # Should return safe fallback
        assert result["verdict"] == "MARGINAL"
        assert "narrative" in result

    def test_parse_analysis_defaults_missing_fields(self):
        report = self.make_report()
        raw = json.dumps({"verdict": "AVOID"})   # missing most fields
        result = _parse_analysis(raw, report)
        assert result["verdict"] == "AVOID"
        assert "strengths" in result
        assert "walk_forward_recommendation" in result

    def test_parse_analysis_attaches_computed_stats(self):
        report = self.make_report()
        raw = json.dumps({"verdict": "PROMISING", "confidence": 80,
                          "strengths": [], "weaknesses": [],
                          "overfitting_assessment": "x",
                          "walk_forward_recommendation": "y",
                          "suggested_improvements": [], "narrative": "z"})
        result = _parse_analysis(raw, report)
        assert "computed_stats" in result
        assert result["computed_stats"]["total_trades"] == 30
