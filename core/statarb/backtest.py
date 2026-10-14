"""
QuantOS — StatArb (BankNifty test bed): Signal Backtest and Calibration
───────────────────────────────────────────────────────────────────────
docs/STATARB_BANKNIFTY_METHODOLOGY.md "Trading rules", "P&L and costs",
"Pass bar". Pure logic over a residuals.Panel plus precomputed scores.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

import numpy as np

from core.backtest.parser import BacktestTrade, _compute_metrics
from core.pairs.costs import position_cost
from core.statarb.residuals import Panel, Score, exclusion_reasons, score

ENTRY_S = 1.25
EXIT_LONG_S = -0.50
EXIT_SHORT_S = 0.75
STOP_S = 3.0
MAX_HOLD_DAYS = 20
RESULTS_BLACKOUT_DAYS = 5
NOTIONAL = 500_000.0
SLIPPAGE_BPS_PER_SIDE = 2.0
CALIBRATION_HORIZON = 10


def compute_scores(panel: Panel, model: str, start_idx: int,
                   sectors: Optional[dict[str, str]] = None) -> list[list[Optional[Score]]]:
    """scores[t][j] for t >= start_idx (None before)."""
    out: list[list[Optional[Score]]] = [[None] * len(panel.symbols) for _ in panel.dates]
    for t in range(start_idx, len(panel.dates)):
        reasons = exclusion_reasons(panel, t)
        for j in range(len(panel.symbols)):
            out[t][j] = score(panel, t, j, model, reasons, sectors)
    return out


@dataclass(frozen=True)
class StatArbTrade:
    symbol:       str
    model:        str
    side:         str     # "LONG" = long stock / short family
    signal_date:  date
    entry_date:   date
    exit_date:    date
    entry_s:      float
    exit_reason:  str     # "reverted" | "stop" | "max_hold" | "pre_results" | "end_of_data"
    days_held:    int
    stock_return: float   # simple, roll-adjusted
    hedge_return: float   # Σ h_j R_j (per rupee of stock), unsigned
    hedge_gross:  float   # Σ |h_j|
    n_rolls:      int
    gross_pnl:    float
    cost:         float

    @property
    def net_pnl(self) -> float:
        return self.gross_pnl - self.cost


def _leg_cost(notional: float, ret: float, direction: str, entry: date, exit_: date, n_rolls: int) -> float:
    if notional <= 0:
        return 0.0
    slip = SLIPPAGE_BPS_PER_SIDE / 1e4
    cost = position_cost(notional, notional * (1 + ret), 1, 1, direction, entry, exit_)
    cost += 2 * slip * notional
    for _ in range(n_rolls):
        cost += position_cost(notional, notional, 1, 1, direction, exit_, exit_) + 2 * slip * notional
    return cost


def _ffill_price(panel: Panel, t: int, j: int) -> float:
    col = panel.adj[: t + 1, j]
    ok = np.where(~np.isnan(col))[0]
    return float(col[ok[-1]]) if len(ok) else float("nan")


def _close_trade(panel: Panel, open_: dict, t_exit: int, reason: str) -> StatArbTrade:
    j, t_in, sc = open_["j"], open_["t_entry"], open_["score"]
    p_in, p_out = panel.adj[t_in, j], _ffill_price(panel, t_exit, j)
    stock_ret = p_out / p_in - 1
    hedge_ret = 0.0
    for k, h in zip(sc.peer_idx, sc.hedge):
        q_in = _ffill_price(panel, t_in, k)
        q_out = _ffill_price(panel, t_exit, k)
        hedge_ret += h * (q_out / q_in - 1)
    sign = 1.0 if open_["side"] == "LONG" else -1.0
    gross = sign * NOTIONAL * (stock_ret - hedge_ret)

    expiries = {e for e in panel.expiry[t_in:t_exit + 1, j] if e is not None}
    n_rolls = max(0, len(expiries) - 1)
    hedge_gross = float(sum(abs(h) for h in sc.hedge))
    d_in, d_out = panel.dates[t_in], panel.dates[t_exit]
    stock_dir = "BUY" if sign > 0 else "SELL"
    hedge_dir = "SELL" if (sign * sum(sc.hedge)) > 0 else "BUY"
    cost = (_leg_cost(NOTIONAL, stock_ret, stock_dir, d_in, d_out, n_rolls)
            + _leg_cost(NOTIONAL * hedge_gross, hedge_ret / hedge_gross if hedge_gross else 0.0,
                        hedge_dir, d_in, d_out, n_rolls))
    return StatArbTrade(
        symbol=panel.symbols[j], model=sc.model, side=open_["side"],
        signal_date=panel.dates[open_["t_signal"]], entry_date=d_in, exit_date=d_out,
        entry_s=sc.s, exit_reason=reason, days_held=t_exit - t_in,
        stock_return=stock_ret, hedge_return=hedge_ret, hedge_gross=hedge_gross,
        n_rolls=n_rolls, gross_pnl=gross, cost=cost,
    )


def simulate(
    panel: Panel,
    scores: list[list[Optional[Score]]],
    start_idx: int,
    results_days: dict[str, set[int]],
) -> list[StatArbTrade]:
    """Per-stock state machine. Signal at close t -> fill at close t+1.
    results_days: {symbol: panel row indices of results reaction days}."""
    T = len(panel.dates)
    trades: list[StatArbTrade] = []
    for j, sym in enumerate(panel.symbols):
        reactions = results_days.get(sym, set())
        open_: Optional[dict] = None
        pending: Optional[tuple[str, object]] = None  # ("enter", (side, t_signal, score)) | ("exit", reason)

        for t in range(start_idx, T):
            have_price = not math.isnan(panel.adj[t, j])

            if pending and have_price:
                kind, payload = pending
                if kind == "enter":
                    side, t_signal, sc = payload
                    open_ = {"j": j, "side": side, "t_signal": t_signal, "t_entry": t, "score": sc}
                else:
                    trades.append(_close_trade(panel, open_, t, payload))
                    open_ = None
                pending = None

            if open_ and pending is None and have_price and (t + 1) in reactions:
                trades.append(_close_trade(panel, open_, t, "pre_results"))
                open_ = None
                continue

            sc = scores[t][j]
            if pending is not None or sc is None:
                continue

            if open_:
                if t + 1 - open_["t_entry"] >= MAX_HOLD_DAYS:
                    pending = ("exit", "max_hold")
                elif sc.s is not None:
                    if abs(sc.s) >= STOP_S and (sc.s < 0) == (open_["side"] == "LONG"):
                        pending = ("exit", "stop")
                    elif open_["side"] == "LONG" and sc.s >= EXIT_LONG_S:
                        pending = ("exit", "reverted")
                    elif open_["side"] == "SHORT" and sc.s <= EXIT_SHORT_S:
                        pending = ("exit", "reverted")
            elif sc.tradeable and abs(sc.s) >= ENTRY_S and abs(sc.s) < STOP_S:
                if any(abs(t - r) <= RESULTS_BLACKOUT_DAYS or abs(t + 1 - r) <= RESULTS_BLACKOUT_DAYS
                       for r in reactions):
                    continue
                pending = ("enter", ("LONG" if sc.s < 0 else "SHORT", t, sc))

        if open_:
            trades.append(_close_trade(panel, open_, T - 1, "end_of_data"))
    return sorted(trades, key=lambda tr: tr.entry_date)


# ─── Metrics ────────────────────────────────────────────────────────────────

def to_backtest_trades(trades: list[StatArbTrade]) -> list[BacktestTrade]:
    """%-return basis = stock-leg notional (methodology doc)."""
    out, cum = [], 0.0
    for i, t in enumerate(sorted(trades, key=lambda x: x.entry_date)):
        cum += t.gross_pnl
        out.append(BacktestTrade(
            trade_num=i + 1, direction="Long" if t.side == "LONG" else "Short", qty=1,
            entry_date=datetime.combine(t.entry_date, datetime.min.time()), entry_price=NOTIONAL,
            exit_date=datetime.combine(t.exit_date, datetime.min.time()), exit_price=NOTIONAL + t.gross_pnl,
            profit=t.gross_pnl, profit_pct=t.gross_pnl / NOTIONAL * 100, cum_profit=cum,
            bars_held=max(1, t.days_held), costs=t.cost,
        ))
    return out


def metrics(trades: list[StatArbTrade]):
    return _compute_metrics(to_backtest_trades(trades))


@dataclass(frozen=True)
class Calibration:
    buckets:  dict[str, tuple[int, float]]  # label -> (n, mean 10d fwd residual return)
    long_n:   int
    long_mean: float
    short_n:  int
    short_mean: float
    t_stat:   float


_BUCKETS = [("s <= -2", -math.inf, -2.0), ("-2 < s <= -1.25", -2.0, -1.25),
            ("-1.25 < s < 1.25", -1.25, 1.25), ("1.25 <= s < 2", 1.25, 2.0), ("s >= 2", 2.0, math.inf)]


def _bucket(s: float) -> str:
    if s <= -2.0:
        return _BUCKETS[0][0]
    if s <= -ENTRY_S:
        return _BUCKETS[1][0]
    if s < ENTRY_S:
        return _BUCKETS[2][0]
    if s < 2.0:
        return _BUCKETS[3][0]
    return _BUCKETS[4][0]


def calibrate(panel: Panel, scores: list[list[Optional[Score]]], start_idx: int,
              horizon: int = CALIBRATION_HORIZON) -> Calibration:
    """Non-overlapping samples every `horizon` rows: forward residual return
    Σ_{t+1..t+h} (r_i - h·r_peers), hedge frozen at t."""
    by_bucket: dict[str, list[float]] = {label: [] for label, *_ in _BUCKETS}
    longs, shorts = [], []
    T = len(panel.dates)
    for t in range(start_idx, T - horizon, horizon):
        for j in range(len(panel.symbols)):
            sc = scores[t][j]
            if sc is None or not sc.tradeable:
                continue
            fwd = panel.returns[t + 1:t + horizon + 1]
            if np.isnan(fwd[:, j]).any() or np.isnan(fwd[:, list(sc.peer_idx)]).any():
                continue
            resid = float(fwd[:, j].sum() - (fwd[:, list(sc.peer_idx)] @ np.array(sc.hedge)).sum())
            by_bucket[_bucket(sc.s)].append(resid)
            if sc.s <= -ENTRY_S:
                longs.append(resid)
            elif sc.s >= ENTRY_S:
                shorts.append(resid)

    def _mean(x):
        return float(np.mean(x)) if x else float("nan")

    if len(longs) > 1 and len(shorts) > 1:
        se = math.sqrt(np.var(longs, ddof=1) / len(longs) + np.var(shorts, ddof=1) / len(shorts))
        t_stat = (_mean(longs) - _mean(shorts)) / se if se > 0 else float("nan")
    else:
        t_stat = float("nan")
    return Calibration(
        buckets={k: (len(v), _mean(v)) for k, v in by_bucket.items()},
        long_n=len(longs), long_mean=_mean(longs), short_n=len(shorts), short_mean=_mean(shorts),
        t_stat=t_stat,
    )


def verdict(trades: list[StatArbTrade], cal: Calibration,
            recent_years: tuple[int, ...] = (2025,)) -> dict[str, bool]:
    """Pass-bar checks. recent_years: one "PF > 1 on exits from Jan 1 of
    that year" check each -- BankNifty pre-registered (2025,), Nifty 50
    (2024, 2025)."""
    ordered = sorted(trades, key=lambda x: x.exit_date)
    mid = len(ordered) // 2
    overall = metrics(ordered)
    checks = {
        "edge (PF > 1 and Sharpe > 0.5)": bool(ordered) and overall.has_positive_edge,
        "PF > 1 first half": mid > 0 and metrics(ordered[:mid]).profit_factor > 1.0,
        "PF > 1 second half": mid > 0 and metrics(ordered[mid:]).profit_factor > 1.0,
    }
    for year in recent_years:
        recent = [t for t in ordered if t.exit_date >= date(year, 1, 1)]
        checks[f"PF > 1 exits {year}+"] = bool(recent) and metrics(recent).profit_factor > 1.0
    checks.update({
        "calibration: long bucket > 0": cal.long_mean > 0,
        "calibration: short bucket < 0": cal.short_mean < 0,
        "calibration: t > 2": cal.t_stat > 2.0,
    })
    return checks


def concurrency(trades: list[StatArbTrade], panel: Panel, start_idx: int) -> tuple[float, int]:
    """(average, max) number of positions open at each close from start_idx."""
    import bisect

    open_per_day = np.zeros(len(panel.dates), dtype=int)
    for tr in trades:
        a = bisect.bisect_left(panel.dates, tr.entry_date)
        b = bisect.bisect_left(panel.dates, tr.exit_date)
        open_per_day[a:b] += 1
    window = open_per_day[start_idx:]
    return (float(window.mean()) if len(window) else 0.0, int(window.max()) if len(window) else 0)
