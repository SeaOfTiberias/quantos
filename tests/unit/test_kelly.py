"""
US-07 Dynamic Kelly Position Sizing — Unit Tests
"""

import pytest
from datetime import datetime, timedelta, timezone

from core.risk.kelly import (
    ClosedTrade, KellyStats, SizingResult,
    MIN_TRADES_FOR_KELLY, LOOKBACK_TRADES,
    MIN_SIZE_PCT, MAX_SIZE_PCT, FALLBACK_SIZE_PCT,
)
from core.risk.kelly_calculator import (
    compute_kelly_stats, calculate_position_size, _kelly_formula,
)
from core.risk.trade_history import TradeHistoryService, format_sizing_whatsapp


# ─── Fixtures ────────────────────────────────────────────────────────────────

def make_trade(
    symbol: str = "RELIANCE",
    entry: float = 100.0,
    exit: float = 110.0,
    qty: int = 10,
    direction: str = "BUY",
    days_ago: int = 1,
    strategy: str = "darvas_breakout",
) -> ClosedTrade:
    now = datetime.now(timezone.utc)
    return ClosedTrade(
        trade_id=f"T-{symbol}-{days_ago}",
        symbol=symbol,
        entry_price=entry,
        exit_price=exit,
        quantity=qty,
        direction=direction,
        entry_date=now - timedelta(days=days_ago + 1),
        exit_date=now - timedelta(days=days_ago),
        strategy=strategy,
    )


def make_winning_trades(n: int, win_pct: float = 0.05) -> list[ClosedTrade]:
    """Generate n winning BUY trades with a fixed % gain."""
    return [
        make_trade(entry=100.0, exit=100.0 * (1 + win_pct), days_ago=i)
        for i in range(n)
    ]


def make_losing_trades(n: int, loss_pct: float = 0.03) -> list[ClosedTrade]:
    """Generate n losing BUY trades with a fixed % loss."""
    return [
        make_trade(entry=100.0, exit=100.0 * (1 - loss_pct), days_ago=i)
        for i in range(n)
    ]


def make_mixed_trades(wins: int, losses: int, win_pct=0.05, loss_pct=0.03) -> list[ClosedTrade]:
    return make_winning_trades(wins, win_pct) + make_losing_trades(losses, loss_pct)


# ─── ClosedTrade Tests ─────────────────────────────────────────────────────────

class TestClosedTrade:
    # S5-1: `pnl`/`pnl_pct`/`is_win` are now NET of transaction costs; the raw
    # price move lives on `gross_pnl`/`gross_pnl_pct`. Costs are small (~₹1 on a
    # ₹1k notional) but always > 0, so net is strictly inside gross.

    def test_gross_pnl_long_winning(self):
        trade = make_trade(entry=100.0, exit=110.0, qty=10, direction="BUY")
        assert trade.gross_pnl == 100.0   # (110-100)*10

    def test_pnl_long_winning_is_net(self):
        trade = make_trade(entry=100.0, exit=110.0, qty=10, direction="BUY")
        assert trade.costs > 0
        assert trade.pnl == pytest.approx(100.0 - trade.costs)
        assert trade.pnl < trade.gross_pnl

    def test_pnl_long_losing_is_net(self):
        trade = make_trade(entry=100.0, exit=95.0, qty=10, direction="BUY")
        assert trade.gross_pnl == -50.0
        assert trade.pnl == pytest.approx(-50.0 - trade.costs)  # costs deepen the loss

    def test_gross_pnl_short_winning(self):
        trade = make_trade(entry=100.0, exit=90.0, qty=10, direction="SELL")
        assert trade.gross_pnl == 100.0   # short profits when price falls
        assert trade.pnl == pytest.approx(100.0 - trade.costs)

    def test_pnl_short_losing_is_net(self):
        trade = make_trade(entry=100.0, exit=110.0, qty=10, direction="SELL")
        assert trade.gross_pnl == -100.0
        assert trade.pnl == pytest.approx(-100.0 - trade.costs)

    def test_pnl_pct_long_net(self):
        trade = make_trade(entry=100.0, exit=110.0, direction="BUY")
        assert trade.gross_pnl_pct == pytest.approx(0.10)
        assert trade.pnl_pct < 0.10                      # costs shave the return
        assert trade.pnl_pct == pytest.approx(0.10, abs=0.005)

    def test_pnl_pct_short_net(self):
        trade = make_trade(entry=100.0, exit=90.0, direction="SELL")
        assert trade.gross_pnl_pct == pytest.approx(0.10)
        assert trade.pnl_pct < 0.10

    def test_is_win_true(self):
        trade = make_trade(entry=100.0, exit=110.0, direction="BUY")
        assert trade.is_win is True

    def test_is_win_false(self):
        trade = make_trade(entry=100.0, exit=90.0, direction="BUY")
        assert trade.is_win is False

    def test_marginal_gross_win_that_costs_flip_to_loss(self):
        # A trade whose gross gain is smaller than its round-trip costs is a
        # NET loss — the whole point of S5-1.
        trade = make_trade(entry=1000.0, exit=1000.05, qty=10, direction="BUY")
        assert trade.gross_pnl > 0
        assert trade.pnl < 0
        assert trade.is_win is False

    def test_pnl_pct_zero_entry_safe(self):
        trade = make_trade(entry=0.0, exit=10.0)
        assert trade.pnl_pct == 0.0


