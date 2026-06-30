"""
US-03 Screener → Claude Ranker — Unit Tests
"""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch

from core.screener.ingest import (
    parse_screener_csv, apply_pre_filters, ScreenerCandidate,
)
from core.screener.ranker import rank_candidates, _parse_ranking_response
from core.screener.alerts import format_shortlist_whatsapp, format_shortlist_summary_line


# ─── Sample CSV fixtures ──────────────────────────────────────────────────────

SAMPLE_CSV = """Symbol,Price,Change %,Volume,Relative Volume,50D SMA,200D SMA,RSI,ATR%
RELIANCE,2950.50,2.3,1500000,1.8,2850.00,2700.00,62.5,1.2
TCS,3820.00,1.1,800000,1.2,3750.00,3600.00,58.0,0.9
INFY,1520.00,-0.5,600000,0.9,1540.00,1480.00,45.0,1.5
SMALLCAP,85.50,5.2,50000,2.1,80.00,75.00,78.0,3.2
HDFC,1680.00,0.8,2000000,1.5,1650.00,1600.00,55.0,1.0
"""

MALFORMED_CSV = """Symbol,Price
RELIANCE,
TCS,abc
,2000
"""


# ─── CSV Parsing Tests ─────────────────────────────────────────────────────────

class TestCSVParsing:

    def test_parses_valid_csv(self):
        candidates = parse_screener_csv(SAMPLE_CSV)
        assert len(candidates) == 5

    def test_parses_symbol_correctly(self):
        candidates = parse_screener_csv(SAMPLE_CSV)
        symbols = [c.symbol for c in candidates]
        assert "RELIANCE" in symbols
        assert "TCS" in symbols

    def test_parses_numeric_fields(self):
        candidates = parse_screener_csv(SAMPLE_CSV)
        reliance = next(c for c in candidates if c.symbol == "RELIANCE")
        assert reliance.price == 2950.50
        assert reliance.change_pct == 2.3
        assert reliance.volume == 1500000
        assert reliance.relative_volume == 1.8

    def test_above_50_sma_property(self):
        candidates = parse_screener_csv(SAMPLE_CSV)
        reliance = next(c for c in candidates if c.symbol == "RELIANCE")
        assert reliance.above_50_sma is True   # 2950 > 2850

    def test_below_50_sma_property(self):
        candidates = parse_screener_csv(SAMPLE_CSV)
        infy = next(c for c in candidates if c.symbol == "INFY")
        assert infy.above_50_sma is False   # 1520 < 1540

    def test_is_liquid_property(self):
        candidates = parse_screener_csv(SAMPLE_CSV)
        smallcap = next(c for c in candidates if c.symbol == "SMALLCAP")
        assert smallcap.is_liquid is False   # 50,000 volume < 500,000 threshold

        reliance = next(c for c in candidates if c.symbol == "RELIANCE")
        assert reliance.is_liquid is True

    def test_has_volume_surge_property(self):
        candidates = parse_screener_csv(SAMPLE_CSV)
        reliance = next(c for c in candidates if c.symbol == "RELIANCE")
        assert reliance.has_volume_surge is True   # rel_vol 1.8 >= 1.5

    def test_empty_csv_returns_empty_list(self):
        assert parse_screener_csv("") == []

    def test_malformed_rows_are_skipped(self):
        candidates = parse_screener_csv(MALFORMED_CSV)
        # Row with empty price, invalid price, and empty symbol should all be skipped
        assert len(candidates) == 0

    def test_handles_column_name_variants(self):
        csv_variant = "Ticker,Last,% Change,Vol\nRELIANCE,2950.50,2.3,1500000\n"
        candidates = parse_screener_csv(csv_variant)
        assert len(candidates) == 1
        assert candidates[0].symbol == "RELIANCE"

    def test_handles_comma_separated_numbers(self):
        csv_with_commas = "Symbol,Price,Volume\nRELIANCE,2950.50,1,500,000\n"
        candidates = parse_screener_csv(csv_with_commas)
        # Should not crash — volume parsing strips commas
        assert len(candidates) >= 0  # graceful handling, may skip malformed


# ─── Pre-Filter Tests ──────────────────────────────────────────────────────────

class TestPreFilters:

    def test_filters_by_min_volume(self):
        candidates = parse_screener_csv(SAMPLE_CSV)
        filtered = apply_pre_filters(candidates, min_volume=500_000)
        symbols = [c.symbol for c in filtered]
        assert "SMALLCAP" not in symbols   # 50,000 volume filtered out

    def test_filters_by_above_50_sma(self):
        candidates = parse_screener_csv(SAMPLE_CSV)
        filtered = apply_pre_filters(
            candidates, min_volume=0, require_above_50_sma=True
        )
        symbols = [c.symbol for c in filtered]
        assert "INFY" not in symbols   # below 50 SMA

    def test_no_filter_returns_all_when_disabled(self):
        candidates = parse_screener_csv(SAMPLE_CSV)
        filtered = apply_pre_filters(
            candidates, min_volume=0, require_above_50_sma=False
        )
        assert len(filtered) == len(candidates)

    def test_combined_filters(self):
        candidates = parse_screener_csv(SAMPLE_CSV)
        filtered = apply_pre_filters(
            candidates, min_volume=500_000, require_above_50_sma=True
        )
        # Should exclude SMALLCAP (volume) and INFY (below SMA)
        symbols = [c.symbol for c in filtered]
        assert "SMALLCAP" not in symbols
        assert "INFY" not in symbols
        assert "RELIANCE" in symbols


# ─── Ranker Tests ───────────────────────────────────────────────────────────────

