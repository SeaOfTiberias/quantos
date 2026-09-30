#!/usr/bin/env python3
"""
QuantOS — ORB exit-policy study under the calibrated pricing (2026-09-30)
───────────────────────────────────────────────────────────────────────────
Written BEFORE it was run. The 2026-09-21 exit study ran on the old pricing
(zero intraday time decay), so its "hold to 15:20 unless the trail arms"
conclusion is not trustworthy. This reruns the entry signal with five exit
policies (core/orb_scalping/exit_policies.POLICIES):
  V0 current rules | V1 arm at 0.5 RW | V2 breakeven at 0.5 RW |
  V3 time stop 60 min if not armed | V4 trail 1 RW from entry
each expressed two ways:
  OPTIONS  ATM long option, premium rebuilt under the FROZEN calibrated
           convention (docs/ORB_TIME_CONVENTION_CALIBRATION.md) incl. the 25%
           premium stop; Stratified costs; 1 lot.
  FUTURES  the same index-point P&L x lot -- no time decay, no vega -- minus
           brokerage Rs20/order, STT 0.02% on the sell leg, exchange 0.00173%,
           SEBI 0.0001%, stamp 0.002% on the buy leg, 18% GST, and 1 index
           point of slippage each way. Uses the index as the futures-price proxy
           (the intraday basis change is small).
BANKNIFTY expiry day skipped (the fix-2 decision) in both.

PRE-REGISTERED bar. Several variants are tested at once and 20+ candidates came
before, so a variant "works" for an index only if it clears ALL of PF > 1.0,
Sharpe > 0.5, and per-trade net t-statistic > 3 (Fable, 2026-09-30). V0 is the
benchmark and is judged the same way. Each index is reported separately, never
pooled.
Sanity gate, checked before reporting: V0 must reproduce
signal.simulate_day trade-for-trade on the real candles, or the script stops.

Offline (cached candles). Usage:
    python scripts/backtest_orb_exits.py [--out docs/ORB_EXIT_POLICY_RESULTS.md]
"""
from __future__ import annotations

import argparse
import math
import pickle
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.backtest.parser import _compute_metrics  # noqa: E402
from core.orb_scalping.backtest import (  # noqa: E402
    BANKNIFTY_LOT_SIZE,
    BANKNIFTY_STRIKE_INTERVAL,
    NIFTY_LOT_SIZE,
    NIFTY_STRIKE_INTERVAL,
    _to_backtest_trade,
    group_by_day,
    is_banknifty_monthly_expiry_day,
    resolve_banknifty_expiry,
    resolve_nifty_expiry,
)
from core.orb_scalping.exit_policies import POLICIES, ExitPolicy, simulate_day_with_policy  # noqa: E402
from core.orb_scalping.expiry import is_nifty_weekly_expiry_day  # noqa: E402
from core.orb_scalping.premium import TimeWeights, reconstruct_premium  # noqa: E402
from core.orb_scalping.signal import simulate_day  # noqa: E402
from datetime import timedelta  # noqa: E402
from scripts.backtest_orb_time_convention import CALIBRATION_DOC, CANDLES, load_frozen  # noqa: E402

T_BAR = 3.0


def futures_cost(entry: float, exit_: float, lot: int) -> float:
    buy, sell = entry * lot, exit_ * lot
    brokerage = 40.0
    stt = 0.0002 * sell
    exchange = 0.0000173 * (buy + sell)
    sebi = 0.000001 * (buy + sell)
    stamp = 0.00002 * buy
    gst = 0.18 * (brokerage + exchange + sebi)
    slippage = 2 * 1.0 * lot
    return brokerage + stt + exchange + sebi + stamp + gst + slippage


def t_stat(nets: list[float]) -> float:
    if len(nets) < 2:
        return 0.0
    sd = statistics.stdev(nets)
    return statistics.mean(nets) / (sd / math.sqrt(len(nets))) if sd > 0 else 0.0


