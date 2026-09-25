#!/usr/bin/env python3
"""
QuantOS — Darvas ATR-Stop (Bucket B): Live Execution
──────────────────────────────────────────────────────────────────────
docs/DARVAS_ATR_STOP_BACKTEST_RESULTS.md's Bucket B (35% < box width <=
50%, ATR-scaled trailing stop) is the second strategy in this project --
alongside candidate 18 (ORB scalping) -- to clear both its pre-registered
statistical bar AND a real-capital equity-curve/position-sizing pass
(docs/DARVAS_ATR_STOP_EQUITY_CURVE_RESULTS.md). Until now it had ZERO
live execution code. This is that code: config-gated
(darvas_atr_stop.{enabled,dry_run}, both default to the safest setting),
halt-checked (agent/risk_guard.py), and position-tracked, same shape as
scripts/run_orb_scalping_live.py -- adapted for equities held over
days-to-weeks instead of same-day options.

Deliberately NOT built on core/darvas/scanner.py / core/darvas/alerts.py
(the Stage B "scanner:" config block already live in agent/config.yaml):
that pipeline's default filter (max_box_width=35) EXCLUDES Bucket B's own
35-50% width range outright, its stop is the fixed
sl_ceil_buffer_pct=2% this candidate's whole methodology chain
(docs/DARVAS_TRAILING_STOP_BACKTEST_METHODOLOGY.md ->
docs/DARVAS_ATR_STOP_BACKTEST_METHODOLOGY.md) found insufficient, and it
is human-confirm-gated via Telegram -- a review already on record
(memory: quantos_fable_rationale_review) found that a human veto on a
systematic signal corrupts the track record a backtest verdict is
supposed to stand for. This script reuses only what's actually validated:
core/darvas/weekly_discovery.py::analyse_symbol/_atr directly (unmodified,
same functions scripts/backtest_darvas_atr_stop.py calls), that script's
own _stop_from_atr/ATR_MULTIPLIER/ATR_PERIOD (imported, not
reimplemented, so live can never silently drift from the backtest's own
stop math), and core/execution/order_service.py's generic
enter_position/flatten_position/reconcile_position/update_stop (layer 1,
already broker-agnostic and dry_run-aware, built explicitly "for ORB --
and any future strategy" per its own docstring). Universe:
agent/universe_nifty500.txt, the SAME file the backtest itself scanned
(NOT core/darvas/scanner.py's own universe_file key).

Timing model (why this is a single DAILY fire, not an intraday poll):
this candidate's own signal is fundamentally end-of-day -- a "FRESH
BREAKOUT" is a property of a fully-closed daily bar
(analyse_symbol's own prev_close <= box_ceil gate), and the backtest
walks the trade day-by-day (bar.low/bar.high vs stop/target), never
intraday. One fire per trading day, scheduled shortly after market open
(deploy/systemd/quantos-darvas-atr-stop-live.timer), does the following
per symbol using ONLY fully-closed daily bars (strictly before today --
_fetch_daily_through_yesterday filters out any forming bar, matching the
backtest's own historical-only lookback exactly):

  1. No open position: analyse_symbol on daily-through-yesterday. A
     FRESH BREAKOUT in Bucket B's own 35-50% width band is sized at
     `equity_fraction` (default 0.09 -- the grid-searched, NOT re-tuned,
     figure from docs/DARVAS_ATR_STOP_EQUITY_CURVE_RESULTS.md's
     `optimal_fraction_by_growth`) of current paper equity, capped by
     real available cash exactly as
     scripts/simulate_darvas_atr_stop_equity_curve.py::simulate()
     computes it (see _position_size below) -- then entered via
     order_service.enter_position: a MARKET buy (approximating the
     backtest's "next day's open" -- this script fires a few minutes
     into today's session, a small and honestly-disclosed timing gap,
     same class of approximation run_orb_scalping_live.py already
     accepts for its own entries) plus a resting SL_M stop at the
     ATR-scaled initial stop, product_type=CNC (delivery -- a Darvas
     hold spans days-to-weeks, so INTRADAY would auto-square-off the
     same day and silently destroy the whole strategy).
  2. An open position: the resting SL_M stop is real and broker-enforced
     continuously, so `reconcile_position` (live only -- dry_run has no
     real order to reconcile) is checked FIRST and is authoritative.
     Failing that (or in dry_run), yesterday's fully-closed bar is
     checked against the CURRENT stop/target exactly as
     scripts/backtest_darvas_atr_stop.py::_simulate_exit_atr checks one
     day-step (bar.low <= stop / bar.high >= target) -- target has no
     resting order (no OCO/bracket support in this project's broker
     layer), so it is only ever caught the fire AFTER it happened, a
     documented one-day lag. If nothing exited, analyse_symbol re-runs
     on the same daily-through-yesterday history to see whether a NEW,
     higher-confirmed box appeared; if so the stop trails up (ATR
     recomputed as of the new box, never frozen at entry, never lowered)
     via order_service.update_stop, and the target trails to the new
     box's own measured move if it's larger -- identical rule to the
     backtest's own trailing logic, just one day-step per fire instead
     of walked in a loop.

A missed fire (systemd skip, broker outage) means a FRESH BREAKOUT that
happened on the skipped day is simply never entered -- analyse_symbol's
prev_close <= box_ceil gate makes a breakout a single-day event, so
there is nothing to "catch up" on later without changing the entry-price
semantics. Same accepted, self-healing-by-omission shape as every other
daily-cadence job in this project (see quantos-momentum-shortlist.service).

2026-09-25: split into two phases (see "Two-phase schedule" below main's
helpers) -- the per-symbol logic above is unchanged, but the ~500 history
fetches now run post-market and only the resulting orders run in market
hours. A plan older than PLAN_MAX_AGE_DAYS is refused, not traded.

Usage:
    python scripts/run_darvas_atr_stop_live.py --phase scan      # ~18:00 IST
    python scripts/run_darvas_atr_stop_live.py --phase execute   # ~09:45 IST
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.main import load_config  # noqa: E402
from agent.risk_guard import IST, read_halt_reason  # noqa: E402
from core.brokers import get_broker  # noqa: E402
from core.brokers.base import OHLCV, OrderDirection, ProductType  # noqa: E402
from core.darvas.weekly_discovery import DEFAULT_CONFIG, analyse_symbol  # noqa: E402
from core.darvas_atr_stop.dry_run_log import DarvasDryRunTrade, append_dry_run_trade  # noqa: E402
from core.darvas_atr_stop.live_positions import (  # noqa: E402
    DARVAS_ATR_STOP_OPEN_POSITIONS_PATH,
    DarvasOpenPosition,
    add_position,
    get_position,
    load_open_positions,
    remove_position,
    update_trail,
)
from core.execution.order_service import (  # noqa: E402
    enter_position,
    flatten_position,
    reconcile_position,
    update_stop,
)
from core.risk import ClosedTrade, TradeHistoryService  # noqa: E402
from scripts.backtest_darvas_atr_stop import _stop_from_atr  # noqa: E402
from scripts.backtest_darvas_box_width import BUCKETS, MIN_BARS, WIDE_CFG  # noqa: E402

STRATEGY_NAME = "darvas_atr_stop"
BUCKET_B_LABEL = "35-50%"
_BUCKET_B_PREDICATE = dict(BUCKETS)[BUCKET_B_LABEL]

TRADE_HISTORY_PATH = Path.home() / ".quantos" / "trade_history.json"
# Same daily-fetch window weekly_discovery.py's own DEFAULT_CONFIG uses --
# comfortably covers box-confirmation + ATR(14) and stays under Fyers'
# 366-day cap on daily-resolution history requests.
HISTORY_DAYS = DEFAULT_CONFIG["history_days"]


# ─── Data fetch ──────────────────────────────────────────────────────────

def _fetch_daily_through_yesterday(broker, symbol: str, today: date) -> list[OHLCV]:
    """Only fully-closed daily bars strictly before `today` -- guarantees
    analyse_symbol/_atr ever see the exact same shape of history the
    backtest fed them (never a forming, still-updating bar for today)."""
    to_dt = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc)
    from_dt = to_dt - timedelta(days=HISTORY_DAYS)
    candles = broker.get_historical_data(symbol, "1d", from_dt, to_dt)
    return sorted((c for c in candles if c.timestamp.date() < today), key=lambda c: c.timestamp)


# ─── Position sizing ─────────────────────────────────────────────────────

def _position_size(trades: list[ClosedTrade], positions: dict[str, DarvasOpenPosition],
                    starting_capital: float, equity_fraction: float, entry_price: float,
                    symbol: str, min_capital_floor: float = 0.0) -> tuple[int, str]:
    """Equity-fraction sizing capped by real available cash -- the SAME
    formula scripts/simulate_darvas_atr_stop_equity_curve.py::simulate()
    already validated (mining-derived, holdout-checked): `current_equity
    = starting_capital + sum(realized net pnl)` is algebraically identical
    to that script's Account.cash + positions_value(marked at entry price)
    -- see this function's own docstring math check in the module that
    introduced it. `invested` (cost basis of currently open positions, at
    THEIR OWN entry prices) is what a single-trade formula has no way to
    see and single-trade Kelly got wrong for this candidate (mean 12.2,
    max 29 concurrent Bucket B positions in the mining window) -- this
    caps spendable cash by what's actually left, not by total equity."""
    strategy_trades = [t for t in trades if t.strategy == STRATEGY_NAME]
    current_equity = starting_capital + sum(t.pnl for t in strategy_trades)
    if current_equity < min_capital_floor:
        return 0, (f"{symbol}: equity Rs{current_equity:,.0f} below floor "
                    f"Rs{min_capital_floor:,.0f} -- refusing entry")
    invested = sum(p.quantity * p.entry_price for p in positions.values())
    available_cash = current_equity - invested
    target_notional = equity_fraction * current_equity
    spendable = min(target_notional, available_cash)
    if spendable < entry_price:
        return 0, (f"{symbol}: insufficient cash (spendable Rs{spendable:,.0f} "
                    f"< entry price Rs{entry_price:,.2f})")
    qty = int(spendable // entry_price)
    return qty, (f"{symbol}: sized {qty} shares ({equity_fraction:.1%} of "
                 f"Rs{current_equity:,.0f} equity, spendable Rs{spendable:,.0f})")


# ─── Entry ───────────────────────────────────────────────────────────────

def _scan_entry(symbol: str, daily: list[OHLCV]) -> Optional[dict]:
    """The DECISION half of an entry, from fully-closed bars only -- no
    broker call. Returns the plan-ready signal dict, or None for no trade.
    The evening scan (--phase scan) calls this; the next morning's
    --phase execute acts on it via _execute_entry."""
    if len(daily) < MIN_BARS:
        return None
    result = analyse_symbol(symbol, daily, cfg=WIDE_CFG)
    if result is None or result.status != "FRESH BREAKOUT":
        return None
    if result.box_width_pct is None or not _BUCKET_B_PREDICATE(result.box_width_pct):
        return None  # only Bucket B (35-50%) is the validated edge -- everything else is a no-trade

    initial_stop = _stop_from_atr(daily, len(daily) - 1, result.box_ceiling)
    if initial_stop <= 0:
        print(f"  {symbol}: ATR-derived stop {initial_stop:.2f} is non-positive -- skipping.")
        return None
    return dict(symbol=symbol, initial_stop=round(initial_stop, 2), target=result.mm_target,
                box_ceiling=result.box_ceiling, box_width_pct=result.box_width_pct,
                last_close=daily[-1].close, tags=[])


def _execute_entry(broker, signal: dict, positions: dict[str, DarvasOpenPosition],
                    trade_history: TradeHistoryService, dry_run: bool, equity_fraction: float,
                    starting_capital: float, min_capital_floor: float, today_iso: str,
                    positions_path: Optional[Path] = None) -> None:
    """The ACTION half of an entry: live price check, sizing, order."""
    symbol = signal["symbol"]
    initial_stop = signal["initial_stop"]
    ltp = broker.get_ltp([symbol]).get(symbol)
    price_estimate = ltp if ltp else signal["last_close"]
    if price_estimate <= initial_stop:
        print(f"  {symbol}: price {price_estimate:.2f} already at/below the ATR stop "
              f"{initial_stop:.2f} -- stale/invalid signal, skipping.")
        return

    qty, note = _position_size(trade_history.get_trade_history(), positions, starting_capital,
                                equity_fraction, price_estimate, symbol, min_capital_floor)
    print(f"  {note}")
    if qty < 1:
        return

    tag = f"darvas-atr-stop-{symbol.replace(':', '-')}-{today_iso}"
    entry_result = enter_position(
        broker, symbol=symbol, direction=OrderDirection.BUY, quantity=qty,
        product_type=ProductType.CNC, protective_stop_trigger=initial_stop,
        tag=tag, dry_run=dry_run,
    )
    entry_price = entry_result.fill_price if entry_result.fill_price else price_estimate
    position = DarvasOpenPosition(
        symbol=symbol, quantity=qty, entry_price=entry_price, entry_date=today_iso,
        box_width_pct=signal["box_width_pct"], seen_ceiling=signal["box_ceiling"],
        current_stop=initial_stop, current_target=signal["target"],
        entry_order_id=entry_result.entry_order_id or "", stop_order_id=entry_result.stop_order_id or "",
    )
    add_position(positions, position, path=positions_path)
    tags = f" tags={','.join(signal['tags'])}" if signal.get("tags") else ""
    print(f"  {symbol}: ENTERED qty={qty} entry~={entry_price:.2f} stop={initial_stop:.2f} "
          f"target={signal['target']:.2f} width={signal['box_width_pct']:.1f}%{tags} dry_run={dry_run}")


def _detect_and_enter(broker, symbol: str, daily: list[OHLCV],
                       positions: dict[str, DarvasOpenPosition], trade_history: TradeHistoryService,
                       dry_run: bool, equity_fraction: float, starting_capital: float,
                       min_capital_floor: float, today_iso: str,
                       positions_path: Optional[Path] = None) -> None:
    signal = _scan_entry(symbol, daily)
    if signal is None:
        return
    _execute_entry(broker, signal, positions, trade_history, dry_run, equity_fraction,
                   starting_capital, min_capital_floor, today_iso, positions_path=positions_path)


# ─── Exit / trail ─────────────────────────────────────────────────────────

def _close_out(symbol: str, existing: DarvasOpenPosition, exit_price: Optional[float],
                exit_timestamp, reason: str, positions: dict[str, DarvasOpenPosition],
                trade_history: TradeHistoryService, positions_path: Optional[Path] = None) -> None:
    if exit_price is None:
        print(f"  {symbol}: position closed but no exit price could be determined "
              f"(reason={reason}) -- removing from tracking without a ClosedTrade record.")
        remove_position(positions, symbol, path=positions_path)
        return
    if isinstance(exit_timestamp, str):
        exit_timestamp = datetime.fromisoformat(exit_timestamp)

    trade = ClosedTrade(
        trade_id=f"darvas-atr-stop-{symbol.replace(':', '-')}-{existing.entry_date}",
        symbol=symbol, entry_price=existing.entry_price, exit_price=exit_price,
        quantity=existing.quantity, direction="BUY",
        entry_date=datetime.fromisoformat(existing.entry_date), exit_date=exit_timestamp,
        strategy=STRATEGY_NAME,
    )
    trade_history.record_closed_trade(trade)
    remove_position(positions, symbol, path=positions_path)
    print(f"  {symbol}: CLOSED reason={reason} exit_price={exit_price} pnl={trade.pnl:.2f}")


def _force_exit(broker, symbol: str, existing: DarvasOpenPosition, exit_price_estimate: float,
                 reason: str, dry_run: bool, positions: dict[str, DarvasOpenPosition],
                 trade_history: TradeHistoryService, positions_path: Optional[Path] = None,
                 dry_run_log_path: Optional[Path] = None) -> None:
    flat_result = flatten_position(
        broker, symbol=symbol, direction=OrderDirection.BUY, quantity=existing.quantity,
        product_type=ProductType.CNC, stop_order_id=existing.stop_order_id,
        tag=f"darvas-atr-stop-{symbol.replace(':', '-')}-exit", dry_run=dry_run,
    )
    if dry_run:
        # No real fill price exists to record into trade_history (that
        # feeds real Kelly/equity-fraction sizing; a dry_run guess has no
        # place in it) -- but a completed round trip IS worth a durable,
        # queryable record: core/darvas_atr_stop/dry_run_log.py exists
        # precisely so this doesn't only live in journalctl. A best-effort
        # live quote is captured too, for observability only.
        exit_ltp = None
        try:
            exit_ltp = broker.get_ltp([symbol]).get(symbol)
        except Exception as e:
            print(f"  {symbol}: could not fetch exit quote for the dry-run log ({e}).")
        append_dry_run_trade(DarvasDryRunTrade(
            symbol=symbol, entry_timestamp=existing.entry_date, entry_price=existing.entry_price,
            exit_timestamp=datetime.now(timezone.utc).isoformat(), exit_reason=reason,
            quantity=existing.quantity, box_width_pct=existing.box_width_pct,
            seen_ceiling=existing.seen_ceiling, boundary_price=exit_price_estimate, exit_ltp=exit_ltp,
        ), path=dry_run_log_path)
        print(f"  {symbol}: [dry_run] would exit reason={reason} near {exit_price_estimate:.2f} "
              f"-- removing from tracking, no ClosedTrade recorded (dry-run log updated).")
        remove_position(positions, symbol, path=positions_path)
        return
    exit_price = flat_result.fill_price if flat_result.fill_price else exit_price_estimate
    _close_out(symbol, existing, exit_price, datetime.now(timezone.utc), reason,
               positions, trade_history, positions_path=positions_path)


def _manage_existing_position(broker, symbol: str, daily: list[OHLCV], existing: DarvasOpenPosition,
                               dry_run: bool, positions: dict[str, DarvasOpenPosition],
                               trade_history: TradeHistoryService,
                               positions_path: Optional[Path] = None,
                               dry_run_log_path: Optional[Path] = None) -> None:
    """Reconciles the real resting stop first (live only -- it is
    broker-enforced continuously and is the most accurate source for a
    stop-out; dry_run has no real order to reconcile). Failing that, walks
    ONE day-step of scripts/backtest_darvas_atr_stop.py::_simulate_exit_atr's
    own logic against yesterday's now fully-closed bar: stop/target check,
    then (if still open) a trail update from the same day's data."""
    if not dry_run:
        reconcile = reconcile_position(broker, symbol=symbol, stop_order_id=existing.stop_order_id)
        if not reconcile.still_open:
            reason = "stop" if reconcile.exit_reason == "sl_fill" else (reconcile.exit_reason or "unknown")
            _close_out(symbol, existing, reconcile.exit_price,
                       reconcile.exit_timestamp or datetime.now(timezone.utc), reason,
                       positions, trade_history, positions_path=positions_path)
            return

    if not daily:
        return  # no new closed bar since entry -- nothing to check yet

    action = _scan_existing(symbol, daily, existing)
    if action is not None:
        _apply_existing_action(broker, symbol, existing, action, dry_run, positions, trade_history,
                               positions_path=positions_path, dry_run_log_path=dry_run_log_path)


def _scan_existing(symbol: str, daily: list[OHLCV], existing: DarvasOpenPosition) -> Optional[dict]:
    """The DECISION half of managing an open position: one day-step of
    _simulate_exit_atr against the last fully-closed bar -- no broker call.
    Returns {"action": "exit", ...} / {"action": "trail", ...} / None."""
    if not daily:
        return None
    bar = daily[-1]
    if bar.low <= existing.current_stop:
        return dict(action="exit", reason="stop", boundary=existing.current_stop)
    if bar.high >= existing.current_target:
        return dict(action="exit", reason="target", boundary=existing.current_target)

    result = analyse_symbol(symbol, daily, cfg=WIDE_CFG)
    if result is None or result.box_ceiling is None or result.box_ceiling <= existing.seen_ceiling:
        return None
    new_stop = _stop_from_atr(daily, len(daily) - 1, result.box_ceiling)
    if new_stop <= existing.current_stop:
        return None
    new_target = existing.current_target
    if result.mm_target and result.mm_target > new_target:
        new_target = result.mm_target
    return dict(action="trail", new_stop=round(new_stop, 2), new_target=new_target,
                new_ceiling=result.box_ceiling)


def _apply_existing_action(broker, symbol: str, existing: DarvasOpenPosition, action: dict,
                            dry_run: bool, positions: dict[str, DarvasOpenPosition],
                            trade_history: TradeHistoryService,
                            positions_path: Optional[Path] = None,
                            dry_run_log_path: Optional[Path] = None) -> None:
    """The ACTION half. Re-validates a trail against the position's CURRENT
    stop, since the position file may have moved since the plan was built."""
    if action["action"] == "exit":
        _force_exit(broker, symbol, existing, action["boundary"], action["reason"], dry_run,
                    positions, trade_history, positions_path=positions_path,
                    dry_run_log_path=dry_run_log_path)
        return
    if action["action"] != "trail" or action["new_stop"] <= existing.current_stop:
        return

    if not dry_run:
        update_stop(broker, stop_order_id=existing.stop_order_id,
                    new_trigger_price=action["new_stop"], dry_run=dry_run)
    new_target = max(existing.current_target, action["new_target"])
    update_trail(positions, symbol, current_stop=action["new_stop"],
                current_target=new_target, seen_ceiling=action["new_ceiling"], path=positions_path)
    print(f"  {symbol}: trailed stop {existing.current_stop:.2f} -> {action['new_stop']:.2f} "
          f"(new box ceiling {action['new_ceiling']:.2f})")


# ─── Per-symbol orchestration ──────────────────────────────────────────────

def process_symbol(broker, symbol: str, positions: dict[str, DarvasOpenPosition],
                    trade_history: TradeHistoryService, dry_run: bool, equity_fraction: float,
                    starting_capital: float, min_capital_floor: float, today: date,
                    positions_path: Optional[Path] = None,
                    dry_run_log_path: Optional[Path] = None) -> None:
    daily = _fetch_daily_through_yesterday(broker, symbol, today)
    existing = get_position(positions, symbol)

    if existing is not None:
        _manage_existing_position(broker, symbol, daily, existing, dry_run, positions,
                                   trade_history, positions_path=positions_path,
                                   dry_run_log_path=dry_run_log_path)
        return

    # Hard kill-switch (agent/risk_guard.py, S4-2/P0-2) -- refuses NEW
    # entries only, same as run_orb_scalping_live.py; exit management above
    # this branch is never gated by it.
    halt_reason = read_halt_reason()
    if halt_reason:
        print(f"  {symbol}: entry refused -- trading halted ({halt_reason})")
        return

    _detect_and_enter(broker, symbol, daily, positions, trade_history, dry_run, equity_fraction,
                       starting_capital, min_capital_floor, today.isoformat(),
                       positions_path=positions_path)


def _load_universe(universe_file: str) -> list[str]:
    path = Path(universe_file)
    if not path.exists():
        return []
    return [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")]


# ─── Two-phase schedule: evening scan -> morning execute ─────────────────
#
# Every input to every decision above is a fully-closed daily bar, so the
# ~500 history fetches don't need market hours at all. Running them at
# 09:20 IST collided with candidate 18/18b's own Fyers calls in the same
# minutes (rate-limit errors observed most days, 2026-09-21..25). So:
#   --phase scan     (post-market, ~18:00 IST): fetch every symbol, decide
#                    entries/exits/trails, write PLAN_PATH. No orders.
#   --phase execute  (~09:45 IST): read the plan, place only its orders.
# The scan on day D sees bars through D -- exactly what a D+1 morning fire
# of the old single-phase design saw -- so decisions are unchanged.

PLAN_PATH = Path.home() / ".quantos" / "darvas_atr_stop_plan.json"
# Fri scan -> Mon execute is 3 days; a Monday holiday makes it 4. Anything
# older is refused rather than traded on (fail closed). The NSE calendar
# module can't answer this: it only covers past sessions.
PLAN_MAX_AGE_DAYS = 4
DEFAULT_TAG_UNIVERSES = {
    "Alpha50": "agent/universe_alpha50.txt",
    "Mom30": "agent/universe_nifty200momentum30.txt",
}


def _load_tag_sets(tag_universes: dict) -> dict[str, set[str]]:
    return {label: set(_load_universe(path)) for label, path in tag_universes.items()}


def _tags_for(symbol: str, tag_sets: dict[str, set[str]]) -> list[str]:
    return [label for label, members in tag_sets.items() if symbol in members]


def _write_plan(plan: dict, path: Optional[Path] = None) -> None:
    path = path or PLAN_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(plan, indent=2))
    tmp.replace(path)


def _load_plan(path: Optional[Path] = None) -> Optional[dict]:
    path = path or PLAN_PATH
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def plan_refusal_reason(plan: Optional[dict], today: date) -> Optional[str]:
    """None if the plan may be executed today, else why not."""
    if plan is None:
        return "no plan file (did the evening scan run?)"
    if plan.get("executed_on"):
        return f"plan already executed on {plan['executed_on']}"
    as_of = date.fromisoformat(plan["bars_as_of"])
    if as_of >= today:
        return f"plan bars_as_of {as_of} is not before today {today}"
    age = (today - as_of).days
    if age > PLAN_MAX_AGE_DAYS:
        return f"plan is stale: bars_as_of {as_of} is {age} days old (max {PLAN_MAX_AGE_DAYS})"
    return None


# Today's bar only counts once the session is over; a scan caught up on
# boot during market hours must never read a still-forming bar.
SESSION_FINAL_IST = (15, 45)


def last_final_bar_date(now_ist: datetime) -> date:
    """The latest date whose daily bar is complete as of `now_ist`."""
    today = now_ist.date()
    if (now_ist.hour, now_ist.minute) >= SESSION_FINAL_IST:
        return today
    return today - timedelta(days=1)


def run_scan(broker, symbols: list[str], positions: dict[str, DarvasOpenPosition],
             tag_sets: dict[str, set[str]], through: date,
             retry_pause_s: float = 60.0) -> dict:
    """Decide everything from bars dated <= `through`. Returns the plan."""
    cutoff = through + timedelta(days=1)   # _fetch_* keeps bars strictly before its date arg
    all_symbols = sorted(set(symbols) | set(positions.keys()))
    fetched: dict[str, list[OHLCV]] = {}
    failures: dict[str, str] = {}

    def _fetch(pending: list[str]) -> None:
        for n, symbol in enumerate(pending, 1):
            try:
                fetched[symbol] = _fetch_daily_through_yesterday(broker, symbol, cutoff)
                failures.pop(symbol, None)
            except Exception as e:
                failures[symbol] = str(e)
            if n < len(pending):
                time.sleep(0.3)   # be polite to the Fyers API across a ~500-symbol scan

    _fetch(all_symbols)
    if failures:
        # One retry pass after a pause -- rate-limit errors are transient;
        # a bad ticker will simply fail again and stay listed in the plan.
        print(f"  {len(failures)} fetch failure(s); retrying once after {retry_pause_s:.0f}s")
        time.sleep(retry_pause_s)
        _fetch(sorted(failures))

    last_bar = {s: d[-1].timestamp.date() for s, d in fetched.items() if d}
    bars_as_of = max(last_bar.values()) if last_bar else None

    entries, position_actions = [], {}
    for symbol in sorted(fetched):
        daily = fetched[symbol]
        existing = positions.get(symbol)
        if existing is not None:
            action = _scan_existing(symbol, daily, existing)
            if action is not None:
                position_actions[symbol] = action
            continue
        if not daily or last_bar[symbol] != bars_as_of:
            continue   # no bar for the latest session (suspended/stale) -- never enter on old data
        signal = _scan_entry(symbol, daily)
        if signal is not None:
            signal["tags"] = _tags_for(symbol, tag_sets)
            entries.append(signal)

    return dict(
        generated_at=datetime.now(timezone.utc).isoformat(),
        through=through.isoformat(),
        bars_as_of=bars_as_of.isoformat() if bars_as_of else None,
        symbols_scanned=len(all_symbols),
        entries=entries,
        position_actions=position_actions,
        failures=failures,
        executed_on=None,
    )


def run_execute(broker, plan: dict, positions: dict[str, DarvasOpenPosition],
                trade_history: TradeHistoryService, dry_run: bool, equity_fraction: float,
                starting_capital: float, min_capital_floor: float, today: date,
                positions_path: Optional[Path] = None,
                dry_run_log_path: Optional[Path] = None) -> None:
    """Place only what the plan says. Open positions are handled first
    (exits free cash before new entries are sized)."""
    for symbol in sorted(positions):
        existing = positions[symbol]
        try:
            if not dry_run:
                reconcile = reconcile_position(broker, symbol=symbol, stop_order_id=existing.stop_order_id)
                if not reconcile.still_open:
                    reason = "stop" if reconcile.exit_reason == "sl_fill" else (reconcile.exit_reason or "unknown")
                    _close_out(symbol, existing, reconcile.exit_price,
                               reconcile.exit_timestamp or datetime.now(timezone.utc), reason,
                               positions, trade_history, positions_path=positions_path)
                    continue
            action = plan.get("position_actions", {}).get(symbol)
            if action is not None:
                _apply_existing_action(broker, symbol, existing, action, dry_run, positions,
                                       trade_history, positions_path=positions_path,
                                       dry_run_log_path=dry_run_log_path)
        except Exception as e:
            print(f"  {symbol}: position management failed ({e}) -- will be re-evaluated tonight.")

    entries = plan.get("entries", [])
    if not entries:
        return
    # Hard kill-switch (agent/risk_guard.py) -- refuses NEW entries only;
    # exit management above is never gated by it.
    halt_reason = read_halt_reason()
    if halt_reason:
        print(f"  {len(entries)} planned entr(ies) refused -- trading halted ({halt_reason})")
        return
    for signal in entries:
        if signal["symbol"] in positions:
            continue
        try:
            _execute_entry(broker, signal, positions, trade_history, dry_run, equity_fraction,
                           starting_capital, min_capital_floor, today.isoformat(),
                           positions_path=positions_path)
        except Exception as e:
            print(f"  {signal['symbol']}: entry failed ({e}) -- signal is single-day, not retried.")
        time.sleep(0.3)


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default="agent/config.yaml")
    parser.add_argument("--phase", choices=["scan", "execute"], required=True)
    args = parser.parse_args(argv)

    config = load_config(args.config)
    cfg = config.get("darvas_atr_stop", {})
    if not cfg.get("enabled", False):
        print("darvas_atr_stop.enabled is false in agent/config.yaml -- nothing to do.")
        return 0

    dry_run = bool(cfg.get("dry_run", True))
    equity_fraction = float(cfg.get("equity_fraction", 0.09))
    starting_capital = float(cfg.get("starting_capital", 0.0))
    min_capital_floor = float(cfg.get("min_capital_floor", 0.0))
    universe_file = cfg.get("universe_file", "agent/universe_nifty500.txt")
    today = datetime.now(IST).date()

    if args.phase == "execute":
        plan = _load_plan()
        refusal = plan_refusal_reason(plan, today)
        if refusal:
            print(f"Not executing: {refusal}.")
            # Already-executed is a normal Persistent= catch-up re-fire; anything else is an anomaly.
            return 0 if plan and plan.get("executed_on") else 1

    broker = get_broker(config)
    if not broker.connect():
        print("ERROR: broker connect() failed -- check the Fyers token.")
        return 1

    positions = load_open_positions()

    if args.phase == "scan":
        symbols = _load_universe(universe_file)
        if not symbols:
            print(f"Universe file {universe_file} is empty or missing -- nothing to scan.")
            return 0
        tag_sets = _load_tag_sets(cfg.get("tag_universes", DEFAULT_TAG_UNIVERSES))
        through = last_final_bar_date(datetime.now(IST))
        plan = run_scan(broker, symbols, positions, tag_sets, through)
        previous = _load_plan()
        if previous and previous.get("bars_as_of") == plan["bars_as_of"] and previous.get("executed_on"):
            plan["executed_on"] = previous["executed_on"]   # a re-scan must not re-arm an executed plan
        _write_plan(plan)
        if plan["bars_as_of"] != through.isoformat():
            print(f"WARNING: latest bar is {plan['bars_as_of']}, expected {through} -- "
                  f"holiday/weekend, or Fyers' bar not final yet.")
        for s in plan["entries"]:
            tags = ",".join(s["tags"]) or "-"
            print(f"  PLAN entry {s['symbol']}: stop={s['initial_stop']:.2f} target={s['target']:.2f} "
                  f"width={s['box_width_pct']:.1f}% tags={tags}")
        for sym, a in plan["position_actions"].items():
            print(f"  PLAN {a['action']} {sym}: {a}")
        for sym, err in plan["failures"].items():
            print(f"  FAILED {sym}: {err}")
        print(f"Scan done: {plan['symbols_scanned']} symbols, bars_as_of={plan['bars_as_of']}, "
              f"{len(plan['entries'])} entr(ies), {len(plan['position_actions'])} position action(s), "
              f"{len(plan['failures'])} failure(s).")
        return 0

    trade_history = TradeHistoryService(persist_path=TRADE_HISTORY_PATH)
    run_execute(broker, plan, positions, trade_history, dry_run, equity_fraction,
                starting_capital, min_capital_floor, today)
    plan["executed_on"] = today.isoformat()
    _write_plan(plan)
    print(f"Execute done for plan bars_as_of={plan['bars_as_of']} dry_run={dry_run}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
