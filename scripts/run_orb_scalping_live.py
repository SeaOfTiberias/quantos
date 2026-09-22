#!/usr/bin/env python3
"""
QuantOS — Candidate 18 ORB Scalping: Live Execution (layer 2)
──────────────────────────────────────────────────────────────────────
Also runs Candidate 18b via `--variant filtered`
(docs/ORB_ENTRY_FILTER_METHODOLOGY.md) -- 18b is 18's own signal with an
entry gate layered on top, a distinct strategy in its own right (own
config block, own position store, own dry-run log), ALONGSIDE unfiltered
18, never instead of it. Default `--variant unfiltered` is candidate 18
exactly as pre-registered, unchanged.

docs/ORB_EXECUTION_LAYER_DESIGN.md's layer 2: the ORB-specific tactics
that tell layer 1 (core/execution/order_service.py) when and what to
trade, and feed it exit conditions. Gated by agent/config.yaml's
`orb_scalping.{enabled,dry_run}` (18) / `orb_scalping_filtered.
{enabled,dry_run}` (18b) -- both blocks default to the safest setting
(enabled: false, dry_run: true) and stay there until each strategy's own
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
  2. No tracked position + state says "in_position" + this underlying hasn't
     already had its one trade today (core/orb_scalping/live_positions.py's
     ORB_TRADED_TODAY_PATH, checked independently of compute_live_state()'s own
     candle-lagged status -- see has_traded_today()'s docstring for why): resolve
     ATM strike -> expiry -> tradeable symbol -> order_service.enter_position()
     (places a MARKET entry + a real resting SL_M at the fixed 25%-of-premium
     stop) -> persist an OrbOpenPosition and mark the underlying traded for today.
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
     TradeHistoryService and removes the OrbOpenPosition -- but NOT the
     traded-today mark, which persists for the rest of the day (candidate 18
     is "one trade per day, first breakout only", core/orb_scalping/signal.py's
     simulate_day() docstring).

Usage:
    python scripts/run_orb_scalping_live.py
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

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
from core.orb_scalping.dry_run_log import (  # noqa: E402
    DryRunTrade,
    ORB_DRY_RUN_LOG_FILTERED_PATH,
    append_dry_run_trade,
)
from core.orb_scalping.entry_filter import (  # noqa: E402
    banknifty_entry_allowed,
    nifty_entry_allowed,
)
from core.orb_scalping.live_positions import (  # noqa: E402
    ORB_OPEN_POSITIONS_FILTERED_PATH,
    ORB_TRADED_TODAY_FILTERED_PATH,
    OrbOpenPosition,
    add_position,
    get_position,
    has_traded_today,
    load_open_positions,
    load_traded_today,
    mark_traded_today,
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

# Type of the per-underlying entry gate docs/ORB_ENTRY_FILTER_METHODOLOGY.md
# adds for the `--variant filtered` sibling: (trade_date, today's first 5m
# candle's open) -> allowed. Uniform shape across both mined predicates so
# process_underlying/(_enter_new_position) never need to know which
# underlying they belong to -- NIFTY's ignores the open, BankNifty's
# (built as a closure in main(), prior_daily_close already captured)
# ignores the date.
EntryFilter = Callable[[date, float], bool]


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
                         positions: dict, trade_date_iso: str, now_utc: datetime,
                         traded_today: set, positions_path: Optional[Path] = None,
                         traded_today_path: Optional[Path] = None) -> None:
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
    add_position(positions, position, path=positions_path)
    mark_traded_today(traded_today, underlying, trade_date_iso, path=traded_today_path)
    print(f"  {underlying}: ENTERED {state.direction} strike={strike} expiry={expiry} "
          f"premium={entry_premium} qty={quantity} dry_run={dry_run}")


def _close_out(underlying: str, existing: OrbOpenPosition, exit_price: Optional[float],
                exit_timestamp, reason: str, positions: dict,
                trade_history: TradeHistoryService, positions_path: Optional[Path] = None) -> None:
    if exit_price is None:
        print(f"  {underlying}: position closed but no exit price could be determined "
              f"(reason={reason}) -- removing from tracking without a ClosedTrade record.")
        remove_position(positions, underlying, existing.trade_date, path=positions_path)
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
    remove_position(positions, underlying, existing.trade_date, path=positions_path)
    print(f"  {underlying}: CLOSED reason={reason} exit_price={exit_price} pnl={trade.pnl:.2f}")


def _manage_existing_position(broker, underlying: str, spot_symbol: str, state,
                               existing: OrbOpenPosition, dry_run: bool, positions: dict,
                               trade_history: TradeHistoryService, now_utc: datetime,
                               positions_path: Optional[Path] = None,
                               dry_run_log_path: Optional[Path] = None) -> None:
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
                       reason, positions, trade_history, positions_path=positions_path)
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
            # place in it). A best-effort live quote is still captured for
            # core/orb_scalping/dry_run_log.py's own separate, lower-stakes
            # record -- observability only, never fed into sizing -- since
            # otherwise a dry-run close leaves no queryable price at all.
            exit_premium = None
            try:
                exit_premium = broker.get_ltp([existing.option_symbol]).get(existing.option_symbol)
            except Exception as e:
                print(f"  {underlying}: could not fetch exit quote for the dry-run log ({e}).")
            append_dry_run_trade(DryRunTrade(
                underlying=underlying, direction=existing.direction,
                entry_timestamp=existing.entry_timestamp, entry_premium=existing.entry_premium,
                exit_timestamp=now_utc.isoformat(), exit_reason=reason,
                quantity=existing.quantity, exit_premium=exit_premium,
            ), path=dry_run_log_path)
            print(f"  {underlying}: [dry_run] would exit reason={reason} -- "
                  f"removing from tracking, no ClosedTrade recorded.")
            remove_position(positions, underlying, existing.trade_date, path=positions_path)
        else:
            _close_out(underlying, existing, flat_result.fill_price, now_utc, reason, positions,
                       trade_history, positions_path=positions_path)
        return

    # Still open, nothing forced this fire -- refresh the persisted
    # index-level trailing state for observability (does not drive any
    # broker call, see the docstring above).
    if state.status == "in_position" and state.current_stop is not None:
        update_stops(positions, underlying, existing.trade_date,
                     current_index_stop=state.current_stop, armed=state.armed,
                     path=positions_path)


def process_underlying(broker, underlying: str, spot_symbol: str, dte_floor_days: int,
                        strike_interval: float, lots_per_trade: int, dry_run: bool,
                        positions: dict, trade_history: TradeHistoryService,
                        traded_today: set, entry_filter: Optional[EntryFilter] = None,
                        positions_path: Optional[Path] = None,
                        traded_today_path: Optional[Path] = None,
                        dry_run_log_path: Optional[Path] = None) -> None:
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
        # core/orb_scalping/signal.py::simulate_day() is explicit: "one trade per day,
        # first breakout only". This check enforces the same rule live, from a source
        # of truth (ORB_TRADED_TODAY_PATH, set at entry) that a live-side force-exit
        # can't invalidate -- unlike compute_live_state()'s own candle-close-only
        # replay, which lags any live-LTP-speed exit (index-stop or session-flatten)
        # by up to one candle and, without this check, briefly still reports
        # "in_position" right after such an exit, letting the same breakout be
        # re-entered as if it were new. Caught live 2026-09-10 (session-flatten path)
        # and again 2026-09-11 (index-stop path) -- this replaces the narrower
        # session-flatten-only wall-clock guard the first fix added, since that was a
        # special case of this same rule.
        if state.status != "in_position" or has_traded_today(traded_today, underlying, trade_date_iso):
            return
        # docs/ORB_ENTRY_FILTER_METHODOLOGY.md's --variant filtered gate --
        # None (unfiltered candidate 18, the only variant that has ever
        # placed a real order) always allows, reproducing every existing
        # caller's behaviour exactly. `closed` is guaranteed non-empty here:
        # state.status == "in_position" requires a breakout after the
        # opening range, which itself requires OPENING_RANGE_CANDLES closed
        # bars to exist.
        if entry_filter is not None and not entry_filter(trade_date, closed[0].open):
            print(f"  {underlying}: entry filtered out for {trade_date_iso} "
                  f"(docs/ORB_ENTRY_FILTER_METHODOLOGY.md)")
            return
        _enter_new_position(broker, underlying, state, dte_floor_days, strike_interval,
                             lots_per_trade, dry_run, positions, trade_date_iso, now_utc,
                             traded_today, positions_path=positions_path,
                             traded_today_path=traded_today_path)
        return

    _manage_existing_position(broker, underlying, spot_symbol, state, existing, dry_run,
                               positions, trade_history, now_utc, positions_path=positions_path,
                               dry_run_log_path=dry_run_log_path)


def _fetch_prior_daily_close(broker, spot_symbol: str, today: date) -> Optional[float]:
    """Most recent daily close strictly before `today`. A small (14
    calendar-day) window comfortably covers any run of holidays/weekends
    -- this is the SAME data core/orb_scalping/conditions.py::gap_pct was
    mined against, fetched fresh each fire since only --variant filtered
    calls this at all, and only for BankNifty (NIFTY's filter needs no
    daily data). Returns None (never raises past this point) if the
    fetch fails or returns nothing usable -- see
    core/orb_scalping/entry_filter.py::banknifty_entry_allowed for why a
    missing prior close means "not a gap day", not a crash."""
    try:
        from_dt = datetime.combine(today - timedelta(days=14), datetime.min.time(), tzinfo=timezone.utc)
        to_dt = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc)
        daily = broker.get_historical_data(spot_symbol, "1d", from_dt, to_dt)
    except Exception as e:
        print(f"  could not fetch prior daily close for {spot_symbol} ({e}) -- "
              f"gap filter will treat today as not a gap day.")
        return None
    prior = [c for c in daily if c.timestamp.date() < today]
    if not prior:
        return None
    return sorted(prior, key=lambda c: c.timestamp)[-1].close


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--variant", choices=["unfiltered", "filtered"], default="unfiltered",
        help="'unfiltered' (default) is candidate 18 exactly as pre-registered -- the only "
             "variant that has ever placed a real order. 'filtered' is CANDIDATE 18b "
             "(docs/ORB_ENTRY_FILTER_METHODOLOGY.md): same signal, gated to NIFTY "
             "Monday/Friday and BankNifty big-gap-day entries only, its own config block "
             "(orb_scalping_filtered), its own position store and dry-run log -- it runs "
             "ALONGSIDE unfiltered candidate 18, never in place of it.",
    )
    args = parser.parse_args(argv)
    filtered = args.variant == "filtered"

    config = load_config("agent/config.yaml")
    config_key = "orb_scalping_filtered" if filtered else "orb_scalping"
    orb_cfg = config.get(config_key, {})
    if not orb_cfg.get("enabled", False):
        print(f"{config_key}.enabled is false in agent/config.yaml -- nothing to do.")
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

    positions_path = ORB_OPEN_POSITIONS_FILTERED_PATH if filtered else None
    traded_today_path = ORB_TRADED_TODAY_FILTERED_PATH if filtered else None
    dry_run_log_path = ORB_DRY_RUN_LOG_FILTERED_PATH if filtered else None

    # trade_history.json stays shared/unparametrized: dry_run never writes to
    # it (see _manage_existing_position's dry_run branch), and this project's
    # standing gate means neither variant will flip dry_run:false without a
    # fresh, separate go-ahead -- if that ever happens the shared file
    # becomes a real question, not one this document needs to answer today.
    trade_history = TradeHistoryService(persist_path=TRADE_HISTORY_PATH)
    positions = load_open_positions(path=positions_path)
    traded_today = load_traded_today(path=traded_today_path)

    # Fetched ONCE per fire, not per underlying -- NIFTY's filter needs no
    # daily data at all, and BankNifty needs at most one prior close.
    prior_banknifty_close = (
        _fetch_prior_daily_close(broker, "NIFTY BANK", datetime.now(timezone.utc).date())
        if filtered else None
    )

    for underlying, spot_symbol, strike_interval in UNDERLYINGS:
        entry_filter: Optional[EntryFilter] = None
        if filtered:
            if underlying == "NIFTY":
                entry_filter = lambda trade_date, _open: nifty_entry_allowed(trade_date)  # noqa: E731
            else:
                entry_filter = (
                    lambda _trade_date, first_open, _prior=prior_banknifty_close:
                    banknifty_entry_allowed(first_open, _prior)
                )  # noqa: E731
        try:
            process_underlying(broker, underlying, spot_symbol, dte_floor_days[underlying],
                                strike_interval, lots_per_trade, dry_run, positions, trade_history,
                                traded_today, entry_filter=entry_filter,
                                positions_path=positions_path, traded_today_path=traded_today_path,
                                dry_run_log_path=dry_run_log_path)
        except Exception as e:
            print(f"  {underlying}: fire failed ({e}) -- self-healing, will retry next fire.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
