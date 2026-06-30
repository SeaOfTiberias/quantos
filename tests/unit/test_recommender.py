"""
US-05b Options Intelligence — Claude Recommender Tests
"""

import pytest
import json
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from core.options.models import OptionChainSnapshot, OptionLeg, OptionType, StrategyTemplate
from core.options.recommender import recommend_strategy, _parse_strategy_choice, _aggregate_greeks
from core.options.alerts import format_strategy_whatsapp
from core.regime.models import Regime, RegimeResult


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


def make_regime(regime_type: Regime = Regime.TRENDING_BULL, strategies=None) -> RegimeResult:
    from datetime import datetime, timezone
    return RegimeResult(
        regime=regime_type,
        confidence=80.0,
        allowed_strategies=strategies or ["darvas_breakout", "bull_call_spread", "covered_call"],
        size_multiplier=1.0,
        timestamp=datetime.now(timezone.utc),
        trend_signal="BULL",
        vix_signal="LOW",
        breadth_signal="STRONG",
    )


def make_claude_response(strategy: str, confidence: float = 80.0, rationale: str = "Test rationale"):
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=json.dumps({
        "strategy": strategy,
        "confidence": confidence,
        "rationale": rationale,
    }))]
    return mock_response


class TestRecommendStrategy:

    @pytest.mark.asyncio
    async def test_recommends_allowed_strategy(self):
        chain = make_test_chain()
        regime = make_regime(strategies=["bull_call_spread"])

        with patch("core.options.recommender._claude.messages.create",
                   new_callable=AsyncMock,
                   return_value=make_claude_response("bull_call_spread")):
            rec = await recommend_strategy(chain, regime)

        assert rec.strategy == StrategyTemplate.BULL_CALL_SPREAD
        assert rec.underlying == "NIFTY"

    @pytest.mark.asyncio
    async def test_raises_when_no_strategies_allowed(self):
        chain = make_test_chain()
        regime = make_regime(strategies=["darvas_breakout"])  # not an options strategy

        with pytest.raises(ValueError):
            await recommend_strategy(chain, regime)

    @pytest.mark.asyncio
    async def test_recommendation_includes_greeks(self):
        chain = make_test_chain()
        regime = make_regime(strategies=["iron_condor"])

        with patch("core.options.recommender._claude.messages.create",
                   new_callable=AsyncMock,
                   return_value=make_claude_response("iron_condor")):
            rec = await recommend_strategy(chain, regime)

        assert rec.net_delta is not None
        assert rec.net_theta is not None
        assert rec.net_vega is not None

    @pytest.mark.asyncio
    async def test_recommendation_includes_rationale(self):
        chain = make_test_chain()
        regime = make_regime(strategies=["bull_call_spread"])

        with patch("core.options.recommender._claude.messages.create",
                   new_callable=AsyncMock,
                   return_value=make_claude_response("bull_call_spread", rationale="Bullish breakout setup")):
            rec = await recommend_strategy(chain, regime)

        assert rec.rationale == "Bullish breakout setup"

    @pytest.mark.asyncio
    async def test_falls_back_when_claude_picks_invalid_strategy(self):
        chain = make_test_chain()
        regime = make_regime(strategies=["bull_call_spread", "covered_call"])

        # Claude hallucinates a strategy not in the allowed list
        with patch("core.options.recommender._claude.messages.create",
                   new_callable=AsyncMock,
                   return_value=make_claude_response("naked_call_invalid")):
            rec = await recommend_strategy(chain, regime)

        # Should fall back to first allowed strategy
        assert rec.strategy in [StrategyTemplate.BULL_CALL_SPREAD, StrategyTemplate.COVERED_CALL]

    @pytest.mark.asyncio
    async def test_pop_is_calculated(self):
        chain = make_test_chain()
        regime = make_regime(strategies=["bull_call_spread"])

        with patch("core.options.recommender._claude.messages.create",
                   new_callable=AsyncMock,
                   return_value=make_claude_response("bull_call_spread")):
            rec = await recommend_strategy(chain, regime)

        assert 0 <= rec.probability_of_profit <= 100

    @pytest.mark.asyncio
    async def test_regime_context_included(self):
        chain = make_test_chain()
        regime = make_regime(regime_type=Regime.RANGING, strategies=["iron_condor"])

        with patch("core.options.recommender._claude.messages.create",
                   new_callable=AsyncMock,
                   return_value=make_claude_response("iron_condor")):
            rec = await recommend_strategy(chain, regime)

        assert "RANGING" in rec.regime_context


class TestParseStrategyChoice:

    def test_parses_valid_json(self):
        raw = json.dumps({"strategy": "iron_condor", "confidence": 75, "rationale": "test"})
        result = _parse_strategy_choice(raw, ["iron_condor", "bull_call_spread"])
        assert result["strategy"] == "iron_condor"

    def test_strips_markdown_fences(self):
        raw = "```json\n" + json.dumps({"strategy": "iron_condor", "confidence": 75, "rationale": "x"}) + "\n```"
        result = _parse_strategy_choice(raw, ["iron_condor"])
        assert result["strategy"] == "iron_condor"

    def test_invalid_strategy_falls_back_to_first_allowed(self):
        raw = json.dumps({"strategy": "made_up_strategy", "confidence": 75, "rationale": "x"})
        result = _parse_strategy_choice(raw, ["iron_condor", "bull_call_spread"])
        assert result["strategy"] == "iron_condor"

    def test_malformed_json_returns_safe_default(self):
        result = _parse_strategy_choice("not json at all", ["bull_call_spread"])
        assert result["strategy"] == "bull_call_spread"
        assert "Fallback" in result["rationale"]


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
            rationale="Range-bound regime with elevated IV favours premium selling",
            regime_context="RANGING (confidence 75)",
            confidence_score=82.0,
        )
        msg = format_strategy_whatsapp(rec)
        assert "NIFTY" in msg
        assert "Iron Condor" in msg
        assert "68" in msg

    def test_format_handles_unlimited_loss(self):
        from core.options.models import StrategyRecommendation, StrategyLeg
        rec = StrategyRecommendation(
            underlying="NIFTY", strategy=StrategyTemplate.SHORT_STRANGLE,
            legs=[StrategyLeg(action="SELL", option_type=OptionType.CALL, strike=22500, premium=80)],
            net_delta=0.1, net_gamma=0.001, net_theta=10.0, net_vega=-5.0,
            max_profit=8000, max_loss=float("-inf"), probability_of_profit=60.0,
            rationale="test", regime_context="RANGING", confidence_score=70.0,
        )
        msg = format_strategy_whatsapp(rec)
        assert "Unlimited" in msg
