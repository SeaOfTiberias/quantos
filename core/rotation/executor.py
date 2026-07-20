"""
QuantOS — S8-3 Weekly RS-Momentum Rotation: live executor
─────────────────────────────────────────────────────────
Orchestrates one weekly rebalance: fetch universe data, rank via
core/rotation/ranker.py (the SAME ranking function
scripts/backtest_rs_momentum.py was validated against — see that module's
docstring for why sharing one function matters), diff the target basket
against current holdings (agent/rotation_positions.py), size new entrants,
and place CNC (delivery) orders.

Runs fully automatically — no per-trade human confirm. This is a deliberate,
narrowly-scoped carve-out from the project's default human-in-loop
constraint, agreed for this one systematic strategy (see
docs/SPRINT4_BACKLOG.md's S8-3 "Live execution engineering" section). The
kill switch (agent/risk_guard.py) is still checked before every batch of
buys; sells (dropping a symbol that fell out of the top-N) always proceed,
matching the kill switch's existing "refuse entries, keep managing exits"
philosophy.

rotation.dry_run (config) defaults to True: computes and logs the full
rebalance plan without placing real orders. Flip to False only after
watching a live-data dry run and confirming it matches expectations.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from agent import risk_guard
from agent.rotation_positions import (
    RotationPosition, add_position, load_rotation_positions, remove_position,
)
from core.brokers.base import BrokerAdapter, Order, OrderDirection, OrderType, ProductType
from core.rotation.ranker import (
    LOOKBACK_DAYS, TOP_N, build_symbol_series, diff_target_basket,
    rank_universe, value_as_of,
)

logger = logging.getLogger("quantos.agent.rotation")

# Polite delay between order placements — mirrors core/darvas/weekly_discovery.py's
# asyncio.sleep(0.5) between fetches. No rate-limiting exists anywhere on
# BrokerAdapter.place_order today, and a cold-start week can place up to
# TOP_N orders back-to-back.
ORDER_PLACEMENT_DELAY_SECONDS = 0.5

# Calendar-day history window fetched per symbol: LOOKBACK_DAYS (252) trading
# days is roughly one calendar year; +~50 days covers NSE holidays/weekends
# so the window still warms up cleanly. Mirrors the backtest's own warmup
# margin (scripts/backtest_rs_momentum.py uses "+400d" for a multi-year
# replay; a single point-in-time live ranking needs far less).
FETCH_WINDOW_DAYS = 400


@dataclass
class RebalanceResult:
    buys: list[dict] = field(default_factory=list)          # {symbol, quantity, price, order_id}
    sells: list[dict] = field(default_factory=list)         # {symbol, quantity, entry_price, order_id}
    skipped_buys: list[dict] = field(default_factory=list)  # {symbol, reason}
    dry_run: bool = True


async def _fetch_universe_series(broker: BrokerAdapter, universe: list[str],
                                  sem: asyncio.Semaphore) -> dict:
    """Fetch each universe symbol's recent daily history and build its
    SymbolSeries. Reuses the exact same throttled/retried fetch function the
    S8-3 backtest itself uses (scripts/validate_regime_classifier.py's
    fetch_chunked_daily), so live and backtest share fetch behaviour too,
    not just the ranking formula."""
    from scripts.validate_regime_classifier import fetch_chunked_daily

    to_date = datetime.now(timezone.utc)
    from_date = to_date - timedelta(days=FETCH_WINDOW_DAYS)

    symbol_series = {}
    for symbol in universe:
        candles = await fetch_chunked_daily(broker, symbol, from_date, to_date, sem)
        if len(candles) >= LOOKBACK_DAYS:
            symbol_series[symbol] = build_symbol_series(candles)
    return symbol_series


def _latest_price(symbol_series: dict, symbol: str, as_of: datetime):
    series = symbol_series.get(symbol)
    if series is None:
        return None
    v = value_as_of(series, as_of)
    return v[0] if v else None


def _size_new_entrants(buys: list[str], price_lookup: dict, available_capital: float,
                        position_size: float) -> tuple[dict, list]:
    """Sequential, rank-order sizing that can never exceed available capital
    in aggregate. `buys` is already rank-ordered best-first (diff_target_basket
    preserves target_basket's order), so each name gets up to `position_size`,
    capped by whatever capital remains after funding higher-ranked names
    first — a name whose share price exceeds the REMAINING budget is skipped
    rather than force-bought.

    An earlier version computed one global scale factor and floored every
    position to >=1 share, which could overshoot the total budget once a
    scaled-down target fell below share price (e.g. 20 names sharing a small
    account, several priced above their fair share — flooring each to 1
    share summed to more than what was actually available). This can't:
    remaining capital is tracked and checked before every buy. Returns
    (symbol -> quantity, list of {symbol, reason} for anything skipped)."""
    if not buys:
        return {}, []

    remaining = available_capital
    sized, skipped = {}, []
    for symbol in buys:
        price = price_lookup.get(symbol)
        if not price or price <= 0:
            skipped.append({"symbol": symbol, "reason": "no live price available"})
            continue
        if price > remaining:
            skipped.append({"symbol": symbol, "reason": "insufficient remaining capital"})
            continue
        qty = max(1, int(min(position_size, remaining) // price))
        cost = qty * price
        sized[symbol] = qty
        remaining -= cost

    if skipped:
        logger.warning(
            "Rotation: available capital %.2f could not fund all %d new entrants "
            "at target size %.2f each — %d skipped for insufficient remaining "
            "capital (higher-ranked names funded first, rank order preserved).",
            available_capital, len(buys), position_size,
            sum(1 for s in skipped if s["reason"] == "insufficient remaining capital"))
    return sized, skipped


def _poll_fill_price(broker: BrokerAdapter, order_id: str,
                      initial_average_price, fallback_price: float) -> float:
    """MARKET orders usually fill within seconds — poll briefly for the fill
    price, but don't block the executor indefinitely if it's slow. Same
    pattern as agent/main.py's _size_and_place_order: check the initial
    place_order response first, only poll get_order_status if that didn't
    already carry a fill price."""
    fill_price = initial_average_price
    for _ in range(5):
        if fill_price:
            break
        time.sleep(1)
        try:
            fill_price = broker.get_order_status(order_id).average_price
        except Exception:
            break
    return fill_price or fallback_price


async def run_weekly_rebalance(
    broker: BrokerAdapter,
    universe: list[str],
    *,
    top_n: int = TOP_N,
    position_size: float = 100_000.0,
    dry_run: bool = True,
) -> RebalanceResult:
    sem = asyncio.Semaphore(2)
    symbol_series = await _fetch_universe_series(broker, universe, sem)
    logger.info("Rotation: %d/%d universe symbols have enough history to be ranked",
                len(symbol_series), len(universe))

    as_of = datetime.now(timezone.utc)
    target_basket = rank_universe(symbol_series, as_of, top_n)
    logger.info("Rotation target basket (top %d): %s", top_n, ", ".join(target_basket) or "none")

    positions = load_rotation_positions()
    plan = diff_target_basket(set(positions), target_basket)
    result = RebalanceResult(dry_run=dry_run)

    # Sells first (drop-outs) — always proceed, even if halted, matching the
    # kill switch's "refuse entries, keep managing exits" philosophy.
    for symbol in plan.sells:
        pos = positions.get(symbol)
        if pos is None:
            continue
        if dry_run:
            logger.info("[DRY RUN] Rotation would SELL %s qty=%d (entry %.2f)",
                        symbol, pos.quantity, pos.entry_price)
            result.sells.append({"symbol": symbol, "quantity": pos.quantity,
                                  "entry_price": pos.entry_price, "order_id": None})
            continue
        try:
            order_result = broker.place_order(Order(
                symbol=symbol, direction=OrderDirection.SELL, quantity=pos.quantity,
                order_type=OrderType.MARKET, product_type=ProductType.CNC,
                tag="rotation",
            ))
            remove_position(positions, symbol)
            result.sells.append({"symbol": symbol, "quantity": pos.quantity,
                                  "entry_price": pos.entry_price, "order_id": order_result.order_id})
            logger.info("Rotation SELL placed: %s qty=%d (order %s)",
                        symbol, pos.quantity, order_result.order_id)
        except Exception as e:
            logger.error("Rotation SELL failed for %s — will retry next cycle: %s", symbol, e)
        await asyncio.sleep(ORDER_PLACEMENT_DELAY_SECONDS)

    # Buys (new entrants) — refused in full while the kill switch is halted.
    if plan.buys:
        halt_reason = risk_guard.read_halt_reason()
        if halt_reason:
            logger.warning("Rotation: trading halted (%s) — skipping all %d new entries this cycle.",
                            halt_reason, len(plan.buys))
            result.skipped_buys.extend(
                {"symbol": s, "reason": f"halted: {halt_reason}"} for s in plan.buys)
        else:
            price_lookup = {s: _latest_price(symbol_series, s, as_of) for s in plan.buys}
            try:
                available_capital = float(broker.get_funds().get("available", 0) or 0)
            except Exception as e:
                logger.warning("Rotation: could not fetch available capital: %s", e)
                available_capital = 0.0

            sized, skipped = _size_new_entrants(plan.buys, price_lookup, available_capital, position_size)
            result.skipped_buys.extend(skipped)

            for symbol, qty in sized.items():
                price = price_lookup[symbol]
                if dry_run:
                    logger.info("[DRY RUN] Rotation would BUY %s qty=%d (~%.2f/share, ~%.2f notional)",
                                symbol, qty, price, qty * price)
                    result.buys.append({"symbol": symbol, "quantity": qty, "price": price, "order_id": None})
                    continue
                try:
                    order_result = broker.place_order(Order(
                        symbol=symbol, direction=OrderDirection.BUY, quantity=qty,
                        order_type=OrderType.MARKET, product_type=ProductType.CNC,
                        tag="rotation",
                    ))
                    fill_price = _poll_fill_price(
                        broker, order_result.order_id, order_result.average_price, price)
                    add_position(positions, RotationPosition(
                        symbol=symbol, quantity=qty, entry_price=fill_price,
                        entry_date=datetime.now(timezone.utc).isoformat(),
                    ))
                    result.buys.append({"symbol": symbol, "quantity": qty,
                                         "price": fill_price, "order_id": order_result.order_id})
                    logger.info("Rotation BUY placed: %s qty=%d (order %s)",
                                symbol, qty, order_result.order_id)
                except Exception as e:
                    logger.error("Rotation BUY failed for %s: %s", symbol, e)
                    result.skipped_buys.append({"symbol": symbol, "reason": f"order failed: {e}"})
                await asyncio.sleep(ORDER_PLACEMENT_DELAY_SECONDS)

    return result
