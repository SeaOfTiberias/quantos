"""
Cockpit Analyst Chat — Unit Tests
────────────────────────────────────
cloud/analyst/chat.py (context building, daily cap) and the
POST /analyst/chat route it backs. The chat endpoint is public (a browser
can't hold the cloud secret), so the daily cap is the only cost/abuse
guard today — these tests pin that behaviour down.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

import cloud.analyst.chat as chat
import cloud.api.positions_routes as positions_routes
import cloud.api.regime_routes as regime_routes
from cloud.analyst.chat import ChatLimitExceeded, ask_analyst
from cloud.api.main import app
from core.regime.models import Regime, RegimeResult


@pytest.fixture(autouse=True)
def _isolated_state(monkeypatch):
    monkeypatch.setattr(regime_routes, "_synced_regime", None)
    monkeypatch.setattr(regime_routes, "_synced_at", None)
    monkeypatch.setattr(positions_routes, "_synced_positions", None)
    monkeypatch.setattr(positions_routes, "_synced_at", None)
    monkeypatch.setattr(chat, "_chat_calls_today", {})


def _text_response(text: str):
    block = SimpleNamespace(type="text", text=text)
    return SimpleNamespace(content=[block], usage=SimpleNamespace(input_tokens=10, output_tokens=20))


class TestBuildContext:

    @pytest.mark.asyncio
    async def test_reports_unknown_when_nothing_synced(self, monkeypatch):
        async def _fake_get_db():
            class _DB:
                async def fetch_recent_signals(self, limit=5):
                    return []
            return _DB()
        monkeypatch.setattr("cloud.api.db.get_db", _fake_get_db)

        context = await chat._build_context()
        assert "unknown" in context
        assert "Open positions: none" in context
        assert "Recent signals: none today" in context

    @pytest.mark.asyncio
    async def test_reflects_real_synced_state(self, monkeypatch):
        result = RegimeResult(
            regime=Regime.TRENDING_BULL, confidence=88.0,
            allowed_strategies=["darvas_breakout"], size_multiplier=1.0,
            timestamp=datetime.now(timezone.utc),
            trend_signal="BULL", vix_signal="LOW", breadth_signal="STRONG",
        )
        monkeypatch.setattr(regime_routes, "_synced_regime", result)
        monkeypatch.setattr(regime_routes, "_synced_at", datetime.now(timezone.utc))
        monkeypatch.setattr(positions_routes, "_synced_positions", [
            {"symbol": "HDFCBANK", "qty": 50, "entry": 1680.0, "ltp": 1705.0,
             "pnl": 1250.0, "pnl_pct": 1.49, "strategy": "darvas_breakout"},
        ])

        async def _fake_get_db():
            class _DB:
                async def fetch_recent_signals(self, limit=5):
                    return [{"symbol": "TCS", "action": "BUY", "price": 3800.0,
                              "status": "CONFIRMED", "confluence_score": 82}]
            return _DB()
        monkeypatch.setattr("cloud.api.db.get_db", _fake_get_db)

        context = await chat._build_context()
        assert "TRENDING_BULL" in context
        assert "HDFCBANK" in context
        assert "TCS" in context


class TestAskAnalyst:

    @pytest.mark.asyncio
    async def test_returns_claude_text(self, monkeypatch):
        monkeypatch.setattr(chat, "_build_context", AsyncMock(return_value="Regime: unknown"))
        with patch.object(chat._claude.messages, "create", new_callable=AsyncMock,
                           return_value=_text_response("You have no open positions.")):
            reply = await ask_analyst("What are my positions?")
        assert reply == "You have no open positions."

    @pytest.mark.asyncio
    async def test_raises_once_daily_cap_hit(self, monkeypatch):
        monkeypatch.setattr(chat, "CHAT_DAILY_LIMIT", 1)
        monkeypatch.setattr(chat, "_build_context", AsyncMock(return_value="Regime: unknown"))
        with patch.object(chat._claude.messages, "create", new_callable=AsyncMock,
                           return_value=_text_response("ok")):
            await ask_analyst("first message")
            with pytest.raises(ChatLimitExceeded):
                await ask_analyst("second message")


class TestChatRoute:

    @pytest.mark.asyncio
    async def test_returns_reply_on_success(self, monkeypatch):
        monkeypatch.setattr("cloud.api.analyst_routes.ask_analyst",
                             AsyncMock(return_value="All quiet — no open positions."))
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post("/analyst/chat", json={"message": "How's my portfolio?"})
        assert r.status_code == 200
        body = r.json()
        assert body["reply"] == "All quiet — no open positions."
        assert body["limited"] is False

    @pytest.mark.asyncio
    async def test_reports_limited_on_cap(self, monkeypatch):
        async def _raise(*a, **kw):
            raise ChatLimitExceeded("Daily analyst chat limit (60) reached.")
        monkeypatch.setattr("cloud.api.analyst_routes.ask_analyst", _raise)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post("/analyst/chat", json={"message": "hi"})
        assert r.status_code == 200
        assert r.json()["limited"] is True

    @pytest.mark.asyncio
    async def test_graceful_error_on_claude_failure(self, monkeypatch):
        async def _raise(*a, **kw):
            raise RuntimeError("boom")
        monkeypatch.setattr("cloud.api.analyst_routes.ask_analyst", _raise)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post("/analyst/chat", json={"message": "hi"})
        assert r.status_code == 200
        assert "unavailable" in r.json()["reply"]

    @pytest.mark.asyncio
    async def test_rejects_empty_message(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post("/analyst/chat", json={"message": ""})
        assert r.status_code == 422
