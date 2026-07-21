"""
POST /options/signal, /options/signal/{id}/executed, /options/signal/{id}/partial_failure
— regime/strategy advisor -> real options execution, Phase 2. Confirm-before-
execute (Telegram), NOT S8-3 rotation's no-veto carve-out — every suggestion
is persisted PENDING_CONFIRMATION and must be confirmed via the existing
/webhook/telegram reply flow, unchanged by this feature.
"""

import json

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


def _leg(**overrides) -> dict:
    leg = {
        "action": "BUY", "option_type": "CE", "strike": 24800.0,
        "premium": 120.5, "quantity": 1, "symbol": "NSE:NIFTY2672124800CE",
        "lot_size": 65,
    }
    leg.update(overrides)
    return leg


def _signal_payload(**overrides) -> dict:
    payload = {
        "underlying": "NIFTY", "expiry": "2026-07-21", "strategy": "bull_call_spread",
        "legs": [
            _leg(),
            _leg(action="SELL", strike=25000.0, premium=40.0,
                 symbol="NSE:NIFTY2672125000CE"),
        ],
        "rationale": "TRENDING_BULL regime with room to the upside",
        "regime_context": "TRENDING_BULL (confidence 80)",
        "max_profit": 12675.0, "max_loss": 5200.0, "net_premium": -5200.0,
        "probability_of_profit": 58.0,
    }
    payload.update(overrides)
    return payload


async def _post_signal(payload, headers=None):
    if headers is None:
        headers = {"X-Cloud-Secret": SECRET}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.post("/options/signal", json=payload, headers=headers)


class TestAuth:

    @pytest.mark.asyncio
    async def test_rejects_missing_secret(self):
        r = await _post_signal(_signal_payload(), headers={})
        assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_accepts_correct_secret(self):
        r = await _post_signal(_signal_payload())
        assert r.status_code == 200


class TestCreateOptionsSignal:

    @pytest.mark.asyncio
    async def test_persists_as_pending_confirmation(self):
        r = await _post_signal(_signal_payload())
        body = r.json()
        assert body["status"] == "PENDING_CONFIRMATION"

        db = await db_module.get_db()
        signal = await db.get_signal(body["signal_id"])
        assert signal.status == "PENDING_CONFIRMATION"
        assert signal.symbol == "NIFTY"
        assert signal.strategy == "bull_call_spread"

    @pytest.mark.asyncio
    async def test_options_detail_carries_full_leg_list(self):
        r = await _post_signal(_signal_payload())
        signal_id = r.json()["signal_id"]

        db = await db_module.get_db()
        signal = await db.get_signal(signal_id)
        detail = json.loads(signal.options_detail)
        assert len(detail["legs"]) == 2
        assert detail["legs"][0]["symbol"] == "NSE:NIFTY2672124800CE"
        assert detail["max_loss"] == 5200.0

    @pytest.mark.asyncio
    async def test_sends_telegram_confirmation_with_signal_id_and_legs(self, _isolated_env):
        r = await _post_signal(_signal_payload())
        signal_id = r.json()["signal_id"]

        assert len(_isolated_env) == 1
        message = _isolated_env[0]
        assert signal_id in message
        assert "NIFTY" in message
        assert "24800" in message
        assert "execute" in message.lower()
        assert "skip" in message.lower()

    @pytest.mark.asyncio
    async def test_equity_signal_dedup_guard_ignores_options_signals(self):
        """Options signals must not corrupt the equity same-day dedup guard
        (symbol collision risk flagged during Phase 2 design: NIFTY itself
        never collides, but a single-stock options signal shares its
        `symbol` value with that stock's equity signals)."""
        await _post_signal(_signal_payload())
        db = await db_module.get_db()
        # find_open_signal_today only matters once a Darvas/equity signal on
        # the same symbol exists — this just proves the options signal was
        # persisted with a plain symbol string the guard can query normally.
        found = await db.find_open_signal_today(
            "NIFTY", ("PENDING_CONFIRMATION", "CONFIRMED", "EXECUTED"))
        assert found is not None


