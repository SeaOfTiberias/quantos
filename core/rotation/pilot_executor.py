"""
QuantOS — Momentum Turnover Real-Capital Pilot: quarterly executor
────────────────────────────────────────────────────────────────────────────
Real-money counterpart to core/rotation/paper_executor.py's paper walk-forward
— runs ALONGSIDE it, does not replace it. The paper ledger still owns the
strategy's OOS verdict (needs 4 completed quarters, no verdict before then).
This pilot's sole purpose is to generate real trade-level data (fills,
slippage, closed trades) that nothing in the project has ever produced —
Kelly-criterion sizing (core/risk/kelly.py) has been wired into the live
agent since an earlier sprint but has never seen a single real closed trade.

Deliberately small and bounded (see agent/config.yaml's rotation_pilot
block): position_size ~Rs2,500 vs the strategy's design Rs50,000, sized off
the account's existing idle balance, with a hard stop-loss on the PILOT's
own cumulative realized P&L (not a bet the strategy is profitable at scale
— the paper walk-forward still owns that question).

Reuses, rather than reimplements:
  - core/rotation/paper_executor.py's most_recent_quarter_end /
    is_eligible_to_rebalance (the exact same quarter-boundary gate).
  - core/rotation/ranker.py's rank_universe / diff_target_basket /
    build_symbol_series / value_as_of (identical to S8-3 and the paper
    walk-forward — ranking behaviour can never silently diverge between
    the three).
  - core/rotation/executor.py's _size_new_entrants (sequential rank-order,
    capital-capped sizing) and _poll_fill_price.
  - agent/risk_guard.py's read_halt_reason() — the GLOBAL kill switch also
    gates this pilot's buys, on top of the pilot's own stop-loss below.

dry_run defaults True — same rollout discipline every other real-order
executor in this codebase uses (core/rotation/executor.py, S8-3's own
launch): flip to False only after watching a live-data dry run.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from agent import risk_guard
from agent.rotation_pilot_positions import (
    PilotPosition, PilotState, load_state, save_state,
)
from core.brokers.base import BrokerAdapter, Order, OrderDirection, OrderType, ProductType
from core.risk.kelly import ClosedTrade
from core.risk.trade_history import TradeHistoryService
from core.rotation.executor import ORDER_PLACEMENT_DELAY_SECONDS, _poll_fill_price, _size_new_entrants
from core.rotation.paper_executor import is_eligible_to_rebalance, most_recent_quarter_end
from core.rotation.ranker import (
    LOOKBACK_DAYS, TOP_N, SymbolSeries, build_symbol_series, diff_target_basket,
    rank_universe, value_as_of,
)

logger = logging.getLogger("quantos.rotation.pilot")

FETCH_WINDOW_DAYS = 400   # mirrors executor.py / paper_executor.py's own margin


def pilot_halt_reason(realized_pnl: float, capital_reference: float, max_loss_pct: float) -> Optional[str]:
    """Pilot-scoped stop-loss check — cumulative REALIZED pilot P&L only
    (not the whole broker account's, which may hold unrelated positions).
    Trips once realized_pnl <= -(max_loss_pct * capital_reference).

    No separate persisted halt flag: a tripped pilot places no more buys,
    so realized_pnl can't recover on its own — this check stays tripped on
    every subsequent quarter through the same state file, without needing
    a second file to keep in sync."""
    if capital_reference <= 0:
        return None
    loss_limit = max_loss_pct * capital_reference
    if realized_pnl <= -loss_limit:
        return (f"pilot realized loss {realized_pnl:,.2f} breached limit "
                f"-{loss_limit:,.2f} ({max_loss_pct:.1%} of {capital_reference:,.2f})")
    return None


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
class PilotRebalanceResult:
    quarter_end:  str
    buys:         list[dict] = field(default_factory=list)
    sells:        list[dict] = field(default_factory=list)
    skipped_buys: list[dict] = field(default_factory=list)
    realized_pnl: float = 0.0
    dry_run:      bool = True


async def run_quarterly_pilot_rebalance(
    broker: BrokerAdapter,
    universe: list[str],
    *,
    top_n: int = TOP_N,
    position_size: float,
    max_loss_pct: float,
    capital_reference: float,
    trade_history_path,
    dry_run: bool = True,
    now: Optional[datetime] = None,
) -> Optional[PilotRebalanceResult]:
    """Runs at most one quarterly pilot rebalance. Returns None (no-op) if
    today hasn't reached the next quarter boundary yet, or that boundary was
    already rebalanced — safe and cheap to call every day from a
    daily-firing caller, same self-healing pattern as the paper walk-forward."""
    as_of = now or datetime.now(timezone.utc)
    state = load_state()

    if not is_eligible_to_rebalance(as_of, state.last_rebalanced_quarter_end):
        return None

    boundary = most_recent_quarter_end(as_of).isoformat()
    logger.info("Rotation pilot: quarter boundary %s reached, rebalancing over "
                "%d universe symbols (dry_run=%s)", boundary, len(universe), dry_run)

    sem = asyncio.Semaphore(2)
    symbol_series = await _fetch_universe_series(broker, universe, sem)
    logger.info("Rotation pilot: %d/%d universe symbols have enough history to be ranked",
                len(symbol_series), len(universe))

    target_basket = rank_universe(symbol_series, as_of, top_n)
    plan = diff_target_basket(set(state.positions.keys()), target_basket)
    result = PilotRebalanceResult(quarter_end=boundary, dry_run=dry_run)

    sizer = TradeHistoryService(persist_path=trade_history_path)

    # Sells first (rank drop-outs) — always proceed, even if halted, same
    # "refuse entries, keep managing exits" philosophy as risk_guard/executor.py.
    for symbol in plan.sells:
        pos = state.positions.get(symbol)
        if pos is None:
            continue
        price = _latest_price(symbol_series, symbol, as_of)
        if price is None:
            logger.warning("Rotation pilot: no live price for %s to close rank-dropout "
                            "position — carrying at entry price", symbol)
            price = pos.entry_price

        if dry_run:
            logger.info("[DRY RUN] Rotation pilot would SELL %s qty=%d (entry %.2f)",
                        symbol, pos.quantity, pos.entry_price)
            result.sells.append({"symbol": symbol, "quantity": pos.quantity,
                                  "entry_price": pos.entry_price, "exit_price": price, "order_id": None})
            continue

        try:
            order_result = broker.place_order(Order(
                symbol=symbol, direction=OrderDirection.SELL, quantity=pos.quantity,
                order_type=OrderType.MARKET, product_type=ProductType.CNC,
                tag="rotation_pilot",
            ))
            fill_price = _poll_fill_price(broker, order_result.order_id,
                                           order_result.average_price, price)

            trade = ClosedTrade(
                trade_id=order_result.order_id, symbol=symbol,
                entry_price=pos.entry_price, exit_price=fill_price, quantity=pos.quantity,
                direction="BUY", entry_date=datetime.fromisoformat(pos.entry_date),
                exit_date=as_of, strategy="rotation_pilot",
            )
            state.realized_pnl += trade.pnl
            sizer.record_closed_trade(trade)

            del state.positions[symbol]
            result.sells.append({"symbol": symbol, "quantity": pos.quantity,
                                  "entry_price": pos.entry_price, "exit_price": fill_price,
                                  "order_id": order_result.order_id})
            logger.info("Rotation pilot SELL placed: %s qty=%d (order %s, net pnl %.2f)",
                        symbol, pos.quantity, order_result.order_id, trade.pnl)
        except Exception as e:
            logger.error("Rotation pilot SELL failed for %s — will retry next cycle: %s", symbol, e)
        await asyncio.sleep(ORDER_PLACEMENT_DELAY_SECONDS)

    # Buys (new entrants) — refused in full if either the global kill switch
    # or the pilot's own stop-loss has tripped.
    if plan.buys:
        halt_reason = risk_guard.read_halt_reason()
        pilot_halt = pilot_halt_reason(state.realized_pnl, capital_reference, max_loss_pct)
        reason = halt_reason or pilot_halt
        if reason:
            logger.warning("Rotation pilot: trading halted (%s) — skipping all %d new "
                            "entries this cycle.", reason, len(plan.buys))
            result.skipped_buys.extend({"symbol": s, "reason": f"halted: {reason}"} for s in plan.buys)
        else:
            price_lookup = {s: _latest_price(symbol_series, s, as_of) for s in plan.buys}
            try:
                available_capital = float(broker.get_funds().get("available", 0) or 0)
            except Exception as e:
                logger.warning("Rotation pilot: could not fetch available capital: %s", e)
                available_capital = 0.0

            sized, skipped = _size_new_entrants(plan.buys, price_lookup, available_capital, position_size)
            result.skipped_buys.extend(skipped)

            for symbol, qty in sized.items():
                price = price_lookup[symbol]
                if dry_run:
                    logger.info("[DRY RUN] Rotation pilot would BUY %s qty=%d (~%.2f/share, "
                                "~%.2f notional)", symbol, qty, price, qty * price)
                    result.buys.append({"symbol": symbol, "quantity": qty, "price": price, "order_id": None})
                    continue
                try:
                    order_result = broker.place_order(Order(
                        symbol=symbol, direction=OrderDirection.BUY, quantity=qty,
                        order_type=OrderType.MARKET, product_type=ProductType.CNC,
                        tag="rotation_pilot",
                    ))
                    fill_price = _poll_fill_price(broker, order_result.order_id,
                                                   order_result.average_price, price)
                    state.positions[symbol] = PilotPosition(
                        symbol=symbol, quantity=qty, entry_price=fill_price,
                        entry_date=as_of.isoformat(),
                    )
                    result.buys.append({"symbol": symbol, "quantity": qty,
                                         "price": fill_price, "order_id": order_result.order_id})
                    logger.info("Rotation pilot BUY placed: %s qty=%d (order %s)",
                                symbol, qty, order_result.order_id)
                except Exception as e:
                    logger.error("Rotation pilot BUY failed for %s: %s", symbol, e)
                    result.skipped_buys.append({"symbol": symbol, "reason": f"order failed: {e}"})
                await asyncio.sleep(ORDER_PLACEMENT_DELAY_SECONDS)

    state.last_rebalanced_quarter_end = boundary
    save_state(state)
    result.realized_pnl = state.realized_pnl

    logger.info("Rotation pilot: quarter %s done — %d buys, %d sells, %d skipped, "
                "cumulative realized pnl Rs%.2f", boundary, len(result.buys), len(result.sells),
                len(result.skipped_buys), state.realized_pnl)
    return result