def run_index(candles, vix, underlying: str, policy: ExitPolicy, tw: TimeWeights, vol: float):
    lot, interval = ((NIFTY_LOT_SIZE, NIFTY_STRIKE_INTERVAL) if underlying == "NIFTY"
                     else (BANKNIFTY_LOT_SIZE, BANKNIFTY_STRIKE_INTERVAL))
    resolve = resolve_nifty_expiry if underlying == "NIFTY" else resolve_banknifty_expiry
    is_exp = is_nifty_weekly_expiry_day if underlying == "NIFTY" else is_banknifty_monthly_expiry_day
    idx, vx = group_by_day(candles), group_by_day(vix)
    days = set(idx)
    last = max(days)
    days |= {last + timedelta(days=i) for i in range(1, 70) if (last + timedelta(days=i)).weekday() < 5}
    opt, fut = [], []
    for n, day in enumerate(sorted(idx)):
        if not vx.get(day):
            continue
        expiry_day = is_exp(day, days)
        if underlying == "BANKNIFTY" and expiry_day:
            continue
        it = simulate_day_with_policy(idx[day], policy)
        if it is None:
            continue
        expiry, _ = resolve(day, days)
        pt = reconstruct_premium(it, idx[day], vx[day], expiry, interval, time_weights=tw, vol_scale=vol)
        opt.append(_to_backtest_trade(
            entry_dt=pt.entry_timestamp, exit_dt=pt.exit_timestamp, entry_premium=pt.entry_premium,
            exit_premium=pt.exit_premium, lot_size=lot, trade_num=n,
            bars_held=it.exit_index - it.entry_index, variant="stratified",
            underlying=underlying, is_expiry_day=expiry_day))
        sign = 1 if it.direction == "CALL" else -1
        gross = (it.exit_price - it.entry_price) * sign * lot
        fut.append((gross - futures_cost(it.entry_price, it.exit_price, lot), it.exit_reason))
    return opt, fut


def check_v0_parity(candles) -> None:
    for day, dc in group_by_day(candles).items():
        a, b = simulate_day(dc), simulate_day_with_policy(dc, ExitPolicy())
        if a != b:
            raise SystemExit(f"V0 parity FAILED on {day}: {a} != {b}")


def run(data: dict, frozen: dict) -> str:
    tw = TimeWeights(frozen["session"], frozen["weeknight"], frozen["weekend"])
    vol = {"NIFTY": frozen["k_nifty"], "BANKNIFTY": frozen["k_banknifty"]}
    for key in ("nifty", "banknifty"):
        check_v0_parity(data[key])
    head = ("| Policy | N | Win | PF | Sharpe | Net Rs | t | Bar |\n|---|---|---|---|---|---|---|---|")
    out = ["# ORB exit-policy study (calibrated pricing + futures)", "",
           "Method, variants and the pre-registered bar (PF > 1, Sharpe > 0.5, t > 3): "
           "`scripts/backtest_orb_exits.py` docstring, committed before this run. V0 parity with "
           "signal.simulate_day verified on every day of real candles. 1 lot; BANKNIFTY expiry day skipped.", ""]
    for underlying, key in (("NIFTY", "nifty"), ("BANKNIFTY", "banknifty")):
        o_rows, f_rows, reasons = [], [], []
        for p in POLICIES:
            opt, fut = run_index(data[key], data["vix"], underlying, p, tw, vol[underlying])
            m = _compute_metrics(opt)
            nets = [t.profit - t.costs for t in opt]
            t = t_stat(nets)
            ok = m.profit_factor > 1 and m.sharpe_ratio > 0.5 and t > T_BAR
            o_rows.append(f"| {p.name} | {m.total_trades} | {m.win_rate:.0%} | {m.profit_factor:.2f} | "
                          f"{m.sharpe_ratio:.2f} | {sum(nets):,.0f} | {t:.2f} | {'PASS' if ok else 'FAIL'} |")
            fn = [x for x, _ in fut]
            wins, losses = sum(x for x in fn if x > 0), -sum(x for x in fn if x <= 0)
            pf = wins / losses if losses else float("inf")
            ft = t_stat(fn)
            f_rows.append(f"| {p.name} | {len(fn)} | {sum(1 for x in fn if x > 0) / max(len(fn), 1):.0%} | "
                          f"{pf:.2f} | — | {sum(fn):,.0f} | {ft:.2f} | "
                          f"{'PASS' if pf > 1 and ft > T_BAR else 'FAIL'} |")
            from collections import Counter
            reasons.append(f"- {p.name}: " + ", ".join(f"{r} {c}" for r, c in Counter(r for _, r in fut).most_common()))
        out += [f"## {underlying} — options (calibrated pricing)", "", head, *o_rows, "",
                f"## {underlying} — futures (same signal, no time decay)", "",
                "Futures bar: PF > 1 and t > 3 (Sharpe not computed on this ledger).", "", head, *f_rows, "",
                f"Exit reasons ({underlying}):", *reasons, ""]
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="docs/ORB_EXIT_POLICY_RESULTS.md")
    args = ap.parse_args(argv)
    frozen, _ = load_frozen(CALIBRATION_DOC.read_text(encoding="utf-8"))
    report = run(pickle.loads(CANDLES.read_bytes()), frozen)
    Path(args.out).write_text(report + "\n", encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
