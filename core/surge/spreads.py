"""
QuantOS — Candidate 23 Stage 2: bull call spread simulation and strike picker
──────────────────────────────────────────────────────────────────────────────
docs/SURGE_SPREAD_STAGE2_METHODOLOGY.md "Trade construction", "P&L and
costs", "Strike-pair selection". Pure logic over the Stage 1 events, the
futures panel, and the cached CE rows from core/surge/options.py.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

import numpy as np
import pandas as pd

from core.backtest.parser import BacktestTrade, _compute_metrics
from core.statarb.residuals import Panel

KS = (0, 1, 2, 3)
WS = (1, 2, 3, 4)
STRUCTURES = tuple(f"L{k}W{w}" for k in KS for w in WS)
MIN_TDAYS_TO_EXPIRY = 5
HOLD = 8
TICK = 0.05
SCENARIOS = {"clean": 0.0, "base": 0.01, "stressed": 0.02}
GATING = "stressed"
MIN_MINING = 100
MIN_HOLDOUT = 30
BROKERAGE_PER_ORDER = 20.0
FALLBACK_NOTIONAL = 500_000.0


def stt_sell_rate(d: date) -> float:
    if d >= date(2026, 4, 1):
        return 0.0015
    if d >= date(2024, 10, 1):
        return 0.001
    if d >= date(2023, 4, 1):
        return 0.000625
    return 0.0005


def exchange_rate(d: date) -> float:
    return 0.0003503 if d >= date(2024, 10, 1) else 0.00053


def statutory_cost(p_long: float, p_short: float, v_long: float, v_short: float,
                   lot: int, d_in: date, d_out: date) -> float:
    """Per-share statutory cost of one bull-call-spread round trip:
    buy long + sell short at entry, sell long + buy short at exit."""
    turnover_in, turnover_out = p_long + p_short, v_long + v_short
    stt = p_short * stt_sell_rate(d_in) + v_long * stt_sell_rate(d_out)
    exch = turnover_in * exchange_rate(d_in) + turnover_out * exchange_rate(d_out)
    sebi = 1e-6 * (turnover_in + turnover_out)
    stamp = 3e-5 * (p_long + v_short)
    brokerage = 4 * BROKERAGE_PER_ORDER / max(lot, 1)
    return stt + exch + sebi + stamp + brokerage + 0.18 * (brokerage + exch + sebi)


def bidask_cost(prices: tuple[float, ...], c: float) -> float:
    if c <= 0:
        return 0.0
    return sum(max(c * p, TICK) for p in prices)


@dataclass(frozen=True)
class SpreadTrade:
    symbol: str
    structure: str
    holdout: bool
    entry: date
    exit: date
    days: int
    debit: float
    width: float
    gross: float
    costs: dict[str, float]
    results: bool
    exit_fallback: str          # "" | "settle" | "intrinsic"

    def ret(self, scenario: str) -> float:
        return (self.gross - self.costs[scenario]) / self.debit


@dataclass
class Stage2Result:
    trades: list[SpreadTrade]
    metrics: dict[tuple[str, str, str], object]     # (structure, split, scenario) -> BacktestMetrics
    chosen: Optional[str]
    verdict: str
    reasons: list[str]
    skips: Counter = field(default_factory=Counter)
    n_events: int = 0
    cutoff: Optional[date] = None


def _lot_map(rows: pd.DataFrame) -> dict[str, int]:
    """Earliest 2024+ NSE lot per symbol, for pre-2024 brokerage."""
    r = rows[(rows["lot"] > 0) & (rows["trade_date"] >= date(2024, 1, 1))].sort_values("trade_date")
    return r.groupby("symbol")["lot"].first().to_dict()


def build_trades(panel: Panel, events: list, rows: pd.DataFrame, cutoff: date) -> tuple[list[SpreadTrade], Counter]:
    col = {s: j for j, s in enumerate(panel.symbols)}
    pos = {d: i for i, d in enumerate(panel.dates)}
    chains = {key: g for key, g in rows.groupby(["trade_date", "symbol"], sort=False)}
    lots = _lot_map(rows)
    skips: Counter = Counter()
    trades: list[SpreadTrade] = []
    T = len(panel.dates)

    def first_index_on_or_after(d: date) -> int:
        lo, hi = 0, T
        while lo < hi:
            mid = (lo + hi) // 2
            if panel.dates[mid] < d:
                lo = mid + 1
            else:
                hi = mid
        return lo

    for e in events:
        j, t = col[e.symbol], e.t
        chain = chains.get((panel.dates[t], e.symbol))
        if chain is None or chain.empty:
            skips["no option chain on entry day"] += 1
            continue
        expiry = None
        for x in sorted(chain["expiry"].unique()):
            if first_index_on_or_after(x) - t >= MIN_TDAYS_TO_EXPIRY:
                expiry = x
                break
        if expiry is None:
            skips["no expiry with >= 5 trading days"] += 1
            continue
        exit_i = min(t + HOLD, first_index_on_or_after(expiry) - 1)
        if exit_i >= T or exit_i <= t:
            skips["exit beyond data"] += 1
            continue
        s_t, s_e = panel.raw[t, j], panel.raw[exit_i, j]
        if np.isnan(s_t) or np.isnan(s_e):
            skips["no futures price on entry/exit"] += 1
            continue

        legs_t = chain[chain["expiry"] == expiry].sort_values("strike")
        strikes = legs_t["strike"].to_numpy()
        a = int(np.argmin(np.abs(strikes - s_t)))
        by_k_t = {r.strike: r for r in legs_t.itertuples()}
        exit_chain = chains.get((panel.dates[exit_i], e.symbol))
        by_k_e = ({r.strike: r for r in exit_chain[exit_chain["expiry"] == expiry].itertuples()}
                  if exit_chain is not None else {})
        d_in, d_out = panel.dates[t], panel.dates[exit_i]

        def exit_value(k: float) -> tuple[float, str]:
            r = by_k_e.get(k)
            if r is not None and r.contracts > 0 and r.close > 0:
                return float(r.close), ""
            if r is not None and r.settle > 0:
                return float(r.settle), "settle"
            return max(float(s_e) - k, 0.0), "intrinsic"

        for k in KS:
            for w in WS:
                name = f"L{k}W{w}"
                il, ish = a + k, a + k + w
                if ish >= len(strikes):
                    skips[f"{name}: strike off the chain"] += 1
                    continue
                kl, ks = float(strikes[il]), float(strikes[ish])
                rl, rs = by_k_t[kl], by_k_t[ks]
                if not (rl.contracts > 0 and rs.contracts > 0 and rl.close > 0 and rs.close > 0):
                    skips[f"{name}: leg untraded on entry"] += 1
                    continue
                debit, width = float(rl.close - rs.close), ks - kl
                if not 0 < debit < width:
                    skips[f"{name}: debit outside (0, width)"] += 1
                    continue
                vl, fl = exit_value(kl)
                vs, fs = exit_value(ks)
                lot = int(rl.lot) if rl.lot > 0 else lots.get(e.symbol) or max(int(FALLBACK_NOTIONAL / s_t), 1)
                stat = statutory_cost(float(rl.close), float(rs.close), vl, vs, lot, d_in, d_out)
                prices = (float(rl.close), float(rs.close), vl, vs)
                costs = {sc: stat + bidask_cost(prices, c) for sc, c in SCENARIOS.items()}
                trades.append(SpreadTrade(
                    symbol=e.symbol, structure=name, holdout=d_in >= cutoff, entry=d_in, exit=d_out,
                    days=exit_i - t, debit=debit, width=width, gross=(vl - vs) - debit, costs=costs,
                    results=bool(e.cond["results"]), exit_fallback=fl or fs,
                ))
    return trades, skips


def _metrics(trades: list[SpreadTrade], scenario: str):
    bt = []
    for i, tr in enumerate(sorted(trades, key=lambda x: x.entry)):
        bt.append(BacktestTrade(
            trade_num=i + 1, direction="Long", qty=1,
            entry_date=datetime.combine(tr.entry, datetime.min.time()), entry_price=100.0,
            exit_date=datetime.combine(tr.exit, datetime.min.time()),
            exit_price=100.0 * (1 + tr.gross / tr.debit),
            profit=100.0 * tr.gross / tr.debit, profit_pct=100.0 * tr.gross / tr.debit,
            cum_profit=0.0, bars_held=max(tr.days, 1), costs=100.0 * tr.costs[scenario] / tr.debit,
        ))
    return _compute_metrics(bt)


def run_stage2(panel: Panel, events: list, rows: pd.DataFrame, *, cutoff: date) -> Stage2Result:
    trades, skips = build_trades(panel, events, rows, cutoff)
    metrics = {}
    for s in STRUCTURES:
        for split_name, flag in (("mining", False), ("holdout", True)):
            sub = [t for t in trades if t.structure == s and t.holdout == flag]
            for sc in SCENARIOS:
                metrics[(s, split_name, sc)] = _metrics(sub, sc)

    eligible = [s for s in STRUCTURES
                if metrics[(s, "mining", GATING)].total_trades >= MIN_MINING
                and metrics[(s, "mining", GATING)].profit_factor > 1.0]
    reasons: list[str] = []
    if not eligible:
        return Stage2Result(trades, metrics, None, "FAIL",
                            [f"no structure has >= {MIN_MINING} mining trades with Stressed PF > 1"],
                            skips, len(events), cutoff)
    chosen = max(eligible, key=lambda s: (metrics[(s, "mining", GATING)].sharpe_ratio,
                                          -int(s[1]), -int(s[3])))
    h = metrics[(chosen, "holdout", GATING)]
    checks = {
        f"holdout trades >= {MIN_HOLDOUT}": h.total_trades >= MIN_HOLDOUT,
        "holdout Stressed PF > 1.0": h.profit_factor > 1.0,
        "holdout Stressed Sharpe > 0.5": h.sharpe_ratio > 0.5,
    }
    reasons = [f"{k}: {'pass' if v else 'FAIL'}" for k, v in checks.items()]
    return Stage2Result(trades, metrics, chosen, "PASS" if all(checks.values()) else "FAIL",
                        reasons, skips, len(events), cutoff)
