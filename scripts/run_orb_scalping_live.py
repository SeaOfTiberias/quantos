#!/usr/bin/env python3
"""
QuantOS — Candidate 18 ORB Scalping: Live Execution (layer 2)
──────────────────────────────────────────────────────────────────────
docs/ORB_EXECUTION_LAYER_DESIGN.md's layer 2: the ORB-specific tactics
that tell layer 1 (core/execution/order_service.py) when and what to
trade, and feed it exit conditions. Gated by agent/config.yaml's
`orb_scalping.{enabled,dry_run}` -- both default to the safest setting
(enabled: false, dry_run: true) and stay there until the design doc's
go/no-go checklist clears AND the user gives a fresh, explicit capital
go-ahead ([[feedback_confirm_before_scaling_capital]]). Nothing in this
script overrides that gate.

Same deployment shape as scripts/probe_orb_scalping_stopout_spreads.py:
a stateless oneshot fired every fire during NSE market hours by a
systemd timer, not a standing process -- this VM OOM-killed itself twice
on 2026-07-15, and every job on it since has been a cheap, fail-silent
oneshot. Position state persists in
core/orb_scalping/live_positions.py's OrbOpenPosition store
(~/.quantos/orb_open_positions.json) so a restart doesn't lose track of
an open trade.

Per fire, for each underlying (NIFTY, BankNifty):
  1. Fetch today's closed 5m candles -> core/orb_scalping/live_state.py's
     compute_live_state() -- the same opening-range/breakout/arm/trail
     rules the backtest and the stop-out probe already use.
  2. No tracked position + state says "in_position": resolve ATM strike
     -> expiry -> tradeable symbol -> order_service.enter_position()
     (places a MARKET entry + a real resting SL_M at the fixed 25%-of-
     premium stop) -> persist an OrbOpenPosition.
  3. Tracked position: order_service.reconcile_position() first -- this
     is how a fill of the real resting 25%-premium stop is noticed (the
     broker closes it on its own; this script just needs to notice and
     record the trade). If still open, actively check the INDEX-level
     stop (live LTP vs the trailing stop compute_live_state() reports)
     and the 15:20 IST session-flatten -- neither has a backing broker
     order (see the module-level note above _manage_existing_position
     for why), so this script force-exits via
     order_service.flatten_position() when either fires.
  4. Any close (broker-side premium-stop fill, index-stop force-exit, or
     session-flatten) records a ClosedTrade via the existing
     TradeHistoryService and removes the OrbOpenPosition.

Usage:
    python scripts/run_orb_scalping_live.py
"""

from __future__ import annotations

import sys
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.main import load_config  # noqa: E402
from core.brokers import get_broker  # noqa: E402
from core.brokers.base import OrderDirection, ProductType  # noqa: E402
from core.execution.order_service import (  # noqa: E402
    enter_position,
    flatten_position,
    reconcile_position,
)
from core.options import fyers_symbol_master as sm  # noqa: E402
from core.options.models import OptionType  # noqa: E402
from core.orb_scalping.backtest import (  # noqa: E402
    BANKNIFTY_STRIKE_INTERVAL,
    NIFTY_STRIKE_INTERVAL,
)
from core.orb_scalping.contract_selection import (  # noqa: E402
    BANKNIFTY_DTE_FLOOR_DAYS,
    NIFTY_DTE_FLOOR_DAYS,
    fetch_chain_row_near_strike,
    select_expiry,
)
from core.orb_scalping.live_positions import (  # noqa: E402
    OrbOpenPosition,
    add_position,
    get_position,
    load_open_positions,
    remove_position,
    update_stops,
)
from core.orb_scalping.live_state import compute_live_state  # noqa: E402
from core.orb_scalping.premium import PREMIUM_STOP_PCT, atm_strike  # noqa: E402
from core.orb_scalping.signal import SESSION_FLATTEN_UTC  # noqa: E402
from core.risk import ClosedTrade, TradeHistoryService  # noqa: E402