# ─── Kelly Formula Tests ───────────────────────────────────────────────────────

class TestKellyFormula:

    def test_kelly_formula_positive_edge(self):
        # 60% win rate, 2:1 win/loss ratio → positive Kelly
        f = _kelly_formula(win_rate=0.6, win_loss_ratio=2.0)
        assert f > 0

    def test_kelly_formula_negative_edge(self):
        # 30% win rate, 1:1 ratio → negative Kelly
        f = _kelly_formula(win_rate=0.3, win_loss_ratio=1.0)
        assert f < 0

    def test_kelly_formula_known_value(self):
        # f* = W - (1-W)/R = 0.5 - 0.5/2 = 0.25
        f = _kelly_formula(win_rate=0.5, win_loss_ratio=2.0)
        assert f == pytest.approx(0.25)

    def test_kelly_formula_zero_ratio_safe(self):
        f = _kelly_formula(win_rate=0.5, win_loss_ratio=0.0)
        assert f == 0.0


# ─── Kelly Stats Computation Tests ─────────────────────────────────────────────

class TestComputeKellyStats:

    def test_insufficient_trades_flagged(self):
        trades = make_mixed_trades(wins=5, losses=5)   # only 10, need 20
        stats = compute_kelly_stats(trades)
        assert stats.has_sufficient_data is False
        assert stats.sample_size == 10

    def test_sufficient_trades_computed(self):
        trades = make_mixed_trades(wins=15, losses=10)   # 25 total
        stats = compute_kelly_stats(trades)
        assert stats.has_sufficient_data is True
        assert stats.sample_size == 25

    def test_win_rate_calculation(self):
        trades = make_mixed_trades(wins=15, losses=10)
        stats = compute_kelly_stats(trades)
        assert stats.win_rate == pytest.approx(15 / 25)

    def test_avg_win_loss_pct(self):
        # Net-of-cost (S5-1): costs (~0.1% of notional) shave winners and deepen
        # losers, so the averages sit just inside the gross 5%/3% inputs.
        trades = make_mixed_trades(wins=15, losses=10, win_pct=0.05, loss_pct=0.03)
        stats = compute_kelly_stats(trades)
        assert stats.avg_win_pct == pytest.approx(0.05, abs=0.003)
        assert stats.avg_win_pct < 0.05
        assert stats.avg_loss_pct == pytest.approx(0.03, abs=0.003)
        assert stats.avg_loss_pct > 0.03

    def test_win_loss_ratio(self):
        # Gross 2:1 (6% vs 3%) compresses slightly once costs bite both sides.
        trades = make_mixed_trades(wins=15, losses=10, win_pct=0.06, loss_pct=0.03)
        stats = compute_kelly_stats(trades)
        assert stats.win_loss_ratio == pytest.approx(2.0, abs=0.15)
        assert stats.win_loss_ratio < 2.0

    def test_all_wins_no_losses_handled(self):
        trades = make_winning_trades(25)
        stats = compute_kelly_stats(trades)
        assert stats.has_sufficient_data is True
        assert stats.avg_loss_pct == 0.0
        assert stats.win_loss_ratio == 10.0  # capped sentinel value

    def test_is_positive_edge_property(self):
        trades = make_mixed_trades(wins=18, losses=7, win_pct=0.06, loss_pct=0.02)
        stats = compute_kelly_stats(trades)
        assert stats.is_positive_edge is True

    def test_negative_edge_detected(self):
        trades = make_mixed_trades(wins=8, losses=17, win_pct=0.02, loss_pct=0.05)
        stats = compute_kelly_stats(trades)
        assert stats.is_positive_edge is False


# ─── Position Sizing Tests (with guardrails) ───────────────────────────────────