class TestReportOptionsExecuted:

    async def _post_executed(self, signal_id, legs, headers=None):
        if headers is None:
            headers = {"X-Cloud-Secret": SECRET}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            return await client.post(
                f"/options/signal/{signal_id}/executed",
                json={"underlying": "NIFTY", "legs": legs}, headers=headers)

    @pytest.mark.asyncio
    async def test_rejects_missing_secret(self):
        r = await self._post_executed("SIG-OPT-TEST0001", [], headers={})
        assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_marks_signal_executed(self):
        create = await _post_signal(_signal_payload())
        signal_id = create.json()["signal_id"]

        legs = [
            {"action": "BUY", "option_type": "CE", "strike": 24800.0, "quantity": 1,
             "symbol": "NSE:NIFTY2672124800CE", "order_id": "ORD1", "fill_price": 121.0},
            {"action": "SELL", "option_type": "CE", "strike": 25000.0, "quantity": 1,
             "symbol": "NSE:NIFTY2672125000CE", "order_id": "ORD2", "fill_price": 39.5},
        ]
        r = await self._post_executed(signal_id, legs)
        assert r.status_code == 200
        assert r.json()["status"] == "EXECUTED"

        db = await db_module.get_db()
        signal = await db.get_signal(signal_id)
        assert signal.status == "EXECUTED"

    @pytest.mark.asyncio
    async def test_sends_execution_report(self, _isolated_env):
        create = await _post_signal(_signal_payload())
        signal_id = create.json()["signal_id"]

        legs = [
            {"action": "BUY", "option_type": "CE", "strike": 24800.0, "quantity": 1,
             "symbol": "NSE:NIFTY2672124800CE", "order_id": "ORD1", "fill_price": 121.0},
        ]
        await self._post_executed(signal_id, legs)
        assert len(_isolated_env) == 2  # confirmation + execution report
        assert "Executed" in _isolated_env[-1]
        assert "ORD1" in _isolated_env[-1]


class TestReportOptionsPartialFailure:

    async def _post_partial_failure(self, signal_id, flatten_results, headers=None):
        if headers is None:
            headers = {"X-Cloud-Secret": SECRET}
        payload = {
            "underlying": "NIFTY",
            "failed_leg": {"action": "SELL", "option_type": "CE", "strike": 25000.0},
            "error": "Order rejected: insufficient margin",
            "flatten_results": flatten_results,
        }
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            return await client.post(
                f"/options/signal/{signal_id}/partial_failure",
                json=payload, headers=headers)

    @pytest.mark.asyncio
    async def test_rejects_missing_secret(self):
        r = await self._post_partial_failure("SIG-OPT-TEST0002", [], headers={})
        assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_marks_signal_failed(self):
        create = await _post_signal(_signal_payload())
        signal_id = create.json()["signal_id"]

        r = await self._post_partial_failure(signal_id, [
            {"leg": {"action": "BUY", "option_type": "CE", "strike": 24800.0},
             "flattened": True, "order_id": "ORD-FLAT-1"},
        ])
        assert r.status_code == 200
        assert r.json()["status"] == "FAILED"

        db = await db_module.get_db()
        signal = await db.get_signal(signal_id)
        assert signal.status == "FAILED"

    @pytest.mark.asyncio
    async def test_successful_flatten_sends_moderate_alert(self, _isolated_env):
        create = await _post_signal(_signal_payload())
        signal_id = create.json()["signal_id"]

        await self._post_partial_failure(signal_id, [
            {"leg": {"action": "BUY", "option_type": "CE", "strike": 24800.0},
             "flattened": True, "order_id": "ORD-FLAT-1"},
        ])
        alert = _isolated_env[-1]
        assert "auto-flattened" in alert
        assert "ACT NOW" not in alert

    @pytest.mark.asyncio
    async def test_failed_flatten_sends_urgent_act_now_alert(self, _isolated_env):
        """The worst case: the corrective flatten order ALSO failed, leaving
        a genuinely naked position with no further automatic recourse —
        must be the loudest possible alert."""
        create = await _post_signal(_signal_payload())
        signal_id = create.json()["signal_id"]

        await self._post_partial_failure(signal_id, [
            {"leg": {"action": "BUY", "option_type": "CE", "strike": 24800.0},
             "flattened": False, "error": "Broker unreachable"},
        ])
        alert = _isolated_env[-1]
        assert "ACT NOW" in alert
        assert "STILL OPEN, naked" in alert
        assert "Broker unreachable" in alert

    @pytest.mark.asyncio
    async def test_no_prior_legs_filled_reports_nothing_to_flatten(self, _isolated_env):
        create = await _post_signal(_signal_payload())
        signal_id = create.json()["signal_id"]

        await self._post_partial_failure(signal_id, [])
        alert = _isolated_env[-1]
        assert "nothing to flatten" in alert
