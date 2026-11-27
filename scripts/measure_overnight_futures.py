#!/usr/bin/env python3
"""
QuantOS desk edge E3, phase 1: overnight vs intraday returns in NIFTY / BANKNIFTY futures.
Pre-registration: docs/E3_OVERNIGHT_PREREG_2026-11-27.md (measurement only, no trade rules).

    python scripts/measure_overnight_futures.py --worked    # 5 nights per index by hand, then stop
    python scripts/measure_overnight_futures.py             # the full measurement

Data: index futures from the cached F&O bhavcopy zips (core/fno/bhavcopy_futures.py), no network.
Contract: on each session d, the nearest expiry strictly after d (so a position opened at d's close
can be closed at the next session's open). Overnight = open(next) / close(d) - 1 on that contract;
intraday = close(d) / open(d) - 1 on the same contract. `close` is NSE's futures closing price
(last-30-minute VWAP). A night counts only if the next cached file is the next NSE session
(core.reference.calendar), so data gaps are never bridged.
"""

from __future__ import annotations

import argparse
import math
import statistics
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.fno import bhavcopy_futures as bf  # noqa: E402

START = date(2019, 2, 11)
HALF_SPLIT = date(2023, 1, 1)
SYMBOLS = ("NIFTY", "BANKNIFTY")
SLIP_CLOSE_BPS, SLIP_OPEN_BPS = 1.0, 2.0      # per side
NOTIONAL_IF_NO_LOT = 1_000_000.0             # Rs, for the Rs20 brokerage cap when the lot size is unknown
COST_2026 = date(2026, 4, 1)                 # verdict costs: today's rates on every night
T_PASS = 2.24                                # one-sided 1.25%: 2.5% split over the two indices
OUT = Path("docs/E3_OVERNIGHT_RESULTS_2026-11-27.md")


@dataclass(frozen=True)
class Night:
    symbol: str
    d: date
    nxt: date
    expiry: date
    open_d: float
    close_d: float
    open_next: float
    last_d: Optional[float]
    lot: Optional[int]

    @property
    def overnight(self) -> float:
        return self.open_next / self.close_d - 1

    @property
    def intraday(self) -> float:
        return self.close_d / self.open_d - 1


def nights(data: dict[date, list[bf.FutRow]], symbol: str, next_session) -> list[Night]:
    days = sorted(data)
    out = []
    for d, n in zip(days, days[1:]):
        if next_session(d) != n:
            continue                                        # a missing file: never bridged
        if d.weekday() >= 5 or n.weekday() >= 5:
            continue                                        # special weekend sessions (Muhurat, Budget, DR drills)
        c = bf.contract_after(data[d], symbol, d)
        if c is None:
            continue
        m = [r for r in data[n] if r.symbol == symbol and r.expiry == c.expiry]
        if not m or min(c.open, c.close, m[0].open) <= 0:
            continue
        out.append(Night(symbol, d, n, c.expiry, c.open, c.close, m[0].open, c.last, c.lot_size))
    return out


def round_trip_bps(price: float, lot: Optional[int], cost_date: date, slip_bps: float) -> float:
    """Round-trip cost of one long futures position, in bps of notional: charges at cost_date's
    rates (core/pairs/costs.py) plus slippage."""
    from core.pairs.costs import position_cost
    lot = lot or max(1, round(NOTIONAL_IF_NO_LOT / price))
    notional = price * lot
    rupees = position_cost(price, price, lot, 1, "BUY", cost_date, cost_date)
    return rupees / notional * 1e4 + slip_bps


def t_stat(x: list[float]) -> float:
    if len(x) < 3:
        return float("nan")
    sd = statistics.stdev(x)
    return statistics.mean(x) / (sd / math.sqrt(len(x))) if sd else float("nan")


def summarize(gross_bps: list[float], cost_bps: list[float]) -> dict:
    net = [g - c for g, c in zip(gross_bps, cost_bps)]
    return dict(n=len(net), gross=statistics.mean(gross_bps) if net else float("nan"),
                cost=statistics.mean(cost_bps) if net else float("nan"),
                net=statistics.mean(net) if net else float("nan"), t=t_stat(net),
                hit=sum(x > 0 for x in net) / len(net) if net else float("nan"))


def verdict(ns: list[Night], cost_fn) -> dict:
    """Phase 1 for one index: alive if the net overnight mean at 2026 costs is > 0 over the whole
    sample with t >= T_PASS, and > 0 in both halves."""
    def part(sel):
        g = [n.overnight * 1e4 for n in sel]
        c = [cost_fn(n) for n in sel]
        return summarize(g, c)
    full = part(ns)
    h1 = part([n for n in ns if n.d < HALF_SPLIT])
    h2 = part([n for n in ns if n.d >= HALF_SPLIT])
    alive = full["net"] > 0 and full["t"] >= T_PASS and h1["net"] > 0 and h2["net"] > 0
    return dict(full=full, h1=h1, h2=h2, alive=alive)


