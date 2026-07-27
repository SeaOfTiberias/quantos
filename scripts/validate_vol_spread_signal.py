#!/usr/bin/env python3
"""
QuantOS — Vol-Conditioning Signal Validation: IV-minus-RV Spread
──────────────────────────────────────────────────────────────────
S8-1 (docs/REGIME_VALIDATION.md) proved core/regime/classifier.py doesn't
reliably separate forward market outcomes. This script validates a
candidate replacement signal — India VIX (implied vol) minus trailing
realized NIFTY vol — fully on its own terms, against real forward
realized volatility. See docs/VOL_SPREAD_METHODOLOGY.md for every design
choice (RV window, spread construction, bucketing, pass/fail bar), fixed
BEFORE this script was run.

This is deliberately NOT connected to VRP's trade data (docs/VRP_BACKTEST_RESULTS.md)
in this script or its output — see docs/VOL_SPREAD_METHODOLOGY.md's
"mandatory sequencing" section for why.

Method
──────
Replay NIFTY 50 + India VIX daily closes day-by-day. At each day `t` (from
the 21st trading day onward, using ONLY data available through `t`):
  - IV_t = India VIX close on/before t (no lookahead).
  - RV_trailing_20d_t = annualized stdev of daily NIFTY returns over the
    prior 20 sessions (t-19..t).
  - Spread_t = IV_t - RV_trailing_20d_t.
Then, using the (now-known) future:
  - RV_fwd_20d_t = annualized stdev of daily NIFTY returns over the next
    20 sessions (t+1..t+20).
  - Earned premium_t = IV_t - RV_fwd_20d_t.
Days are bucketed into quintiles of Spread_t (data-driven cutpoints from
the full sample) and each bucket's mean earned premium / hit rate is
reported.

Fetch layer (fetch_chunked_daily, NIFTY_SYMBOL, VIX_SYMBOL) is reused
directly from scripts/validate_regime_classifier.py and core/regime/fetcher.py
rather than reimplemented — same chunked/throttled/retried broker calls
already proven against this same broker.

Usage
─────
    python scripts/validate_vol_spread_signal.py
    python scripts/validate_vol_spread_signal.py --years 5 --out docs/VOL_SPREAD_VALIDATION.md

Read-only: no orders, no cloud sync — pure market-data reads via the
broker configured in agent/config.yaml. Needs a fresh Fyers auth token.
"""

import argparse
import asyncio
import logging
import math
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, pstdev
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.main import load_config  # noqa: E402
from core.brokers.base import BrokerAdapter, OHLCV  # noqa: E402
from core.regime.fetcher import NIFTY_SYMBOL, VIX_SYMBOL  # noqa: E402
from scripts.validate_regime_classifier import fetch_chunked_daily  # noqa: E402

logger = logging.getLogger(__name__)

RV_WINDOW = 20              # trading days, both trailing and forward (see methodology doc for why 20 not 10)
TRADING_DAYS_PER_YEAR = 252
NUM_BUCKETS = 5              # quintiles


# ─── Pure replay logic (no I/O — unit-testable with synthetic candles) ────────

@dataclass
class SpreadDay:
    date:            datetime
    iv:               float               # India VIX close at t
    rv_trailing:      float               # annualized RV, t-19..t
    spread:           float               # iv - rv_trailing
    fwd_rv:           Optional[float] = None  # annualized RV, t+1..t+20 (None near end of series)


def _annualized_rv(closes: list[float]) -> float:
    """Annualized %-vol from a list of >=2 closes (pstdev of daily %
    returns * sqrt(252)), matching India VIX's own annualized-% scale."""
    if len(closes) < 2:
        return 0.0
    rets_pct = [(closes[i] - closes[i - 1]) / closes[i - 1] * 100 for i in range(1, len(closes))]
    return pstdev(rets_pct) * math.sqrt(TRADING_DAYS_PER_YEAR)


def compute_daily_series(
    nifty_candles: list[OHLCV], vix_candles: list[OHLCV],
) -> list[SpreadDay]:
    """Walk NIFTY's trading calendar day by day. Spread_t uses only data
    available through t (no lookahead); fwd_rv_t uses the (now-known)
    future purely as the outcome being scored, never as an input."""
    nifty_closes = [c.close for c in nifty_candles]

    days: list[SpreadDay] = []
    for i in range(RV_WINDOW, len(nifty_candles)):
        date = nifty_candles[i].timestamp

        vix_idx = None
        for j, c in enumerate(vix_candles):
            if c.timestamp.date() <= date.date():
                vix_idx = j
            else:
                break
        if vix_idx is None:
            continue
        iv = vix_candles[vix_idx].close

        rv_trailing = _annualized_rv(nifty_closes[i - RV_WINDOW: i + 1])

        fwd_rv = None
        if i + RV_WINDOW < len(nifty_candles):
            fwd_rv = _annualized_rv(nifty_closes[i: i + RV_WINDOW + 1])

        days.append(SpreadDay(
            date=date, iv=iv, rv_trailing=rv_trailing,
            spread=iv - rv_trailing, fwd_rv=fwd_rv,
        ))

    return days


def quintile_cutoffs(values: list[float]) -> list[float]:
    """4 cutpoints splitting sorted values into 5 equal-count buckets,
    computed once from the full sample (data-driven, not hand-picked)."""
    s = sorted(values)
    n = len(s)
    return [s[min(n - 1, int(n * q / NUM_BUCKETS))] for q in range(1, NUM_BUCKETS)]


def assign_bucket(spread: float, cutoffs: list[float]) -> int:
    """1-indexed bucket: 1 = lowest/most-negative spread quintile, 5 = highest."""
    for i, c in enumerate(cutoffs, start=1):
        if spread < c:
            return i
    return NUM_BUCKETS


