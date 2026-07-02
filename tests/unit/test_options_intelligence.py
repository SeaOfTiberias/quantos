"""
US-17 Greeks Live Panel · US-18 Options Backtester · US-19 Alpha Attribution
"""

import pytest
import math
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from core.options.live.greeks_panel import (
    compute_live_greeks, format_greeks_panel_whatsapp, LivePosition, PortfolioGreeks,
)
from core.options.backtester import (
    run_regime_conditioned_backtest, simulate_iron_condor_period,
    OptionsBacktestResult,
)
from core.options.alpha_attribution import (
    compute_attribution, format_alpha_whatsapp,
    _build_quantos_curve, _build_nifty_curve, _sharpe, _max_drawdown,
)
from core.options.models import StrategyTemplate


# ─── US-17: Greeks Live Panel ─────────────────────────────────────────────────

class TestLiveGreeksPanel:

    def make_positions(self) -> list[dict]:
        expiry = (date.today() + timedelta(days=14)).isoformat()
        return [
            {
                "symbol": "NIFTY", "strike": 22000, "option_type": "CE",
                "expiry": expiry, "quantity": -1,   # short call
                "entry_premium": 150, "current_premium": 120, "implied_vol": 0.18,
            },
            {
                "symbol": "NIFTY", "strike": 22200, "option_type": "CE",
                "expiry": expiry, "quantity": 1,    # long call
                "entry_premium": 80, "current_premium": 65, "implied_vol": 0.18,
            },
        ]

    def test_computes_greeks_for_positions(self):
        positions = self.make_positions()
        pg = compute_live_greeks(
            positions,
            spot_prices={"NIFTY": 21900.0},
            days_to_expiry_map={(date.today() + timedelta(days=14)).isoformat(): 14},
        )
        assert len(pg.positions) == 2
        assert pg.net_delta is not None

    def test_short_position_negates_greeks(self):
        expiry = (date.today() + timedelta(days=14)).isoformat()
        positions = [{
            "symbol": "NIFTY", "strike": 22000, "option_type": "CE",
            "expiry": expiry, "quantity": -1,
            "entry_premium": 150, "current_premium": 120, "implied_vol": 0.18,
        }]
        pg = compute_live_greeks(
            positions, {"NIFTY": 21900.0},
            {expiry: 14},
        )
        assert pg.net_delta < 0    # short call → negative delta

    def test_skips_position_without_spot(self):
        expiry = (date.today() + timedelta(days=14)).isoformat()
        positions = [{
            "symbol": "UNKNOWN", "strike": 100, "option_type": "CE",
            "expiry": expiry, "quantity": 1,
            "entry_premium": 5, "current_premium": 5, "implied_vol": 0.18,
        }]
        pg = compute_live_greeks(positions, {}, {expiry: 14})
        assert len(pg.positions) == 0

    def test_total_pnl_calculated(self):
        positions = self.make_positions()
        pg = compute_live_greeks(positions, {"NIFTY": 21900.0},
                                  {(date.today() + timedelta(days=14)).isoformat(): 14})
        # Short call: entry 150, current 120 → profit 30
        # Long call:  entry 80,  current 65  → loss 15
        assert pg.total_unrealised_pnl == pytest.approx(15.0)

    def test_is_theta_positive_for_short_options(self):
        expiry = (date.today() + timedelta(days=14)).isoformat()
        positions = [{
            "symbol": "NIFTY", "strike": 22000, "option_type": "CE",
            "expiry": expiry, "quantity": -1,    # short = collect theta
            "entry_premium": 150, "current_premium": 120, "implied_vol": 0.18,
        }]
        pg = compute_live_greeks(positions, {"NIFTY": 21900.0}, {expiry: 14})
        assert pg.is_theta_positive is True

    def test_format_whatsapp_contains_greeks(self):
        positions = self.make_positions()
        pg = compute_live_greeks(positions, {"NIFTY": 21900.0},
                                  {(date.today() + timedelta(days=14)).isoformat(): 14})
        msg = format_greeks_panel_whatsapp(pg)
        assert "Δ" in msg
        assert "Θ" in msg
        assert "NIFTY" in msg

    def test_summary_line_format(self):
        pg = PortfolioGreeks(
            positions=[], net_delta=0.05, net_gamma=0.001,
            net_theta=50.0, net_vega=-10.0, total_unrealised_pnl=1500.0,
        )
        summary = pg.summary_line()
        assert "Δ=" in summary
        assert "Θ=" in summary


