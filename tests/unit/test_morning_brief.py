"""
US-14 Morning Intelligence Brief — Unit Tests
"""

import pytest
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

from core.morning.brief import (
    MorningBriefData, MorningBrief, generate_morning_brief, _format_whatsapp,
)
from core.morning.scheduler import run_morning_brief_job


def make_brief_data(
    regime: str = "TRENDING_BULL",
    candidates: list = None,
    events: list = None,
    darvas_enabled: bool = True,
) -> MorningBriefData:
    top_candidates = candidates if candidates is not None else [
        {"symbol": "RELIANCE", "score": 88, "rationale": "Strong breakout"},
        {"symbol": "TCS", "score": 75, "rationale": "Decent RS"},
    ]
    upcoming_events = events if events is not None else [
        {"event_type": "RBI_POLICY", "event_date": "2026-07-04",
         "impact": "HIGH", "description": "RBI MPC meeting"},
    ]
    return MorningBriefData(
        date=date(2026, 7, 1),
        regime=regime,
        regime_confidence=82.0,
        trend_signal="BULL",
        vix_signal="LOW",
        darvas_enabled=darvas_enabled,
        allowed_strategies=["darvas_breakout", "bull_call_spread"],
        top_candidates=top_candidates,
        upcoming_events=upcoming_events,
        kelly_size_pct=0.025,
        kelly_method="KELLY",
        trade_history_count=35,
        prev_day_pnl=2500.0,
        prev_day_trades=2,
        open_positions=["INFY", "HDFCBANK"],
    )


class TestFormatWhatsapp:

    def test_contains_regime(self):
        data = make_brief_data()
        msg = _format_whatsapp(data, "Test narrative.")
        assert "TRENDING BULL" in msg

    def test_contains_candidates(self):
        data = make_brief_data()
        msg = _format_whatsapp(data, "Narrative.")
        assert "RELIANCE" in msg
        assert "TCS" in msg

    def test_contains_event_risk(self):
        data = make_brief_data()
        msg = _format_whatsapp(data, "Narrative.")
        assert "RBI" in msg

    def test_contains_sizing(self):
        data = make_brief_data()
        msg = _format_whatsapp(data, "Narrative.")
        assert "2.5%" in msg

    def test_contains_prev_day_pnl(self):
        data = make_brief_data()
        msg = _format_whatsapp(data, "Narrative.")
        assert "2,500" in msg

    def test_contains_narrative(self):
        data = make_brief_data()
        msg = _format_whatsapp(data, "Markets look bullish today.")
        assert "Markets look bullish today." in msg

    def test_darvas_gated_when_wrong_regime(self):
        data = make_brief_data(regime="RANGING", darvas_enabled=False)
        msg = _format_whatsapp(data, "Narrative.")
        assert "Gated" in msg or "❌" in msg

    def test_no_candidates_message(self):
        data = make_brief_data(candidates=[], events=[])
        msg = _format_whatsapp(data, "Narrative.")
        assert "None today" in msg

    def test_no_events_message(self):
        data = make_brief_data(candidates=[], events=[])
        msg = _format_whatsapp(data, "Narrative.")
        assert "RBI" not in msg
        assert "Event Risk" not in msg

    def test_open_positions_shown(self):
        data = make_brief_data()
        msg = _format_whatsapp(data, "Narrative.")
        assert "INFY" in msg
        assert "HDFCBANK" in msg

    def test_regime_emoji_bull(self):
        data = make_brief_data(regime="TRENDING_BULL")
        msg = _format_whatsapp(data, "Narrative.")
        assert "🟢" in msg

    def test_regime_emoji_ranging(self):
        data = make_brief_data(regime="RANGING")
        msg = _format_whatsapp(data, "Narrative.")
        assert "🟡" in msg


class TestGenerateMorningBrief:

    @pytest.mark.asyncio
    async def test_generates_brief_with_narrative(self):
        data = make_brief_data()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Markets look bullish. Darvas active. RELIANCE leads.")]

        with patch("core.morning.brief._claude.messages.create",
                   new_callable=AsyncMock, return_value=mock_response):
            brief = await generate_morning_brief(data)

        assert isinstance(brief, MorningBrief)
        assert "bullish" in brief.narrative.lower() or len(brief.narrative) > 0

    @pytest.mark.asyncio
    async def test_fallback_narrative_on_claude_error(self):
        data = make_brief_data()

        with patch("core.morning.brief._claude.messages.create",
                   new_callable=AsyncMock, side_effect=Exception("API error")):
            brief = await generate_morning_brief(data)

        assert brief.narrative is not None
        assert len(brief.narrative) > 0
        assert "TRENDING_BULL" in brief.narrative or "2.5%" in brief.narrative

    @pytest.mark.asyncio
    async def test_whatsapp_message_in_brief(self):
        data = make_brief_data()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Brief narrative here.")]

        with patch("core.morning.brief._claude.messages.create",
                   new_callable=AsyncMock, return_value=mock_response):
            brief = await generate_morning_brief(data)

        assert len(brief.whatsapp_message) > 100
        assert "QuantOS" in brief.whatsapp_message


class TestRunMorningBriefJob:

    @pytest.mark.asyncio
    async def test_runs_without_services(self):
        """Should work with no services — uses defaults."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="No services configured.")]

        with patch("core.morning.brief._claude.messages.create",
                   new_callable=AsyncMock, return_value=mock_response):
            result = await run_morning_brief_job()

        assert "regime" in result
        assert "message" in result
        assert result["status"] in ("delivered", "generated")

    @pytest.mark.asyncio
    async def test_includes_regime_when_service_provided(self):
        mock_regime_service = MagicMock()
        mock_result = MagicMock()
        mock_result.regime.value = "RANGING"
        mock_result.confidence = 70.0
        mock_result.trend_signal = "NEUTRAL"
        mock_result.vix_signal = "MODERATE"
        mock_result.darvas_enabled = False
        mock_result.allowed_strategies = ["iron_condor"]
        mock_regime_service.get_regime = AsyncMock(return_value=mock_result)

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Range-bound market.")]

        with patch("core.morning.brief._claude.messages.create",
                   new_callable=AsyncMock, return_value=mock_response):
            result = await run_morning_brief_job(regime_service=mock_regime_service)

        assert result["regime"] == "RANGING"

    @pytest.mark.asyncio
    async def test_graceful_degradation_on_regime_error(self):
        mock_regime_service = MagicMock()
        mock_regime_service.get_regime = AsyncMock(side_effect=Exception("Broker down"))

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Fallback brief.")]

        with patch("core.morning.brief._claude.messages.create",
                   new_callable=AsyncMock, return_value=mock_response):
            result = await run_morning_brief_job(regime_service=mock_regime_service)

        # Should still complete — regime defaults to UNCERTAIN
        assert result["regime"] == "UNCERTAIN"
        assert "message" in result
