"""
Option Strategy Chain Analysis Tests

Covers core/options/recommender.py's analyse_chain() — deterministic legs/
Greeks/risk-reward for a human-chosen template, no Claude call, no regime
dependency. Rewritten 2026-07-25 when the Claude-driven, regime-gated
recommend_strategy() was removed (see recommender.py's module docstring).
"""

import pytest
from datetime import date, timedelta

from core.options.models import OptionChainSnapshot, OptionLeg, OptionType, StrategyTemplate
from core.options.recommender import analyse_chain, _aggregate_greeks
from core.options.strategy_builder import StrategyBuildError
from core.options.alerts import format_strategy_whatsapp


def make_test_chain(spot: float = 22000.0) -> OptionChainSnapshot:
    expiry = date.today() + timedelta(days=14)
    legs = []
    for offset in range(-1000, 1100, 100):
        strike = spot + offset
        call_premium = max(5.0, 200 - abs(offset) * 0.15) if offset <= 300 else max(5.0, 120 - abs(offset) * 0.1)
        put_premium  = max(5.0, 200 - abs(offset) * 0.15) if offset >= -300 else max(5.0, 120 - abs(offset) * 0.1)
        legs.append(OptionLeg(strike=strike, option_type=OptionType.CALL, expiry=expiry,
                              premium=round(call_premium, 2), open_interest=50000, volume=10000,
                              implied_vol=0.18))
        legs.append(OptionLeg(strike=strike, option_type=OptionType.PUT, expiry=expiry,
                              premium=round(put_premium, 2), open_interest=50000, volume=10000,
                              implied_vol=0.18))
    return OptionChainSnapshot(
        underlying="NIFTY", spot_price=spot, expiry=expiry, legs=legs,
        iv_rank=55.0, iv_percentile=60.0, pcr=1.1, max_pain=spot,
    )


class TestAnalyseChain:

    def test_builds_requested_template(self):
        chain = make_test_chain()
        rec = analyse_chain(chain, StrategyTemplate.BULL_CALL_SPREAD)

        assert rec.strategy == StrategyTemplate.BULL_CALL_SPREAD
        assert rec.underlying == "NIFTY"

    def test_includes_greeks(self):
        chain = make_test_chain()
        rec = analyse_chain(chain, StrategyTemplate.IRON_CONDOR)

        assert rec.net_delta is not None
        assert rec.net_theta is not None
        assert rec.net_vega is not None

    def test_no_rationale_or_confidence_fields(self):
        """The whole point of this rewrite: no Claude narrative or score."""
        chain = make_test_chain()
        rec = analyse_chain(chain, StrategyTemplate.BULL_CALL_SPREAD)

        assert not hasattr(rec, "rationale")
        assert not hasattr(rec, "regime_context")
        assert not hasattr(rec, "confidence_score")

    def test_pop_is_calculated(self):
        chain = make_test_chain()
        rec = analyse_chain(chain, StrategyTemplate.BULL_CALL_SPREAD)

        assert 0 <= rec.probability_of_profit <= 100

    def test_raises_on_unbuildable_template(self):
        # Empty chain has no legs at all — every template should fail to build.
        expiry = date.today() + timedelta(days=14)
        empty_chain = OptionChainSnapshot(
            underlying="NIFTY", spot_price=22000.0, expiry=expiry, legs=[],
            iv_rank=55.0, iv_percentile=60.0, pcr=1.1, max_pain=22000.0,
        )
        with pytest.raises(StrategyBuildError):
            analyse_chain(empty_chain, StrategyTemplate.IRON_CONDOR)


class TestAggregateGreeks:

    def test_aggregates_multi_leg_strategy(self):
        from core.options.strategy_builder import build_strategy
        chain = make_test_chain()
        legs, _ = build_strategy(StrategyTemplate.IRON_CONDOR, chain)

        net_delta, net_gamma, net_theta, net_vega = _aggregate_greeks(legs, chain)

        # Iron condor should be roughly delta-neutral
        assert -0.3 < net_delta < 0.3

    def test_short_strategy_has_positive_theta(self):
        """Premium-selling strategies should show positive net theta (time decay benefits seller)."""
        from core.options.strategy_builder import build_strategy
        chain = make_test_chain()
        legs, _ = build_strategy(StrategyTemplate.SHORT_STRANGLE, chain)

        net_delta, net_gamma, net_theta, net_vega = _aggregate_greeks(legs, chain)
        assert net_theta > 0   # selling options = positive theta


class TestWhatsappFormatting:

    def test_format_includes_underlying_and_strategy(self):
        from core.options.models import StrategyRecommendation, StrategyLeg
        rec = StrategyRecommendation(
            underlying="NIFTY", strategy=StrategyTemplate.IRON_CONDOR,
            legs=[
                StrategyLeg(action="SELL", option_type=OptionType.CALL, strike=22500, premium=80),
                StrategyLeg(action="BUY", option_type=OptionType.CALL, strike=22700, premium=30),
            ],
            net_delta=0.05, net_gamma=0.001, net_theta=15.0, net_vega=-8.0,
            max_profit=5000, max_loss=15000, probability_of_profit=68.0,
        )
        msg = format_strategy_whatsapp(rec)
        assert "NIFTY" in msg
        assert "Iron Condor" in msg
        assert "68" in msg
        assert "No algorithmic recommendation" in msg

    def test_format_handles_unlimited_loss(self):
        from core.options.models import StrategyRecommendation, StrategyLeg
        rec = StrategyRecommendation(
            underlying="NIFTY", strategy=StrategyTemplate.SHORT_STRANGLE,
            legs=[StrategyLeg(action="SELL", option_type=OptionType.CALL, strike=22500, premium=80)],
            net_delta=0.1, net_gamma=0.001, net_theta=10.0, net_vega=-5.0,
            max_profit=8000, max_loss=float("-inf"), probability_of_profit=60.0,
        )
        msg = format_strategy_whatsapp(rec)
        assert "Unlimited" in msg