class TestCalculatePositionSize:

    def test_fallback_used_with_insufficient_history(self):
        trades = make_mixed_trades(wins=3, losses=2)  # only 5 trades
        result = calculate_position_size(trades, capital=500000, symbol="RELIANCE")
        assert result.method == "FIXED_FALLBACK"
        assert result.size_pct == FALLBACK_SIZE_PCT

    def test_zero_edge_uses_minimum_size(self):
        trades = make_mixed_trades(wins=5, losses=20, win_pct=0.01, loss_pct=0.05)
        result = calculate_position_size(trades, capital=500000, symbol="RELIANCE")
        assert result.method == "ZERO_EDGE"
        assert result.size_pct == MIN_SIZE_PCT

    def test_positive_edge_uses_kelly(self):
        trades = make_mixed_trades(wins=18, losses=7, win_pct=0.08, loss_pct=0.03)
        result = calculate_position_size(trades, capital=500000, symbol="RELIANCE")
        assert result.method == "KELLY"
        assert result.kelly_stats.is_positive_edge is True

    def test_size_never_exceeds_max_cap(self):
        # Engineer an extreme edge that would suggest huge Kelly sizing
        trades = make_mixed_trades(wins=24, losses=1, win_pct=0.15, loss_pct=0.01)
        result = calculate_position_size(trades, capital=500000, symbol="RELIANCE")
        assert result.size_pct <= MAX_SIZE_PCT

    def test_size_never_below_min_floor(self):
        trades = make_mixed_trades(wins=12, losses=13, win_pct=0.02, loss_pct=0.019)
        result = calculate_position_size(trades, capital=500000, symbol="RELIANCE")
        assert result.size_pct >= MIN_SIZE_PCT

    def test_risk_amount_matches_capital_pct(self):
        trades = make_mixed_trades(wins=3, losses=2)  # fallback case
        result = calculate_position_size(trades, capital=1000000, symbol="TCS")
        assert result.risk_amount == pytest.approx(1000000 * FALLBACK_SIZE_PCT)

    def test_uses_lookback_window(self):
        """Only the most recent `lookback` trades should be used."""
        # Old losing trades: far in the past (days_ago 100-139)
        old_losing = [
            make_trade(entry=100.0, exit=90.0, days_ago=100 + i)
            for i in range(40)
        ]
        # Recent winning trades: most recent (days_ago 0-24)
        recent_winning = [
            make_trade(entry=100.0, exit=108.0, days_ago=i)
            for i in range(25)
        ]
        all_trades = old_losing + recent_winning  # 65 total

        result = calculate_position_size(
            all_trades, capital=500000, symbol="RELIANCE", lookback=25
        )
        # With lookback=25, should only see recent_winning trades → all wins → high win rate
        assert result.kelly_stats.sample_size == 25
        assert result.kelly_stats.win_rate == 1.0

    def test_notes_explain_method(self):
        trades = make_mixed_trades(wins=3, losses=2)
        result = calculate_position_size(trades, capital=500000, symbol="RELIANCE")
        assert len(result.notes) > 0
        assert any("Insufficient" in n for n in result.notes)


# ─── SizingResult.position_quantity Tests ──────────────────────────────────────

class TestPositionQuantity:

    def test_position_quantity_calculation(self):
        result = SizingResult(
            symbol="RELIANCE", capital=500000, size_pct=0.02,
            risk_amount=10000, method="KELLY",
        )
        # risk ₹10,000, entry 2950, stop 2900 → risk_per_share = 50
        qty = result.position_quantity(entry_price=2950.0, stop_loss_price=2900.0)
        assert qty == 200   # 10000 / 50

    def test_position_quantity_zero_risk_per_share(self):
        result = SizingResult(
            symbol="RELIANCE", capital=500000, size_pct=0.02,
            risk_amount=10000, method="KELLY",
        )
        qty = result.position_quantity(entry_price=2950.0, stop_loss_price=2950.0)
        assert qty == 0


# ─── TradeHistoryService Tests ─────────────────────────────────────────────────