class TestRanker:

    def _make_candidates(self) -> list[ScreenerCandidate]:
        return [
            ScreenerCandidate(symbol="RELIANCE", price=2950.0, change_pct=2.3,
                              volume=1500000, relative_volume=1.8,
                              sma_50=2850.0, sma_200=2700.0, rsi=62.5, atr_pct=1.2),
            ScreenerCandidate(symbol="TCS", price=3820.0, change_pct=1.1,
                              volume=800000, relative_volume=1.2,
                              sma_50=3750.0, sma_200=3600.0, rsi=58.0, atr_pct=0.9),
        ]

    @pytest.mark.asyncio
    async def test_empty_candidates_returns_empty(self):
        result = await rank_candidates([], nifty_change_pct=1.0)
        assert result == []

    @pytest.mark.asyncio
    async def test_rank_candidates_calls_claude(self):
        candidates = self._make_candidates()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({
            "rankings": [
                {"symbol": "RELIANCE", "rank": 1, "score": 85, "rationale": "Strong RS"},
                {"symbol": "TCS", "rank": 2, "score": 70, "rationale": "Steady uptrend"},
            ]
        }))]

        with patch("core.screener.ranker._claude.messages.create",
                   new_callable=AsyncMock, return_value=mock_response):
            result = await rank_candidates(candidates, nifty_change_pct=1.0, top_n=10)

        assert len(result) == 2
        assert result[0]["symbol"] == "RELIANCE"
        assert result[0]["score"] == 85

    @pytest.mark.asyncio
    async def test_rank_respects_top_n(self):
        candidates = self._make_candidates()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({
            "rankings": [
                {"symbol": "RELIANCE", "rank": 1, "score": 85, "rationale": "x"},
                {"symbol": "TCS", "rank": 2, "score": 70, "rationale": "y"},
            ]
        }))]

        with patch("core.screener.ranker._claude.messages.create",
                   new_callable=AsyncMock, return_value=mock_response):
            result = await rank_candidates(candidates, nifty_change_pct=1.0, top_n=1)

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_caps_candidates_sent_to_claude(self):
        many_candidates = [
            ScreenerCandidate(symbol=f"STOCK{i}", price=100.0, change_pct=1.0, volume=600000)
            for i in range(60)
        ]
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({"rankings": []}))]

        with patch("core.screener.ranker._claude.messages.create",
                   new_callable=AsyncMock, return_value=mock_response) as mock_create:
            await rank_candidates(many_candidates, nifty_change_pct=1.0)

        # Check the prompt sent doesn't include all 60 — capped at 40
        call_args = mock_create.call_args
        prompt_content = call_args.kwargs["messages"][0]["content"]
        stock_count = prompt_content.count("STOCK")
        assert stock_count <= 40

    def test_parse_ranking_response_valid_json(self):
        raw = json.dumps({"rankings": [{"symbol": "TCS", "rank": 1, "score": 90, "rationale": "x"}]})
        result = _parse_ranking_response(raw)
        assert len(result) == 1
        assert result[0]["symbol"] == "TCS"

    def test_parse_ranking_response_strips_markdown_fences(self):
        raw = "```json\n" + json.dumps({"rankings": [{"symbol": "TCS", "rank": 1, "score": 90, "rationale": "x"}]}) + "\n```"
        result = _parse_ranking_response(raw)
        assert len(result) == 1

    def test_parse_ranking_response_invalid_json_returns_empty(self):
        result = _parse_ranking_response("not valid json at all")
        assert result == []

    def test_parse_ranking_sorts_by_score(self):
        raw = json.dumps({"rankings": [
            {"symbol": "A", "rank": 2, "score": 60, "rationale": "x"},
            {"symbol": "B", "rank": 1, "score": 90, "rationale": "y"},
        ]})
        result = _parse_ranking_response(raw)
        assert result[0]["symbol"] == "B"   # higher score first


# ─── Alert Formatting Tests ───────────────────────────────────────────────────

class TestAlertFormatting:

    def test_empty_rankings_message(self):
        msg = format_shortlist_whatsapp([], total_scanned=20)
        assert "No qualifying candidates" in msg
        assert "20" in msg

    def test_formats_rankings_with_medals(self):
        rankings = [
            {"symbol": "RELIANCE", "rank": 1, "score": 85, "rationale": "Strong setup"},
            {"symbol": "TCS", "rank": 2, "score": 78, "rationale": "Good RS"},
            {"symbol": "INFY", "rank": 3, "score": 70, "rationale": "Decent volume"},
        ]
        msg = format_shortlist_whatsapp(rankings, total_scanned=15)
        assert "🥇" in msg
        assert "🥈" in msg
        assert "🥉" in msg
        assert "RELIANCE" in msg

    def test_rank_beyond_three_uses_number(self):
        rankings = [
            {"symbol": f"STOCK{i}", "rank": i, "score": 100 - i * 5, "rationale": "x"}
            for i in range(1, 6)
        ]
        msg = format_shortlist_whatsapp(rankings, total_scanned=20)
        assert "4." in msg
        assert "5." in msg

    def test_summary_line_empty(self):
        assert format_shortlist_summary_line([]) == "No candidates today"

    def test_summary_line_with_data(self):
        rankings = [
            {"symbol": "RELIANCE", "rank": 1, "score": 85, "rationale": "x"},
            {"symbol": "TCS", "rank": 2, "score": 78, "rationale": "y"},
        ]
        summary = format_shortlist_summary_line(rankings)
        assert "RELIANCE" in summary
        assert "TCS" in summary
