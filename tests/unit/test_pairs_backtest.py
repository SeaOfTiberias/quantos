"""
Pairs Trading — Walk-Forward Simulation Unit Tests

Covers core/pairs/backtest.py's pure window-scheduling and entry/exit logic
per docs/PAIRS_TRADING_METHODOLOGY.md's "Walk-forward schedule" and
"Entry / exit rules" sections.
"""

import math
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.pairs.backtest import (  # noqa: E402
    FuturesDay, formation_trading_windows, run_walk_forward, simulate_pair,
)
from core.pairs.cointegration import CointegrationResult  # noqa: E402

FAR_EXPIRY = date(2030, 1, 1)  # never triggers the force-close rule


def _pair(beta=0.0, mean=0.0, std=1.0):
    # beta=0 collapses z_t to just log(close_a) (since -beta*log(b) == 0 and
    # mean/std=0/1 leave it unscaled), which makes test scenarios easy to
    # construct by choosing close_a directly.
    return CointegrationResult(
        symbol_a="A", symbol_b="B", hedge_ratio=beta,
        spread_mean=mean, spread_std=std, adf_pvalue=0.01, n_obs=100,
    )


def _series(closes: list[float], start=date(2026, 1, 1), expiry=FAR_EXPIRY, lot_size=1) -> list[FuturesDay]:
    return [FuturesDay(start + timedelta(days=i), c, lot_size, expiry) for i, c in enumerate(closes)]


# ─── formation_trading_windows ──────────────────────────────────────────────

def test_formation_trading_windows_basic_schedule():
    windows = formation_trading_windows(date(2024, 1, 1), date(2024, 12, 31))
    assert windows[0] == (date(2024, 1, 1), date(2024, 7, 1), date(2024, 7, 1), date(2024, 10, 1))
    for w in windows:
        assert w[0] < w[1] <= w[2] < w[3]


def test_formation_trading_windows_steps_by_trading_months():
    windows = formation_trading_windows(date(2024, 1, 1), date(2025, 1, 1))
    assert windows[1][0] == date(2024, 4, 1)  # stepped forward by 3 months


def test_formation_trading_windows_empty_if_too_short():
    assert formation_trading_windows(date(2024, 1, 1), date(2024, 3, 1)) == []


# ─── simulate_pair: entry/exit rules ────────────────────────────────────────

def test_no_trade_when_z_never_crosses_threshold():
    pair = _pair()
    closes = [0.0, 0.5, -0.5, 1.0, -1.0]  # log(close_a) stays within [-2, 2]
    b_series = _series([1.0] * len(closes))
    a_series = _series([math.exp(c) for c in closes])
    trades = simulate_pair(pair, a_series, b_series)
    assert trades == []


def test_entry_and_mean_reversion_exit():
    pair = _pair()
    log_a = [0.0, 2.5, 1.0, -0.1, 0.0]  # crosses +2 on day 1, reverts through 0 on day 3
    a_series = _series([math.exp(c) for c in log_a])
    b_series = _series([1.0] * len(log_a))
    trades = simulate_pair(pair, a_series, b_series)
    assert len(trades) == 1
    t = trades[0]
    assert t.exit_reason == "mean_reversion"
    assert t.direction_a == "SELL"  # z > +2 -> short the A leg
    assert t.direction_b == "BUY"
    assert t.entry_date == date(2026, 1, 2)
    assert t.exit_date == date(2026, 1, 4)


def test_entry_negative_z_direction():
    pair = _pair()
    log_a = [0.0, -2.5, -1.0, 0.1, 0.0]
    a_series = _series([math.exp(c) for c in log_a])
    b_series = _series([1.0] * len(log_a))
    trades = simulate_pair(pair, a_series, b_series)
    assert len(trades) == 1
    assert trades[0].direction_a == "BUY"  # z < -2 -> long the A leg
    assert trades[0].direction_b == "SELL"


def test_max_hold_exit():
    pair = _pair()
    # Enters day 1 at z=2.5, then plateaus at z=1.5 (above 0, never reverts) for 25 days.
    log_a = [0.0, 2.5] + [1.5] * 25
    a_series = _series([math.exp(c) for c in log_a])
    b_series = _series([1.0] * len(log_a))
    trades = simulate_pair(pair, a_series, b_series)
    assert len(trades) == 1
    assert trades[0].exit_reason == "max_hold"


def test_forced_pre_expiry_exit():
    pair = _pair()
    near_expiry = date(2026, 1, 5)  # 3 calendar days after entry (day 1 = Jan 2)
    log_a = [0.0, 2.5, 1.5, 1.5, 1.5, 1.5, 1.5]
    a_series = _series([math.exp(c) for c in log_a], expiry=near_expiry)
    b_series = _series([1.0] * len(log_a), expiry=near_expiry)
    trades = simulate_pair(pair, a_series, b_series)
    assert len(trades) == 1
    assert trades[0].exit_reason == "forced_pre_expiry"


def test_no_overlapping_open_positions_but_reentry_after_exit_is_allowed():
    pair = _pair()
    # Enters day 1 (z=2.5), z never reverts (plateaus at 3.0) so the position
    # is force-closed by max_hold at hold_days==20, then immediately
    # re-qualifies (z is still > 2.0) and opens a SECOND, non-overlapping
    # trade the same rules would open for any fresh day. Two sequential
    # trades is correct: "one open position at a time" (never two
    # simultaneous positions) is a different rule from "no re-entry."
    log_a = [0.0, 2.5] + [3.0] * 25
    a_series = _series([math.exp(c) for c in log_a])
    b_series = _series([1.0] * len(log_a))
    trades = simulate_pair(pair, a_series, b_series)
    assert len(trades) == 2
    assert trades[0].exit_reason == "max_hold"
    assert trades[0].exit_date < trades[1].entry_date  # never overlapping


def test_net_pnl_is_gross_minus_cost():
    pair = _pair()
    log_a = [0.0, 2.5, 1.0, -0.1]
    a_series = _series([math.exp(c) for c in log_a], lot_size=100)
    b_series = _series([1.0] * len(log_a), lot_size=100)
    trades = simulate_pair(pair, a_series, b_series)
    t = trades[0]
    assert t.net_pnl == t.gross_pnl - t.cost
    assert t.cost > 0


# ─── run_walk_forward: smoke test end-to-end ────────────────────────────────

def test_run_walk_forward_smoke():
    import numpy as np
    rng = np.random.default_rng(42)
    n = 300
    log_b = np.cumsum(rng.normal(0, 0.01, n)) + 5.0
    log_a = 1.2 * log_b + rng.normal(0, 0.02, n)
    dates_ = [date(2024, 1, 1) + timedelta(days=i) for i in range(n)]
    price_data = {
        "A": [FuturesDay(d, float(math.exp(c)), 1, FAR_EXPIRY) for d, c in zip(dates_, log_a)],
        "B": [FuturesDay(d, float(math.exp(c)), 1, FAR_EXPIRY) for d, c in zip(dates_, log_b)],
    }
    candidates = [("A", "B", "test_sector")]
    folds = run_walk_forward(candidates, price_data, dates_[0], dates_[-1])
    assert len(folds) >= 1
    for fold in folds:
        assert fold.n_pairs_tested >= 0
        for t in fold.trades:
            assert t.symbol_a == "A"
            assert t.symbol_b == "B"