class TestTradeHistoryService:

    def test_record_closed_trade_adds_to_history(self):
        service = TradeHistoryService()
        trade = make_trade()
        service.record_closed_trade(trade)
        assert len(service.get_trade_history()) == 1

    def test_record_closed_trade_triggers_recalc(self):
        service = TradeHistoryService()
        trade = make_trade()
        result = service.record_closed_trade(trade)
        assert isinstance(result, SizingResult)

    def test_get_trade_history_filters_by_symbol(self):
        service = TradeHistoryService()
        service.record_closed_trade(make_trade(symbol="RELIANCE"))
        service.record_closed_trade(make_trade(symbol="TCS"))

        reliance_trades = service.get_trade_history(symbol="RELIANCE")
        assert len(reliance_trades) == 1
        assert reliance_trades[0].symbol == "RELIANCE"

    def test_stats_summary_empty(self):
        service = TradeHistoryService()
        stats = service.stats_summary()
        assert stats["total_trades"] == 0
        assert stats["win_rate"] is None

    def test_stats_summary_with_trades(self):
        service = TradeHistoryService()
        service.record_closed_trade(make_trade(entry=100, exit=110))  # win
        service.record_closed_trade(make_trade(entry=100, exit=90))   # loss

        stats = service.stats_summary()
        assert stats["total_trades"] == 2
        assert stats["win_rate"] == 0.5

    def test_get_last_sizing_returns_none_initially(self):
        service = TradeHistoryService()
        assert service.get_last_sizing("RELIANCE") is None

    def test_get_last_sizing_after_trade(self):
        service = TradeHistoryService()
        service.record_closed_trade(make_trade(symbol="RELIANCE"))
        last = service.get_last_sizing("RELIANCE")
        assert last is not None


# ─── Trade History Persistence (S4-4 / P1-1) ───────────────────────────────────

class TestTradeHistoryPersistence:

    def test_history_survives_restart(self, tmp_path):
        path = tmp_path / "trade_history.json"
        service = TradeHistoryService(persist_path=path)
        service.record_closed_trade(make_trade(symbol="RELIANCE"))
        service.record_closed_trade(make_trade(symbol="TCS", entry=100, exit=95))

        # Simulate the daily agent restart: brand-new instance, same file
        reloaded = TradeHistoryService(persist_path=path)
        trades = reloaded.get_trade_history()
        assert len(trades) == 2
        assert {t.symbol for t in trades} == {"RELIANCE", "TCS"}
        assert trades[0].pnl == make_trade(symbol="RELIANCE").pnl

    def test_twentieth_trade_flips_to_kelly_across_restarts(self, tmp_path):
        """S4-4 AC: Kelly's 20-trade minimum must be reachable even though
        the agent restarts daily."""
        path = tmp_path / "trade_history.json"

        # 19 trades recorded across three separate "agent sessions"
        for session_slice in (range(0, 7), range(7, 14), range(14, 19)):
            service = TradeHistoryService(persist_path=path)
            for i in session_slice:
                exit_price = 112.0 if i % 3 != 2 else 96.0  # ~2:1 winners, positive edge
                service.record_closed_trade(
                    make_trade(entry=100.0, exit=exit_price, days_ago=25 - i))

        # Fresh restart, 19 trades on disk → still building history
        service = TradeHistoryService(persist_path=path)
        assert len(service.get_trade_history()) == 19
        assert service.get_current_sizing("RELIANCE", capital=500000).method == "FIXED_FALLBACK"

        # The 20th closed trade flips the method
        result = service.record_closed_trade(make_trade(entry=100.0, exit=112.0, days_ago=5))
        assert result.method == "KELLY"

    def test_corrupt_file_starts_empty_without_crashing(self, tmp_path):
        path = tmp_path / "trade_history.json"
        path.write_text("{not valid json")
        service = TradeHistoryService(persist_path=path)
        assert service.get_trade_history() == []
        # And recording still works (file gets rewritten cleanly)
        service.record_closed_trade(make_trade())
        assert len(TradeHistoryService(persist_path=path).get_trade_history()) == 1

    def test_no_persist_path_stays_in_memory(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        service = TradeHistoryService()
        service.record_closed_trade(make_trade())
        assert list(tmp_path.iterdir()) == []  # nothing written anywhere near us


# ─── WhatsApp Formatting Tests ─────────────────────────────────────────────────

class TestSizingWhatsappFormat:

    def test_format_contains_symbol_and_size(self):
        result = SizingResult(
            symbol="RELIANCE", capital=500000, size_pct=0.025,
            risk_amount=12500, method="KELLY",
            kelly_stats=KellyStats(
                sample_size=30, win_rate=0.6, avg_win_pct=0.05,
                avg_loss_pct=0.03, win_loss_ratio=1.67, raw_kelly=0.20,
                has_sufficient_data=True,
            ),
        )
        msg = format_sizing_whatsapp(result)
        assert "RELIANCE" in msg
        assert "2.50%" in msg
        assert "INR 12,500" in msg

    def test_format_fallback_method_label(self):
        result = SizingResult(
            symbol="TCS", capital=500000, size_pct=0.02,
            risk_amount=10000, method="FIXED_FALLBACK",
        )
        msg = format_sizing_whatsapp(result)
        assert "Fixed" in msg or "Building History" in msg
