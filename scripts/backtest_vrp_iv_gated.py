#!/usr/bin/env python3
"""
QuantOS — IV-Gated Short Premium Backtest Driver
──────────────────────────────────────────────────
Runs docs/VRP_IV_GATED_METHODOLOGY.md (pre-committed 2026-10-06) over the
bhavcopy cache: one entry cycle per week, three arms (strangle primary,
straddle and iron condor secondary), gated by the entry day's ATM IV vs
its trailing 52-cycle percentile. Verdict on Segment A only (2019-2023,
data the exploratory IV cut never saw); Segments B and C reported only.

Memory: streams the cache once to learn each day's expiries, then loads
only the entry and expiry days it needs, instead of holding ~3M rows.

Applies docs/VRP_IV_GATED_ADDENDUM_DATA_QUALITY.md: entry-day prices
only from contracts that traded (volume > 0), and a zero settlement is
treated as missing.

Usage:
    python scripts/backtest_vrp_iv_gated.py
    python scripts/backtest_vrp_iv_gated.py --out docs/VRP_IV_GATED_RESULTS.md
"""

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.options.vrp import iv_gated as g  # noqa: E402
from core.options.vrp.bhavcopy import DEFAULT_PARSED_CACHE_DIR, load_cached_range  # noqa: E402
from core.options.vrp.simulator import _underlying_settlement  # noqa: E402
from core.options.vrp.strikes import build_entry_cycles, select_strangle  # noqa: E402

START, END = date(2019, 2, 11), date(2026, 10, 5)


def _day(d: date, cache: Path) -> list:
    return list(load_cached_range(d, d, cache))


def _traded(rows: list) -> list:
    """Addendum rule 1: only contracts that actually traded that day.
    Untraded legacy rows carry a placeholder close (volume/OI/OHLC all 0)."""
    return [r for r in rows if r.volume > 0]


def _settlement_disagrees(rows: list, expiry: date) -> bool:
    """Methodology data check: on its own expiry day every row for that
    expiry should carry one shared settlement value."""
    vals = {round(r.settle_price, 2) for r in rows if r.expiry == expiry and r.settle_price is not None}
    return len(vals) > 1


def run(cache: Path):
    print(f"Indexing cached days {START} .. {END} ...")
    expiries_by_date: dict = {}
    for r in load_cached_range(START, END, cache):
        expiries_by_date.setdefault(r.trade_date, set()).add(r.expiry)
    cycles = build_entry_cycles(expiries_by_date)
    print(f"{len(expiries_by_date)} trading days, {len(cycles)} entry cycles")

    records = []   # (cycle, atm_iv, trades_by_arm)
    no_atm = zero_settlement = 0
    bad_settlement: list[date] = []
    fallbacks = {"strangle": 0, "iron_condor_wing": 0}
    for i, c in enumerate(cycles, 1):
        rows = _traded(_day(c.entry_date, cache))
        expiry_rows = _day(c.expiry_date, cache)
        settlement = _underlying_settlement(expiry_rows, c.expiry_date)
        if not settlement:
            settlement = None   # addendum rule 2: a 0 settlement is missing, never priced at 0
            zero_settlement += 1
        if expiry_rows and _settlement_disagrees(expiry_rows, c.expiry_date):
            bad_settlement.append(c.expiry_date)
        strangle = select_strangle(rows, c.entry_date, c.expiry_date, c.dte)
        atm = g.select_atm(rows, c.expiry_date, c.dte)
        if atm is None:
            no_atm += 1
        trades = g.build_trades(strangle, atm, rows, c.entry_date, c.expiry_date, c.dte, settlement)
        if strangle is not None and "fallback" in (strangle.call.method + strangle.put.method):
            fallbacks["strangle"] += 1
        ic = trades.get("iron_condor")
        if ic is not None and any(l.side == g.LONG and l.method != "delta" for l in ic.legs):
            fallbacks["iron_condor_wing"] += 1
        records.append((c, atm.iv if atm else None, trades))
        if i % 50 == 0:
            print(f"  {i}/{len(cycles)} cycles built")

    states = g.gate_states([iv for _, iv, _ in records])
    print(f"{zero_settlement} cycles with a zero/missing settlement treated as unsettled")
    return records, states, no_atm, bad_settlement, fallbacks


def _segment_rows(records, states, arm: str, seg: str):
    return [(c.entry_date, s, trades.get(arm))
            for (c, _, trades), s in zip(records, states)
            if s is not None and g.segment_of(c.entry_date) == seg]


