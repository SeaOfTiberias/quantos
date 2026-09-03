"""
QuantOS — ORB condition-mining: split + pass-bar evaluation
──────────────────────────────────────────────────────────────
Implements docs/ORB_CONDITION_MINING_METHODOLOGY.md's mining/holdout split
and three-step pass bar, over the same `BacktestTrade`/`BacktestMetrics`
types every other candidate in this project is graded with
(core/backtest/parser.py) — no private metrics implementation here.

Nothing in this module looks at, or decides, a firing condition. It answers
one question per candidate condition: does restricting trades to
`predicate(conditions) is True` improve on the unconditional Stratified
baseline on BOTH the mining set and an untouched, later holdout set. That
is the entire contract; turning an `informative=True` verdict into an
actual gate is explicitly a separate, later, freshly pre-registered step
per the methodology doc.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Sequence

from core.backtest.parser import BacktestMetrics, BacktestTrade, _compute_metrics
from core.orb_scalping.conditions import TradeConditions

# Reuses core/backtest/parser.py's own `is_overfit_risk` threshold rather
# than inventing a new one — see the methodology doc's pass-bar section.
MIN_SAMPLE_SIZE = 30

Predicate = Callable[[TradeConditions], Optional[bool]]


@dataclass(frozen=True)
class ConditionedTrade:
    """One trade, paired with the condition values measured at its entry."""
    trade: BacktestTrade
    conditions: TradeConditions


@dataclass(frozen=True)
class ConditionVerdict:
    """The full evidence trail for one candidate condition, on one index —
    every field that went into the informative/not-informative call, not
    just the final bit, so a report can show its work."""
    name: str
    underlying: str
    mining_true_n: int
    mining_true_metrics: BacktestMetrics
    mining_baseline_metrics: BacktestMetrics
    holdout_true_n: int
    holdout_true_metrics: BacktestMetrics
    holdout_baseline_metrics: BacktestMetrics
    informative: bool
    reason: str


def time_based_split(
    trades: Sequence[ConditionedTrade], holdout_fraction: float = 0.2,
) -> tuple[list[ConditionedTrade], list[ConditionedTrade]]:
    """Chronological 80/20 split by entry_date — mining set is the earliest
    80%, holdout is the most recent 20%. Per the methodology doc, the
    cutoff is computed from whatever real trade dates are supplied, not
    fixed to a calendar date in advance; the 80/20 *fraction* is what's
    pinned. Call once per underlying — NIFTY and BankNifty never share a
    cutoff."""
    ordered = sorted(trades, key=lambda ct: ct.trade.entry_date)
    cutoff = int(round(len(ordered) * (1 - holdout_fraction)))
    return ordered[:cutoff], ordered[cutoff:]


def _subset(trades: Sequence[ConditionedTrade], predicate: Predicate) -> list[BacktestTrade]:
    return [ct.trade for ct in trades if predicate(ct.conditions) is True]


def evaluate_condition(
    name: str, underlying: str,
    mining: Sequence[ConditionedTrade], holdout: Sequence[ConditionedTrade],
    predicate: Predicate,
) -> ConditionVerdict:
    """The methodology doc's three-step pass bar, checked in order:
    1. minimum sample size (>=30) on BOTH the mining-true and holdout-true
       subsets;
    2. the mining-true subset clears `has_positive_edge` AND improves on
       the mining set's own unconditional baseline;
    3. the SAME condition, on the untouched holdout set, also clears
       `has_positive_edge` AND improves on the holdout's own baseline.

    A condition that cannot be evaluated on some trades (`predicate`
    returning None, e.g. an unclassified Weinstein stage) simply excludes
    those trades from the true/false split — it does not count against or
    for the condition either way.
    """
    mining_true = _subset(mining, predicate)
    holdout_true = _subset(holdout, predicate)
    mining_baseline = [ct.trade for ct in mining]
    holdout_baseline = [ct.trade for ct in holdout]

    mining_true_m = _compute_metrics(mining_true)
    holdout_true_m = _compute_metrics(holdout_true)
    mining_base_m = _compute_metrics(mining_baseline)
    holdout_base_m = _compute_metrics(holdout_baseline)

    def verdict(informative: bool, reason: str) -> ConditionVerdict:
        return ConditionVerdict(
            name=name, underlying=underlying,
            mining_true_n=len(mining_true), mining_true_metrics=mining_true_m,
            mining_baseline_metrics=mining_base_m,
            holdout_true_n=len(holdout_true), holdout_true_metrics=holdout_true_m,
            holdout_baseline_metrics=holdout_base_m,
            informative=informative, reason=reason,
        )

    if len(mining_true) < MIN_SAMPLE_SIZE or len(holdout_true) < MIN_SAMPLE_SIZE:
        return verdict(
            False,
            f"sample too small (mining n={len(mining_true)}, holdout n={len(holdout_true)}, "
            f"need >={MIN_SAMPLE_SIZE} each) — step 1 of 3",
        )

    mining_pass = (
        mining_true_m.has_positive_edge
        and mining_true_m.profit_factor > mining_base_m.profit_factor
        and mining_true_m.sharpe_ratio > mining_base_m.sharpe_ratio
    )
    if not mining_pass:
        return verdict(
            False,
            "did not clear has_positive_edge with a margin over the mining-set "
            "baseline — step 2 of 3",
        )

    holdout_pass = (
        holdout_true_m.has_positive_edge
        and holdout_true_m.profit_factor > holdout_base_m.profit_factor
        and holdout_true_m.sharpe_ratio > holdout_base_m.sharpe_ratio
    )
    if not holdout_pass:
        return verdict(
            False,
            "passed the mining set but the holdout set did not confirm it "
            "— step 3 of 3, this is the check that actually matters",
        )

    return verdict(
        True,
        "cleared sample size, mining-set improvement, and holdout confirmation",
    )