UNDERLYINGS = [
    # (underlying, spot_symbol, strike_interval)
    ("NIFTY", "NIFTY 50", NIFTY_STRIKE_INTERVAL),
    ("BANKNIFTY", "NIFTY BANK", BANKNIFTY_STRIKE_INTERVAL),
]

TRADE_HISTORY_PATH = Path.home() / ".quantos" / "trade_history.json"
SESSION_OPEN_UTC = time(3, 45)   # 09:15 IST -- same convention as the two spread probes


def _exit_reason(*, past_flatten: bool, index_stop_hit: bool, candle_confirmed_stop: bool,
                  candle_exit_reason: Optional[str], armed: bool) -> Optional[str]:
    """Pure priority rule, factored out for unit testing without a broker.
    None means "no forced exit this fire". A live LTP cross is more
    certain than a candle-close-only fallback, so it wins when both are
    true; session_flatten only applies when nothing else already fired."""
    if not (past_flatten or index_stop_hit or candle_confirmed_stop):
        return None
    if candle_confirmed_stop and not index_stop_hit:
        return candle_exit_reason  # "stop" | "trailing_stop"
    if index_stop_hit:
        return "trailing_stop" if armed else "stop"
    return "session_flatten"


def _enter_new_position(broker, underlying: str, state, dte_floor_days: int,
                         strike_interval: float, lots_per_trade: int, dry_run: bool,
                         positions: dict, trade_date_iso: str, now_utc: datetime) -> None:
    trade_date = now_utc.date()
    strike = atm_strike(state.entry_price, strike_interval)
    expiries = sm.list_expiries(underlying)
    expiry = select_expiry(expiries, trade_date, dte_floor_days)
    if expiry is None:
        print(f"  {underlying}: no suitable expiry found, skipping entry.")
        return

    # dte_floor_rolled: true iff the floor actually moved the choice versus
    # the unconstrained nearest expiry -- same "next_week" vs "front_week"
    # distinction core/orb_scalping/backtest.py's resolve_nifty_expiry makes.
    unfloored = select_expiry(expiries, trade_date, 0)
    dte_floor_rolled = unfloored is not None and unfloored != expiry

    option_type = "CE" if state.direction == "CALL" else "PE"
    chain_row = fetch_chain_row_near_strike(broker, underlying, expiry, strike, option_type, strike_interval)
    if chain_row is None or not chain_row.get("ltp"):
        print(f"  {underlying}: no live quote for strike={strike} {option_type}, skipping entry.")
        return
    entry_premium = float(chain_row["ltp"])
    protective_stop_trigger = round(entry_premium * (1 - PREMIUM_STOP_PCT), 4)

    opt_enum = OptionType.CALL if state.direction == "CALL" else OptionType.PUT
    try:
        resolved = sm.resolve_option_symbol(underlying, expiry, strike, opt_enum)
    except sm.SymbolMasterError as e:
        print(f"  {underlying}: could not resolve tradeable symbol ({e}), skipping entry.")
        return

    quantity = resolved.lot_size * lots_per_trade
    tag = f"orb-{underlying.lower()}-{trade_date_iso}"
    entry_result = enter_position(
        broker, symbol=resolved.symbol, direction=OrderDirection.BUY, quantity=quantity,
        product_type=ProductType.INTRADAY, protective_stop_trigger=protective_stop_trigger,
        tag=tag, dry_run=dry_run,
    )
    position = OrbOpenPosition(
        underlying=underlying, option_symbol=resolved.symbol, direction=state.direction,
        option_type=option_type, quantity=quantity, strike=strike, expiry=expiry.isoformat(),
        dte_floor_rolled=dte_floor_rolled, entry_index_level=state.entry_price,
        entry_premium=entry_premium, entry_timestamp=now_utc.isoformat(),
        current_index_stop=state.current_stop, current_premium_stop=protective_stop_trigger,
        armed=state.armed, entry_order_id=entry_result.entry_order_id or "",
        stop_order_id=entry_result.stop_order_id or "", trade_date=trade_date_iso,
    )
    add_position(positions, position)
    print(f"  {underlying}: ENTERED {state.direction} strike={strike} expiry={expiry} "
          f"premium={entry_premium} qty={quantity} dry_run={dry_run}")


