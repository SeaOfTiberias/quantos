"""
agent/paper_rotation_positions.py — JSON persistence for the momentum
turnover walk-forward's virtual ledger (candidate 11 OOS confirmation),
separate from agent/rotation_positions.py's REAL S8-3 rotation holdings.
"""

import pytest

from agent import paper_rotation_positions as prp


@pytest.fixture(autouse=True)
def _isolated_state_path(tmp_path, monkeypatch):
    monkeypatch.setattr(prp, "PAPER_WALKFORWARD_STATE_PATH", tmp_path / "paper_walkforward.json")


class TestLoadState:

    def test_missing_file_starts_fresh_ledger_at_initial_capital(self):
        state = prp.load_state(1_000_000.0)
        assert state.initial_capital == 1_000_000.0
        assert state.cash == 1_000_000.0
        assert state.positions == {}
        assert state.closed_trades == []
        assert state.equity_curve == []
        assert state.last_rebalanced_quarter_end is None

    def test_corrupt_file_starts_fresh_ledger(self):
        prp.PAPER_WALKFORWARD_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        prp.PAPER_WALKFORWARD_STATE_PATH.write_text("not json")
        state = prp.load_state(1_000_000.0)
        assert state.cash == 1_000_000.0


class TestSaveAndReload:

    def test_full_roundtrip(self):
        state = prp.load_state(1_000_000.0)
        state.cash = 950_000.0
        state.positions["A"] = prp.PaperPosition(
            symbol="A", quantity=100, entry_price=500.0, entry_date="2026-09-30")
        state.closed_trades.append(prp.PaperTrade(
            symbol="B", entry_date="2026-06-30", entry_price=200.0,
            exit_date="2026-09-30", exit_price=220.0, quantity=50,
            exit_reason="rank_dropout", cost=45.5))
        state.equity_curve.append(prp.EquityPoint(date="2026-09-30", equity=999_500.0))
        state.last_rebalanced_quarter_end = "2026-09-30"
        prp.save_state(state)

        reloaded = prp.load_state(1_000_000.0)
        assert reloaded.cash == 950_000.0
        assert reloaded.positions["A"].quantity == 100
        assert reloaded.closed_trades[0].symbol == "B"
        assert reloaded.closed_trades[0].cost == 45.5
        assert reloaded.equity_curve[0].equity == 999_500.0
        assert reloaded.last_rebalanced_quarter_end == "2026-09-30"

    def test_reload_ignores_the_initial_capital_argument_once_a_file_exists(self):
        state = prp.load_state(1_000_000.0)
        prp.save_state(state)
        reloaded = prp.load_state(9_999.0)   # different arg -- stored value must win
        assert reloaded.initial_capital == 1_000_000.0
