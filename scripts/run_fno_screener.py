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

Each pick also gets debit spreads (core/fno_screener/spreads.py: bull call
for calls, bear put for puts), priced at the Fyers bid/ask when both legs
have a two-sided quote, else at bhavcopy closes and marked so. The spread
sized to the 5-session move is the primary line; the single option is shown
second and only if its own bid-ask passes the gate. NEAR setups go to a
watchlist with no contract. The Nifty-vs-EMA20 regime is a logged label.

Writes ~/.quantos/fno_screener_latest.json and appends each run to
~/.quantos/fno_screener_history.jsonl. Then rebuilds
~/.quantos/fno_screener_outcomes.json: every pick of the last
OUTCOME_LOOKBACK_DAYS tracked through its next 5 sessions from the cached
bhavcopies (core/fno_screener/outcomes.py). The cockpit's #/picks page reads
all three (cloud/api/fno_picks_routes.py).

Usage:
    python scripts/run_fno_screener.py                  # VM timer, ~18:15 IST
    python scripts/run_fno_screener.py --no-telegram    # print only (still logs the picks)
    python scripts/run_fno_screener.py --dry-run        # print only, write nothing
    python scripts/run_fno_screener.py --outcomes-only  # just rebuild the outcome log
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
from core.fno_screener.outcomes import pick_key, track_pick  # noqa: E402
from core.fno_screener.screener import (  # noqa: E402
    IST, Candidate, ScreenerConfig, ScreenResult, bar_date, bid_ask_pct, build_candidates, format_telegram,
    market_regime,
)
from core.fno_screener.spreads import build_spreads, spread_line  # noqa: E402
from core.marketdata.option_chain_recorder import parse_expiries  # noqa: E402
from core.options.models import OptionType  # noqa: E402
from core.options.fyers_symbol_master import SymbolMasterError, resolve_option_symbol  # noqa: E402
from core.options.vrp.bhavcopy import BhavcopyNotAvailable, fetch_raw  # noqa: E402
from core.trade_watcher.rules import ExitRules  # noqa: E402

QUANTOS_DIR = Path.home() / ".quantos"
BHAVCOPY_DIR = QUANTOS_DIR / "nse_fo_bhavcopy"
LATEST_PATH = QUANTOS_DIR / "fno_screener_latest.json"
HISTORY_PATH = QUANTOS_DIR / "fno_screener_history.jsonl"
OUTCOMES_PATH = QUANTOS_DIR / "fno_screener_outcomes.json"
OUTCOME_LOOKBACK_DAYS = 20       # a pick is complete after 5 sessions; inside the 21-day bhavcopy cache
CHAIN_STRIKES = 15               # strikes each side of ATM in a Fyers option-chain call
CHAIN_SPACING_S = 0.4
BHAVCOPY_KEEP_DAYS = 21
FETCH_WINDOW_DAYS = 400          # > 252 sessions for the 52-week-high window
REFERENCE_SYMBOL = "RELIANCE"    # tells us whether today was a session
MARKET_SYMBOL = "NIFTY"          # Nifty 50 index, for the regime label
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


def _results_dates(cands: list, trade_date) -> dict:
    """{symbol: next results date} from the NSE results calendar; {} if it can't be read."""
    try:
        from core.ideas import events
        cal = events.refresh(events.DEFAULT_PATH)
        out = {}
        for c in cands:
            d = events.next_results(cal, c.symbol, trade_date)
            if d:
                out[c.symbol] = d
        return out
    except Exception as e:                                   # never let the calendar block tonight's message
        print(f"WARNING: results calendar unavailable: {e}")
        return {}


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


# ─── Spreads ─────────────────────────────────────────────────────────────────

def _chain_quotes(client, fyers_symbol_fn, symbol: str, expiry: date, side: OptionType) -> dict:
    """strike -> (bid, ask) for one expiry and side, or {} on any failure.
    Two calls: the first lists the expiries (and their epochs)."""
    def call(epoch: str = "") -> dict:
        resp = client.optionchain(data={"symbol": fyers_symbol_fn(symbol), "strikecount": CHAIN_STRIKES,
                                        "timestamp": epoch})
        time.sleep(CHAIN_SPACING_S)
        return (resp.get("data") or {}) if resp.get("code") == 200 else {}
    try:
        first = call()
        epoch = next((ep for d, ep, _ in parse_expiries(first) if d == expiry), None)
        if epoch is None:
            return {}
        data = call(epoch)
    except Exception as e:                                   # quotes are optional; close prices still work
        print(f"  {symbol}: option chain failed ({e}) -- spreads priced at bhavcopy closes.")
        return {}
    return {float(r.get("strike_price") or 0): (float(r.get("bid") or 0), float(r.get("ask") or 0))
            for r in data.get("optionsChain", []) or [] if r.get("option_type") == side.value}


def _quotes_for(cands: list[Candidate], broker) -> dict:
    """(side, symbol) -> {strike: (bid, ask)} on each pick's expiry; {} when unavailable."""
    from core.brokers.fyers import _fyers_symbol
    client = getattr(broker, "_client", None)
    return {(c.side.value, c.symbol): (_chain_quotes(client, _fyers_symbol, c.symbol, c.contract.quote.expiry, c.side)
                                       if client else {})
            for c in cands}


def _with_bid_ask(cands: list[Candidate], quotes: dict) -> list[Candidate]:
    """Stamp the single option's own bid-ask % (the gate is applied in format_telegram)."""
    out = []
    for c in cands:
        ba = bid_ask_pct(quotes.get((c.side.value, c.symbol), {}).get(c.contract.quote.strike))
        out.append(dataclasses.replace(c, contract=dataclasses.replace(c.contract, bid_ask_pct=ba)))
    return out


