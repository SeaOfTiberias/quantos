"""
Claude Pre-Trade Analyst — Regime Wiring Unit Tests
──────────────────────────────────────────────────────
US-04/US-05: _get_regime() used to always return a hardcoded stub
("TRENDING"/"UPTREND"/VIX 14.2) regardless of real market conditions.
It now reads the regime the local agent synced via POST /regime/sync
(cloud/api/regime_routes.py), falling back to an explicitly-labeled
UNKNOWN regime — not a fake-confident one — when nothing has synced yet.
"""

from datetime import datetime, timezone

import pytest

import cloud.api.regime_routes as regime_routes
from cloud.analyst.pre_trade import _get_regime
from core.regime.models import Regime, RegimeResult


@pytest.fixture(autouse=True)
def _isolated_regime_store(monkeypatch):
    monkeypatch.setattr(regime_routes, "_synced_regime", None)
    monkeypatch.setattr(regime_routes, "_synced_at", None)


class TestGetRegime:

    @pytest.mark.asyncio
    async def test_falls_back_to_unknown_when_nothing_synced(self):
        regime = await _get_regime("RELIANCE")
        assert regime["classification"] == "UNKNOWN"
        assert regime["allowed_strategies"] == []
        assert "note" in regime

    @pytest.mark.asyncio
    async def test_reflects_real_synced_regime(self, monkeypatch):
        result = RegimeResult(
            regime=Regime.TRENDING_BULL, confidence=88.0,
            allowed_strategies=["darvas_breakout"], size_multiplier=1.0,
            timestamp=datetime.now(timezone.utc),
            trend_signal="BULL", vix_signal="LOW", breadth_signal="STRONG",
        )
        monkeypatch.setattr(regime_routes, "_synced_regime", result)
        monkeypatch.setattr(regime_routes, "_synced_at", datetime.now(timezone.utc))

        regime = await _get_regime("RELIANCE")

        assert regime["classification"] == "TRENDING_BULL"
        assert regime["nifty_trend"] == "BULL"
        assert regime["vix_signal"] == "LOW"
        assert regime["confidence"] == 88.0
        assert regime["allowed_strategies"] == ["darvas_breakout"]
        assert "note" not in regime
