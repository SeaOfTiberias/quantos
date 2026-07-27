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

def test_simulate_pair_uses_adj_close_for_z_when_present():
    """docs/PAIRS_TRADING_V2_METHODOLOGY.md Fix 2: the z-score signal must
    use adj_close, never raw close, when an adjusted series was built --
    even if raw close would have crossed the entry threshold, a flat
    adj_close must produce no trade."""
    pair = _pair()
    raw_start = date(2026, 1, 1)
    a_series = [
        FuturesDay(raw_start, math.exp(0.0), 1, FAR_EXPIRY, adj_close=math.exp(0.0)),
        FuturesDay(raw_start + timedelta(days=1), math.exp(9.0), 1, FAR_EXPIRY, adj_close=math.exp(0.1)),
        FuturesDay(raw_start + timedelta(days=2), math.exp(9.0), 1, FAR_EXPIRY, adj_close=math.exp(0.0)),
    ]
    b_series = _series([1.0, 1.0, 1.0])
    trades = simulate_pair(pair, a_series, b_series)
    assert trades == []  # raw close's log=9.0 would have entered; adj_close never left [-2,2]


def test_simulate_pair_fills_at_raw_close_never_adjusted_close():
    """Even with an adjusted series driving the signal, actual fill prices
    (used for P&L/cost) must always be the raw close."""
    pair = _pair()
    raw_start = date(2026, 1, 1)
    a_series = [
        FuturesDay(raw_start, math.exp(0.0), 1, FAR_EXPIRY, adj_close=math.exp(0.0)),
        FuturesDay(raw_start + timedelta(days=1), 55.0, 1, FAR_EXPIRY, adj_close=math.exp(2.5)),
        FuturesDay(raw_start + timedelta(days=2), 60.0, 1, FAR_EXPIRY, adj_close=math.exp(0.0)),
    ]
    b_series = _series([1.0, 1.0, 1.0])
    trades = simulate_pair(pair, a_series, b_series)
    assert len(trades) == 1
    assert trades[0].entry_price_a == 55.0  # raw, not exp(2.5)
    assert trades[0].exit_price_a == 60.0


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


def test_run_walk_forward_excludes_pair_with_corporate_action_jump():
    """docs/PAIRS_TRADING_V2_METHODOLOGY.md Fix 1: a symbol with a >2x (or
    <0.5x) day-to-day RAW close jump in the formation window must exclude
    the whole pair from that fold, reflected in n_pairs_excluded_corp_action,
    never silently feeding a corrupted hedge-ratio estimate."""
    import numpy as np
    rng = np.random.default_rng(3)
    n = 300
    log_base = np.cumsum(rng.normal(0, 0.01, n)) + 5.0
    log_a = log_base + rng.normal(0, 0.005, n)
    log_b = log_base + rng.normal(0, 0.005, n)
    dates_ = [date(2024, 1, 1) + timedelta(days=i) for i in range(n)]

    closes_a = [float(math.exp(c)) for c in log_a]
    closes_a[50] = closes_a[49] * 5.0   # unadjusted 5x jump -- suspected corp action

    price_data = {
        "A": [FuturesDay(d, c, 1, FAR_EXPIRY) for d, c in zip(dates_, closes_a)],
        "B": [FuturesDay(d, float(math.exp(c)), 1, FAR_EXPIRY) for d, c in zip(dates_, log_b)],
    }
    candidates = [("A", "B", "s")]
    folds = run_walk_forward(candidates, price_data, dates_[0], dates_[-1])
    assert folds[0].n_pairs_excluded_corp_action == 1
    assert folds[0].n_pairs_tested == 0
    assert folds[0].trades == []


