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
    python scripts/backtest_emt_vwap.py --underlying banknifty
    python scripts/backtest_emt_vwap.py --shorts
"""

import argparse
import asyncio
import csv
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.main import load_config  # noqa: E402
from core.brokers.base import OHLCV  # noqa: E402
from core.emt.backtest import MODES, build_bars, by_day, metrics, run  # noqa: E402
from scripts.backtest_dow_theory_trend import fetch_chunked_intraday  # noqa: E402

# index, continuous future (cont_flag=1, volume only), round-trip cost in points, cost sensitivity
UNDERLYINGS = {
    "nifty": ("NIFTY 50", "NSE:NIFTY26NOVFUT", 2.0, (1.0, 4.0)),
    "banknifty": ("NIFTY BANK", "NSE:BANKNIFTY26NOVFUT", 5.0, (2.5, 10.0)),
}
KS = (0.5, 1.0, 1.5, 2.0)
MIN_IS_TRADES, PASS_N, PASS_PF = 30, 40, 1.2
CACHE = Path("data_cache")


def _save(path: Path, candles: list[OHLCV]) -> None:
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ts", "o", "h", "l", "c", "v"])
        for c in candles:
            w.writerow([int(c.timestamp.timestamp()), c.open, c.high, c.low, c.close, c.volume])


async def fetch(days: int, underlying: str) -> tuple[list[OHLCV], list[OHLCV]]:
    index, future = UNDERLYINGS[underlying][:2]
    from core.brokers import get_broker
    broker = get_broker(load_config("agent/config.yaml"))
    if not broker.connect():
        raise SystemExit("broker connect() failed -- refresh the Fyers token")
    to = datetime.now(timezone.utc)
    frm = to - timedelta(days=days)
    sem = asyncio.Semaphore(1)
    idx = await fetch_chunked_intraday(broker, index, frm, to, sem, delay=1.0)
    fut = await fetch_chunked_intraday(broker, future, frm, to, sem, delay=1.0)
    stamp = to.strftime("%Y%m%d")
    _save(CACHE / f"emt_{underlying}_5m_{stamp}.csv", idx)
    _save(CACHE / f"emt_{underlying}fut_5m_{stamp}.csv", fut)
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


def report(idx: list[OHLCV], fut: list[OHLCV], underlying: str = "nifty") -> str:
    index, _, cost, cost_sens = UNDERLYINGS[underlying]
    bars = build_bars(idx, fut)
    days = sorted(by_day(bars))
    half = len(days) // 2
    is_days, oos_days = set(days[:half]), set(days[half:])
    out = [
        f"# EMT on {index} 5-minute — phase 1 results (index points)",
        "",
        f"Rules: docs/EMT_VWAP_METHODOLOGY.md. Data {days[0]} to {days[-1]} ({len(days)} sessions, "
        f"{len(bars)} bars). IS {days[0]}..{days[half - 1]}, OOS {days[half]}..{days[-1]}. "
        f"Costs: {cost:g} pts per round trip unless stated.",
        "",
    ]
    verdict = None
    for mode in MODES:
        out += [f"## Variant `{mode}`" + (" (primary)" if mode == "vwap_ema" else " (comparison)"), "", HEAD]
        best_k, best = None, None
        for k in KS:
            m = metrics(run(bars, k, mode, is_days), cost)
            out.append(_row(f"IS k={k:g}", m))
            if m.get("n", 0) >= MIN_IS_TRADES and (best is None or m["mean_net"] > best):
                best_k, best = k, m["mean_net"]
        for k in KS:
            out.append(_row(f"OOS k={k:g}", metrics(run(bars, k, mode, oos_days), cost)))
        out.append("")
        if best_k is None:
            out += [f"No k reached {MIN_IS_TRADES} IS trades.", ""]
            if mode == "vwap_ema":
                verdict = "FAIL (too few trades)"
            continue
        oos_trades = run(bars, best_k, mode, oos_days)
        m = metrics(oos_trades, cost)
        out += [f"Chosen on IS: k={best_k:g}. OOS at other costs:", "", HEAD]
        for c in cost_sens:
            out.append(_row(f"OOS k={best_k:g} cost {c:g}", metrics(oos_trades, c)))
        longs = [t for t in oos_trades if t.side > 0]
        shorts = [t for t in oos_trades if t.side < 0]
        out += [_row(f"OOS k={best_k:g} longs", metrics(longs, cost)),
                _row(f"OOS k={best_k:g} shorts", metrics(shorts, cost)), ""]
        if mode == "vwap_ema":
            ok = m.get("n", 0) >= PASS_N and m["mean_net"] > 0 and m["pf"] >= PASS_PF
            verdict = (f"{'PASS' if ok else 'FAIL'}: OOS k={best_k:g}, n={m.get('n', 0)}, "
                       f"net {m.get('mean_net', 0):+.2f} pts/trade, PF {m.get('pf', 0):.2f} "
                       f"(bar: n>={PASS_N}, net>0, PF>={PASS_PF})")
    out[4:4] = [f"**Verdict (primary `vwap_ema`): {verdict}**", ""]
    return "\n".join(out)


# shorts-only addendum: k picked on the already-seen year, confirmed on the two years before it
DISCOVERY_FROM, CONFIRM_FROM = date(2025, 10, 27), date(2023, 10, 27)


def shorts_report(idx: list[OHLCV], fut: list[OHLCV], underlying: str = "nifty") -> str:
    index, _, cost, cost_sens = UNDERLYINGS[underlying]
    bars = build_bars(idx, fut)
    days = sorted(by_day(bars))
    disc = {d for d in days if d >= DISCOVERY_FROM}
    conf = sorted(d for d in days if CONFIRM_FROM <= d < DISCOVERY_FROM)
    out = [
        f"# EMT on {index} 5-minute — shorts only (index points)",
        "",
        f"Rules: docs/EMT_VWAP_METHODOLOGY.md, shorts-only addendum. Variant `vwap_ema`. Discovery "
        f"{min(disc)}..{max(disc)} ({len(disc)} sessions, already seen); confirmation {conf[0]}..{conf[-1]} "
        f"({len(conf)} sessions, never looked at). Costs: {cost:g} pts per round trip unless stated.",
        "",
        "## Discovery (k chosen here)", "", HEAD,
    ]
    best_k, best = None, None
    for k in KS:
        m = metrics(run(bars, k, "vwap_ema", disc, side=-1), cost)
        out.append(_row(f"shorts k={k:g}", m))
        if m.get("n", 0) >= MIN_IS_TRADES and (best is None or m["mean_net"] > best):
            best_k, best = k, m["mean_net"]
    if best_k is None:
        return "\n".join(out + ["", f"No k reached {MIN_IS_TRADES} trades; nothing to confirm."])
    trades = run(bars, best_k, "vwap_ema", set(conf), side=-1)
    m = metrics(trades, cost)
    out += ["", f"## Confirmation (k={best_k:g} only)", "", HEAD, _row(f"shorts k={best_k:g}", m)]
    for c in cost_sens:
        out.append(_row(f"shorts k={best_k:g} cost {c:g}", metrics(trades, c)))
    split = CONFIRM_FROM.replace(year=CONFIRM_FROM.year + 1)
    for label, part in ((f"{conf[0]}..{split}", [t for t in trades if t.day < split]),
                        (f"{split}..{conf[-1]}", [t for t in trades if t.day >= split])):
        out.append(_row(f"year {label}", metrics(part, cost)))
    ok = m.get("n", 0) >= PASS_N and m["mean_net"] > 0 and m["pf"] >= PASS_PF
    verdict = (f"{'PASS' if ok else 'FAIL'}: confirmation k={best_k:g}, n={m.get('n', 0)}, "
               f"net {m.get('mean_net', 0):+.2f} pts/trade, PF {m.get('pf', 0):.2f} "
               f"(bar: n>={PASS_N}, net>0, PF>={PASS_PF})")
    out[4:4] = [f"**Verdict (shorts only): {verdict}**", ""]
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--underlying", choices=sorted(UNDERLYINGS), default="nifty")
    ap.add_argument("--days", type=int, default=365)
    ap.add_argument("--shorts", action="store_true", help="shorts-only addendum (fetches back to 2023-10-27)")
    ap.add_argument("--out")
    args = ap.parse_args()
    suffix = ("" if args.underlying == "nifty" else f"_{args.underlying.upper()}") + ("_SHORTS" if args.shorts else "")
    args.out = args.out or f"docs/EMT_VWAP_RESULTS{suffix}.md"
    if args.shorts:
        args.days = max(args.days, (datetime.now(timezone.utc).date() - CONFIRM_FROM).days + 30)
    idx, fut = asyncio.run(fetch(args.days, args.underlying))
    text = (shorts_report if args.shorts else report)(idx, fut, args.underlying)
    Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
