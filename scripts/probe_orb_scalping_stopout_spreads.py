#!/usr/bin/env python3
"""
QuantOS — Candidate 18 Event-Triggered Stop-Out Spread Probe
──────────────────────────────────────────────────────────────────────
Read-only. No orders, ever. Zero capital at risk.

Every spread sample this project has taken so far (scripts/probe_orb_
scalping_real_spreads.py) is on a fixed 3x/day clock during calm market
moments -- but this strategy's real exits are stop-outs, which by nature
happen during fast-market moments the fixed clock never observes. This
script closes that gap: it watches the live ORB signal during market
hours using core/orb_scalping/live_state.py (the same opening-range/
trailing-stop rules core/orb_scalping/signal.py already has 1977 tests
covering, replayed against TODAY's still-growing candle list instead of
a complete historical day), and the INSTANT a stop-out condition would
fire -- either the index-level trailing stop or the 25%-of-entry-premium
secondary stop from core/orb_scalping/premium.py -- it snapshots the
REAL bid-ask spread on the actual option contract at that exact moment.
No BS-reconstructed premium: the entry premium is captured from a real
live quote the moment a position is first observed, same as the exit.

Designed to run as a STATELESS oneshot fired every ~1 minute during NSE
market hours (deploy/systemd/quantos-orb-stopout-probe.{service,timer}),
not a standing process -- this VM OOM-killed itself twice on 2026-07-15
and every other job on it since has been a cheap, fail-silent oneshot
rather than a second always-on process
([[quantos_vm_oom_incident]]/[[quantos_orb_options_scalping_status]]
2026-09-03 handoff). Nothing is held in memory between fires: each run
re-derives "am I in a position, what's the current stop" from today's
already-closed 5-minute candles, and its OWN output log
(data_cache/orb_scalping_stopout_spread_samples.csv) doubles as the
cross-fire memory -- an "entry" row records the captured entry premium/
strike/expiry so later fires don't need to re-derive it, and an "exit"
row's presence is what stops a stop-out from being logged twice. A
missed fire (VM down, stale token) is harmless and self-healing, same
convention as every other probe/timer job on this VM.

1-minute polling catches a live stop-cross within roughly a minute of it
happening, not at the literal tick -- a disclosed fidelity tradeoff
against running a second always-on process on a box with an OOM history,
made explicitly with the user 2026-09-03 (see the memory above). A
candle that has ALREADY closed past the stop (state.exit_reason in
"stop"/"trailing_stop") is also treated as a trigger, as a fallback for a
missed fire -- but a plain "session_flatten" (reaching 15:20 IST with no
stop ever touched) is explicitly NOT a stop-out and is never logged: that
would just reintroduce the fixed-clock probe's own "calm moment, not a
stop-out moment" contamination.

Usage:
    python scripts/probe_orb_scalping_stopout_spreads.py
    python scripts/probe_orb_scalping_stopout_spreads.py --summarize
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.main import load_config  # noqa: E402
from core.brokers import get_broker  # noqa: E402
from core.options import fyers_symbol_master as sm  # noqa: E402
from core.orb_scalping.backtest import (  # noqa: E402
    BANKNIFTY_STRIKE_INTERVAL,
    NIFTY_STRIKE_INTERVAL,
)
from core.orb_scalping.live_state import compute_live_state  # noqa: E402
from core.orb_scalping.premium import PREMIUM_STOP_PCT, atm_strike  # noqa: E402
from scripts.probe_orb_scalping_real_spreads import select_expiry  # noqa: E402

NIFTY_DTE_FLOOR_DAYS = 2   # core/orb_scalping/backtest.py's resolve_nifty_expiry
BANKNIFTY_DTE_FLOOR_DAYS = 0  # resolve_banknifty_expiry has no floor

LOG_PATH = Path("data_cache/orb_scalping_stopout_spread_samples.csv")
LOG_FIELDS = [
    "sampled_at_utc", "trade_date", "underlying", "event", "direction",
    "strike", "expiry", "dte", "option_type",
    "entry_premium", "premium_stop_level", "entry_timestamp_utc",
    "spot_at_event", "stop_level_at_event", "minutes_since_entry",
    "trigger_reason", "bid", "ask", "ltp", "spread_pct_of_mid",
]

UNDERLYINGS = [
    # (underlying, spot_symbol, dte_floor_days, strike_interval)
    ("NIFTY", "NIFTY 50", NIFTY_DTE_FLOOR_DAYS, NIFTY_STRIKE_INTERVAL),
    ("BANKNIFTY", "NIFTY BANK", BANKNIFTY_DTE_FLOOR_DAYS, BANKNIFTY_STRIKE_INTERVAL),
]


# ─── Log read/write helpers (the log doubles as this stateless script's memory) ──

def _load_today_rows(underlying: str, trade_date: date) -> list[dict]:
    if not LOG_PATH.exists():
        return []
    rows = csv.DictReader(LOG_PATH.open(newline="", encoding="utf-8"))
    return [r for r in rows if r["underlying"] == underlying and r["trade_date"] == trade_date.isoformat()]


def _find_event(rows: list[dict], event: str) -> dict | None:
    matches = [r for r in rows if r["event"] == event]
    return matches[0] if matches else None


def _append_row(writer: csv.DictWriter, row: dict) -> None:
    writer.writerow(row)


# ─── Option chain lookup at a fixed (already-decided) strike ────────────────

def _fetch_chain_row(broker, underlying: str, expiry: date, strike: float, option_type: str,
                      strike_interval: float) -> dict | None:
    """Nearest row to `strike` for the given option_type -- tolerant match
    (within half a strike interval) rather than an exact float equality
    check, same defensive spirit as scripts/probe_orb_scalping_real_
    spreads.py's _atm_rows(), just pinned to a specific strike instead of
    nearest-to-spot (this strike was fixed at entry and never re-struck,
    per core/orb_scalping/premium.py's atm_strike() contract)."""
    expiry_epoch = sm.get_expiry_epoch(underlying, expiry)
    raw_chain = broker.get_option_chain(underlying, expiry_epoch)
    rows = raw_chain.get("optionsChain", [])
    candidates = [r for r in rows if r.get("option_type") == option_type]
    if not candidates:
        return None
    nearest = min(candidates, key=lambda r: abs(r.get("strike_price", 0) - strike))
    if abs(nearest.get("strike_price", 0) - strike) > strike_interval / 2:
        return None
    return nearest


def decide_trigger(*, index_triggered: bool, candle_confirmed_stop: bool,
                    premium_triggered: bool, armed: bool,
                    candle_exit_reason: str | None) -> str | None:
    """Pure decision rule, factored out for unit testing without a broker.
    None means "still open, nothing to log yet". Priority mirrors core/
    orb_scalping/premium.py's own tie-break docstring ("if both the index-
    level exit and the 25% premium stop would trigger on the SAME candle,
    the premium stop takes precedence") for the one case where only the
    premium side fired; otherwise the index-level result (live-LTP cross,
    or the candle-close fallback) wins, since that's what a real broker-
    resident stop order actually executes on."""
    if not (index_triggered or candle_confirmed_stop or premium_triggered):
        return None
    if premium_triggered and not (index_triggered or candle_confirmed_stop):
        return "premium_stop"
    if candle_confirmed_stop and not index_triggered:
        return candle_exit_reason  # "stop" | "trailing_stop", candle-close fallback
    return "trailing_stop" if armed else "stop"


def _spread_fields(row: dict) -> dict:
    bid, ask, ltp = row.get("bid", 0), row.get("ask", 0), row.get("ltp", 0)
    mid = (bid + ask) / 2 if (bid and ask) else None
    spread_pct = (ask - bid) / mid * 100 if mid else None
    return {"bid": bid, "ask": ask, "ltp": ltp,
            "spread_pct_of_mid": round(spread_pct, 3) if spread_pct is not None else ""}


# ─── Per-underlying probe ────────────────────────────────────────────────────

def probe_underlying(broker, underlying: str, spot_symbol: str, dte_floor_days: int,
                      strike_interval: float, writer: csv.DictWriter) -> None:
    now_utc = datetime.now(timezone.utc)
    trade_date = now_utc.date()  # UTC calendar date == IST session date, project convention
    session_start_utc = datetime.combine(trade_date, time(3, 45), tzinfo=timezone.utc)

    candles = broker.get_historical_data(spot_symbol, "5m", session_start_utc, now_utc)
    closed = sorted(
        (c for c in candles if c.timestamp + timedelta(minutes=5) <= now_utc),
        key=lambda c: c.timestamp,
    )
    state = compute_live_state(closed)
    print(f"{underlying}: status={state.status} direction={state.direction} "
          f"stop={state.current_stop} armed={state.armed}")

    if state.status in ("forming_range", "no_breakout_yet", "pending_entry"):
        return

    today_rows = _load_today_rows(underlying, trade_date)
    entry_row = _find_event(today_rows, "entry")

    if entry_row is None:
        if state.status != "in_position":
            # Either an ordinary session_flatten (no stop-out to measure),
            # or a stop-out that already happened before this probe ever
            # captured a real entry premium -- e.g. every fire across the
            # whole life of the position was missed (VM down, stale
            # token). In that case there is no honest entry price left to
            # report; skip rather than fabricate one from a post-hoc
            # quote, which would silently mislabel a stale/unrelated
            # reading as this trade's entry premium.
            return
        # First observation of a live position today -- capture the real
        # entry premium now (a proxy for "at entry": up to ~1 minute of
        # drift from the actual breakout, the disclosed cost of 1-minute
        # polling -- see module docstring).
        strike = atm_strike(state.entry_price, strike_interval)
        expiries = sm.list_expiries(underlying)
        expiry = select_expiry(expiries, trade_date, dte_floor_days)
        if expiry is None:
            print(f"  {underlying}: no suitable expiry found, skipping entry capture.")
            return
        dte = (expiry - trade_date).days
        option_type = "CE" if state.direction == "CALL" else "PE"
        chain_row = _fetch_chain_row(broker, underlying, expiry, strike, option_type, strike_interval)
        if chain_row is None or not chain_row.get("ltp"):
            print(f"  {underlying}: no live quote for strike={strike} {option_type}, skipping entry capture.")
            return
        entry_premium = chain_row["ltp"]
        entry_row = {
            "sampled_at_utc": now_utc.isoformat(), "trade_date": trade_date.isoformat(),
            "underlying": underlying, "event": "entry", "direction": state.direction,
            "strike": strike, "expiry": expiry.isoformat(), "dte": dte, "option_type": option_type,
            "entry_premium": entry_premium,
            "premium_stop_level": round(entry_premium * (1 - PREMIUM_STOP_PCT), 4),
            "entry_timestamp_utc": now_utc.isoformat(),
            "spot_at_event": state.entry_price, "stop_level_at_event": state.current_stop,
            "minutes_since_entry": 0, "trigger_reason": "",
            **_spread_fields(chain_row),
        }
        _append_row(writer, entry_row)
        print(f"  {underlying}: ENTRY captured -- {state.direction} strike={strike} "
              f"expiry={expiry} premium={entry_premium}")

    if _find_event(today_rows, "exit") is not None:
        return  # already logged this stop-out earlier today

    strike = float(entry_row["strike"])
    expiry = date.fromisoformat(entry_row["expiry"])
    option_type = entry_row["option_type"]
    entry_premium = float(entry_row["entry_premium"])
    premium_stop_level = float(entry_row["premium_stop_level"])
    entry_timestamp = datetime.fromisoformat(entry_row["entry_timestamp_utc"])

    spot_ltp = broker.get_ltp([spot_symbol]).get(spot_symbol)
    chain_row = _fetch_chain_row(broker, underlying, expiry, strike, option_type, strike_interval)
    if chain_row is None:
        print(f"  {underlying}: no live quote for the held contract this fire, will retry next fire.")
        return

    index_triggered = state.current_stop is not None and spot_ltp is not None and (
        spot_ltp <= state.current_stop if entry_row["direction"] == "CALL" else spot_ltp >= state.current_stop
    )
    candle_confirmed_stop = state.status == "flattened" and state.exit_reason in ("stop", "trailing_stop")
    premium_triggered = bool(chain_row.get("ltp")) and chain_row["ltp"] <= premium_stop_level

    trigger_reason = decide_trigger(
        index_triggered=index_triggered, candle_confirmed_stop=candle_confirmed_stop,
        premium_triggered=premium_triggered, armed=state.armed,
        candle_exit_reason=state.exit_reason,
    )
    if trigger_reason is None:
        return  # still open, nothing to log yet

    minutes_since_entry = (now_utc - entry_timestamp).total_seconds() / 60.0
    exit_row = {
        "sampled_at_utc": now_utc.isoformat(), "trade_date": trade_date.isoformat(),
        "underlying": underlying, "event": "exit", "direction": entry_row["direction"],
        "strike": strike, "expiry": expiry.isoformat(), "dte": entry_row["dte"], "option_type": option_type,
        "entry_premium": entry_premium, "premium_stop_level": premium_stop_level,
        "entry_timestamp_utc": entry_row["entry_timestamp_utc"],
        "spot_at_event": spot_ltp, "stop_level_at_event": state.current_stop,
        "minutes_since_entry": round(minutes_since_entry, 1), "trigger_reason": trigger_reason,
        **_spread_fields(chain_row),
    }
    _append_row(writer, exit_row)
    print(f"  {underlying}: STOP-OUT captured -- reason={trigger_reason} "
          f"spread_pct_of_mid={exit_row['spread_pct_of_mid']}%")


def summarize_log() -> int:
    if not LOG_PATH.exists():
        print(f"No log yet at {LOG_PATH} -- run without --summarize first.")
        return 1
    rows = list(csv.DictReader(LOG_PATH.open(newline="", encoding="utf-8")))
    exits = [r for r in rows if r["event"] == "exit" and r["spread_pct_of_mid"]]
    print(f"{len(rows)} total logged rows "
          f"({len({r['trade_date'] for r in rows})} distinct trade days) from {LOG_PATH}\n")
    by_key: dict[tuple, list] = {}
    for r in exits:
        by_key.setdefault((r["underlying"], r["trigger_reason"]), []).append(float(r["spread_pct_of_mid"]))
    if not exits:
        print("No stop-out events captured yet.")
        return 0
    for (underlying, reason), pcts in sorted(by_key.items()):
        avg = sum(pcts) / len(pcts)
        print(f"{underlying} {reason}: n={len(pcts)}  mean spread_pct_of_mid={avg:.2f}%  "
              f"min={min(pcts):.2f}%  max={max(pcts):.2f}%")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--summarize", action="store_true", help="Print stats from the log so far, no live fetch.")
    args = parser.parse_args()

    if args.summarize:
        return summarize_log()

    config = load_config("agent/config.yaml")
    broker = get_broker(config)
    if not broker.connect():
        print("ERROR: broker connect() failed -- check the Fyers token.")
        return 1

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    is_new = not LOG_PATH.exists()
    with LOG_PATH.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=LOG_FIELDS)
        if is_new:
            writer.writeheader()
        for underlying, spot_symbol, dte_floor_days, strike_interval in UNDERLYINGS:
            try:
                probe_underlying(broker, underlying, spot_symbol, dte_floor_days, strike_interval, writer)
            except Exception as e:
                print(f"  {underlying}: probe fire failed ({e}) -- self-healing, will retry next fire.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
