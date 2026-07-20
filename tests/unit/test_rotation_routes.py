"""
POST /rotation/report — S8-3 weekly rotation reporting. Agent -> cloud,
authed like /correlation/sync and /regime/sync. Persists real (non-dry-run)
trades as EXECUTED signal rows for cockpit visibility and sends one
consolidated Telegram summary either way.
"""

import pytest
from httpx import AsyncClient, ASGITransport

import cloud.api.auth as auth
import cloud.api.db as db_module
from cloud.api.main import app

SECRET = "test-cloud-secret"


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch):
    monkeypatch.setattr(db_module, "_db_instance", None)
    monkeypatch.setattr(auth, "CLOUD_API_SECRET", SECRET)

    sent = []

    async def _fake_send_telegram(message: str) -> bool:
        sent.append(message)
        return True

    monkeypatch.setattr("cloud.api.notifier.send_telegram", _fake_send_telegram)
    yield sent


def _payload(**overrides) -> dict:
    payload = {
        "dry_run": False,
        "buys": [{"symbol": "RELIANCE", "quantity": 40, "price": 2500.0}],
        "sells": [{"symbol": "TCS", "quantity": 10, "entry_price": 3400.0}],
        "skipped_buys": [{"symbol": "INFY", "reason": "insufficient available capital"}],
        "timestamp": 1_753_000_000.0,
    }
    payload.update(overrides)
    return payload


async def _post(payload, headers=None):
    if headers is None:
        headers = {"X-Cloud-Secret": SECRET}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.post("/rotation/report", json=payload, headers=headers)


class TestAuth:

    @pytest.mark.asyncio
    async def test_rejects_missing_secret(self):
        r = await _post(_payload(), headers={})
        assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_accepts_correct_secret(self):
        r = await _post(_payload())
        assert r.status_code == 200
        assert r.json()["received"] is True


class TestLivePersistence:

    @pytest.mark.asyncio
    async def test_live_buys_and_sells_persisted_as_executed_signals(self):
        await _post(_payload(dry_run=False))

        db = await db_module.get_db()
        records = await db.fetch_recent_signals(limit=20)
        by_symbol = {r["symbol"]: r for r in records}

        assert by_symbol["RELIANCE"]["action"] == "BUY"
        assert by_symbol["RELIANCE"]["status"] == "EXECUTED"
        assert by_symbol["RELIANCE"]["strategy"] == "weekly_rotation"
        assert by_symbol["RELIANCE"]["execution_price"] == 2500.0

        assert by_symbol["TCS"]["action"] == "SELL"
        assert by_symbol["TCS"]["status"] == "EXECUTED"
        assert by_symbol["TCS"]["execution_price"] == 3400.0

    @pytest.mark.asyncio
    async def test_dry_run_does_not_persist_any_signal(self):
        await _post(_payload(dry_run=True))

        db = await db_module.get_db()
        records = await db.fetch_recent_signals(limit=20)
        assert records == []

    @pytest.mark.asyncio
    async def test_dry_run_still_sends_telegram_summary(self, _isolated_env):
        await _post(_payload(dry_run=True))
        assert len(_isolated_env) == 1
        assert "DRY RUN" in _isolated_env[0]

    @pytest.mark.asyncio
    async def test_live_run_sends_telegram_summary_without_dry_run_tag(self, _isolated_env):
        await _post(_payload(dry_run=False))
        assert len(_isolated_env) == 1
        assert "DRY RUN" not in _isolated_env[0]
        assert "RELIANCE" in _isolated_env[0]
        assert "TCS" in _isolated_env[0]
        assert "INFY" in _isolated_env[0]

    @pytest.mark.asyncio
    async def test_no_buys_or_sells_still_returns_200(self):
        r = await _post(_payload(buys=[], sells=[], skipped_buys=[]))
        assert r.status_code == 200


class TestReportRotationFailure:
    """POST /rotation/failed — the unattended systemd timer's only way to
    surface a failure (most likely a stale Fyers auth token) to the user,
    since the interactive OAuth refresh can't run unattended and a failed
    weekly run would otherwise just sit silently in a systemd log."""

    async def _post_failure(self, error: str, headers=None):
        if headers is None:
            headers = {"X-Cloud-Secret": SECRET}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            return await client.post("/rotation/failed", json={"error": error}, headers=headers)

    @pytest.mark.asyncio
    async def test_rejects_missing_secret(self):
        r = await self._post_failure("Fyers connect error: token expired", headers={})
        assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_sends_telegram_alert_with_the_error(self, _isolated_env):
        r = await self._post_failure("Fyers connect error: token expired")
        assert r.status_code == 200
        assert len(_isolated_env) == 1
        assert "token expired" in _isolated_env[0]

    @pytest.mark.asyncio
    async def test_does_not_persist_any_signal(self):
        await self._post_failure("boom")
        db = await db_module.get_db()
        assert await db.fetch_recent_signals(limit=20) == []