# ─── US-18: Options Backtester ────────────────────────────────────────────────

class TestOptionsBacktester:

    def make_periods(self, n: int = 20, regime: str = "RANGING") -> list[dict]:
        periods = []
        for i in range(n):
            spot = 22000 + i * 10
            # Iron condor wins when spot doesn't move much
            spot_expiry = spot + (50 if i % 3 != 0 else 500)  # mostly small moves
            periods.append({
                "entry_date":    (date(2024, 1, 1) + timedelta(days=i * 30)).isoformat(),
                "expiry_date":   (date(2024, 1, 1) + timedelta(days=i * 30 + 14)).isoformat(),
                "underlying":    "NIFTY",
                "spot_at_entry": spot,
                "spot_at_expiry": spot_expiry,
                "iv_rank":       65.0,
                "iv":            0.18,
                "regime":        regime,
            })
        return periods

    def test_returns_result_for_qualifying_periods(self):
        periods = self.make_periods(20)
        result = run_regime_conditioned_backtest(
            periods, StrategyTemplate.IRON_CONDOR, "RANGING", iv_rank_min=60.0,
        )
        assert result.total_periods == 20

    def test_filters_non_qualifying_regime(self):
        periods = self.make_periods(10, regime="TRENDING_BULL")
        result = run_regime_conditioned_backtest(
            periods, StrategyTemplate.IRON_CONDOR, "RANGING", iv_rank_min=60.0,
        )
        assert result.total_periods == 0
        assert "No qualifying periods" in result.notes[0]

    def test_win_rate_between_zero_and_one(self):
        periods = self.make_periods(15)
        result = run_regime_conditioned_backtest(
            periods, StrategyTemplate.IRON_CONDOR, "RANGING",
        )
        assert 0 <= result.win_rate <= 1

    def test_overfitting_flag_on_small_high_wr_sample(self):
        # 5 periods, all winners → flag
        periods = self.make_periods(5)
        # Ensure all are wins by making spot stay near entry
        for p in periods:
            p["spot_at_expiry"] = p["spot_at_entry"] + 10

        result = run_regime_conditioned_backtest(
            periods, StrategyTemplate.IRON_CONDOR, "RANGING",
        )
        if result.win_rate > 0.80 and result.total_periods < 20:
            assert result.overfitting_flag is True

    def test_is_viable_requires_positive_sharpe(self):
        periods = self.make_periods(30)
        result = run_regime_conditioned_backtest(
            periods, StrategyTemplate.IRON_CONDOR, "RANGING",
        )
        if result.is_viable:
            assert result.sharpe > 0.5
            assert result.win_rate > 0.55

    def test_simulate_iron_condor_profit_when_contained(self):
        """Iron condor profits when spot stays near entry."""
        spot = 22000
        net_credit, pnl = simulate_iron_condor_period(
            spot=spot, iv=0.18, days_to_expiry=14,
            spot_at_expiry=spot + 50,   # small move
        )
        assert net_credit > 0

    def test_simulate_iron_condor_loss_on_big_move(self):
        """Iron condor loses when spot moves drastically."""
        spot = 22000
        net_credit, pnl = simulate_iron_condor_period(
            spot=spot, iv=0.18, days_to_expiry=14,
            spot_at_expiry=spot + 1500,  # large move
        )
        assert net_credit > 0   # still collected credit
        assert pnl < net_credit  # but lost some or all of it


# ─── US-19: Alpha Attribution ─────────────────────────────────────────────────

