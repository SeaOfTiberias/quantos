#!/usr/bin/env python3
"""
QuantOS — F&O Option-Buy Candidate Screener (evening, Telegram)
────────────────────────────────────────────────────────────────
Screening aid for DISCRETIONARY call/put buys -- places no orders. After
the close it ranks the stock F&O universe for call and put setups
(core/fno_screener/screener.py), names one slightly-ITM contract per name
that passes liquidity and the per-lot cost cap, and sends the top
candidates to Telegram with the trade watcher's exit levels pre-computed.
You place the trade yourself; scripts/run_trade_watcher.py takes over.

Data:
  - NSE F&O bhavcopy (archive host, no auth): the F&O universe, futures OI
    for the build-up check, every stock option's close / OI / volume.
    Today's file is published some time after the close, so the script
    waits for it (up to --wait-minutes) once Fyers shows today was a
    session.
  - Fyers daily bars (~400 days, chunked) for the setup logic.

Writes ~/.quantos/fno_screener_latest.json and appends each run to
~/.quantos/fno_screener_history.jsonl, so how the candidates actually
played out can be checked later.

Usage:
    python scripts/run_fno_screener.py                  # VM timer, ~18:15 IST
    python scripts/run_fno_screener.py --no-telegram    # print only
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import sys
import time
from datetime import date, datetime, time as dtime, timedelta, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.main import load_config  # noqa: E402
from core.brokers import get_broker  # noqa: E402
from core.fno_screener.bhavcopy import FnoDay, parse_fno_day  # noqa: E402
from core.fno_screener.screener import (  # noqa: E402
    IST, Candidate, ScreenerConfig, ScreenResult, bar_date, build_candidates, format_telegram,
)
from core.options.fyers_symbol_master import SymbolMasterError, resolve_option_symbol  # noqa: E402
from core.options.vrp.bhavcopy import BhavcopyNotAvailable, fetch_raw  # noqa: E402
from core.trade_watcher.rules import ExitRules  # noqa: E402

QUANTOS_DIR = Path.home() / ".quantos"
BHAVCOPY_DIR = QUANTOS_DIR / "nse_fo_bhavcopy"
LATEST_PATH = QUANTOS_DIR / "fno_screener_latest.json"
HISTORY_PATH = QUANTOS_DIR / "fno_screener_history.jsonl"
BHAVCOPY_KEEP_DAYS = 21
FETCH_WINDOW_DAYS = 400          # > 252 sessions for the 52-week-high window
REFERENCE_SYMBOL = "RELIANCE"    # tells us whether today was a session
SESSION_FINAL_AT = dtime(15, 45)  # IST; before this today's daily bar is still forming
TELEGRAM_LIMIT = 3900            # Telegram caps a message at 4096 chars


# ─── Bhavcopy ────────────────────────────────────────────────────────────────

def _fetch_day(d: date) -> Optional[FnoDay]:
    try:
        return parse_fno_day(fetch_raw(d, BHAVCOPY_DIR), d)
    except BhavcopyNotAvailable:
        return None


def _wait_for_day(d: date, wait_minutes: int) -> Optional[FnoDay]:
    deadline = time.monotonic() + wait_minutes * 60
    while True:
        day = _fetch_day(d)
        if day is not None or time.monotonic() >= deadline:
            return day
        print(f"F&O bhavcopy for {d} not published yet -- retrying in 10 min.", flush=True)
        time.sleep(600)


def _past_day(trade_date: date, sessions_back: int) -> Optional[FnoDay]:
    """The bhavcopy `sessions_back` sessions before trade_date (404 = holiday/weekend)."""
    d, found = trade_date, 0
    for _ in range(sessions_back * 3 + 10):
        d -= timedelta(days=1)
        if d.weekday() >= 5:
            continue
        try:
            raw = fetch_raw(d, BHAVCOPY_DIR)
        except BhavcopyNotAvailable:
            continue
        found += 1
        if found == sessions_back:
            return parse_fno_day(raw, d)
    return None


def _prune_cache() -> None:
    cutoff = time.time() - BHAVCOPY_KEEP_DAYS * 86400
    for f in BHAVCOPY_DIR.glob("*.zip"):
        if f.stat().st_mtime < cutoff:
            f.unlink(missing_ok=True)


# ─── Bars ────────────────────────────────────────────────────────────────────

async def _fetch_bars(broker, symbols: list[str], through: date) -> dict:
    from scripts.validate_regime_classifier import fetch_chunked_daily

    to_dt = datetime.now(timezone.utc)
    from_dt = to_dt - timedelta(days=FETCH_WINDOW_DAYS)
    # One request at a time (~2/s with fetch_chunked_daily's 0.5 s delay):
    # leaves headroom under Fyers' per-minute cap for the trade watcher's
    # quote polling if this is ever run during market hours.
    sem = asyncio.Semaphore(1)
    out = {}
    for symbol in symbols:
        candles = await fetch_chunked_daily(broker, symbol, from_dt, to_dt, sem)
        by_date = {bar_date(c): c for c in candles if bar_date(c) <= through}   # chunk overlaps collapse here
        if by_date:
            out[symbol] = [by_date[d] for d in sorted(by_date)]
    return out


# ─── Output ──────────────────────────────────────────────────────────────────

def _with_fyers_symbols(cands: list[Candidate]) -> list[Candidate]:
    out = []
    for c in cands:
        q = c.contract.quote
        try:
            sym = resolve_option_symbol(q.symbol, q.expiry, q.strike, q.option_type).symbol
            c = dataclasses.replace(c, contract=dataclasses.replace(c.contract, fyers_symbol=sym))
        except (SymbolMasterError, OSError) as e:
            print(f"  {q.symbol}: Fyers symbol lookup failed ({e}) -- showing a readable name instead.")
        out.append(c)
    return out


def _jsonable(obj):
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if hasattr(obj, "value"):
        return obj.value
    raise TypeError(type(obj))


def _save(result: ScreenResult) -> None:
    record = {"generated_at": datetime.now(timezone.utc).isoformat(), **dataclasses.asdict(result)}
    text = json.dumps(record, default=_jsonable)
    LATEST_PATH.write_text(json.dumps(record, default=_jsonable, indent=2))
    with HISTORY_PATH.open("a") as f:
        f.write(text + "\n")


def _chunks(text: str, limit: int = TELEGRAM_LIMIT) -> list[str]:
    """Split on blank lines (whole candidate blocks stay together)."""
    out, cur = [], ""
    for block in text.split("\n\n"):
        if cur and len(cur) + len(block) + 2 > limit:
            out.append(cur)
            cur = block
        else:
            cur = f"{cur}\n\n{block}" if cur else block
    if cur:
        out.append(cur)
    return out


def _send(text: str) -> bool:
    from cloud.api.notifier import send_telegram
    return all([asyncio.run(send_telegram(part)) for part in _chunks(text)])


# ─── Main ────────────────────────────────────────────────────────────────────

def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="agent/config.yaml")
    ap.add_argument("--no-telegram", action="store_true")
    ap.add_argument("--wait-minutes", type=int, default=150,
                    help="how long to wait for today's bhavcopy to be published")
    args = ap.parse_args(argv)

    config = load_config(args.config)
    raw_cfg = config.get("fno_screener", {}) or {}
    if not raw_cfg.get("enabled", False):
        print("fno_screener.enabled is false in agent/config.yaml -- nothing to do.")
        return 0
    cfg = ScreenerConfig.from_config(raw_cfg)
    rules = ExitRules.from_config(config.get("trade_watcher", {}))

    broker = get_broker(config)
    if not broker.connect():
        print("ERROR: broker connect() failed -- check the Fyers token.")
        return 1

    # The session to screen = the latest daily bar Fyers has (today after a
    # trading day, else the last session). Its bhavcopy must exist.
    today = datetime.now(IST).date()
    ref = broker.get_historical_data(REFERENCE_SYMBOL, "1d",
                                     datetime.now(timezone.utc) - timedelta(days=10), datetime.now(timezone.utc))
    if not ref:
        print(f"ERROR: no recent daily bars for {REFERENCE_SYMBOL}.")
        return 1
    sessions = sorted({bar_date(c) for c in ref})
    if sessions[-1] == today and datetime.now(IST).time() < SESSION_FINAL_AT:
        sessions.pop()                                  # run before the close: use the last full session
    trade_date = sessions[-1]
    BHAVCOPY_DIR.mkdir(parents=True, exist_ok=True)
    day = _wait_for_day(trade_date, args.wait_minutes if trade_date == today else 0)
    if day is None:
        print(f"ERROR: no F&O bhavcopy for {trade_date} after waiting {args.wait_minutes} min.")
        return 1
    past = _past_day(trade_date, cfg.oi_lookback_sessions)
    if past is None:
        print("WARNING: no lookback bhavcopy -- OI build-up shown as n/a.")
    _prune_cache()

    symbols = day.symbols
    print(f"Screening {len(symbols)} F&O stocks, session {trade_date} "
          f"(OI vs {past.trade_date if past else 'n/a'}).", flush=True)
    bars = asyncio.run(_fetch_bars(broker, symbols, trade_date))
    missing = sorted(set(symbols) - set(bars))
    if missing:
        print(f"No bars for {len(missing)}: {', '.join(missing[:15])}{' ...' if len(missing) > 15 else ''}")

    result = build_candidates(bars, day, past, cfg)
    result.calls = _with_fyers_symbols(result.calls)
    result.puts = _with_fyers_symbols(result.puts)
    _save(result)

    message = format_telegram(result, rules, cfg)
    print(message)
    if not args.no_telegram and not _send(message):
        print("ERROR: Telegram send failed (credentials missing or API error) -- see warnings above.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
