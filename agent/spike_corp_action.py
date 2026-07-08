#!/usr/bin/env python3
"""
QuantOS — S5-3 Corporate-Action Verification Spike
──────────────────────────────────────────────────
Read-only diagnostic answering one question: does the broker's daily
`get_historical_data` return SPLIT-ADJUSTED OHLC, or RAW (unadjusted) prices?

The whole Darvas pipeline (box detection, ATR stops, RR sizing) assumes a
continuous price series. If the broker feed is unadjusted, a stock split or
bonus injects an artificial overnight "gap" of the split factor — which would
blow a Darvas box wide open, fabricate a false breakout/breakdown, and poison
every historical ATR. This spike measures that empirically instead of guessing.

Method
──────
Fetch daily candles spanning a KNOWN corporate action (default: NESTLEIND's
1:10 face-value split, ex-date 2024-01-05 — a 10x factor is impossible to
mistake for a real price move). Then compare the last close BEFORE the ex-date
to the first open ON/AFTER it:

    boundary_ratio = pre_split_close / post_split_open

  • ratio ≈ split_factor (e.g. ~10)  → feed is UNADJUSTED (raw as-traded;
                                       the split shows up as an artificial gap)
  • ratio ≈ 1.0                      → feed is ADJUSTED (history back-scaled;
                                       no artificial gap, series is continuous)

Read-only: no orders, no cloud sync, no watchlist writes — pure market-data
reads via the broker configured in agent/config.yaml.

Usage
─────
    python agent/spike_corp_action.py
    python agent/spike_corp_action.py --symbol IRCTC --ex-date 2021-10-28 --factor 5
    python agent/spike_corp_action.py --config agent/config.yaml
"""

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.main import load_config


def _classify(ratio: float, factor: float) -> str:
    """Verdict from the boundary ratio, with a generous tolerance band so a
    real ±few-% move on the ex-date doesn't flip the call."""
    if abs(ratio - 1.0) < 0.15:
        return "ADJUSTED"
    if abs(ratio - factor) < factor * 0.15:
        return "UNADJUSTED"
    return "INCONCLUSIVE"


def main() -> int:
    parser = argparse.ArgumentParser(description="S5-3: is broker daily OHLC split-adjusted?")
    parser.add_argument("--config", default="agent/config.yaml")
    parser.add_argument("--symbol", default="NESTLEIND",
                        help="NSE symbol that underwent a known split/bonus")
    parser.add_argument("--ex-date", default="2024-01-05",
                        help="Ex/record date of the corporate action (YYYY-MM-DD)")
    parser.add_argument("--factor", type=float, default=10.0,
                        help="Split/bonus factor, e.g. 10 for a 1:10 split")
    parser.add_argument("--window", type=int, default=20,
                        help="Trading-day-ish window either side of the ex-date")
    args = parser.parse_args()

    ex_date = datetime.strptime(args.ex_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    from_date = ex_date - timedelta(days=args.window)
    to_date = ex_date + timedelta(days=args.window)

    config = load_config(args.config)
    from core.brokers import get_broker
    broker = get_broker(config)
    print(f"Connecting to broker: {config.get('broker')} ...")
    broker.connect()
    print(f"Broker connected: {broker}\n")

    print(f"Corporate action under test: {args.symbol} - 1:{args.factor:g} on {args.ex_date}")
    print(f"Fetching daily candles {from_date.date()} -> {to_date.date()} ...\n")
    candles = broker.get_historical_data(args.symbol, "1d", from_date, to_date)

    if not candles:
        print("!! No candles returned in the window. The broker's daily history may")
        print("   not reach this far back — try a more recent corporate action via")
        print("   --symbol/--ex-date/--factor.")
        return 2

    ex_naive = ex_date.date()
    pre = [c for c in candles if c.timestamp.date() < ex_naive]
    post = [c for c in candles if c.timestamp.date() >= ex_naive]

    print(f"{'date':<12}{'open':>12}{'high':>12}{'low':>12}{'close':>12}{'volume':>14}")
    for c in candles:
        marker = "  <== ex-date onward" if c.timestamp.date() >= ex_naive else ""
        print(f"{str(c.timestamp.date()):<12}{c.open:>12.2f}{c.high:>12.2f}"
              f"{c.low:>12.2f}{c.close:>12.2f}{c.volume:>14,d}{marker}")

    print()
    if not pre or not post:
        print("!! Window did not straddle the ex-date (all candles on one side).")
        print("   Widen --window or check the ex-date.")
        return 2

    pre_close = pre[-1].close
    post_open = post[0].open
    ratio = pre_close / post_open if post_open else float("inf")
    verdict = _classify(ratio, args.factor)

    print("-- Boundary analysis -------------------------------------")
    print(f"  last close BEFORE ex-date ({pre[-1].timestamp.date()}):  {pre_close:>12.2f}")
    print(f"  first open ON/AFTER ex-date ({post[0].timestamp.date()}): {post_open:>12.2f}")
    print(f"  boundary ratio (pre_close / post_open):     {ratio:>8.3f}")
    print(f"  split factor under test:                    {args.factor:>8.3f}")
    print()
    print(f"  VERDICT: broker daily OHLC is {verdict}")
    if verdict == "UNADJUSTED":
        print("           -> a corp-action-adjusted OHLC store IS needed (S5-3 conditional).")
    elif verdict == "ADJUSTED":
        print("           -> no adjusted store needed; the conditional 5 pts can be dropped.")
    else:
        print("           -> ratio matched neither ~1 nor ~factor; verify the ex-date/factor,")
        print("             the split may not be the one in this window.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