def summarize(days: list[SpreadDay]) -> str:
    """Build the markdown report body from a completed replay."""
    scored = [d for d in days if d.fwd_rv is not None]

    if not scored:
        return "# IV-minus-RV Vol Spread Validation\n\n**No days scored.**\n"

    cutoffs = quintile_cutoffs([d.spread for d in scored])
    by_bucket: dict[int, list[SpreadDay]] = {b: [] for b in range(1, NUM_BUCKETS + 1)}
    for d in scored:
        by_bucket[assign_bucket(d.spread, cutoffs)].append(d)

    bucket_stats = {}
    for b, bd in by_bucket.items():
        if not bd:
            continue
        premiums = [d.iv - d.fwd_rv for d in bd]
        hits = sum(1 for p in premiums if p > 0)
        bucket_stats[b] = {
            "n": len(bd),
            "mean_spread": mean(d.spread for d in bd),
            "mean_iv": mean(d.iv for d in bd),
            "mean_fwd_rv": mean(d.fwd_rv for d in bd),
            "mean_premium": mean(premiums),
            "hit_rate": hits / len(bd) * 100,
        }

    header = (
        f"**Replayed {len(days)} trading days, {len(scored)} scored with a full "
        f"forward window** ({days[0].date.date()} to {days[-1].date.date()})."
    )
    lines = [
        "# IV-minus-RV Vol Spread Validation",
        "",
        header,
        "",
        "## Earned premium by spread quintile",
        "",
        "(Q1 = lowest/most-negative spread, Q5 = highest spread. "
        "Earned premium = IV_t − forward-20d realized vol; positive means "
        "the vol sold at IV_t would have come in cheaper than priced.)",
        "",
        "| Bucket | n | Mean spread | Mean IV | Mean fwd 20d RV | Mean earned premium | % premium earned |",
        "|---|---|---|---|---|---|---|",
    ]
    for b in range(1, NUM_BUCKETS + 1):
        st = bucket_stats.get(b)
        if not st:
            lines.append(f"| Q{b} | 0 | - | - | - | - | - |")
            continue
        lines.append(
            f"| Q{b} | {st['n']} | {st['mean_spread']:+.2f} | {st['mean_iv']:.2f} | "
            f"{st['mean_fwd_rv']:.2f} | {st['mean_premium']:+.2f} | {st['hit_rate']:.0f}% |"
        )

    lines += ["", "## Verdict", ""]

    q1, q5 = bucket_stats.get(1), bucket_stats.get(NUM_BUCKETS)
    if q1 and q5:
        premium_gap = q5["mean_premium"] - q1["mean_premium"]
        hit_gap = q5["hit_rate"] - q1["hit_rate"]
        lines.append(
            f"- Q5's mean earned premium ({q5['mean_premium']:+.2f}, n={q5['n']}) vs "
            f"Q1's ({q1['mean_premium']:+.2f}, n={q1['n']}): gap = {premium_gap:+.2f} vol points."
        )
        lines.append(
            f"- Q5's premium-earned hit rate ({q5['hit_rate']:.0f}%, n={q5['n']}) vs "
            f"Q1's ({q1['hit_rate']:.0f}%, n={q1['n']}): gap = {hit_gap:+.0f}pp."
        )
    lines.append(
        ""
        "Read the gaps above against the sample sizes (`n`) in the table — a few "
        "points on a handful of days is noise, not signal. This report presents "
        "the numbers; it does not compute a significance test, matching the "
        "zero-code, direct-arithmetic style of docs/REGIME_VALIDATION.md."
    )

    return "\n".join(lines)


# ─── Fetch + orchestration (I/O — needs a connected broker) ───────────────────

async def main_async(args) -> int:
    config = load_config(args.config)
    from core.brokers import get_broker
    broker = get_broker(config)
    print(f"Connecting to broker: {config.get('broker')} ...")
    broker.connect()
    print(f"Broker connected: {broker}\n")

    to_date = datetime.now(timezone.utc)
    from_date = to_date - timedelta(days=365 * args.years + 40)  # +40d warmup for the 20d windows
    sem = asyncio.Semaphore(2)

    print(f"Fetching NIFTY daily candles {from_date.date()} -> {to_date.date()} ...")
    nifty_candles = await fetch_chunked_daily(broker, NIFTY_SYMBOL, from_date, to_date, sem)
    print(f"  {len(nifty_candles)} candles")

    print("Fetching India VIX daily candles ...")
    vix_candles = await fetch_chunked_daily(broker, VIX_SYMBOL, from_date, to_date, sem)
    print(f"  {len(vix_candles)} candles")

    if len(nifty_candles) < RV_WINDOW + 10:
        print(f"ERROR: only {len(nifty_candles)} NIFTY candles - need at least "
              f"{RV_WINDOW + 10} for a meaningful replay. Try --years higher "
              f"or check broker connectivity.")
        return 1
    if len(vix_candles) < RV_WINDOW + 10:
        print(f"ERROR: only {len(vix_candles)} India VIX candles - need at least "
              f"{RV_WINDOW + 10}. The IV source (India VIX) is not usable for the "
              f"requested window with this broker connection — see "
              f"docs/VOL_SPREAD_METHODOLOGY.md's IV-source section.")
        return 1

    print("Replaying spread day-by-day (no lookahead) ...")
    days = compute_daily_series(nifty_candles, vix_candles)
    print(f"  {len(days)} days scored")

    report = summarize(days)
    Path(args.out).write_text(report + "\n", encoding="utf-8")
    print(f"\nWrote {args.out}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default="agent/config.yaml")
    parser.add_argument("--years", type=int, default=5, help="years of history to replay")
    parser.add_argument("--out", default="docs/VOL_SPREAD_VALIDATION.md")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING)
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