def _spreads_for(cands: list[Candidate], day: FnoDay, quotes: dict) -> dict:
    """(side, symbol) -> SpreadSet, for the picks that have one."""
    out = {}
    for c in cands:
        q = c.contract.quote
        s = build_spreads(day, c.symbol, c.side, q.expiry, q.strike, c.contract.dte, c.contract.iv,
                          quotes.get((c.side.value, c.symbol), {}))
        if s is not None:
            out[(c.side.value, c.symbol)] = s
    return out


def _market(broker, trade_date: date):
    """Nifty close vs EMA20 as of trade_date, or None (a label; never blocks the run)."""
    try:
        now = datetime.now(timezone.utc)
        bars = broker.get_historical_data(MARKET_SYMBOL, "1d", now - timedelta(days=90), now) or []
        bars = sorted((c for c in bars if bar_date(c) <= trade_date), key=lambda c: c.timestamp)
        return market_regime(bars)
    except Exception as e:
        print(f"WARNING: Nifty regime unavailable ({e}).")
        return None


# ─── Outcomes ────────────────────────────────────────────────────────────────

def _days_after(trade_date: date, through: date, cache: dict) -> list[FnoDay]:
    """Bhavcopy days after trade_date and before `through`, at most 5."""
    out, d = [], trade_date
    while len(out) < 5:
        d += timedelta(days=1)
        if d >= through:
            break
        if d.weekday() >= 5:
            continue
        if d not in cache:
            cache[d] = _fetch_day(d)
        if cache[d] is not None:
            out.append(cache[d])
    return out


def _update_outcomes(through: date) -> int:
    """Rebuild the outcome record of every unfinished pick of the last
    OUTCOME_LOOKBACK_DAYS; complete records are kept as they are."""
    try:
        existing = json.loads(OUTCOMES_PATH.read_text())
    except (OSError, ValueError):
        existing = {}
    if not HISTORY_PATH.exists():
        return 0
    records = {}
    for line in HISTORY_PATH.read_text().splitlines():          # a re-run of a day replaces its picks
        if line.strip():
            r = json.loads(line)
            records[r["trade_date"]] = r
    cutoff = through - timedelta(days=OUTCOME_LOOKBACK_DAYS)
    cache: dict = {}
    n = 0
    for td, r in sorted(records.items()):
        trade_date = date.fromisoformat(td)
        if trade_date < cutoff:
            continue
        for cand in r.get("calls", []) + r.get("puts", []):
            key = pick_key(td, cand["side"], cand["symbol"])
            if existing.get(key, {}).get("complete"):
                continue
            if not cand.get("spreads"):                          # logged before spreads existed: rebuild from closes
                if trade_date not in cache:
                    cache[trade_date] = _fetch_day(trade_date)
                pick_day, q = cache[trade_date], cand["contract"]["quote"]
                s = pick_day and build_spreads(pick_day, cand["symbol"], OptionType(cand["side"]),
                                               date.fromisoformat(q["expiry"]), float(q["strike"]),
                                               cand["contract"]["dte"], cand["contract"].get("iv"))
                cand = {**cand, "spreads": dataclasses.asdict(s) if s else None}
            existing[key] = track_pick(td, cand, _days_after(trade_date, through, cache))
            n += 1
    OUTCOMES_PATH.write_text(json.dumps(existing, default=_jsonable))
    return n


def _save(result: ScreenResult, spreads: Optional[dict] = None) -> None:
    record = {"generated_at": datetime.now(timezone.utc).isoformat(), **dataclasses.asdict(result)}
    for cand in record["calls"] + record["puts"]:
        s = (spreads or {}).get((cand["side"].value, cand["symbol"]))
        cand["spreads"] = dataclasses.asdict(s) if s else None
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
    ap.add_argument("--dry-run", action="store_true",
                    help="print only: no Telegram, no history/latest/outcome writes (safe to re-run a logged day)")
    ap.add_argument("--wait-minutes", type=int, default=150,
                    help="how long to wait for today's bhavcopy to be published")
    ap.add_argument("--outcomes-only", action="store_true",
                    help="rebuild ~/.quantos/fno_screener_outcomes.json from the history and exit")
    args = ap.parse_args(argv)

    if args.outcomes_only:
        BHAVCOPY_DIR.mkdir(parents=True, exist_ok=True)
        n = _update_outcomes(datetime.now(IST).date() + timedelta(days=1))
        print(f"Outcome log rebuilt: {n} pick(s) updated -> {OUTCOMES_PATH}")
        return 0

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
    result.market = _market(broker, trade_date)
    quotes = _quotes_for(result.calls + result.puts, broker)
    result.calls = _with_bid_ask(_with_fyers_symbols(result.calls), quotes)
    result.puts = _with_bid_ask(_with_fyers_symbols(result.puts), quotes)
    spreads = _spreads_for(result.calls + result.puts, day, quotes)
    if not args.dry_run:
        _save(result, spreads)
        try:
            print(f"Outcome log: {_update_outcomes(trade_date + timedelta(days=1))} pick(s) updated.")
        except Exception as e:                                   # never let the log block tonight's message
            print(f"WARNING: outcome log update failed: {e}")

    lines = {k: line for k, s in spreads.items() if (line := spread_line(s))}
    message = format_telegram(result, rules, cfg, lines, _results_dates(result.calls + result.puts, trade_date))
    print(message)
    if not (args.no_telegram or args.dry_run) and not _send(message):
        print("ERROR: Telegram send failed (credentials missing or API error) -- see warnings above.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
