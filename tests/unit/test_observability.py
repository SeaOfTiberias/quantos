"""
S5-6 Observability Cockpit — Unit Tests

Covers the three real-data sources the cockpit reads:
  • metrics collector      — rolling latency snapshot + Claude spend estimate
  • SignalDB counts        — today's signals grouped by status
  • /observability route    — aggregation + the agent-heartbeat dead-man
    (AC: heartbeat goes stale when the agent stops syncing).
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from httpx import AsyncClient, ASGITransport

from cloud.api import metrics
from cloud.api.db import SignalDB, Signal
from cloud.api.main import app
import cloud.api.observability_routes as obs_routes


# ─── Metrics collector ─────────────────────────────────────────────────────────

class TestMetrics:

    def setup_method(self):
        metrics.reset()

    def test_empty_snapshot(self):
        snap = metrics.snapshot()
        assert snap["webhook_latency"]["count"] == 0
        assert snap["webhook_latency"]["p50_ms"] is None
        assert snap["claude_spend_today"]["calls"] == 0
        assert snap["claude_spend_today"]["est_usd"] == 0.0

    def test_webhook_latency_percentiles(self):
        for ms in range(1, 101):           # 1..100 ms
            metrics.record_webhook_ms(ms)
        wl = metrics.snapshot()["webhook_latency"]
        assert wl["count"] == 100
        assert wl["last_ms"] == 100.0
        assert 45 <= wl["p50_ms"] <= 55     # median near 50
        assert wl["p95_ms"] >= 90           # tail near 95

    def test_latency_window_is_bounded(self):
        for ms in range(500):               # exceed the 200 window
            metrics.record_webhook_ms(ms)
        assert metrics.snapshot()["webhook_latency"]["count"] == 200

    def test_claude_spend_estimate(self):
        # 1,000,000 input + 1,000,000 output tokens over two calls.
        metrics.record_claude(1200.0, input_tokens=500_000, output_tokens=500_000)
        metrics.record_claude(800.0, input_tokens=500_000, output_tokens=500_000)
        spend = metrics.snapshot()["claude_spend_today"]
        assert spend["calls"] == 2
        assert spend["input_tokens"] == 1_000_000
        assert spend["output_tokens"] == 1_000_000
        # 1M in × $3 + 1M out × $15 = $18 at default prices.
        assert spend["est_usd"] == pytest.approx(18.0, abs=0.01)

    def test_claude_latency_recorded_without_tokens(self):
        metrics.record_claude(1500.0)       # a failed call: latency, no spend
        snap = metrics.snapshot()
        assert snap["claude_latency"]["count"] == 1
        assert snap["claude_spend_today"]["calls"] == 1
        assert snap["claude_spend_today"]["est_usd"] == 0.0


# ─── SignalDB counts_by_status_today ───────────────────────────────────────────

class TestSignalCounts:

    def _sig(self, status, days_ago=0):
        return Signal(
            signal_id=f"SIG-{status}-{days_ago}-{id(status)}",
            user_id="system", symbol="RELIANCE", action="BUY", price=100.0,
            timeframe="1h", strategy="darvas_breakout", confluence_score=85,
            status=status,
            created_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
        )

    @pytest.mark.asyncio
    async def test_groups_todays_signals_by_status(self):
        db = SignalDB()   # fresh in-memory store, isolated from the app singleton
        await db.insert_signal(self._sig("PENDING_CONFIRMATION"))
        await db.insert_signal(self._sig("PENDING_CONFIRMATION"))
        await db.insert_signal(self._sig("EXECUTED"))
        counts = await db.counts_by_status_today()
        assert counts == {"PENDING_CONFIRMATION": 2, "EXECUTED": 1}

    @pytest.mark.asyncio
    async def test_excludes_prior_days(self):
        db = SignalDB()
        await db.insert_signal(self._sig("EXECUTED"))
        await db.insert_signal(self._sig("CLOSED", days_ago=2))   # yesterday-ish
        counts = await db.counts_by_status_today()
        assert counts == {"EXECUTED": 1}

    @pytest.mark.asyncio
    async def test_empty_store_is_empty_dict(self):
        assert await SignalDB().counts_by_status_today() == {}


# ─── Heartbeat / dead-man ──────────────────────────────────────────────────────

class TestHeartbeat:

    def _at(self, seconds_ago):
        return datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)

    def test_fresh_sync_is_live(self):
        with patch.object(obs_routes, "regime_synced_at", return_value=self._at(60)), \
             patch.object(obs_routes, "discovery_synced_at", return_value=None):
            hb = obs_routes._heartbeat()
        assert hb["stale"] is False
        assert hb["age_seconds"] < obs_routes.HEARTBEAT_STALE_SECONDS

    def test_old_sync_goes_stale(self):
        old = self._at(obs_routes.HEARTBEAT_STALE_SECONDS + 120)
        with patch.object(obs_routes, "regime_synced_at", return_value=old), \
             patch.object(obs_routes, "discovery_synced_at", return_value=None):
            hb = obs_routes._heartbeat()
        assert hb["stale"] is True

    def test_no_sync_ever_is_stale(self):
        with patch.object(obs_routes, "regime_synced_at", return_value=None), \
             patch.object(obs_routes, "discovery_synced_at", return_value=None):
            hb = obs_routes._heartbeat()
        assert hb["stale"] is True
        assert hb["last_contact"] is None
        assert hb["age_seconds"] is None

    def test_uses_freshest_of_the_two_sources(self):
        with patch.object(obs_routes, "regime_synced_at", return_value=self._at(5000)), \
             patch.object(obs_routes, "discovery_synced_at", return_value=self._at(30)):
            hb = obs_routes._heartbeat()
        # The 30-s-old watchlist sync wins → live, not the stale regime one.
        assert hb["stale"] is False
        assert hb["age_seconds"] < 120


# ─── /observability route ──────────────────────────────────────────────────────

class TestObservabilityRoute:

    @pytest.mark.asyncio
    async def test_returns_full_shape(self):
        with patch.object(obs_routes, "regime_synced_at", return_value=datetime.now(timezone.utc)), \
             patch.object(obs_routes, "discovery_synced_at", return_value=None):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                r = await client.get("/observability")
        assert r.status_code == 200
        body = r.json()
        for key in ("signal_counts_today", "signals_today_total", "webhook_latency",
                    "claude_latency", "claude_spend_today", "heartbeat", "timestamp"):
            assert key in body
        assert body["heartbeat"]["stale"] is False

    @pytest.mark.asyncio
    async def test_route_reports_stale_when_agent_silent(self):
        with patch.object(obs_routes, "regime_synced_at", return_value=None), \
             patch.object(obs_routes, "discovery_synced_at", return_value=None):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                r = await client.get("/observability")
        assert r.json()["heartbeat"]["stale"] is True
