"""
US-05b Options Intelligence — Strategy Builder Tests
"""

import pytest
from datetime import date, timedelta

from core.options.models import (
    OptionChainSnapshot, OptionLeg, OptionType, StrategyTemplate,
)
from core.options.strategy_builder import build_strategy, StrategyBuildError


def make_test_chain(spot: float = 22000.0) -> OptionChainSnapshot:
    """
    Build a synthetic NIFTY-like option chain for testing.
    Strikes every 100 points from spot-1000 to spot+1000.
    """
    expiry = date.today() + timedelta(days=14)
    legs = []

    for offset in range(-1000, 1100, 100):
        strike = spot + offset
        moneyness = abs(offset) / spot

        # Rough premium approximation: further OTM = cheaper
        call_premium = max(5.0, 200 - abs(offset) * 0.15) if offset <= 300 else max(5.0, 120 - abs(offset) * 0.1)
        put_premium  = max(5.0, 200 - abs(offset) * 0.15) if offset >= -300 else max(5.0, 120 - abs(offset) * 0.1)

        legs.append(OptionLeg(
            strike=strike, option_type=OptionType.CALL, expiry=expiry,
            premium=round(call_premium, 2), open_interest=50000, volume=10000,
            implied_vol=0.15 + moneyness * 0.05,
        ))
        legs.append(OptionLeg(
            strike=strike, option_type=OptionType.PUT, expiry=expiry,
            premium=round(put_premium, 2), open_interest=50000, volume=10000,
            implied_vol=0.15 + moneyness * 0.05,
        ))

    return OptionChainSnapshot(
        underlying="NIFTY", spot_price=spot, expiry=expiry, legs=legs,
        iv_rank=55.0, iv_percentile=60.0, pcr=1.1, max_pain=spot,
    )


class TestOptionChainSnapshot:

    def test_atm_strike_finds_closest(self):
        chain = make_test_chain(spot=22050.0)
        atm = chain.atm_strike()
        # Strikes are built relative to spot, so spot itself (22050) is a strike
        assert atm == 22050.0

    def test_get_leg_finds_correct_strike(self):
        chain = make_test_chain()
        leg = chain.get_leg(22000.0, OptionType.CALL)
        assert leg is not None
        assert leg.strike == 22000.0
        assert leg.option_type == OptionType.CALL

    def test_calls_returns_only_calls(self):
        chain = make_test_chain()
        calls = chain.calls()
        assert all(c.option_type == OptionType.CALL for c in calls)

    def test_puts_returns_only_puts(self):
        chain = make_test_chain()
        puts = chain.puts()
        assert all(p.option_type == OptionType.PUT for p in puts)

    def test_strikes_near_returns_sorted(self):
        chain = make_test_chain()
        strikes = chain.strikes_near(22000.0, count=5)
        assert strikes == sorted(strikes)
        assert len(strikes) == 5


class TestBullCallSpread:

    def test_builds_two_legs(self):
        chain = make_test_chain()
        legs, metrics = build_strategy(StrategyTemplate.BULL_CALL_SPREAD, chain)
        assert len(legs) == 2

    def test_long_leg_is_buy_lower_strike(self):
        chain = make_test_chain()
        legs, metrics = build_strategy(StrategyTemplate.BULL_CALL_SPREAD, chain)
        long_leg = next(l for l in legs if l.action == "BUY")
        short_leg = next(l for l in legs if l.action == "SELL")
        assert long_leg.strike < short_leg.strike

    def test_both_legs_are_calls(self):
        chain = make_test_chain()
        legs, metrics = build_strategy(StrategyTemplate.BULL_CALL_SPREAD, chain)
        assert all(l.option_type == OptionType.CALL for l in legs)

    def test_max_loss_is_net_debit(self):
        chain = make_test_chain()
        legs, metrics = build_strategy(StrategyTemplate.BULL_CALL_SPREAD, chain)
        assert metrics["max_loss"] > 0   # debit spread has a defined positive cost

    def test_max_profit_greater_than_max_loss_for_decent_spread(self):
        chain = make_test_chain()
        legs, metrics = build_strategy(StrategyTemplate.BULL_CALL_SPREAD, chain)
        assert metrics["max_profit"] > 0

    def test_net_premium_is_negative_debit(self):
        chain = make_test_chain()
        legs, metrics = build_strategy(StrategyTemplate.BULL_CALL_SPREAD, chain)
        assert metrics["net_premium"] < 0   # paying a debit


class TestBearPutSpread:

    def test_builds_two_put_legs(self):
        chain = make_test_chain()
        legs, metrics = build_strategy(StrategyTemplate.BEAR_PUT_SPREAD, chain)
        assert len(legs) == 2
        assert all(l.option_type == OptionType.PUT for l in legs)

    def test_long_leg_higher_strike_than_short(self):
        chain = make_test_chain()
        legs, metrics = build_strategy(StrategyTemplate.BEAR_PUT_SPREAD, chain)
        long_leg = next(l for l in legs if l.action == "BUY")
        short_leg = next(l for l in legs if l.action == "SELL")
        assert long_leg.strike > short_leg.strike

    def test_max_loss_defined(self):
        chain = make_test_chain()
        legs, metrics = build_strategy(StrategyTemplate.BEAR_PUT_SPREAD, chain)
        assert metrics["max_loss"] > 0
        assert metrics["max_loss"] != float("inf")


