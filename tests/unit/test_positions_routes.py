"""
Positions Sync Routes — Unit Tests
────────────────────────────────────
POST /positions/sync (agent -> cloud, authed) and GET /positions/status
(public read) — lets the local agent's broker-reported open positions
(the only process with a connected broker, ADR-01) feed the cockpit's
Open Positions panel.
"""

import pytest
from httpx import AsyncClient, ASGITransport

import cloud.api.auth as auth
import cloud.api.positions_routes as positions_routes
from cloud.api.main import app
from cloud.api.positions_routes import get_last_synced_at


@pytest.fixture(autouse=True)
def _isolated_positions_store(monkeypatch):
    monkeypatch.setattr(positions_routes, "_synced_positions", None)
    monkeypatch.setattr(positions_routes, "_synced_at", None)


def _payload(**overrides) -> dict:
    payload = {
        "positions": [
            {"symbol": "HDFCBANK", "qty": 50, "entry": 1680.0, "ltp": 1705.0,
             "pnl": 1250.0, "pnl_pct": 1.49, "strategy": "darvas_breakout"},
        ],
    }
    payload.update(overrides)
    return payload


class TestSyncEndpointAuth:

    @pytest.mark.asyncio
    async def test_rejects_missing_secret_when_configured(self, monkeypatch):
        monkeypatch.setattr(auth, "CLOUD_API_SECRET", "correct_secret")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post("/positions/sync", json=_payload())
        assert r.status_code == 401
        assert get_last_synced_at() is None

    @pytest.mark.asyncio
    async def test_accepts_correct_secret(self, monkeypatch):
        monkeypatch.setattr(auth, "CLOUD_API_SECRET", "correct_secret")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post(
                "/positions/sync", json=_payload(),
                headers={"X-Cloud-Secret": "correct_secret"},
            )
        assert r.status_code == 200
        body = r.json()
        assert body["synced"] is True
        assert body["count"] == 1


class TestPositionsStatusEndpoint:
    """GET /positions/status — public read for the cockpit Open Positions panel."""

    @pytest.mark.asyncio
    async def test_returns_empty_list_before_any_sync(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/positions/status")
        assert r.status_code == 200
        body = r.json()
        assert body["positions"] == []
        assert body["updated_at"] is None

    @pytest.mark.asyncio
    async def test_exposes_synced_positions(self, monkeypatch):
        monkeypatch.setattr(auth, "CLOUD_API_SECRET", "")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post("/positions/sync", json=_payload())
            r = await client.get("/positions/status")

        body = r.json()
        assert len(body["positions"]) == 1
        assert body["positions"][0]["symbol"] == "HDFCBANK"
        assert body["positions"][0]["pnl"] == 1250.0
        assert body["updated_at"] is not None

    @pytest.mark.asyncio
    async def test_sync_wholesale_replaces_previous_positions(self, monkeypatch):
        """A closed-out position must disappear, not linger from a prior sync."""
        monkeypatch.setattr(auth, "CLOUD_API_SECRET", "")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post("/positions/sync", json=_payload())
            await client.post("/positions/sync", json={"positions": []})
            r = await client.get("/positions/status")

        assert r.json()["positions"] == []
