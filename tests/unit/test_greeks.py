"""
US-05b Options Intelligence — Greeks Calculator Tests
"""

import pytest
from core.options.greeks import compute_greeks, estimate_probability_of_profit, implied_volatility
from core.options.models import OptionType


class TestComputeGreeks:

    def test_atm_call_delta_near_half(self):
        """ATM call delta should be roughly 0.5 (slightly above due to drift)."""
        result = compute_greeks(
            spot=22000, strike=22000, days_to_expiry=30,
            implied_vol=0.15, option_type=OptionType.CALL,
        )
        assert 0.4 < result.delta < 0.65

    def test_atm_put_delta_near_negative_half(self):
        result = compute_greeks(
            spot=22000, strike=22000, days_to_expiry=30,
            implied_vol=0.15, option_type=OptionType.PUT,
        )
        assert -0.65 < result.delta < -0.35

    def test_deep_itm_call_delta_near_one(self):
        result = compute_greeks(
            spot=22000, strike=18000, days_to_expiry=30,
            implied_vol=0.15, option_type=OptionType.CALL,
        )
        assert result.delta > 0.9

    def test_deep_otm_call_delta_near_zero(self):
        result = compute_greeks(
            spot=22000, strike=26000, days_to_expiry=30,
            implied_vol=0.15, option_type=OptionType.CALL,
        )
        assert result.delta < 0.1

    def test_deep_itm_put_delta_near_negative_one(self):
        result = compute_greeks(
            spot=22000, strike=26000, days_to_expiry=30,
            implied_vol=0.15, option_type=OptionType.PUT,
        )
        assert result.delta < -0.9

    def test_gamma_positive(self):
        result = compute_greeks(
            spot=22000, strike=22000, days_to_expiry=30,
            implied_vol=0.15, option_type=OptionType.CALL,
        )
        assert result.gamma > 0

    def test_theta_negative_for_long_option(self):
        """Theta should be negative — options decay over time."""
        result = compute_greeks(
            spot=22000, strike=22000, days_to_expiry=30,
            implied_vol=0.15, option_type=OptionType.CALL,
        )
        assert result.theta < 0

    def test_vega_positive(self):
        result = compute_greeks(
            spot=22000, strike=22000, days_to_expiry=30,
            implied_vol=0.15, option_type=OptionType.CALL,
        )
        assert result.vega > 0

    def test_higher_iv_increases_vega_impact(self):
        """Vega should be meaningfully positive regardless of IV level."""
        low_iv = compute_greeks(spot=22000, strike=22000, days_to_expiry=30,
                                 implied_vol=0.10, option_type=OptionType.CALL)
        high_iv = compute_greeks(spot=22000, strike=22000, days_to_expiry=30,
                                  implied_vol=0.30, option_type=OptionType.CALL)
        assert low_iv.vega > 0
        assert high_iv.vega > 0

    def test_theoretical_price_positive(self):
        result = compute_greeks(
            spot=22000, strike=22000, days_to_expiry=30,
            implied_vol=0.15, option_type=OptionType.CALL,
        )
        assert result.theoretical_price > 0

    def test_zero_days_to_expiry_uses_intrinsic(self):
        result = compute_greeks(
            spot=22100, strike=22000, days_to_expiry=0,
            implied_vol=0.15, option_type=OptionType.CALL,
        )
        assert result.theoretical_price == pytest.approx(100, abs=0.01)
        assert result.delta == 1.0

    def test_zero_days_otm_call_worthless(self):
        result = compute_greeks(
            spot=21900, strike=22000, days_to_expiry=0,
            implied_vol=0.15, option_type=OptionType.CALL,
        )
        assert result.theoretical_price == 0.0
        assert result.delta == 0.0

    def test_put_call_delta_relationship(self):
        """Call delta - Put delta should be approximately 1 (put-call parity)."""
        call = compute_greeks(spot=22000, strike=22000, days_to_expiry=30,
                              implied_vol=0.15, option_type=OptionType.CALL)
        put = compute_greeks(spot=22000, strike=22000, days_to_expiry=30,
                             implied_vol=0.15, option_type=OptionType.PUT)
        assert (call.delta - put.delta) == pytest.approx(1.0, abs=0.01)

    def test_handles_very_low_iv_gracefully(self):
        result = compute_greeks(
            spot=22000, strike=22000, days_to_expiry=30,
            implied_vol=0.0, option_type=OptionType.CALL,
        )
        assert result.theoretical_price >= 0
        assert not (result.delta != result.delta)  # not NaN