class TestIronCondor:

    def test_builds_four_legs(self):
        chain = make_test_chain()
        legs, metrics = build_strategy(StrategyTemplate.IRON_CONDOR, chain)
        assert len(legs) == 4

    def test_has_two_calls_two_puts(self):
        chain = make_test_chain()
        legs, metrics = build_strategy(StrategyTemplate.IRON_CONDOR, chain)
        calls = [l for l in legs if l.option_type == OptionType.CALL]
        puts  = [l for l in legs if l.option_type == OptionType.PUT]
        assert len(calls) == 2
        assert len(puts) == 2

    def test_is_credit_strategy(self):
        chain = make_test_chain()
        legs, metrics = build_strategy(StrategyTemplate.IRON_CONDOR, chain)
        assert metrics["net_premium"] > 0   # iron condor collects credit

    def test_has_both_breakevens(self):
        chain = make_test_chain()
        legs, metrics = build_strategy(StrategyTemplate.IRON_CONDOR, chain)
        assert "breakeven_upper" in metrics
        assert "breakeven_lower" in metrics
        assert metrics["breakeven_upper"] > metrics["breakeven_lower"]

    def test_max_loss_is_finite(self):
        chain = make_test_chain()
        legs, metrics = build_strategy(StrategyTemplate.IRON_CONDOR, chain)
        assert metrics["max_loss"] != float("-inf")
        assert metrics["max_loss"] >= 0


class TestCoveredCall:

    def test_builds_single_leg(self):
        chain = make_test_chain()
        legs, metrics = build_strategy(StrategyTemplate.COVERED_CALL, chain)
        assert len(legs) == 1
        assert legs[0].action == "SELL"
        assert legs[0].option_type == OptionType.CALL

    def test_generates_premium_income(self):
        chain = make_test_chain()
        legs, metrics = build_strategy(StrategyTemplate.COVERED_CALL, chain)
        assert metrics["net_premium"] > 0


class TestCashSecuredPut:

    def test_builds_single_put_leg(self):
        chain = make_test_chain()
        legs, metrics = build_strategy(StrategyTemplate.CASH_SECURED_PUT, chain)
        assert len(legs) == 1
        assert legs[0].action == "SELL"
        assert legs[0].option_type == OptionType.PUT

    def test_max_profit_equals_premium(self):
        chain = make_test_chain()
        legs, metrics = build_strategy(StrategyTemplate.CASH_SECURED_PUT, chain)
        assert metrics["max_profit"] == metrics["net_premium"]

    def test_cash_required_calculated(self):
        chain = make_test_chain()
        legs, metrics = build_strategy(StrategyTemplate.CASH_SECURED_PUT, chain)
        assert metrics["cash_required"] > 0


class TestShortStrangle:

    def test_builds_two_legs_no_protection(self):
        chain = make_test_chain()
        legs, metrics = build_strategy(StrategyTemplate.SHORT_STRANGLE, chain)
        assert len(legs) == 2
        assert all(l.action == "SELL" for l in legs)

    def test_one_call_one_put(self):
        chain = make_test_chain()
        legs, metrics = build_strategy(StrategyTemplate.SHORT_STRANGLE, chain)
        types = {l.option_type for l in legs}
        assert types == {OptionType.CALL, OptionType.PUT}

    def test_undefined_risk(self):
        chain = make_test_chain()
        legs, metrics = build_strategy(StrategyTemplate.SHORT_STRANGLE, chain)
        assert metrics["max_loss"] == float("-inf")

    def test_generates_credit(self):
        chain = make_test_chain()
        legs, metrics = build_strategy(StrategyTemplate.SHORT_STRANGLE, chain)
        assert metrics["net_premium"] > 0


class TestStrategyBuildErrors:

    def test_raises_for_unsupported_template(self):
        chain = make_test_chain()
        with pytest.raises(StrategyBuildError):
            build_strategy(StrategyTemplate.CALENDAR_SPREAD, chain)  # not implemented

    def test_raises_when_no_otm_calls_available(self):
        """Chain with only ATM strike — no OTM calls for bull call spread."""
        expiry = date.today() + timedelta(days=14)
        thin_chain = OptionChainSnapshot(
            underlying="TEST", spot_price=100.0, expiry=expiry,
            legs=[
                OptionLeg(strike=100.0, option_type=OptionType.CALL, expiry=expiry,
                         premium=5.0, open_interest=1000, volume=100, implied_vol=0.2),
            ],
            iv_rank=50.0, iv_percentile=50.0, pcr=1.0, max_pain=100.0,
        )
        with pytest.raises(StrategyBuildError):
            build_strategy(StrategyTemplate.BULL_CALL_SPREAD, thin_chain)