def _close_out(underlying: str, existing: OrbOpenPosition, exit_price: Optional[float],
                exit_timestamp, reason: str, positions: dict,
                trade_history: TradeHistoryService) -> None:
    if exit_price is None:
        print(f"  {underlying}: position closed but no exit price could be determined "
              f"(reason={reason}) -- removing from tracking without a ClosedTrade record.")
        remove_position(positions, underlying, existing.trade_date)
        return
    if isinstance(exit_timestamp, str):
        exit_timestamp = datetime.fromisoformat(exit_timestamp)

    trade = ClosedTrade(
        trade_id=f"orb-{underlying.lower()}-{existing.trade_date}",
        symbol=existing.option_symbol,
        entry_price=existing.entry_premium,
        exit_price=exit_price,
        quantity=existing.quantity,
        direction="BUY",   # every ORB entry is a long option, CALL or PUT alike
        entry_date=datetime.fromisoformat(existing.entry_timestamp),
        exit_date=exit_timestamp,
        strategy="orb_scalping",
    )
    trade_history.record_closed_trade(trade)
    remove_position(positions, underlying, existing.trade_date)
    print(f"  {underlying}: CLOSED reason={reason} exit_price={exit_price} pnl={trade.pnl:.2f}")


def _manage_existing_position(broker, underlying: str, spot_symbol: str, state,
                               existing: OrbOpenPosition, dry_run: bool, positions: dict,
                               trade_history: TradeHistoryService, now_utc: datetime) -> None:
    """Reconciles the tracked position against the broker first -- this is
    how a fill of the real resting 25%-of-premium SL_M order is noticed
    (see enter_position(): that order is placed once at entry and never
    trailed, per core/orb_scalping/premium.py's own fixed-threshold model,
    so the broker handles that stop on its own). Only if still open does
    this function actively check the INDEX-level trailing stop and the
    session-flatten time -- NEITHER has a backing broker order: Fyers
    option stop orders trigger on the option's own premium, and there is
    no already-validated way to translate an index-points stop level into
    an equivalent premium trigger without re-deriving option pricing (the
    Black-Scholes machinery this project has deliberately kept out of live
    execution). So the index-level stop is enforced by this function
    re-checking it every fire and force-exiting via
    order_service.flatten_position() when breached, not by moving a
    resting order.

    In dry_run, no real order was ever placed for this position, so the
    broker-side reconcile step is skipped entirely -- checking
    broker.get_positions() for a symbol that was never really bought
    would immediately (and wrongly) look "closed" on the very next fire.
    dry_run relies solely on the script's own state-based checks below."""
    if not dry_run:
        reconcile = reconcile_position(broker, symbol=existing.option_symbol,
                                        stop_order_id=existing.stop_order_id)
        if not reconcile.still_open:
            reason = "premium_stop" if reconcile.exit_reason == "sl_fill" else (reconcile.exit_reason or "unknown")
            _close_out(underlying, existing, reconcile.exit_price, reconcile.exit_timestamp or now_utc,
                       reason, positions, trade_history)
            return

    past_flatten = now_utc.time() >= SESSION_FLATTEN_UTC
    index_ltp = broker.get_ltp([spot_symbol]).get(spot_symbol)
    index_stop_hit = bool(
        existing.current_index_stop is not None and index_ltp is not None and (
            index_ltp <= existing.current_index_stop if existing.direction == "CALL"
            else index_ltp >= existing.current_index_stop
        )
    )
    candle_confirmed_stop = state.status == "flattened" and state.exit_reason in ("stop", "trailing_stop")

    reason = _exit_reason(
        past_flatten=past_flatten, index_stop_hit=index_stop_hit,
        candle_confirmed_stop=candle_confirmed_stop, candle_exit_reason=state.exit_reason,
        armed=existing.armed,
    )
    if reason is not None:
        flat_result = flatten_position(
            broker, symbol=existing.option_symbol, direction=OrderDirection.BUY,
            quantity=existing.quantity, product_type=ProductType.INTRADAY,
            stop_order_id=existing.stop_order_id,
            tag=f"orb-{underlying.lower()}-{existing.trade_date}-exit", dry_run=dry_run,
        )
        if dry_run:
            # No real fill price exists to record -- log and stop tracking
            # without writing a fabricated ClosedTrade into trade_history
            # (that history feeds real Kelly sizing; a dry_run guess has no
            # place in it).
            print(f"  {underlying}: [dry_run] would exit reason={reason} -- "
                  f"removing from tracking, no ClosedTrade recorded.")
            remove_position(positions, underlying, existing.trade_date)
        else:
            _close_out(underlying, existing, flat_result.fill_price, now_utc, reason, positions, trade_history)
        return

    # Still open, nothing forced this fire -- refresh the persisted
    # index-level trailing state for observability (does not drive any
    # broker call, see the docstring above).
    if state.status == "in_position" and state.current_stop is not None:
        update_stops(positions, underlying, existing.trade_date,
                     current_index_stop=state.current_stop, armed=state.armed)


