#!/usr/bin/env python3
"""
QuantOS — S8-2: Fyers Automation Trade-History Retrospective
────────────────────────────────────────────────────────────────
Analyses the user's REAL trade history from Fyers' built-in automation
(5-min EMA9/EMA21 crossover on NIFTY -> buy ATM/near-ATM CE on a bullish
cross, PE on a bearish cross -> exit at +/-Rs2000 P&L or 3:10pm). Answers,
against real fills (not a backtest approximation): how often would a
trailing stop have captured more than the fixed cap did, and how often did
a position ride to the loss cap after the crossover that triggered it had
already reversed.

Round trips are reconstructed from the raw tradebook (one row per fill, not
pre-paired) by matching each SELL to the earliest still-open BUY on the
same option contract, in chronological order. "Overnight"-product rows are
excluded from the primary trailing-stop/invalidation analysis: the
described strategy exits same-day at 3:10pm, so an overnight hold is a
manual override, not the automation's own exit rule -- reported separately,
not folded into the same stats.

The "faster invalidation exit" and "trailing stop" questions both need to
know what the underlying (and therefore the option) was doing WHILE each
trade was open -- the tradebook only has entry/exit fills, not the path in
between. This fetches real NIFTY 5-min candles spanning each trade's window
from the broker (small, fast fetch -- unlike S8-1's multi-year pull, this
is ~20 trades x a few hours each) and computes EMA9/EMA21 on them to check:
did the crossover that triggered entry reverse before the actual exit, and
what was the underlying's peak favourable move during the trade.

Usage:
    python scripts/analyze_s82_trade_history.py <tradebook.csv>
    python scripts/analyze_s82_trade_history.py <tradebook.csv> --out docs/S8_2_TRADE_HISTORY_ANALYSIS.md
"""

import argparse
import csv
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.main import load_config  # noqa: E402
from core.brokers.base import OHLCV  # noqa: E402
from core.regime.fetcher import _ema  # noqa: E402

_IST = timezone(timedelta(hours=5, minutes=30))
NIFTY_MIN_MOVE_FOR_GIVEBACK = 10.0  # points -- floor below which a giveback % is noise, not signal
OPTION_RE = re.compile(r"^NIFTY.*(CE|PE)$")


@dataclass
class Fill:
    symbol: str
    side: str          # BUY | SELL
    dt: datetime        # IST
    qty: float
    price: float
    product: str        # Intraday | Intraday BO | Overnight


@dataclass
class RoundTrip:
    symbol:       str
    entry_dt:     datetime
    exit_dt:      datetime
    qty:          float
    entry_price:  float
    exit_price:   float
    product:      str
    pnl:          float = field(init=False)
    hold_minutes: float = field(init=False)

    def __post_init__(self):
        self.pnl = (self.exit_price - self.entry_price) * self.qty
        self.hold_minutes = (self.exit_dt - self.entry_dt).total_seconds() / 60.0

    @property
    def is_win(self) -> bool:
        return self.pnl > 0

    @property
    def is_time_exit(self) -> bool:
        """Exited at/after 3:09pm IST -- the strategy's stated time-stop."""
        return self.exit_dt.time() >= datetime.strptime("15:09", "%H:%M").time()


def _parse_money(s: str) -> float:
    return float(s.replace(",", "").replace('"', "").strip() or "0")


def load_fills(csv_path: Path) -> list[Fill]:
    lines = csv_path.read_text(encoding="utf-8-sig").splitlines()
    header_idx = next(i for i, ln in enumerate(lines) if ln.startswith("Name,Date"))
    reader = csv.DictReader(lines[header_idx:])
    fills = []
    for row in reader:
        if row.get("Segment") != "Derivatives" or not OPTION_RE.match(row.get("Name", "")):
            continue
        dt = datetime.strptime(row["Date & time"], "%d %b %Y, %I:%M:%S %p").replace(tzinfo=_IST)
        fills.append(Fill(
            symbol=row["Name"], side=row["Side"], dt=dt,
            qty=_parse_money(row["Qty"]), price=_parse_money(row["Traded price"]),
            product=row["Product type"],
        ))
    return fills


