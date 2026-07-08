"""
Portfolio Kill Switch — Unit Tests (S4-2 / P0-2)

Covers the four automatic behaviors and the two invariants from the
acceptance criteria:
  • daily-loss breach (realized, and realized + open-position MTM)
  • 3-consecutive-loss trigger
  • concurrent-position cap
  • halt-flag persistence across an agent "restart", cleared only manually
  • exits are still managed while halted (entries refused, trailing/close
    path in agent.main._manage_open_positions untouched)
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from agent import risk_guard
from core.risk.kelly import ClosedTrade

IST = risk_guard.IST


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _isolated_halt_path(tmp_path, monkeypatch):
    """Point the halt flag at a throwaway file so tests never touch the
    real ~/.quantos/halt."""
    monkeypatch.setattr(risk_guard, "HALT_FLAG_PATH", tmp_path / "halt")


def make_trade(pnl_sign: int = 1, *, entry: float = 100.0, qty: int = 100,
               exit_delta: float = 5.0, days_ago: int = 0,
               symbol: str = "RELIANCE") -> ClosedTrade:
    """A closed BUY trade whose sign is win (+1) or loss (-1). `days_ago`
    shifts the exit date back in IST calendar days."""
    exit_price = entry + exit_delta if pnl_sign > 0 else entry - exit_delta
    exit_date = datetime.now(IST) - timedelta(days=days_ago)
    return ClosedTrade(
        trade_id=f"T-{symbol}-{days_ago}-{pnl_sign}",
        symbol=symbol,
        entry_price=entry,
        exit_price=exit_price,
        quantity=qty,
        direction="BUY",
        entry_date=exit_date - timedelta(hours=1),
        exit_date=exit_date,
    )


def _pos(symbol="RELIANCE", direction="BUY", entry=100.0, qty=100):
    return SimpleNamespace(symbol=symbol, direction=direction,
                           entry_price=entry, quantity=qty)


# ─── Pure calculations ────────────────────────────────────────────────────────

class TestConsecutiveLosses:

    def test_three_in_a_row_counts(self):
        trades = [make_trade(-1) for _ in range(3)]
        assert risk_guard.consecutive_losses(trades) == 3

    def test_stops_at_first_win_from_the_tail(self):
        # win, loss, loss  → only the trailing two losses count
        trades = [make_trade(1), make_trade(-1), make_trade(-1)]
        assert risk_guard.consecutive_losses(trades) == 2

    def test_a_win_at_the_tail_resets_to_zero(self):
        trades = [make_trade(-1), make_trade(-1), make_trade(1)]
        assert risk_guard.consecutive_losses(trades) == 0

    def test_empty_history(self):
        assert risk_guard.consecutive_losses([]) == 0


class TestRealizedPnlToday:

    def test_sums_only_todays_exits(self):
        # Realized P&L is now net of transaction costs (S5-1), so assert against
        # the two same-day trades' net pnl rather than the gross -500 — this
        # still proves the 3-days-ago -5,000 is excluded.
        trades = [
            make_trade(-1, exit_delta=10, qty=100, days_ago=0),   # ~-1000 today
            make_trade(-1, exit_delta=50, qty=100, days_ago=3),   # -5000 but 3d ago
            make_trade(1, exit_delta=5, qty=100, days_ago=0),     # ~+500 today
        ]
        expected_today = trades[0].pnl + trades[2].pnl            # net, both today
        result = risk_guard.realized_pnl_today(trades)
        assert result == pytest.approx(expected_today)
        assert -600 < result < -450                               # excludes the -5,000

    def test_naive_exit_dates_are_taken_at_face_value(self):
        # A broker order history may hand back a naive timestamp.
        t = make_trade(-1, exit_delta=10, qty=100, days_ago=0)    # ~-1000 net
        t.exit_date = t.exit_date.replace(tzinfo=None)
        now = datetime.now(IST).replace(tzinfo=None)
        assert risk_guard.realized_pnl_today([t], now=now) == pytest.approx(t.pnl)
        assert t.pnl < -1000                                       # costs deepen the loss


class TestPositionsMtm:

    def test_long_and_short(self):
        positions = {
            "a": _pos("A", "BUY", entry=100, qty=10),    # ltp 90 → -100
            "b": _pos("B", "SELL", entry=100, qty=10),   # ltp 90 → +100
        }
        ltp = {"A": 90.0, "B": 90.0}
        assert risk_guard.positions_mtm(positions, ltp) == pytest.approx(0.0)

    def test_missing_quote_is_skipped(self):
        positions = {"a": _pos("A", "BUY", entry=100, qty=10)}
        assert risk_guard.positions_mtm(positions, {}) == 0.0


# ─── Trigger evaluation ───────────────────────────────────────────────────────

class TestEvaluateHaltTriggers:

    def test_clean_book_no_trigger(self):
        trades = [make_trade(1), make_trade(-1), make_trade(1)]
        reason = risk_guard.evaluate_halt_triggers(
            trades=trades, open_positions={}, capital=500_000,
            max_daily_loss_pct=0.05)
        assert reason is None

    def test_consecutive_losses_trip(self):
        trades = [make_trade(-1) for _ in range(3)]
        reason = risk_guard.evaluate_halt_triggers(
            trades=trades, open_positions={}, capital=500_000,
            max_daily_loss_pct=0.05)
        assert reason is not None
        assert "consecutive" in reason

    def test_daily_loss_realized_breach(self):
        # -6% of 500k = -30,000 realized today, limit is -25,000.
        trades = [make_trade(-1, exit_delta=300, qty=100, days_ago=0)]
        reason = risk_guard.evaluate_halt_triggers(
            trades=trades, open_positions={}, capital=500_000,
            max_daily_loss_pct=0.05)
        assert reason is not None
        assert "daily loss" in reason

    def test_daily_loss_ignores_prior_days(self):
        # Same big loss but it closed yesterday — must not count toward today.
        trades = [make_trade(-1, exit_delta=300, qty=100, days_ago=1)]
        reason = risk_guard.evaluate_halt_triggers(
            trades=trades, open_positions={}, capital=500_000,
            max_daily_loss_pct=0.05)
        assert reason is None

    def test_open_mtm_pushes_over_the_edge(self):
        # Realized -20,000 today (under the -25,000 limit on its own) plus a
        # bleeding open position at -10,000 MTM → -30,000 total → breach.
        trades = [make_trade(-1, exit_delta=200, qty=100, days_ago=0)]
        positions = {"x": _pos("XYZ", "BUY", entry=100, qty=1000)}  # ltp 90 → -10,000
        reason = risk_guard.evaluate_halt_triggers(
            trades=trades, open_positions=positions, capital=500_000,
            max_daily_loss_pct=0.05, ltp={"XYZ": 90.0})
        assert reason is not None
        assert "daily loss" in reason

    def test_realized_only_is_conservative_without_ltp(self):
        # Same inputs as above but no ltp → MTM omitted → realized alone
        # (-20,000) does not breach, so no halt. Proves MTM is optional and
        # realized-only never over-halts.
        trades = [make_trade(-1, exit_delta=200, qty=100, days_ago=0)]
        positions = {"x": _pos("XYZ", "BUY", entry=100, qty=1000)}
        reason = risk_guard.evaluate_halt_triggers(
            trades=trades, open_positions=positions, capital=500_000,
            max_daily_loss_pct=0.05, ltp=None)
        assert reason is None

    def test_zero_capital_does_not_divide_or_halt(self):
        trades = [make_trade(-1, exit_delta=200, qty=100, days_ago=0)]
        reason = risk_guard.evaluate_halt_triggers(
            trades=trades, open_positions={}, capital=0,
            max_daily_loss_pct=0.05)
        # consecutive is 1 (< 3) and capital 0 disables the % check.
        assert reason is None


# ─── Persistent halt flag ─────────────────────────────────────────────────────

class TestHaltFlag:

    def test_absent_by_default(self):
        assert risk_guard.is_halted() is False
        assert risk_guard.read_halt_reason() is None

    def test_set_then_read(self):
        risk_guard.set_halt("3 consecutive losing trades (limit 3)")
        assert risk_guard.is_halted() is True
        assert "consecutive" in risk_guard.read_halt_reason()

    def test_persists_across_restart(self):
        # "Restart" = the flag file survives; a fresh check still sees it.
        # (The path is module-level and file-backed — nothing in-process
        # holds the halt state, so re-reading == a new agent process.)
        risk_guard.set_halt("daily loss breached")
        assert risk_guard.HALT_FLAG_PATH.exists()

        # Simulate a restart's startup + a full poll tick's worth of guard
        # calls — none of them must clear the flag.
        risk_guard.entry_refusal_reason({}, max_open_positions=5)
        risk_guard.evaluate_halt_triggers(
            trades=[], open_positions={}, capital=500_000, max_daily_loss_pct=0.05)
        assert risk_guard.is_halted() is True

    def test_cleared_only_manually(self):
        risk_guard.set_halt("whatever")
        assert risk_guard.is_halted() is True
        risk_guard.clear_halt()
        assert risk_guard.is_halted() is False
        # Clearing an already-absent flag is a no-op, never raises.
        risk_guard.clear_halt()

    def test_present_but_empty_still_counts_as_halted(self):
        risk_guard.HALT_FLAG_PATH.parent.mkdir(parents=True, exist_ok=True)
        risk_guard.HALT_FLAG_PATH.write_text("")
        assert risk_guard.is_halted() is True
        assert risk_guard.read_halt_reason()  # non-empty fallback string


# ─── Entry gate ───────────────────────────────────────────────────────────────

class TestEntryRefusal:

    def test_allowed_when_clear(self):
        assert risk_guard.entry_refusal_reason({}, max_open_positions=5) is None

    def test_refused_when_halted(self):
        risk_guard.set_halt("daily loss breached")
        reason = risk_guard.entry_refusal_reason({}, max_open_positions=5)
        assert reason is not None and "halted" in reason

    def test_refused_at_position_cap(self):
        positions = {f"s{i}": _pos(f"S{i}") for i in range(5)}
        reason = risk_guard.entry_refusal_reason(positions, max_open_positions=5)
        assert reason is not None and "max open positions" in reason

    def test_cap_boundary_allows_below_limit(self):
        positions = {f"s{i}": _pos(f"S{i}") for i in range(4)}
        assert risk_guard.entry_refusal_reason(positions, max_open_positions=5) is None

    def test_halt_takes_precedence_over_cap(self):
        risk_guard.set_halt("daily loss breached")
        positions = {f"s{i}": _pos(f"S{i}") for i in range(5)}
        reason = risk_guard.entry_refusal_reason(positions, max_open_positions=5)
        assert "halted" in reason


# ─── Exits are still managed while halted ─────────────────────────────────────

class _FakeBroker:
    """Minimal broker for _manage_open_positions: the tracked position no
    longer shows at the broker (its SL_M stop filled), so the manage loop
    must record the close and remove it — even while halted."""

    def __init__(self, sl_order_id):
        self._sl_order_id = sl_order_id

    def get_positions(self):
        return []  # nothing open at the broker → the position closed

    def get_order_history(self):
        from core.brokers.base import OrderStatus
        return [SimpleNamespace(
            order_id=self._sl_order_id, symbol="RELIANCE",
            status=OrderStatus.EXECUTED, average_price=95.0,
            timestamp=datetime.now(timezone.utc),
        )]

    def get_ltp(self, symbols):
        return {s: 95.0 for s in symbols}


class TestExitsManagedWhileHalted:

    def test_close_is_recorded_even_when_halted(self, tmp_path, monkeypatch):
        import agent.main as main
        import agent.positions as positions
        from agent.positions import OpenPosition

        # Isolate all on-disk state.
        monkeypatch.setattr(positions, "OPEN_POSITIONS_PATH", tmp_path / "open.json")
        # Don't hit the network when reporting the close.
        reported = {}
        monkeypatch.setattr(main, "_report_outcome",
                            lambda *a, **k: reported.setdefault("called", True))

        # Halt is active — entries would be refused …
        risk_guard.set_halt("daily loss breached")
        assert risk_guard.entry_refusal_reason({}, max_open_positions=5) is not None

        # … but exit management still runs and closes the position.
        pos = OpenPosition(
            signal_id="SIG-1", symbol="RELIANCE", direction="BUY",
            quantity=100, entry_price=100.0,
            entry_date=datetime.now(timezone.utc).isoformat(),
            timeframe="15m", current_stop=95.0, sl_order_id="SL-1",
        )
        open_positions = {"SIG-1": pos}

        recorded = []
        sizer = SimpleNamespace(record_closed_trade=lambda t: recorded.append(t))

        main._manage_open_positions(
            _FakeBroker("SL-1"), "http://cloud", {}, sizer,
            open_positions, discovery_watchlist={})

        assert "SIG-1" not in open_positions          # position removed
        assert recorded and recorded[0].symbol == "RELIANCE"
        assert recorded[0].exit_price == 95.0
        assert reported.get("called") is True         # close reported to cloud
        assert risk_guard.is_halted() is True         # halt untouched by exits
