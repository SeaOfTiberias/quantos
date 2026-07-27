"""
QuantOS — Momentum Turnover Walk-Forward: paper (no real capital) quarterly executor
──────────────────────────────────────────────────────────────────────────────────
docs/MOMENTUM_TURNOVER_WALKFORWARD_METHODOLOGY.md, pre-committed 2026-07-27.
This is candidate 11's out-of-sample confirmation run for
docs/MOMENTUM_TURNOVER_ABLATION_METHODOLOGY.md's in-sample finding —
NOT a new strategy. Reuses core/rotation/ranker.py's rank_universe()
UNCHANGED (same function S8-3's real rotation and the in-sample ablation
both use), same DELIVERY_COST_MODEL-shaped cost accounting via
core/risk/costs.py's CostModel.cost_of(), same ₹1,000,000 capital /
₹50,000-per-position sizing as the ablation's control. Only the rebalance
cadence (quarterly) and the fact that this accumulates real, live,
never-backtested prices one quarter at a time differ from the in-sample
ablation.

Never calls broker.place_order() — reads history only via the same
fetch_chunked_daily() helper core/rotation/executor.py's live weekly
rotation already uses, to price a purely virtual fill. All state lives in
agent/paper_rotation_positions.py's PAPER_WALKFORWARD_STATE_PATH, entirely
separate from the real S8-3 rotation's agent/rotation_positions.py — there
is no code path from this module to a real order or real funds.

Designed to be called once a day by a daily-firing caller (self-healing
gate, see is_eligible_to_rebalance) rather than relying on hitting one
exact calendar day — see the methodology doc's "self-healing daily gate"
section for why.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from agent.paper_rotation_positions import (
    EquityPoint, PaperPosition, PaperTrade, PaperWalkforwardState, load_state, save_state,
)
from core.brokers.base import BrokerAdapter
from core.risk.costs import CostModel
from core.rotation.executor import _size_new_entrants
from core.rotation.ranker import (
    LOOKBACK_DAYS, TOP_N, SymbolSeries, build_symbol_series, diff_target_basket,
    rank_universe, value_as_of,
)

logger = logging.getLogger("quantos.rotation.paper_walkforward")

# Pre-committed in the methodology doc — identical to the in-sample
# ablation's control, so the eventual OOS Sharpe/CAGR are directly
# comparable, not a different-scale run needing re-normalizing. Do not
# change once the walk-forward has started.
INITIAL_CAPITAL = 1_000_000.0
POSITION_SIZE = 50_000.0

FETCH_WINDOW_DAYS = 400   # mirrors core/rotation/executor.py's own margin


# ─── Quarter-boundary gate ────────────────────────────────────────────────────

def _quarter_end(year: int, quarter: int) -> date:
    month = quarter * 3
    if month == 12:
        return date(year, 12, 31)
    return date(year, month + 1, 1) - timedelta(days=1)


def most_recent_quarter_end(as_of: datetime) -> date:
    """The calendar quarter-end date on or most recently before as_of's
    own date. E.g. as_of=2027-01-03 -> 2026-12-31 (Q4 2026's end, not Q1
    2027's, which hasn't happened yet) — this is what lets the gate below
    self-heal across any gap (weekend, holiday, VM downtime spanning the
    exact boundary) without ever silently skipping a quarter forward."""
    q = (as_of.month - 1) // 3 + 1
    q_end = _quarter_end(as_of.year, q)
    if as_of.date() >= q_end:
        return q_end
    if q == 1:
        return _quarter_end(as_of.year - 1, 4)
    return _quarter_end(as_of.year, q - 1)


def is_eligible_to_rebalance(as_of: datetime, last_rebalanced_quarter_end: Optional[str]) -> bool:
    """True once as_of has reached the most recently closed calendar
    quarter boundary AND that boundary hasn't already been recorded as
    rebalanced. Safe to call once a day — idempotent by construction, and
    self-heals across missed days by always targeting the most recently
    closed boundary rather than "today happens to be exactly quarter-end"."""
    boundary = most_recent_quarter_end(as_of).isoformat()
    return last_rebalanced_quarter_end != boundary


# ─── Fetch + fill helpers (mirror core/rotation/executor.py) ─────────────────

async def _fetch_universe_series(broker: BrokerAdapter, universe: list[str],
                                  sem: asyncio.Semaphore) -> dict[str, SymbolSeries]:
    from scripts.validate_regime_classifier import fetch_chunked_daily

    to_date = datetime.now(timezone.utc)
    from_date = to_date - timedelta(days=FETCH_WINDOW_DAYS)

    symbol_series = {}
    for symbol in universe:
        candles = await fetch_chunked_daily(broker, symbol, from_date, to_date, sem)
        if len(candles) >= LOOKBACK_DAYS:
            symbol_series[symbol] = build_symbol_series(candles)
    return symbol_series


def _latest_price(symbol_series: dict, symbol: str, as_of: datetime) -> Optional[float]:
    series = symbol_series.get(symbol)
    if series is None:
        return None
    v = value_as_of(series, as_of)
    return v[0] if v else None


@dataclass
class PaperRebalanceResult:
    quarter_end:  str
    buys:         list[dict] = field(default_factory=list)
    sells:        list[dict] = field(default_factory=list)
    skipped_buys: list[dict] = field(default_factory=list)
    equity_after: float = 0.0


async def run_quarterly_paper_rebalance(
    broker: BrokerAdapter,
    universe: list[str],
    *,
    top_n: int = TOP_N,
    position_size: float = POSITION_SIZE,
    cost_model: CostModel,
    now: Optional[datetime] = None,
) -> Optional[PaperRebalanceResult]:
    """Runs at most one quarterly paper rebalance. Returns None (no-op) if
    today hasn't reached the next quarter boundary yet, or that boundary
    was already rebalanced — safe and cheap to call every day from a
    daily-firing caller. Returns a PaperRebalanceResult once it actually
    rebalances."""
    as_of = now or datetime.now(timezone.utc)
    state = load_state(INITIAL_CAPITAL)

    if not is_eligible_to_rebalance(as_of, state.last_rebalanced_quarter_end):
        return None

    boundary = most_recent_quarter_end(as_of).isoformat()
    logger.info("Paper walk-forward: quarter boundary %s reached, rebalancing "
                "over %d universe symbols", boundary, len(universe))

    sem = asyncio.Semaphore(2)
    symbol_series = await _fetch_universe_series(broker, universe, sem)
    logger.info("Paper walk-forward: %d/%d universe symbols have enough history "
                "to be ranked", len(symbol_series), len(universe))

    target_basket = rank_universe(symbol_series, as_of, top_n)
    plan = diff_target_basket(state.positions.keys(), target_basket)
    result = PaperRebalanceResult(quarter_end=boundary)

    # Sells first (rank drop-outs) — matches core/rotation/equity_curve.py's
    # simulate_portfolio ordering and its exact cost convention: round-trip
    # cost booked entirely at exit via cost_model.cost_of(entry, exit, qty, "BUY").
    for symbol in plan.sells:
        pos = state.positions.get(symbol)
        if pos is None:
            continue
        price = _latest_price(symbol_series, symbol, as_of)
        if price is None:
            logger.warning("Paper walk-forward: no live price for %s to close "
                            "rank-dropout position — carrying at entry price", symbol)
            price = pos.entry_price
        cost = cost_model.cost_of(pos.entry_price, price, pos.quantity, "BUY")
        state.cash += price * pos.quantity - cost
        state.closed_trades.append(PaperTrade(
            symbol=symbol, entry_date=pos.entry_date, entry_price=pos.entry_price,
            exit_date=as_of.date().isoformat(), exit_price=price, quantity=pos.quantity,
            exit_reason="rank_dropout", cost=round(cost, 2),
        ))
        del state.positions[symbol]
        result.sells.append({"symbol": symbol, "quantity": pos.quantity,
                              "entry_price": pos.entry_price, "exit_price": price})

    # Buys (new entrants) — sized against the walk-forward's OWN virtual
    # cash, never real broker funds. Same sequential rank-order sizing
    # S8-3's real rotation and every backtest in this project share
    # (core/rotation/executor.py's _size_new_entrants), so paper sizing
    # can't silently diverge from what live/backtest sizing would do.
    price_lookup = {s: _latest_price(symbol_series, s, as_of) for s in plan.buys}
    sized, skipped = _size_new_entrants(plan.buys, price_lookup, state.cash, position_size)
    result.skipped_buys.extend(skipped)

    for symbol, qty in sized.items():
        price = price_lookup[symbol]
        state.cash -= price * qty
        state.positions[symbol] = PaperPosition(
            symbol=symbol, quantity=qty, entry_price=price,
            entry_date=as_of.date().isoformat(),
        )
        result.buys.append({"symbol": symbol, "quantity": qty, "price": price})

    holdings_value = sum(
        (_latest_price(symbol_series, s, as_of) or p.entry_price) * p.quantity
        for s, p in state.positions.items()
    )
    equity = state.cash + holdings_value
    state.equity_curve.append(EquityPoint(date=as_of.date().isoformat(), equity=round(equity, 2)))
    state.last_rebalanced_quarter_end = boundary
    save_state(state)

    result.equity_after = round(equity, 2)
    logger.info("Paper walk-forward: quarter %s done — %d buys, %d sells, %d skipped, "
                "equity now Rs%.0f (started Rs%.0f)",
                boundary, len(result.buys), len(result.sells), len(result.skipped_buys),
                equity, state.initial_capital)
    return result