def pair_round_trips(fills: list[Fill]) -> list[RoundTrip]:
    """Match each SELL to the earliest still-open BUY on the same symbol,
    processed in chronological order (FIFO per contract)."""
    by_symbol: dict[str, list[Fill]] = {}
    for f in sorted(fills, key=lambda f: f.dt):
        by_symbol.setdefault(f.symbol, []).append(f)

    trips = []
    for symbol, symbol_fills in by_symbol.items():
        open_buys: list[Fill] = []
        for f in symbol_fills:
            if f.side == "BUY":
                open_buys.append(f)
            elif f.side == "SELL" and open_buys:
                entry = open_buys.pop(0)
                trips.append(RoundTrip(
                    symbol=symbol, entry_dt=entry.dt, exit_dt=f.dt,
                    qty=min(entry.qty, f.qty), entry_price=entry.price,
                    exit_price=f.price, product=entry.product,
                ))
    return sorted(trips, key=lambda t: t.entry_dt)


# ─── NIFTY 5-min path analysis (needs a broker) ────────────────────────────

@dataclass
class TripPathAnalysis:
    trip: RoundTrip
    crossover_reversed_before_exit: Optional[bool] = None
    reversal_dt: Optional[datetime] = None
    minutes_saved_by_faster_exit: Optional[float] = None
    underlying_entry: Optional[float] = None
    underlying_best: Optional[float] = None       # most favourable underlying move during the trade
    underlying_at_exit: Optional[float] = None
    est_giveback_pct: Optional[float] = None       # how much of the peak favourable move was given back


def analyse_trip_path(trip: RoundTrip, candles: list[OHLCV]) -> TripPathAnalysis:
    """candles: 5-min NIFTY OHLCV spanning from well before entry (for EMA
    warmup) through the exit. Direction is inferred from the option type
    (CE=bullish/long-underlying-equivalent, PE=bearish/short-underlying-equivalent)."""
    is_call = trip.symbol.endswith("CE")
    result = TripPathAnalysis(trip=trip)
    if len(candles) < 30:
        return result

    closes = [c.close for c in candles]
    ema9 = [_ema(closes[: i + 1], 9) for i in range(len(closes))]
    ema21 = [_ema(closes[: i + 1], 21) for i in range(len(closes))]

    entry_idx = next((i for i, c in enumerate(candles) if c.timestamp >= trip.entry_dt), None)
    exit_idx = next((i for i, c in enumerate(candles) if c.timestamp >= trip.exit_dt), len(candles) - 1)
    if entry_idx is None or entry_idx >= len(candles):
        return result

    result.underlying_entry = closes[entry_idx]
    result.underlying_at_exit = closes[min(exit_idx, len(closes) - 1)]

    # Best (most favourable) underlying level reached between entry and exit.
    window = closes[entry_idx: exit_idx + 1] or [closes[entry_idx]]
    result.underlying_best = max(window) if is_call else min(window)
    fav_move = (result.underlying_best - result.underlying_entry) if is_call \
        else (result.underlying_entry - result.underlying_best)
    exit_move = (result.underlying_at_exit - result.underlying_entry) if is_call \
        else (result.underlying_entry - result.underlying_at_exit)
    # A giveback % against a near-zero favourable move is numerically
    # unstable (a 2pt move giving back 1pt reads as "50%", a 0.1pt move as
    # thousands of percent) and not a meaningful trailing-stop signal
    # either way -- only report it once the favourable move is large enough
    # to matter (NIFTY_MIN_MOVE_FOR_GIVEBACK points).
    if fav_move >= NIFTY_MIN_MOVE_FOR_GIVEBACK:
        result.est_giveback_pct = max(0.0, (fav_move - exit_move) / fav_move * 100)

    # Did EMA9/EMA21 cross AGAINST the trade's direction before the actual exit?
    for i in range(entry_idx + 1, min(exit_idx + 1, len(candles))):
        bullish_now = ema9[i] > ema21[i]
        if is_call and not bullish_now:
            result.crossover_reversed_before_exit = True
            result.reversal_dt = candles[i].timestamp
            result.minutes_saved_by_faster_exit = (trip.exit_dt - candles[i].timestamp).total_seconds() / 60.0
            break
        if not is_call and bullish_now:
            result.crossover_reversed_before_exit = True
            result.reversal_dt = candles[i].timestamp
            result.minutes_saved_by_faster_exit = (trip.exit_dt - candles[i].timestamp).total_seconds() / 60.0
            break
    else:
        result.crossover_reversed_before_exit = False

    return result


