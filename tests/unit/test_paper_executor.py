"""
core/rotation/paper_executor.py — momentum turnover walk-forward's paper
(no real capital) quarterly rebalance: quarter-boundary gate math and the
rebalance flow itself. docs/MOMENTUM_TURNOVER_WALKFORWARD_METHODOLOGY.md.
"""

import asyncio
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from agent import paper_rotation_positions as prp
from core.brokers.base import OHLCV
from core.risk.costs import CostModel
from core.rotation import paper_executor as pe

TEST_COST_MODEL = CostModel(brokerage_pct=0, brokerage_flat=0, stt_pct=0,
                             exchange_txn_pct=0, sebi_pct=0, stamp_pct=0,
                             gst_pct=0, slippage_bps=0)


@pytest.fixture(autouse=True)
def _isolated_state(tmp_path, monkeypatch):
    monkeypatch.setattr(prp, "PAPER_WALKFORWARD_STATE_PATH", tmp_path / "paper_walkforward.json")


# ─── most_recent_quarter_end / is_eligible_to_rebalance ───────────────────────

class TestMostRecentQuarterEnd:

    def test_mid_quarter_falls_back_to_previous_quarter_end(self):
        # Oct 5 2026 is well inside Q4 -- Q4 hasn't ended yet, so the most
        # recently CLOSED boundary is Q3's end (Sep 30).
        assert pe.most_recent_quarter_end(
            datetime(2026, 10, 5, tzinfo=timezone.utc)) == date(2026, 9, 30)

    def test_exactly_on_quarter_end_returns_that_date(self):
        assert pe.most_recent_quarter_end(
            datetime(2026, 9, 30, tzinfo=timezone.utc)) == date(2026, 9, 30)

    def test_just_past_quarter_end_still_returns_that_boundary(self):
        assert pe.most_recent_quarter_end(
            datetime(2026, 10, 1, tzinfo=timezone.utc)) == date(2026, 9, 30)

    def test_q1_wraps_around_to_prior_year_q4(self):
        # Regression: naively computing "as_of's own quarter's end" for
        # Jan 3 2027 would return Mar 31 2027 (Q1 2027's end, which hasn't
        # happened yet) and silently skip Q4 2026's rebalance forever.
        assert pe.most_recent_quarter_end(
            datetime(2027, 1, 3, tzinfo=timezone.utc)) == date(2026, 12, 31)


class TestIsEligibleToRebalance:

    def test_no_prior_rebalance_and_boundary_passed_is_eligible(self):
        as_of = datetime(2026, 10, 1, tzinfo=timezone.utc)
        assert pe.is_eligible_to_rebalance(as_of, None) is True

    def test_already_rebalanced_this_boundary_is_not_eligible(self):
        as_of = datetime(2026, 10, 5, tzinfo=timezone.utc)  # boundary = Sep 30
        assert pe.is_eligible_to_rebalance(as_of, "2026-09-30") is False

    def test_new_boundary_reached_since_last_rebalance_is_eligible(self):
        as_of = datetime(2027, 1, 3, tzinfo=timezone.utc)  # boundary = Dec 31 2026
        assert pe.is_eligible_to_rebalance(as_of, "2026-09-30") is True

    def test_self_heals_across_a_missed_exact_boundary_day(self):
        # The Dec 31 2026 run never fired (e.g. VM down); Jan 15 2027's
        # daily check must still catch it rather than waiting for Mar 31.
        as_of = datetime(2027, 1, 15, tzinfo=timezone.utc)
        assert pe.is_eligible_to_rebalance(as_of, "2026-09-30") is True


# ─── run_quarterly_paper_rebalance ─────────────────────────────────────────────

def _warmed_up_candles(close: float, high: float = None, n: int = 260) -> list[OHLCV]:
    high = high if high is not None else close
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    candles = [
        OHLCV(timestamp=start + timedelta(days=i), open=high,
              high=high, low=high, close=high, volume=1000)
        for i in range(n - 1)
    ]
    candles.append(OHLCV(timestamp=start + timedelta(days=n - 1), open=close,
                          high=high, low=close, close=close, volume=1000))
    return candles


def _patch_fetch(monkeypatch, candles_by_symbol: dict):
    import scripts.validate_regime_classifier as vrc

    async def _fake_fetch(broker, symbol, from_date, to_date, sem):
        return candles_by_symbol.get(symbol, [])

    monkeypatch.setattr(vrc, "fetch_chunked_daily", _fake_fetch)