def process_underlying(broker, underlying: str, spot_symbol: str, dte_floor_days: int,
                        strike_interval: float, lots_per_trade: int, dry_run: bool,
                        positions: dict, trade_history: TradeHistoryService) -> None:
    now_utc = datetime.now(timezone.utc)
    trade_date = now_utc.date()
    trade_date_iso = trade_date.isoformat()
    session_start_utc = datetime.combine(trade_date, SESSION_OPEN_UTC, tzinfo=timezone.utc)

    candles = broker.get_historical_data(spot_symbol, "5m", session_start_utc, now_utc)
    closed = sorted(
        (c for c in candles if c.timestamp + timedelta(minutes=5) <= now_utc),
        key=lambda c: c.timestamp,
    )
    state = compute_live_state(closed)
    print(f"{underlying}: status={state.status} direction={state.direction} "
          f"stop={state.current_stop} armed={state.armed}")

    existing = get_position(positions, underlying, trade_date_iso)

    if existing is None:
        if state.status != "in_position":
            return
        _enter_new_position(broker, underlying, state, dte_floor_days, strike_interval,
                             lots_per_trade, dry_run, positions, trade_date_iso, now_utc)
        return

    _manage_existing_position(broker, underlying, spot_symbol, state, existing, dry_run,
                               positions, trade_history, now_utc)


def main() -> int:
    config = load_config("agent/config.yaml")
    orb_cfg = config.get("orb_scalping", {})
    if not orb_cfg.get("enabled", False):
        print("orb_scalping.enabled is false in agent/config.yaml -- nothing to do.")
        return 0

    dry_run = bool(orb_cfg.get("dry_run", True))
    lots_per_trade = int(orb_cfg.get("lots_per_trade", 1))
    dte_floor_days = {
        "NIFTY": int(orb_cfg.get("nifty_dte_floor_days", NIFTY_DTE_FLOOR_DAYS)),
        "BANKNIFTY": int(orb_cfg.get("banknifty_dte_floor_days", BANKNIFTY_DTE_FLOOR_DAYS)),
    }

    broker = get_broker(config)
    if not broker.connect():
        print("ERROR: broker connect() failed -- check the Fyers token.")
        return 1

    trade_history = TradeHistoryService(persist_path=TRADE_HISTORY_PATH)
    positions = load_open_positions()

    for underlying, spot_symbol, strike_interval in UNDERLYINGS:
        try:
            process_underlying(broker, underlying, spot_symbol, dte_floor_days[underlying],
                                strike_interval, lots_per_trade, dry_run, positions, trade_history)
        except Exception as e:
            print(f"  {underlying}: fire failed ({e}) -- self-healing, will retry next fire.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