def test_run_walk_forward_clean_pair_not_excluded():
    import numpy as np
    rng = np.random.default_rng(3)
    n = 300
    log_base = np.cumsum(rng.normal(0, 0.01, n)) + 5.0
    log_a = log_base + rng.normal(0, 0.005, n)
    log_b = log_base + rng.normal(0, 0.005, n)
    dates_ = [date(2024, 1, 1) + timedelta(days=i) for i in range(n)]

    price_data = {
        "A": [FuturesDay(d, float(math.exp(c)), 1, FAR_EXPIRY) for d, c in zip(dates_, log_a)],
        "B": [FuturesDay(d, float(math.exp(c)), 1, FAR_EXPIRY) for d, c in zip(dates_, log_b)],
    }
    candidates = [("A", "B", "s")]
    folds = run_walk_forward(candidates, price_data, dates_[0], dates_[-1])
    assert folds[0].n_pairs_excluded_corp_action == 0


def test_run_walk_forward_uses_adj_close_for_cointegration():
    """A pair whose RAW close has an artificial roll-style seam mid-formation
    but whose adj_close is smooth/cointegrated must still pass -- proves the
    cointegration extraction reads adj_close, not raw close."""
    import numpy as np
    rng = np.random.default_rng(11)
    n = 300
    log_base = np.cumsum(rng.normal(0, 0.005, n)) + 5.0
    log_a = log_base + rng.normal(0, 0.002, n)
    log_b = log_base + rng.normal(0, 0.002, n)
    dates_ = [date(2024, 1, 1) + timedelta(days=i) for i in range(n)]

    raw_a = [float(math.exp(c)) for c in log_a]
    adj_a = list(raw_a)
    raw_a[80] *= 1.3   # a seam distortion in RAW only -- moderate, won't trip the corp-action guard

    price_data = {
        "A": [FuturesDay(d, raw_a[i], 1, FAR_EXPIRY, adj_close=adj_a[i])
              for i, d in enumerate(dates_)],
        "B": [FuturesDay(d, float(math.exp(c)), 1, FAR_EXPIRY, adj_close=float(math.exp(c)))
              for d, c in zip(dates_, log_b)],
    }
    candidates = [("A", "B", "s")]
    folds = run_walk_forward(candidates, price_data, dates_[0], dates_[-1])
    # With clean adj_close feeding cointegration, A/B (built from the same
    # log_base) should test/pass same as the clean-series smoke test.
    assert folds[0].n_pairs_tested == 1
    assert folds[0].n_pairs_passed == 1


def test_run_walk_forward_shared_symbol_across_pairs_with_different_coverage():
    """Regression test: a real bug had run_walk_forward cache each pair's
    date-aligned closes in a dict keyed by SYMBOL, so when symbol "A"
    appeared in two candidate pairs (A/B and A/C) with different date
    coverage, the second pair's alignment silently clobbered the first's,
    feeding cointegration.test_pair mismatched-length series and crashing
    with "unaligned series" on real bhavcopy data. A has full coverage; B
    has full coverage; C only has data for HALF the window (simulating a
    stock that started trading futures partway through) -- A/C's alignment
    must not corrupt A/B's."""
    import numpy as np
    rng = np.random.default_rng(7)
    n = 300  # >= ~9 months of calendar days -- enough for one formation+trading fold
    log_base = np.cumsum(rng.normal(0, 0.01, n)) + 5.0
    log_a = log_base + rng.normal(0, 0.005, n)
    log_b = log_base + rng.normal(0, 0.005, n)
    log_c = log_base + rng.normal(0, 0.005, n)
    dates_ = [date(2024, 1, 1) + timedelta(days=i) for i in range(n)]

    price_data = {
        "A": [FuturesDay(d, float(math.exp(c)), 1, FAR_EXPIRY) for d, c in zip(dates_, log_a)],
        "B": [FuturesDay(d, float(math.exp(c)), 1, FAR_EXPIRY) for d, c in zip(dates_, log_b)],
        # C only has the SECOND HALF of the window -- deliberately different
        # coverage from A/B's full-window alignment.
        "C": [FuturesDay(d, float(math.exp(c)), 1, FAR_EXPIRY)
              for d, c in zip(dates_[n // 2:], log_c[n // 2:])],
    }
    candidates = [("A", "B", "s"), ("A", "C", "s")]
    # Must not raise -- this is the exact crash the bug produced.
    folds = run_walk_forward(candidates, price_data, dates_[0], dates_[-1])
    assert len(folds) >= 1
