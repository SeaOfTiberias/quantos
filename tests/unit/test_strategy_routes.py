"""
Strategy Chain Analysis Routes — Unit Tests
────────────────────────────────────────────────────────────
POST /strategy/recommend was rewritten 2026-07-25 (Fable review): no more
regime dependency, no more Claude pick — the caller supplies a `template`
directly and the route returns that template's real legs/Greeks/risk-reward
computed from the supplied chain. See core/options/recommender.py's module
docstring for why the old regime-gated Claude recommendation was removed.
"""

from datetime import date, timedelta

import pytest
from httpx import AsyncClient, ASGITransport

from cloud.api.main import app


def _request_payload(template: str = "iron_condor") -> dict:
    spot = 22000.0
    legs = []
    for offset in range(-600, 700, 100):
        strike = spot + offset
        legs.append({
            "strike": strike, "option_type": "CE", "premium": max(5.0, 150 - abs(offset) * 0.15),
            "open_interest": 50000, "volume": 10000, "implied_vol": 0.18,
        })
        legs.append({
            "strike": strike, "option_type": "PE", "premium": max(5.0, 150 - abs(offset) * 0.15),
            "open_interest": 50000, "volume": 10000, "implied_vol": 0.18,
        })
    return {
        "underlying": "NIFTY",
        "spot_price": spot,
        "expiry": (date.today() + timedelta(days=14)).isoformat(),
        "legs": legs,
        "iv_rank": 45.0,
        "iv_percentile": 50.0,
        "pcr": 1.1,
        "max_pain": spot,
        "template": template,
    }


class TestRecommendEndpoint:

    @pytest.mark.asyncio
    async def test_returns_analysis_with_no_regime_dependency(self):
        """No regime sync needed at all now — this used to 503 without one."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post("/strategy/recommend", json=_request_payload("iron_condor"))

        assert r.status_code == 200
        body = r.json()
        assert body["strategy"] == "iron_condor"
        assert body["underlying"] == "NIFTY"
        assert len(body["legs"]) > 0

    @pytest.mark.asyncio
    async def test_response_has_no_rationale_or_confidence_fields(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post("/strategy/recommend", json=_request_payload("bull_call_spread"))

        body = r.json()
        assert "rationale" not in body
        assert "regime_context" not in body
        assert "confidence_score" not in body

    @pytest.mark.asyncio
    async def test_422_on_unknown_template(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post("/strategy/recommend", json=_request_payload("not_a_real_template"))

        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_422_when_template_cannot_be_built(self):
        payload = _request_payload("iron_condor")
        payload["legs"] = []   # nothing to build a strategy from
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post("/strategy/recommend", json=payload)

        assert r.status_code == 422