def _fmt(s: g.ArmStats) -> str:
    share = "n/a" if s.top_quarter_share is None else f"{s.top_quarter_share:.0%}"
    pf = "inf" if s.profit_factor == float("inf") else f"{s.profit_factor:.3f}"
    return (f"| {s.trades} | {s.win_rate:.1%} | {pf} | {s.sharpe:.3f} | {s.annual_return_pct:+.1f}% "
            f"| {s.max_drawdown_pct:.1f} | {s.worst_trade_pct:.1f}% | {s.avg_pct_credit:+.1f}% "
            f"| {s.gate_runs} | {share} |")


HEADER = ("| Trades | Win rate | PF | Sharpe | Return/yr on margin | Max DD (pts) | Worst trade "
          "| Avg % credit | Runs | Top quarter |\n|---|---|---|---|---|---|---|---|---|---|")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--parsed-cache-dir", type=Path, default=DEFAULT_PARSED_CACHE_DIR)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    records, states, no_atm, bad_settlement, fallbacks = run(args.parsed_cache_dir)
    warmup = sum(1 for s in states if s is None)
    first_live = next((c.entry_date for (c, _, _), s in zip(records, states) if s is not None), None)

    lines = [
        "# IV-Gated Short Premium — Results",
        "",
        "Methodology: docs/VRP_IV_GATED_METHODOLOGY.md (pre-committed 2026-10-06, commit 0749279, "
        "before this ran), with the data-quality rules in docs/VRP_IV_GATED_ADDENDUM_DATA_QUALITY.md "
        "(traded contracts only; zero settlement = missing). The first run, without them, is void. "
        "All figures NET of costs; returns are on margin, idle weeks count as 0.",
        "",
        f"- Cycles: {len(records)} ({START} .. {END}); {warmup} without a gate state "
        f"(warm-up or no ATM IV); first gated cycle {first_live}",
        f"- Cycles with no computable ATM IV: {no_atm}",
        f"- Strangle cycles using the 2% fallback on a leg: {fallbacks['strangle']}; "
        f"condor cycles using a fallback wing: {fallbacks['iron_condor_wing']}",
        f"- Expiry days where rows disagree on the settlement value: {len(bad_settlement)}"
        + (f" ({', '.join(str(d) for d in bad_settlement[:10])}{' ...' if len(bad_settlement) > 10 else ''})"
           if bad_settlement else ""),
        "",
    ]
    verdicts = {}
    for seg, title in (("A", "Segment A — fresh 2019-2023 (THE VERDICT)"),
                       ("B", "Segment B — 2023-2026, where the pattern was first seen (reported only)"),
                       ("C", "Segment C — 2026-07-23 onward (reported only)")):
        lines += [f"## {title}", ""]
        for arm in g.ARMS:
            rows = _segment_rows(records, states, arm, seg)
            if not rows:
                continue
            gated, ungated = g.arm_stats(rows, gated=True), g.arm_stats(rows, gated=False)
            role = "primary" if arm == g.PRIMARY_ARM else "secondary"
            lines += [f"### {arm} ({role}) — {gated.eligible_cycles} eligible cycles, "
                      f"gate open {sum(1 for _, s, _ in rows if s)}", "", HEADER,
                      _fmt(gated).replace("| ", "| **gated** ", 1),
                      _fmt(ungated).replace("| ", "| ungated ", 1), ""]
            if gated.skipped_open:
                lines.append(f"- gate open but arm not tradable/settled: {gated.skipped_open} cycles")
            if seg == "A":
                v, reasons = g.verdict(gated, ungated)
                verdicts[arm] = v
                lines += [f"**{v}**", ""] + [f"- {r}" for r in reasons]
            lines.append("")

    primary = verdicts.get(g.PRIMARY_ARM, "n/a")
    secondary_pass = [a for a, v in verdicts.items() if a != g.PRIMARY_ARM and v == "PASS"]
    headline = f"Primary arm ({g.PRIMARY_ARM}): **{primary}**."
    if primary != "PASS" and secondary_pass:
        headline += (f" Secondary-only pass: {', '.join(secondary_pass)} — needs its own "
                     "pre-registered confirmation on fresh data, not a validated edge.")
    lines[2:2] = ["## Verdict", "", headline, ""]

    report = "\n".join(lines) + "\n"
    print(report)
    if args.out:
        args.out.write_text(report, encoding="utf-8")
        print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
