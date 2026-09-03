"""
ORB condition-mining — split + pass-bar Unit Tests

Covers core/orb_scalping/condition_mining.py per
docs/ORB_CONDITION_MINING_METHODOLOGY.md's mining/holdout split and
three-step pass bar. Synthetic BacktestTrade/TradeConditions fixtures only
— no real market data, no live token needed.
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.backtest.parser import BacktestTrade  # noqa: E402
from core.orb_scalping.conditions import TradeConditions  # noqa: E402
from core.orb_scalping.condition_mining import (  # noqa: E402
    MIN_SAMPLE_SIZE,
    ConditionedTrade,
    evaluate_condition,
    time_based_split,
)
from core.vault.models import Stage  # noqa: E402

_BASE = date(2022, 1, 3)


def _dt(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, 4, 0, tzinfo=timezone.utc)


def trade(entry_offset_days: int, net_profit_pct: float) -> BacktestTrade:
    """One BacktestTrade whose gross figures ARE the net figures (costs=0)
    — sufficient for these tests, which only exercise the split/pass-bar
    logic on top of already-computed per-trade returns."""
    d = _BASE + timedelta(days=entry_offset_days)
    return BacktestTrade(
        trade_num=entry_offset_days, direction="Long", qty=1,
        entry_date=_dt(d), entry_price=100.0,
        exit_date=_dt(d) + timedelta(hours=2), exit_price=100.0 + net_profit_pct,
        profit=net_profit_pct, profit_pct=net_profit_pct,
        cum_profit=0.0, bars_held=4, costs=0.0,
    )


def conditions(entry_offset_days: int, stage: Stage | None = None) -> TradeConditions:
    d = _BASE + timedelta(days=entry_offset_days)
    return TradeConditions(
        entry_date=d, stage=stage, day_of_week=d.strftime("%A"),
        range_width_ratio=1.0, gap_pct=0.0, days_to_expiry=5,
        dte_bucket="5-9", exit_reason="trailing_stop",
    )


def conditioned(entry_offset_days: int, net_profit_pct: float, stage: Stage | None = None) -> ConditionedTrade:
    return ConditionedTrade(
        trade=trade(entry_offset_days, net_profit_pct),
        conditions=conditions(entry_offset_days, stage=stage),
    )


def is_stage2(c: TradeConditions) -> bool | None:
    if c.stage is None:
        return None
    return c.stage is Stage.ADVANCING


# Non-constant return patterns -- BacktestMetrics' Sharpe is 0 for a
# zero-variance sample (see core/backtest/parser.py::_sharpe_ratio), so a
# realistic fixture needs both wins and losses, not one repeated value.
# WINNING: mean +2.0%, PF 7.0, Sharpe well above 0.5. LOSING: the mirror
# image, mean -2.0%, PF 0.15, Sharpe well below 0.5.
WINNING_PATTERN = [4.0, 1.0, 6.0, -1.0, 3.0, -1.0]
LOSING_PATTERN = [-4.0, -1.0, -6.0, 1.0, -3.0, 1.0]


def group(start_offset: int, pattern: list[float], n: int, stage: Optional[Stage]) -> list[ConditionedTrade]:
    return [
        conditioned(start_offset + i, pattern[i % len(pattern)], stage=stage)
        for i in range(n)
    ]


# ─── time_based_split ────────────────────────────────────────────────────

def test_time_based_split_is_chronological_80_20():
    trades = [conditioned(i, 1.0) for i in range(100)]
    mining, holdout = time_based_split(trades)
    assert len(mining) == 80
    assert len(holdout) == 20
    assert max(ct.trade.entry_date for ct in mining) < min(ct.trade.entry_date for ct in holdout)


def test_time_based_split_ignores_input_order():
    trades = [conditioned(i, 1.0) for i in range(50)]
    shuffled = list(reversed(trades))
    mining_a, holdout_a = time_based_split(trades)
    mining_b, holdout_b = time_based_split(shuffled)
    assert [ct.trade.trade_num for ct in mining_a] == [ct.trade.trade_num for ct in mining_b]
    assert [ct.trade.trade_num for ct in holdout_a] == [ct.trade.trade_num for ct in holdout_b]


# ─── evaluate_condition: sample size gate ────────────────────────────────

def test_too_few_condition_true_trades_is_not_informative():
    # Only 5 Stage-2 trades in each half — below MIN_SAMPLE_SIZE.
    mining = [conditioned(i, 5.0, stage=Stage.ADVANCING) for i in range(5)]
    mining += [conditioned(i, -5.0, stage=Stage.DECLINING) for i in range(5, 60)]
    holdout = [conditioned(i, 5.0, stage=Stage.ADVANCING) for i in range(60, 65)]
    holdout += [conditioned(i, -5.0, stage=Stage.DECLINING) for i in range(65, 90)]

    v = evaluate_condition("stage2", "NIFTY", mining, holdout, is_stage2)
    assert not v.informative
    assert "sample too small" in v.reason
    assert v.mining_true_n == 5


# ─── evaluate_condition: mining-set improvement gate ─────────────────────

def test_condition_that_does_not_beat_mining_baseline_is_not_informative():
    # Stage-2 trades UNDERPERFORM the rest -- the condition actively hurts,
    # a clean way to fail "beats its own baseline" deterministically.
    mining = group(0, LOSING_PATTERN, 40, Stage.ADVANCING)
    mining += group(40, WINNING_PATTERN, 40, Stage.DECLINING)
    holdout = group(80, LOSING_PATTERN, 30, Stage.ADVANCING)
    holdout += group(110, WINNING_PATTERN, 30, Stage.DECLINING)

    v = evaluate_condition("stage2", "NIFTY", mining, holdout, is_stage2)
    assert v.mining_true_n >= MIN_SAMPLE_SIZE
    assert not v.informative
    assert "step 2" in v.reason


# ─── evaluate_condition: holdout confirmation gate ───────────────────────

def test_mining_set_win_that_fails_holdout_is_not_informative():
    # Mining set: Stage 2 wins, Stage 4 loses -- clears step 2 easily.
    mining = group(0, WINNING_PATTERN, 40, Stage.ADVANCING)
    mining += group(40, LOSING_PATTERN, 40, Stage.DECLINING)

    # Holdout: the SAME condition now loses -- a mining-set fluke.
    holdout = group(80, LOSING_PATTERN, 30, Stage.ADVANCING)
    holdout += group(110, WINNING_PATTERN, 30, Stage.DECLINING)

    v = evaluate_condition("stage2", "NIFTY", mining, holdout, is_stage2)
    assert v.mining_true_metrics.has_positive_edge
    assert not v.informative
    assert "step 3" in v.reason


# ─── evaluate_condition: real pass ───────────────────────────────────────

def test_condition_confirmed_on_both_sets_is_informative():
    # Stage 2 wins on BOTH mining and holdout; Stage 4 loses on both.
    mining = group(0, WINNING_PATTERN, 40, Stage.ADVANCING)
    mining += group(40, LOSING_PATTERN, 40, Stage.DECLINING)
    holdout = group(80, WINNING_PATTERN, 30, Stage.ADVANCING)
    holdout += group(110, LOSING_PATTERN, 30, Stage.DECLINING)

    v = evaluate_condition("stage2", "NIFTY", mining, holdout, is_stage2)
    assert v.informative
    assert v.reason.startswith("cleared")
    assert v.mining_true_n == 40
    assert v.holdout_true_n == 30


def test_unclassified_trades_are_excluded_not_counted_against():
    # stage=None (unclassified) trades must not land in the "true" subset.
    mining = [conditioned(i, 5.0, stage=Stage.ADVANCING) for i in range(40)]
    mining += [conditioned(40 + i, 1.0, stage=None) for i in range(20)]  # unclassified
    mining += [conditioned(60 + i, -5.0, stage=Stage.DECLINING) for i in range(20)]
    holdout = [conditioned(80 + i, 5.0, stage=Stage.ADVANCING) for i in range(30)]
    holdout += [conditioned(110 + i, -5.0, stage=Stage.DECLINING) for i in range(30)]

    v = evaluate_condition("stage2", "NIFTY", mining, holdout, is_stage2)
    assert v.mining_true_n == 40  # the 20 unclassified never enter true or false
    assert v.mining_baseline_metrics.total_trades == 80  # but stay in the baseline