def cost_2026(n: Night) -> float:
    return round_trip_bps(n.close_d, n.lot, COST_2026, SLIP_CLOSE_BPS + SLIP_OPEN_BPS)


def cost_then(n: Night) -> float:
    return round_trip_bps(n.close_d, n.lot, n.d, SLIP_CLOSE_BPS + SLIP_OPEN_BPS)


def row(name: str, s: dict) -> str:
    return (f"| {name} | {s['n']} | {s['gross']:+.2f} | {s['cost']:.2f} | {s['net']:+.2f} | "
            f"{s['t']:+.2f} | {s['hit']:.1%} |")


HEAD = ["| Slice | Nights | Gross mean (bps) | Cost (bps) | Net mean (bps) | t (net) | Net > 0 |",
        "|---|---|---|---|---|---|---|"]


def report(by_sym: dict[str, list[Night]], last_day: date) -> str:
    out = [f"Window {START} to {last_day}. Costs: charges at 2026 rates (STT 0.05% sell side) plus "
           f"{SLIP_CLOSE_BPS + SLIP_OPEN_BPS:.0f} bps slippage per round trip, on every night (the verdict).", ""]
    for sym, ns in by_sym.items():
        v = verdict(ns, cost_2026)
        out += [f"## {sym}: phase 1 {'ALIVE' if v['alive'] else 'DEAD'}", "",
                "### Overnight (buy at close, sell next open), verdict costs", ""] + HEAD + [
                row("all", v["full"]), row(f"{START} to 2022-12-31", v["h1"]), row("2023-01-01 on", v["h2"]), ""]
        out += ["### Reported, not scored", "", "Overnight net at each night's own historical rates:", ""] + HEAD
        out.append(row("all (rates of the day)", verdict(ns, cost_then)["full"]))
        out += ["", "By year (verdict costs):", ""] + HEAD
        for y in sorted({n.d.year for n in ns}):
            sel = [n for n in ns if n.d.year == y]
            out.append(row(str(y), summarize([n.overnight * 1e4 for n in sel], [cost_2026(n) for n in sel])))
        wk = [n for n in ns if (n.nxt - n.d).days > 1]
        wd = [n for n in ns if (n.nxt - n.d).days == 1]
        out += ["", "Weekend/holiday nights vs one-night gaps (verdict costs):", ""] + HEAD
        out.append(row("one night", summarize([n.overnight * 1e4 for n in wd], [cost_2026(n) for n in wd])))
        out.append(row("weekend/holiday", summarize([n.overnight * 1e4 for n in wk], [cost_2026(n) for n in wk])))
        intr = summarize([n.intraday * 1e4 for n in ns],
                         [round_trip_bps(n.open_d, n.lot, COST_2026, SLIP_CLOSE_BPS + SLIP_OPEN_BPS) for n in ns])
        out += ["", "Intraday mirror (buy at open, sell at close), verdict costs:", ""] + HEAD + [row("all", intr)]
        lp = [n for n in ns if n.last_d]
        if lp:
            g = [(n.open_next / n.last_d - 1) * 1e4 for n in lp]
            out += ["", "Overnight from the last trade instead of the 30-minute VWAP close (2024 on, newer files only):", ""] + HEAD
            out.append(row(f"{lp[0].d} on", summarize(g, [cost_2026(n) for n in lp])))
        out.append("")
    return "\n".join(out)


def worked(by_sym: dict[str, list[Night]]) -> str:
    out = []
    for sym, ns in by_sym.items():
        picks = [ns[0], ns[len(ns) // 4], ns[len(ns) // 2], ns[3 * len(ns) // 4], ns[-1]]
        out += [f"## {sym}", "", "| Night | Next | Expiry | Open d | Close d (VWAP) | Open next | Overnight bps | Intraday bps | Cost 2026 bps |",
                "|---|---|---|---|---|---|---|---|---|"]
        for n in picks:
            out.append(f"| {n.d} | {n.nxt} | {n.expiry} | {n.open_d:.2f} | {n.close_d:.2f} | {n.open_next:.2f} | "
                       f"{n.overnight * 1e4:+.1f} | {n.intraday * 1e4:+.1f} | {cost_2026(n):.2f} |")
        out += ["", f"{len(ns)} nights.", ""]
    return "\n".join(out)


def main(argv=None) -> int:
    from core.reference.calendar import next_trading_day
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--worked", action="store_true")
    a = ap.parse_args(argv)
    data = bf.load(START, date.today())
    by_sym = {s: nights(data, s, next_trading_day) for s in SYMBOLS}
    last_day = max(data)
    print(f"{len(data)} files {min(data)}..{last_day}; nights " + ", ".join(f"{s} {len(v)}" for s, v in by_sym.items()),
          flush=True)
    txt = worked(by_sym) if a.worked else report(by_sym, last_day)
    sys.stdout.buffer.write((txt + "\n").encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