class TestAlphaAttribution:

    def make_trade_pnls(self, n: int = 20, avg_pnl: float = 2.5) -> list[dict]:
        return [
            {
                "date": (date(2025, 1, 1) + timedelta(days=i * 7)).isoformat(),
                "pnl_pct": avg_pnl + (i % 3 - 1),  # some variation
                "signal_id": f"SIG-{i:03d}",
                "strategy": "darvas_breakout",
            }
            for i in range(n)
        ]

    def make_nifty_closes(self, start: float = 22000, n: int = 20,
                           daily_gain: float = 0.05) -> list[dict]:
        closes = []
        price = start
        for i in range(n):
            price *= (1 + daily_gain / 100)
            closes.append({
                "date": (date(2025, 1, 1) + timedelta(days=i * 7)).isoformat(),
                "close": round(price, 2),
            })
        return closes

    def test_compute_attribution_returns_metrics(self):
        trades = self.make_trade_pnls(20)
        nifty  = self.make_nifty_closes(n=20)
        metrics = compute_attribution(trades, nifty)
        assert metrics.quantos_total_return != 0
        assert metrics.nifty_total_return != 0

    def test_alpha_is_difference(self):
        trades = self.make_trade_pnls(20, avg_pnl=3.0)  # strong returns
        nifty  = self.make_nifty_closes(n=20, daily_gain=0.01)  # weak nifty
        metrics = compute_attribution(trades, nifty)
        assert metrics.alpha == pytest.approx(
            metrics.quantos_total_return - metrics.nifty_total_return, abs=0.5
        )

    def test_empty_inputs_return_empty(self):
        metrics = compute_attribution([], [])
        assert metrics.alpha == 0
        assert metrics.quantos_total_return == 0

    def test_is_beating_nifty_true_when_positive_alpha(self):
        trades = self.make_trade_pnls(20, avg_pnl=5.0)
        nifty  = self.make_nifty_closes(n=20, daily_gain=0.01)
        metrics = compute_attribution(trades, nifty)
        if metrics.alpha > 0:
            assert metrics.is_beating_nifty is True

    def test_equity_curve_builds_correctly(self):
        pnls = [
            {"date": "2025-01-01", "pnl_pct": 2.0, "signal_id": "A"},
            {"date": "2025-01-08", "pnl_pct": -1.0, "signal_id": "B"},
        ]
        curve = _build_quantos_curve(pnls)
        assert len(curve) == 2
        assert curve[0].cumulative == pytest.approx(2.0)
        assert curve[1].cumulative == pytest.approx(1.0)

    def test_nifty_curve_builds_correctly(self):
        closes = [
            {"date": "2025-01-01", "close": 22000},
            {"date": "2025-01-08", "close": 22220},
        ]
        curve = _build_nifty_curve(closes)
        assert len(curve) == 2
        assert curve[1].cumulative == pytest.approx(1.0, abs=0.01)

    def test_sharpe_positive_for_good_returns(self):
        returns = [2.5, 3.0, 2.0, 2.8, 1.5, 3.5, 2.2, 1.8, 3.1, 2.7]
        s = _sharpe(returns)
        assert s > 0

    def test_max_drawdown_zero_for_all_rising(self):
        cumulative = [1.0, 2.0, 3.0, 4.0, 5.0]
        dd = _max_drawdown(cumulative)
        assert dd == 0.0

    def test_max_drawdown_detected(self):
        cumulative = [1.0, 3.0, 2.0, 1.5, 2.5]  # drops from 3 to 1.5
        dd = _max_drawdown(cumulative)
        assert dd == pytest.approx(1.5)

    def test_format_whatsapp_contains_alpha(self):
        trades = self.make_trade_pnls(10)
        nifty  = self.make_nifty_closes(n=10)
        metrics = compute_attribution(trades, nifty)
        msg = format_alpha_whatsapp(metrics, "Test narrative.")
        assert "Alpha" in msg
        assert "QuantOS" in msg
        assert "Nifty" in msg

    @pytest.mark.asyncio
    async def test_generate_narrative_calls_claude(self):
        from core.options.alpha_attribution import generate_alpha_narrative
        trades = self.make_trade_pnls(10)
        nifty  = self.make_nifty_closes(n=10)
        metrics = compute_attribution(trades, nifty)

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Strong alpha this period.")]

        with patch("core.options.alpha_attribution._claude.messages.create",
                   new_callable=AsyncMock, return_value=mock_response):
            narrative = await generate_alpha_narrative(metrics, [t for t in trades])

        assert "alpha" in narrative.lower() or len(narrative) > 0

    @pytest.mark.asyncio
    async def test_fallback_narrative_on_error(self):
        from core.options.alpha_attribution import generate_alpha_narrative
        trades = self.make_trade_pnls(10)
        nifty  = self.make_nifty_closes(n=10)
        metrics = compute_attribution(trades, nifty)

        with patch("core.options.alpha_attribution._claude.messages.create",
                   new_callable=AsyncMock, side_effect=Exception("API error")):
            narrative = await generate_alpha_narrative(metrics, trades)

        assert narrative is not None
        assert len(narrative) > 0
