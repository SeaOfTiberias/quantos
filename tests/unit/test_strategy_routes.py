"""
Strategy Recommendation Routes — Regime Wiring Unit Tests
────────────────────────────────────────────────────────────
POST /strategy/recommend used to check a global `_regime_service` in
cloud/api/main.py that was declared but never initialized anywhere —
every call 503'd unconditionally, regardless of market conditions. It
now reads the regime the local agent synced via POST /regime/sync
(cloud/api/regime_routes.py), so it 503s only when nothing has synced
yet, and actually returns a recommendation once it has.
"""

from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

import cloud.api.regime_routes as regime_routes
from cloud.api.main import app
from core.options.models import (
    OptionType, StrategyLeg, StrategyRecommendation, StrategyTemplate,
)
from core.regime.models import Regime, RegimeResult


@pytest.fixture(autouse=True)
def _isolated_regime_store(monkeypatch):
    monkeypatch.setattr(regime_routes, "_synced_regime", None)
    monkeypatch.setattr(regime_routes, "_synced_at", None)


def _minimal_request_payload() -> dict:
    return {
        "underlying": "NIFTY",
        "spot_price": 22000.0,
        "expiry": (date.today() + timedelta(days=14)).isoformat(),
        "legs": [],
        "iv_rank": 45.0,
        "iv_percentile": 50.0,
        "pcr": 1.1,
        "max_pain": 22000.0,
    }


class TestRecommendEndpoint:

    @pytest.mark.asyncio
    async def test_503_when_no_regime_synced(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post("/strategy/recommend", json=_minimal_request_payload())
        assert r.status_code == 503

    @pytest.mark.asyncio
    async def test_returns_recommendation_once_regime_is_synced(self, monkeypatch):
        monkeypatch.setattr(regime_routes, "_synced_regime", RegimeResult(
            regime=Regime.RANGING, confidence=65.0,
            allowed_strategies=["iron_condor"], size_multiplier=0.75,
            timestamp=datetime.now(timezone.utc),
        ))
        monkeypatch.setattr(regime_routes, "_synced_at", datetime.now(timezone.utc))

        fake_rec = StrategyRecommendation(
            underlying="NIFTY", strategy=StrategyTemplate.IRON_CONDOR,
            legs=[
                StrategyLeg(action="SELL", option_type=OptionType.CALL, strike=22200, premium=80.0),
                StrategyLeg(action="BUY", option_type=OptionType.CALL, strike=22300, premium=40.0),
            ],
            net_delta=0.1, net_gamma=0.01, net_theta=-5.0, net_vega=2.0,
            max_profit=2000.0, max_loss=-3000.0, probability_of_profit=68.0,
            rationale="Range-bound market, low IV rank favors premium selling.",
            regime_context="RANGING (confidence 65)", confidence_score=72.0,
        )

        with patch("cloud.api.strategy_routes.recommend_strategy",
                   new_callable=AsyncMock, return_value=fake_rec):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                r = await client.post("/strategy/recommend", json=_minimal_request_payload())

        assert r.status_code == 200
        body = r.json()
        assert body["strategy"] == "iron_condor"
        assert body["underlying"] == "NIFTY"
        assert len(body["legs"]) == 2
