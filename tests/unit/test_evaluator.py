"""core/backtest/evaluator.py -- Stage 1 metrics and the Stage 2 quarter-Kelly NAV."""

from datetime import date, timedelta

from core.backtest.evaluator import (
    EvalTrade, Gates, daily_book, kelly, profit_factor, sharpe, stage1, stage2,
)

D0 = date(2024, 1, 1)


def day(n):
    return D0 + timedelta(days=n)


def trade(n, ret, hold=2, margin=10_000.0, first=-0.01):
    """Entry on day n with entry costs `first`, then straight to `ret` at exit."""
    return EvalTrade(day(n), day(n + hold), margin, {day(n): first, day(n + hold): ret}, f"t{n}")


CAL = [day(i) for i in range(400)]


def test_profit_factor_and_kelly():
    assert profit_factor([0.2, 0.2, -0.1]) == 4.0
    assert kelly([0.1, 0.1, -0.1, -0.1]) == 0.0                       # W 0.5, R 1
    assert abs(kelly([0.3, 0.3, -0.1, -0.1]) - (0.5 - 0.5 / 3)) < 1e-12
    assert kelly([]) is None and kelly([-0.1]) == 0.0


def test_daily_book_and_sharpe():
    book = daily_book([trade(0, 0.05)], CAL[:4])
    assert [round(x, 6) for x in book] == [-0.01, 0.0, 0.06, 0.0]
    assert sharpe([0.0, 0.0]) != sharpe([0.0, 0.0])                    # NaN on zero variance


def test_stage1_gates():
    trades = [trade(i * 3, 0.10 if i % 3 else -0.05) for i in range(120)]
    s = stage1(trades, CAL, split=day(180), gates=Gates(min_trades=100))
    assert s.n == 120 and round(s.win, 3) == 0.667 and s.pf > 3
    assert s.checks["PF > 1 in each half"] and s.checks["n >= 100"]
    bad = stage1([trade(i * 3, -0.05 if i % 3 else 0.10) for i in range(120)], CAL, split=day(180))
    assert not bad.passed


def test_stage2_warmup_lockout_and_growth():
    trades = [trade(i * 3, 0.10 if i % 3 else -0.05) for i in range(120)]
    s = stage2(trades, CAL, 1_000_000.0)
    assert s.warmup > 0 and s.taken > 0 and s.lockouts == 0 and s.end > s.start
    small = stage2([trade(i * 3, 0.10 if i % 3 else -0.05, margin=500_000.0) for i in range(120)], CAL, 100_000.0)
    assert small.lockouts > 0 and not small.passed                  # one lot costs more than a quarter-Kelly slice


def test_stage2_kill_switch_closes_and_skips_next_session():
    good = [trade(i, 0.10, hold=1, first=0.0) for i in range(0, 90, 3)]    # 30 warm-up wins
    crash = EvalTrade(day(100), day(110), 100_000.0, {day(100): 0.0, day(101): -0.9, day(110): -0.9}, "crash")
    nxt = trade(102, 0.10, hold=1, first=0.0)
    s = stage2(good + [crash, nxt], CAL, 1_000_000.0)
    assert s.kills == 1
    assert s.taken == 1                                              # the crash trade; the next-session entry skipped
