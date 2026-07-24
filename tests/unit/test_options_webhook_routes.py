"""
POST /webhook/options, POST /webhook/options/claim, POST /webhook/options/closed
── human-triggered options entry/exit, added 2026-07-25 to replace the
killed regime-gated auto-suggestion. See cloud/api/options_webhook_routes.py's
module docstring for the full design.
"""

from datetime import datetime, timezone

import pytest
from httpx import AsyncClient, ASGITransport

import cloud.api.auth as auth
import cloud.api.options_webhook_routes as webhook_routes
from cloud.api.main import app

WEBHOOK_SECRET = "test-webhook-secret"
CLOUD_SECRET = "test-cloud-secret"


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch):
    monkeypatch.setenv("WEBHOOK_SECRET", WEBHOOK_SECRET)
    monkeypatch.setattr(auth, "CLOUD_API_SECRET", CLOUD_SECRET)
    monkeypatch.setattr(webhook_routes, "_pending", __import__("collections").deque())

    sent = []

    async def _fake_send_telegram(message: str) -> bool:
        sent.append(message)
        return True

    monkeypatch.setattr(webhook_routes, "send_telegram", _fake_send_telegram)
    yield sent


def _alert_payload(**overrides) -> dict:
    payload = {
        "underlying": "NIFTY",
        "template": "bull_call_spread",
        "action": "open",
        "secret": WEBHOOK_SECRET,
        "timestamp": datetime.now(timezone.utc).timestamp(),
    }
    payload.update(overrides)
    return payload


class TestReceiveWebhook:

    @pytest.mark.asyncio
    async def test_queues_valid_alert(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post("/webhook/options", json=_alert_payload())
        assert r.status_code == 200
        body = r.json()
        assert body["underlying"] == "NIFTY"
        assert body["action"] == "open"
        assert body["request_id"].startswith("OWH-")

    @pytest.mark.asyncio
    async def test_rejects_bad_secret(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post("/webhook/options", json=_alert_payload(secret="wrong"))
        assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_rejects_missing_webhook_secret_env(self, monkeypatch):
        monkeypatch.delenv("WEBHOOK_SECRET", raising=False)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post("/webhook/options", json=_alert_payload())
        assert r.status_code == 503

    @pytest.mark.asyncio
    async def test_rejects_missing_timestamp(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post("/webhook/options", json=_alert_payload(timestamp=None))
        assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_rejects_stale_timestamp(self):
        old = datetime.now(timezone.utc).timestamp() - 999
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post("/webhook/options", json=_alert_payload(timestamp=old))
        assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_rejects_invalid_action(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post("/webhook/options", json=_alert_payload(action="delete_everything"))
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_accepts_close_action(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post("/webhook/options", json=_alert_payload(action="close"))
        assert r.status_code == 200
        assert r.json()["action"] == "close"


class TestClaimEndpoint:

    @pytest.mark.asyncio
    async def test_claim_requires_cloud_secret(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post("/webhook/options/claim")
        assert r.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_claim_returns_null_when_empty(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post("/webhook/options/claim", headers={"X-Cloud-Secret": CLOUD_SECRET})
        assert r.status_code == 200
        assert r.json()["request"] is None

    @pytest.mark.asyncio
    async def test_claim_pops_fifo_order(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post("/webhook/options", json=_alert_payload(underlying="NIFTY"))
            await client.post("/webhook/options", json=_alert_payload(underlying="BANKNIFTY"))

            r1 = await client.post("/webhook/options/claim", headers={"X-Cloud-Secret": CLOUD_SECRET})
            r2 = await client.post("/webhook/options/claim", headers={"X-Cloud-Secret": CLOUD_SECRET})
            r3 = await client.post("/webhook/options/claim", headers={"X-Cloud-Secret": CLOUD_SECRET})

        assert r1.json()["request"]["underlying"] == "NIFTY"
        assert r2.json()["request"]["underlying"] == "BANKNIFTY"
        assert r3.json()["request"] is None   # queue drained, no double-claim

    @pytest.mark.asyncio
    async def test_queue_bounded_drops_oldest(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            for i in range(webhook_routes.MAX_QUEUE_SIZE + 5):
                await client.post("/webhook/options", json=_alert_payload(underlying=f"SYM{i}"))
        assert len(webhook_routes._pending) == webhook_routes.MAX_QUEUE_SIZE


class TestClosedReport:

    @pytest.mark.asyncio
    async def test_sends_telegram_notification(self, _isolated_env):
        payload = {
            "underlying": "NIFTY",
            "legs": [{"action": "SELL", "option_type": "CE", "strike": 24800.0}],
            "reason": "trailing_stop_webhook",
        }
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post("/webhook/options/closed", json=payload,
                                   headers={"X-Cloud-Secret": CLOUD_SECRET})
        assert r.status_code == 200
        assert r.json()["closed"] is True
        assert len(_isolated_env) == 1
        assert "NIFTY" in _isolated_env[0]
        assert "no confirmation was required" in _isolated_env[0].lower()

    @pytest.mark.asyncio
    async def test_closed_report_requires_cloud_secret(self):
        payload = {"underlying": "NIFTY", "legs": []}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post("/webhook/options/closed", json=payload)
        assert r.status_code in (401, 403)