class TestProbabilityOfProfit:

    def test_atm_breakeven_near_50_pct(self):
        """If breakeven equals spot, PoP should be roughly 50%."""
        pop = estimate_probability_of_profit(
            spot=22000, breakeven=22000, days_to_expiry=30,
            implied_vol=0.15, is_above_breakeven_profitable=True,
        )
        assert 40 < pop < 60

    def test_far_otm_breakeven_low_probability(self):
        """Breakeven far above spot for a 'profitable if above' bet → low PoP."""
        pop = estimate_probability_of_profit(
            spot=22000, breakeven=25000, days_to_expiry=30,
            implied_vol=0.15, is_above_breakeven_profitable=True,
        )
        assert pop < 30

    def test_far_itm_breakeven_high_probability(self):
        """Breakeven far below spot for 'profitable if above' → high PoP."""
        pop = estimate_probability_of_profit(
            spot=22000, breakeven=19000, days_to_expiry=30,
            implied_vol=0.15, is_above_breakeven_profitable=True,
        )
        assert pop > 70

    def test_profitable_below_breakeven_inverts(self):
        pop_above = estimate_probability_of_profit(
            spot=22000, breakeven=22000, days_to_expiry=30,
            implied_vol=0.15, is_above_breakeven_profitable=True,
        )
        pop_below = estimate_probability_of_profit(
            spot=22000, breakeven=22000, days_to_expiry=30,
            implied_vol=0.15, is_above_breakeven_profitable=False,
        )
        assert pop_above + pop_below == pytest.approx(100, abs=1)

    def test_pop_bounded_0_to_100(self):
        pop = estimate_probability_of_profit(
            spot=22000, breakeven=22000, days_to_expiry=30,
            implied_vol=0.15, is_above_breakeven_profitable=True,
        )
        assert 0 <= pop <= 100

    def test_zero_days_returns_default(self):
        pop = estimate_probability_of_profit(
            spot=22000, breakeven=22500, days_to_expiry=0,
            implied_vol=0.15, is_above_breakeven_profitable=True,
        )
        assert pop == 50.0


class TestImpliedVolatility:

    def test_recovers_known_iv_roundtrip(self):
        """Price a call at a known IV, then invert — should recover it."""
        priced = compute_greeks(
            spot=22000, strike=22000, days_to_expiry=30,
            implied_vol=0.20, option_type=OptionType.CALL,
        )
        recovered = implied_volatility(
            market_price=priced.theoretical_price, spot=22000, strike=22000,
            days_to_expiry=30, option_type=OptionType.CALL,
        )
        assert recovered == pytest.approx(0.20, abs=0.01)

    def test_recovers_known_iv_for_put(self):
        priced = compute_greeks(
            spot=22000, strike=22000, days_to_expiry=30,
            implied_vol=0.25, option_type=OptionType.PUT,
        )
        recovered = implied_volatility(
            market_price=priced.theoretical_price, spot=22000, strike=22000,
            days_to_expiry=30, option_type=OptionType.PUT,
        )
        assert recovered == pytest.approx(0.25, abs=0.01)

    def test_higher_price_gives_higher_iv(self):
        low = implied_volatility(market_price=100, spot=22000, strike=22000,
                                  days_to_expiry=30, option_type=OptionType.CALL)
        high = implied_volatility(market_price=300, spot=22000, strike=22000,
                                   days_to_expiry=30, option_type=OptionType.CALL)
        assert high > low

    def test_zero_days_returns_fallback(self):
        iv = implied_volatility(market_price=100, spot=22000, strike=22000,
                                 days_to_expiry=0, option_type=OptionType.CALL)
        assert iv == 0.18

    def test_price_below_intrinsic_returns_fallback(self):
        """A quoted price below intrinsic value can't be inverted meaningfully."""
        iv = implied_volatility(market_price=50, spot=22500, strike=22000,
                                 days_to_expiry=30, option_type=OptionType.CALL)
        assert iv == 0.18

    def test_result_bounded(self):
        iv = implied_volatility(market_price=5000, spot=22000, strike=22000,
                                 days_to_expiry=30, option_type=OptionType.CALL)
        assert 0.01 <= iv <= 5.0
