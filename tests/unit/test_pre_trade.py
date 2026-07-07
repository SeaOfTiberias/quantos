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
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

import cloud.api.regime_routes as regime_routes
from cloud.analyst.pre_trade import (
    _claude, _extract_confidence_score, analyse_signal,
)
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


# ── Structured scoring output (S4-7 / P1-9, P2-3) ────────────────────────────

def _tool_response(input_dict, name="submit_score"):
    block = SimpleNamespace(type="tool_use", name=name, input=input_dict)
    return SimpleNamespace(content=[block])


class TestExtractConfidenceScore:

    def test_extracts_valid_score(self):
        resp = _tool_response({"confidence_score": 82.5, "recommendation": "EXECUTE"})
        assert _extract_confidence_score(resp) == 82.5

    def test_clamps_out_of_range_scores(self):
        assert _extract_confidence_score(_tool_response({"confidence_score": 150})) == 100.0
        assert _extract_confidence_score(_tool_response({"confidence_score": -5})) == 0.0

    def test_text_only_response_raises(self):
        """No silent 50.0: a response without the forced tool block is an
        error the webhook turns into 'unscored', never a fake-neutral score."""
        resp = SimpleNamespace(content=[SimpleNamespace(type="text", text="Maybe 80?")])
        with pytest.raises(ValueError):
            _extract_confidence_score(resp)

    def test_non_numeric_score_raises(self):
        with pytest.raises(ValueError):
            _extract_confidence_score(_tool_response({"confidence_score": "high"}))

    def test_missing_score_key_raises(self):
        with pytest.raises(ValueError):
            _extract_confidence_score(_tool_response({"recommendation": "SKIP"}))


class TestAnalyseSignalUnscoredPath:

    @pytest.mark.asyncio
    async def test_malformed_response_surfaces_as_unscored_not_50(self):
        """S4-7 AC: a malformed Claude response must raise out of
        analyse_signal (the webhook's except-path records confidence None →
        'unscored' in Telegram) instead of returning 50.0."""
        malformed = SimpleNamespace(content=[SimpleNamespace(type="text", text="not a score")])
        signal = {"signal_id": "SIG-TEST-1", "symbol": "RELIANCE", "action": "BUY",
                  "price": 2950.0, "timeframe": "15m", "strategy": "darvas_breakout",
                  "confluence_score": 85.0, "notes": ""}
        with patch.object(_claude.messages, "create",
                          new_callable=AsyncMock, return_value=malformed):
            with pytest.raises(ValueError):
                await analyse_signal(signal)

    def test_client_timeout_is_bounded(self):
        """P2-3: the pre-trade call sits inside the webhook request — the
        client must not run on the SDK's default (much longer) timeout."""
        assert _claude.timeout == 30.0