def fetch_trip_candles(broker, trip: RoundTrip, max_retries: int = 3) -> list[OHLCV]:
    """5-min NIFTY candles from ~2 hours before entry (EMA9/21 warmup) to
    the exit. Small, fast fetch -- one trade window at a time. Retried with
    backoff on 429s, same pattern as weekly_discovery.py/scanner.py -- a
    ~20-request unthrottled burst still hit Fyers' rate limit in practice."""
    import time
    from_date = (trip.entry_dt - timedelta(hours=3)).astimezone(timezone.utc)
    to_date = (trip.exit_dt + timedelta(minutes=5)).astimezone(timezone.utc)
    for attempt in range(max_retries):
        try:
            candles = broker.get_historical_data("NIFTY 50", "5m", from_date, to_date)
            time.sleep(0.5)
            return candles
        except Exception as e:
            if "429" in str(e) and attempt < max_retries - 1:
                time.sleep(3.0 * (attempt + 1))
                continue
            raise
    return []


# ─── Report ─────────────────────────────────────────────────────────────────

def summarize(trips: list[RoundTrip], overnight: list[RoundTrip],
              analyses: dict[str, TripPathAnalysis]) -> str:
    wins = [t for t in trips if t.is_win]
    losses = [t for t in trips if not t.is_win]
    total_pnl = sum(t.pnl for t in trips)

    lines = [
        "# S8-2 Fyers Automation Trade-History Retrospective",
        "",
        f"**{len(trips)} same-day round trips analysed** (Intraday/Intraday BO NIFTY "
        f"options only; {len(overnight)} Overnight-product trades excluded from these "
        f"stats -- they're manual overrides of the stated same-day exit rule, reported "
        f"separately below).",
        "",
        "## Overall",
        "",
        f"- Win rate: {len(wins)}/{len(trips)} = {len(wins)/len(trips):.0%}" if trips else "- No trades",
        f"- Total gross P&L: Rs{total_pnl:,.0f}",
        f"- Average win: Rs{sum(t.pnl for t in wins)/len(wins):,.0f}" if wins else "- No wins",
        f"- Average loss: Rs{sum(t.pnl for t in losses)/len(losses):,.0f}" if losses else "- No losses",
        f"- Time-stop exits (>=3:09pm): {sum(1 for t in trips if t.is_time_exit)}/{len(trips)}",
        "",
        "## Per-trade P&L (checking whether losses actually ride to the -Rs2000 cap)",
        "",
        "| Date | Symbol | Side | Hold (min) | P&L (Rs) | Exit type |",
        "|---|---|---|---|---|---|",
    ]
    for t in trips:
        side = "CE (bullish)" if t.symbol.endswith("CE") else "PE (bearish)"
        exit_type = "TIME (3:10pm)" if t.is_time_exit else ("P&L cap" if abs(t.pnl) > 1800 else "other/manual")
        lines.append(
            f"| {t.entry_dt.strftime('%Y-%m-%d')} | {t.symbol} | {side} | "
            f"{t.hold_minutes:.0f} | {t.pnl:,.0f} | {exit_type} |"
        )

    reversed_early = [a for a in analyses.values() if a.crossover_reversed_before_exit]
    if reversed_early:
        avg_saved = sum(a.minutes_saved_by_faster_exit for a in reversed_early) / len(reversed_early)
        lines += [
            "",
            "## Question 1: would a faster invalidation exit have helped?",
            "",
            f"Of {len(analyses)} trades with usable NIFTY 5-min data, "
            f"**{len(reversed_early)} had the EMA9/EMA21 crossover reverse AGAINST the "
            f"position before the actual exit** (i.e. the signal that triggered entry had "
            f"already failed, but the position was held anyway until the P&L cap or 3:10pm) — "
            f"averaging {avg_saved:.0f} minutes of extra hold time after invalidation.",
        ]
        for a in analyses.values():
            if a.crossover_reversed_before_exit:
                reversal_ist = a.reversal_dt.astimezone(_IST)
                lines.append(
                    f"  - {a.trip.entry_dt.strftime('%Y-%m-%d')} {a.trip.symbol}: crossover reversed at "
                    f"{reversal_ist.strftime('%H:%M')} IST, actual exit at "
                    f"{a.trip.exit_dt.strftime('%H:%M')} IST ({a.minutes_saved_by_faster_exit:.0f} min later, "
                    f"trade P&L was Rs{a.trip.pnl:,.0f})"
                )

    giveback = [a for a in analyses.values() if a.est_giveback_pct is not None and a.est_giveback_pct > 20]
    if giveback:
        lines += [
            "",
            "## Question 2: would a trailing stop have captured more?",
            "",
            f"Of {len(analyses)} trades, **{len(giveback)} gave back more than 20% of the "
            f"underlying's peak favourable move** between entry and the actual exit — a "
            f"trailing stop on the underlying (approximating the option's premium path) "
            f"would plausibly have locked in more on these:",
        ]
        for a in analyses.values():
            if a.est_giveback_pct is not None and a.est_giveback_pct > 20:
                lines.append(
                    f"  - {a.trip.entry_dt.strftime('%Y-%m-%d')} {a.trip.symbol}: underlying moved "
                    f"{abs(a.underlying_best - a.underlying_entry):.1f} pts favourably at best, "
                    f"gave back {a.est_giveback_pct:.0f}% of that by exit (trade P&L Rs{a.trip.pnl:,.0f})"
                )

    if overnight:
        lines += ["", "## Overnight (manual override) trades — excluded above, reported separately", "",
                   "| Date | Symbol | Hold | P&L (Rs) |", "|---|---|---|---|"]
        for t in overnight:
            lines.append(f"| {t.entry_dt.strftime('%Y-%m-%d')} | {t.symbol} | "
                          f"{t.hold_minutes/60:.1f}h | {t.pnl:,.0f} |")

    lines += [
        "",
        "## Caveats",
        "",
        "- Gross P&L only (Fyers brokerage/STT/GST not deducted here — small relative to "
        "these P&L swings, S8-4's backtest will apply the real options cost model).",
        "- The underlying-move analysis approximates option premium behaviour from NIFTY's "
        "own 5-min path, not the option's own tick data (no historical options price/IV "
        "source exists in this repo yet) — directionally informative, not exact rupee figures.",
        "- Small sample. This grounds S8-4's exit-rule design; it isn't itself a backtest "
        "verdict.",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--config", default="agent/config.yaml")
    parser.add_argument("--out", default="docs/S8_2_TRADE_HISTORY_ANALYSIS.md")
    parser.add_argument("--skip-path-analysis", action="store_true",
                         help="skip the NIFTY 5-min fetch, just report P&L/exit stats")
    args = parser.parse_args()

    fills = load_fills(args.csv_path)
    all_trips = pair_round_trips(fills)
    same_day = [t for t in all_trips if t.product != "Overnight"]
    overnight = [t for t in all_trips if t.product == "Overnight"]
    print(f"Parsed {len(fills)} fills -> {len(all_trips)} round trips "
          f"({len(same_day)} same-day, {len(overnight)} overnight)")

    analyses: dict[str, TripPathAnalysis] = {}
    if not args.skip_path_analysis:
        config = load_config(args.config)
        from core.brokers import get_broker
        broker = get_broker(config)
        print(f"Connecting to broker: {config.get('broker')} ...")
        broker.connect()
        for i, trip in enumerate(same_day):
            key = f"{trip.entry_dt.strftime('%Y-%m-%d')}-{trip.symbol}-{i}"
            try:
                candles = fetch_trip_candles(broker, trip)
                analyses[key] = analyse_trip_path(trip, candles)
            except Exception as e:
                print(f"  Skipping path analysis for {trip.symbol} ({trip.entry_dt.date()}): {e}")

    report = summarize(same_day, overnight, analyses)
    Path(args.out).write_text(report + "\n", encoding="utf-8")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
