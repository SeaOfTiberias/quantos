"""
Regime Sync Routes — Unit Tests
─────────────────────────────────
POST /regime/sync (agent -> cloud, authed) and get_synced_regime() (read
by cloud/analyst/pre_trade.py and cloud/api/strategy_routes.py) — the
bridge that lets the local agent's RegimeService (the only process with
a connected broker, ADR-01) feed real regime data into the cloud API.
"""

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient, ASGITransport

import cloud.api.auth as auth
import cloud.api.regime_routes as regime_routes
from cloud.api.main import app
from cloud.api.regime_routes import get_synced_regime
from core.regime.models import Regime


@pytest.fixture(autouse=True)
def _isolated_regime_store(monkeypatch):
    monkeypatch.setattr(regime_routes, "_synced_regime", None)
    monkeypatch.setattr(regime_routes, "_synced_at", None)


def _payload(**overrides) -> dict:
    payload = {
        "regime": "TRENDING_BULL",
        "confidence": 82.0,
        "allowed_strategies": ["darvas_breakout", "bull_call_spread"],
        "size_multiplier": 1.0,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "trend_signal": "BULL",
        "vix_signal": "LOW",
        "breadth_signal": "STRONG",
        "advance_count": 312,
        "decline_count": 168,
        "unchanged_count": 8,
        "notes": ["Trend=60, VIX=12.0 -> TRENDING BULL"],
    }
    payload.update(overrides)
    return payload


class TestSyncEndpointAuth:

    @pytest.mark.asyncio
    async def test_rejects_missing_secret_when_configured(self, monkeypatch):
        monkeypatch.setattr(auth, "CLOUD_API_SECRET", "correct_secret")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post("/regime/sync", json=_payload())
        assert r.status_code == 401
        assert get_synced_regime() is None

    @pytest.mark.asyncio
    async def test_accepts_correct_secret(self, monkeypatch):
        monkeypatch.setattr(auth, "CLOUD_API_SECRET", "correct_secret")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post(
                "/regime/sync", json=_payload(),
                headers={"X-Cloud-Secret": "correct_secret"},
            )
        assert r.status_code == 200
        assert r.json()["synced"] is True

    @pytest.mark.asyncio
    async def test_noop_guard_when_no_secret_configured(self, monkeypatch):
        monkeypatch.setattr(auth, "CLOUD_API_SECRET", "")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post("/regime/sync", json=_payload())
        assert r.status_code == 200


class TestGetSyncedRegime:

    @pytest.mark.asyncio
    async def test_returns_none_before_any_sync(self):
        assert get_synced_regime() is None

    @pytest.mark.asyncio
    async def test_returns_regime_result_after_sync(self, monkeypatch):
        monkeypatch.setattr(auth, "CLOUD_API_SECRET", "")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post("/regime/sync", json=_payload(confidence=91.0))

        result = get_synced_regime()
        assert result is not None
        assert result.regime == Regime.TRENDING_BULL
        assert result.confidence == 91.0
        assert result.allowed_strategies == ["darvas_breakout", "bull_call_spread"]
        # S5-4: raw advance/decline survives the sync round-trip.
        assert result.advance_count == 312
        assert result.decline_count == 168
        assert result.ad_ratio == pytest.approx(312 / 168)


class TestRegimeStatusEndpoint:
    """GET /regime/status — public read for the cockpit Market Regime panel."""

    @pytest.mark.asyncio
    async def test_returns_null_before_any_sync(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/regime/status")
        assert r.status_code == 200
        assert r.json()["regime"] is None

    @pytest.mark.asyncio
    async def test_exposes_breadth_counts_after_sync(self, monkeypatch):
        monkeypatch.setattr(auth, "CLOUD_API_SECRET", "")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post("/regime/sync", json=_payload())
            r = await client.get("/regime/status")

        body = r.json()
        assert body["regime"] == "TRENDING_BULL"
        assert body["advance_count"] == 312
        assert body["decline_count"] == 168
        assert body["unchanged_count"] == 8
        assert body["ad_ratio"] == round(312 / 168, 2)
        assert body["darvas_enabled"] is True
        assert body["updated_at"] is not None

    def test_stale_sync_treated_as_unavailable(self, monkeypatch):
        monkeypatch.setattr(regime_routes, "_synced_regime", object())  # any non-None sentinel
        monkeypatch.setattr(
            regime_routes, "_synced_at",
            datetime.now(timezone.utc) - timedelta(seconds=regime_routes.MAX_REGIME_AGE_SECONDS + 1),
        )
        assert get_synced_regime() is None

    def test_fresh_sync_not_treated_as_stale(self, monkeypatch):
        from core.regime.models import RegimeResult
        result = RegimeResult(
            regime=Regime.RANGING, confidence=65.0, allowed_strategies=["iron_condor"],
            size_multiplier=0.75, timestamp=datetime.now(timezone.utc),
        )
        monkeypatch.setattr(regime_routes, "_synced_regime", result)
        monkeypatch.setattr(regime_routes, "_synced_at", datetime.now(timezone.utc))
        assert get_synced_regime() is result
