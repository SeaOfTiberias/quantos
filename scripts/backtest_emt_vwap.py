#!/usr/bin/env python3
"""
QuantOS — EMT (exhaustion mean theory) on NIFTY 5-minute, phase 1 (index points)
──────────────────────────────────────────────────────────────────────────────
Rules, grid, split and pass bar: docs/EMT_VWAP_METHODOLOGY.md (fixed before the
first run). Fetches ~1 year of NIFTY 50 5-minute bars and the continuous NIFTY
future's volume from Fyers (needs today's token), caches them under data_cache/,
and writes the report.

Usage:
    python scripts/backtest_emt_vwap.py
    python scripts/backtest_emt_vwap.py --days 365 --out docs/EMT_VWAP_RESULTS.md
"""

import argparse
import asyncio
import csv
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.main import load_config  # noqa: E402
from core.brokers.base import OHLCV  # noqa: E402
from core.emt.backtest import MODES, build_bars, by_day, metrics, run  # noqa: E402
from scripts.backtest_dow_theory_trend import fetch_chunked_intraday  # noqa: E402

INDEX, FUTURE = "NIFTY 50", "NSE:NIFTY26NOVFUT"      # the future is continuous (cont_flag=1); volume only
KS = (0.5, 1.0, 1.5, 2.0)
COST, COST_SENS = 2.0, (1.0, 4.0)
MIN_IS_TRADES, PASS_N, PASS_PF = 30, 40, 1.2
CACHE = Path("data_cache")


def _save(path: Path, candles: list[OHLCV]) -> None:
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ts", "o", "h", "l", "c", "v"])
        for c in candles:
            w.writerow([int(c.timestamp.timestamp()), c.open, c.high, c.low, c.close, c.volume])


async def fetch(days: int) -> tuple[list[OHLCV], list[OHLCV]]:
    from core.brokers import get_broker
    broker = get_broker(load_config("agent/config.yaml"))
    if not broker.connect():
        raise SystemExit("broker connect() failed -- refresh the Fyers token")
    to = datetime.now(timezone.utc)
    frm = to - timedelta(days=days)
    sem = asyncio.Semaphore(1)
    idx = await fetch_chunked_intraday(broker, INDEX, frm, to, sem, delay=1.0)
    fut = await fetch_chunked_intraday(broker, FUTURE, frm, to, sem, delay=1.0)
    stamp = to.strftime("%Y%m%d")
    _save(CACHE / f"emt_nifty_5m_{stamp}.csv", idx)
    _save(CACHE / f"emt_niftyfut_5m_{stamp}.csv", fut)
    return idx, fut


def _row(label: str, m: dict) -> str:
    if not m.get("n"):
        return f"| {label} | 0 | | | | | | | |"
    pf = "inf" if m["pf"] == float("inf") else f"{m['pf']:.2f}"
    r = m["reasons"]
    return (f"| {label} | {m['n']} | {m['win']:.0%} | {m['mean_gross']:+.2f} | {m['mean_net']:+.2f} | "
            f"{m['total_net']:+.0f} | {pf} | {m['t']:+.2f} | {m['max_dd']:.0f} | {m['avg_risk']:.1f} | "
            f"{r.get('target', 0)}/{r.get('stop', 0)}/{r.get('eod', 0)} |")


HEAD = ("| | n | win | gross pts/trade | net pts/trade | net total | PF | t | max DD | avg risk pts | target/stop/eod |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|")


def report(idx: list[OHLCV], fut: list[OHLCV]) -> str:
    bars = build_bars(idx, fut)
    days = sorted(by_day(bars))
    half = len(days) // 2
    is_days, oos_days = set(days[:half]), set(days[half:])
    out = [
        "# EMT on NIFTY 5-minute — phase 1 results (index points)",
        "",
        f"Rules: docs/EMT_VWAP_METHODOLOGY.md. Data {days[0]} to {days[-1]} ({len(days)} sessions, "
        f"{len(bars)} bars). IS {days[0]}..{days[half - 1]}, OOS {days[half]}..{days[-1]}. "
        f"Costs: {COST:g} pts per round trip unless stated.",
        "",
    ]
    verdict = None
    for mode in MODES:
        out += [f"## Variant `{mode}`" + (" (primary)" if mode == "vwap_ema" else " (comparison)"), "", HEAD]
        best_k, best = None, None
        for k in KS:
            m = metrics(run(bars, k, mode, is_days), COST)
            out.append(_row(f"IS k={k:g}", m))
            if m.get("n", 0) >= MIN_IS_TRADES and (best is None or m["mean_net"] > best):
                best_k, best = k, m["mean_net"]
        for k in KS:
            out.append(_row(f"OOS k={k:g}", metrics(run(bars, k, mode, oos_days), COST)))
        out.append("")
        if best_k is None:
            out += [f"No k reached {MIN_IS_TRADES} IS trades.", ""]
            if mode == "vwap_ema":
                verdict = "FAIL (too few trades)"
            continue
        oos_trades = run(bars, best_k, mode, oos_days)
        m = metrics(oos_trades, COST)
        out += [f"Chosen on IS: k={best_k:g}. OOS at other costs:", "", HEAD]
        for c in COST_SENS:
            out.append(_row(f"OOS k={best_k:g} cost {c:g}", metrics(oos_trades, c)))
        longs = [t for t in oos_trades if t.side > 0]
        shorts = [t for t in oos_trades if t.side < 0]
        out += [_row(f"OOS k={best_k:g} longs", metrics(longs, COST)),
                _row(f"OOS k={best_k:g} shorts", metrics(shorts, COST)), ""]
        if mode == "vwap_ema":
            ok = m.get("n", 0) >= PASS_N and m["mean_net"] > 0 and m["pf"] >= PASS_PF
            verdict = (f"{'PASS' if ok else 'FAIL'}: OOS k={best_k:g}, n={m.get('n', 0)}, "
                       f"net {m.get('mean_net', 0):+.2f} pts/trade, PF {m.get('pf', 0):.2f} "
                       f"(bar: n>={PASS_N}, net>0, PF>={PASS_PF})")
    out[4:4] = [f"**Verdict (primary `vwap_ema`): {verdict}**", ""]
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=365)
    ap.add_argument("--out", default="docs/EMT_VWAP_RESULTS.md")
    args = ap.parse_args()
    idx, fut = asyncio.run(fetch(args.days))
    text = report(idx, fut)
    Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