class TestRunQuarterlyPaperRebalance:

    def test_not_yet_due_returns_none_and_places_no_orders(self, monkeypatch):
        # Q2 2026 (boundary Jun 30) already rebalanced -- Aug 15 is still
        # inside Q3, whose own boundary (Sep 30) hasn't arrived yet.
        state = prp.load_state(pe.INITIAL_CAPITAL)
        state.last_rebalanced_quarter_end = "2026-06-30"
        prp.save_state(state)

        broker = MagicMock()
        _patch_fetch(monkeypatch, {"A": _warmed_up_candles(100.0)})
        as_of = datetime(2026, 8, 15, tzinfo=timezone.utc)

        result = asyncio.run(pe.run_quarterly_paper_rebalance(
            broker, ["A"], cost_model=TEST_COST_MODEL, now=as_of))

        assert result is None
        broker.place_order.assert_not_called()

    def test_due_rebalance_never_calls_place_order(self, monkeypatch):
        broker = MagicMock()
        _patch_fetch(monkeypatch, {"A": _warmed_up_candles(100.0)})
        as_of = datetime(2026, 9, 30, tzinfo=timezone.utc)

        result = asyncio.run(pe.run_quarterly_paper_rebalance(
            broker, ["A"], top_n=1, cost_model=TEST_COST_MODEL, now=as_of))

        assert result is not None
        broker.place_order.assert_not_called()
        broker.get_funds.assert_not_called()   # sizing uses the PAPER ledger, not real funds

    def test_buys_and_persists_virtual_position(self, monkeypatch):
        broker = MagicMock()
        _patch_fetch(monkeypatch, {"A": _warmed_up_candles(100.0)})
        as_of = datetime(2026, 9, 30, tzinfo=timezone.utc)

        result = asyncio.run(pe.run_quarterly_paper_rebalance(
            broker, ["A"], top_n=1, position_size=100_000.0,
            cost_model=TEST_COST_MODEL, now=as_of))

        assert result.buys[0]["symbol"] == "A"
        state = prp.load_state(pe.INITIAL_CAPITAL)
        assert "A" in state.positions
        assert state.positions["A"].quantity == 1000  # 100,000 / 100.0
        assert state.last_rebalanced_quarter_end == "2026-09-30"

    def test_second_call_same_quarter_is_a_noop(self, monkeypatch):
        broker = MagicMock()
        _patch_fetch(monkeypatch, {"A": _warmed_up_candles(100.0)})
        as_of_1 = datetime(2026, 9, 30, tzinfo=timezone.utc)
        as_of_2 = datetime(2026, 10, 5, tzinfo=timezone.utc)   # still boundary=Sep 30

        first = asyncio.run(pe.run_quarterly_paper_rebalance(
            broker, ["A"], top_n=1, cost_model=TEST_COST_MODEL, now=as_of_1))
        second = asyncio.run(pe.run_quarterly_paper_rebalance(
            broker, ["A"], top_n=1, cost_model=TEST_COST_MODEL, now=as_of_2))

        assert first is not None
        assert second is None

    def test_sells_rank_dropout_and_books_cost_at_exit(self, monkeypatch):
        state = prp.load_state(pe.INITIAL_CAPITAL)
        state.positions["A"] = prp.PaperPosition(
            symbol="A", quantity=500, entry_price=80.0, entry_date="2026-06-30")
        state.cash -= 500 * 80.0
        prp.save_state(state)

        broker = MagicMock()
        _patch_fetch(monkeypatch, {
            "A": _warmed_up_candles(close=50.0, high=100.0),   # far from high, ranks low
            "B": _warmed_up_candles(close=100.0, high=100.0),  # at high, ranks top
        })
        as_of = datetime(2026, 9, 30, tzinfo=timezone.utc)

        cost_model = CostModel(brokerage_pct=0, brokerage_flat=0, stt_pct=0.01,
                                exchange_txn_pct=0, sebi_pct=0, stamp_pct=0,
                                gst_pct=0, slippage_bps=0)
        result = asyncio.run(pe.run_quarterly_paper_rebalance(
            broker, ["A", "B"], top_n=1, cost_model=cost_model, now=as_of))

        assert any(s["symbol"] == "A" for s in result.sells)
        state = prp.load_state(pe.INITIAL_CAPITAL)
        assert "A" not in state.positions
        sell_trade = next(t for t in state.closed_trades if t.symbol == "A")
        assert sell_trade.exit_reason == "rank_dropout"
        assert sell_trade.cost == pytest.approx(0.01 * 50.0 * 500)   # stt_pct * sell turnover

    def test_no_real_broker_calls_anywhere_in_a_full_buy_and_sell_cycle(self, monkeypatch):
        state = prp.load_state(pe.INITIAL_CAPITAL)
        state.positions["A"] = prp.PaperPosition(
            symbol="A", quantity=100, entry_price=50.0, entry_date="2026-06-30")
        prp.save_state(state)

        broker = MagicMock()
        _patch_fetch(monkeypatch, {
            "A": _warmed_up_candles(close=40.0, high=100.0),
            "B": _warmed_up_candles(close=100.0, high=100.0),
        })
        as_of = datetime(2026, 9, 30, tzinfo=timezone.utc)

        asyncio.run(pe.run_quarterly_paper_rebalance(
            broker, ["A", "B"], top_n=1, cost_model=TEST_COST_MODEL, now=as_of))

        broker.place_order.assert_not_called()
        broker.get_funds.assert_not_called()
