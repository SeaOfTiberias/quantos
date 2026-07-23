"""
QuantOS — S8-3 Rotation: Real Capital-Tracked Equity Curve
────────────────────────────────────────────────────────────
docs/S8_3_BACKTEST_RESULTS.md's headline numbers (profit factor 1.18,
Sharpe 0.63, "net profit" 745.4%) are POOLED PER-TRADE statistics — an
unweighted sum/variance across 2,104 individual trades (core/backtest/
parser.py's _compute_metrics), not a real portfolio equity curve. Proof:
that report's own "max drawdown: 652.4%" is structurally impossible for
a real portfolio (you can't lose more than 100% of unlevered capital) —
it's a cumulative sum of independent trade percentages, not a compounding
account balance. Those pooled stats correctly answered Sprint 7/8's
"is there a signal edge at all" gate, but were never built to answer
"what does my real ₹10L capital actually become."

This module builds that instead: a single simulated account (starting
capital, real position sizing via core/rotation/executor.py's own
_size_new_entrants so backtest sizing can never silently diverge from
live sizing), marked to market daily, so CAGR/Sharpe/max-drawdown are
computed on genuine equity levels — max drawdown is now bounded to
[0, 100]% by construction.

Also supports pluggable per-symbol exit rules layered ON TOP OF the
baseline rank-dropout exit (never replacing it): "stop_loss" and
"ema_cross" are checked on EVERY trading day (not just weekly rebalance
dates), since a real stop-loss or EMA crossover would be monitored daily,
not just when the portfolio happens to rebalance — checking only at
rebalance boundaries would systematically miss/understate exactly the
kind of intra-week drawdown (e.g. a 5% single-day drop) these variants
exist to catch. Entries remain weekly-rebalance-only, matching S8-3's
actual pre-committed methodology (docs/S8_3_MOMENTUM_METHODOLOGY.md) —
these variants change how a position exits, not the entry cadence.

Pre-committed BEFORE running (2026-07-21): exactly two variants get
tested against the baseline (5% fixed stop-loss, EMA9-below-EMA21
cross) — not a parameter sweep, to avoid exactly the overfitting risk
S8-4 was careful about with its own trailing-stop test.
"""

import bisect
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from core.risk.costs import CostModel
from core.rotation.executor import _size_new_entrants
from core.rotation.nifty500_reconstitution import eligible_symbols_asof
from core.rotation.ranker import SymbolSeries, diff_target_basket, rank_universe, value_as_of

STOP_LOSS_PCT_DEFAULT = 0.05
EMA_FAST_DEFAULT = 9
EMA_SLOW_DEFAULT = 21


@dataclass
class ClosedTrade:
    symbol:      str
    entry_date:  datetime
    entry_price: float
    exit_date:   datetime
    exit_price:  float
    qty:         int
    exit_reason: str   # "rank_dropout" | "stop_loss" | "ema_cross" | "final_close"


@dataclass
class EquityCurvePoint:
    date:   datetime
    equity: float   # cash + mark-to-market value of open holdings


@dataclass
class EquityCurveResult:
    exit_rule:          str
    initial_capital:    float
    final_equity:       float
    curve:              list[EquityCurvePoint] = field(default_factory=list)
    trades:             list[ClosedTrade] = field(default_factory=list)
    cagr_pct:           float = 0.0
    sharpe:             float = 0.0
    max_drawdown_pct:   float = 0.0
    max_drawdown_rs:    float = 0.0
    total_return_pct:   float = 0.0

    @property
    def years_span(self) -> float:
        if len(self.curve) < 2:
            return 0.0
        return max(1, (self.curve[-1].date - self.curve[0].date).days) / 365.0


def _ema_series(closes: list[float], span: int) -> list[Optional[float]]:
    """EMA at each index, None until `span` closes have accumulated —
    mirrors ranker.py's rolling_high_series' None-until-warmed-up
    convention so callers treat "not enough data yet" uniformly."""
    if not closes:
        return []
    alpha = 2.0 / (span + 1)
    result: list[Optional[float]] = [None] * len(closes)
    ema = closes[0]
    for i, price in enumerate(closes):
        ema = price if i == 0 else (alpha * price + (1 - alpha) * ema)
        if i >= span - 1:
            result[i] = ema
    return result


def _index_at(series: SymbolSeries, target_date: datetime) -> Optional[int]:
    """Index of the bar exactly on target_date, or None if the symbol has
    no bar that day (listing gap/halt) — distinct from value_as_of's
    "most recent at or before", since exit checks need to know whether
    today's price is actually fresh before marking/triggering on it."""
    idx = bisect.bisect_right(series.dates, target_date) - 1
    if idx < 0 or series.dates[idx] != target_date:
        return None
    return idx


def _extra_exit_reason(
    exit_rule: str, price: float, entry_price: float,
    ema_fast_val: Optional[float], ema_slow_val: Optional[float],
    stop_loss_pct: float,
) -> Optional[str]:
    if exit_rule == "stop_loss":
        if price <= entry_price * (1 - stop_loss_pct):
            return "stop_loss"
    elif exit_rule == "ema_cross":
        if ema_fast_val is not None and ema_slow_val is not None and ema_fast_val < ema_slow_val:
            return "ema_cross"
    return None


def simulate_portfolio(
    daily_dates: list[datetime],
    rebal_dates: set,
    symbol_series: dict[str, SymbolSeries],
    top_n: int,
    initial_capital: float,
    position_size: float,
    cost_model: CostModel,
    exit_rule: str = "rank_only",
    stop_loss_pct: float = STOP_LOSS_PCT_DEFAULT,
    ema_fast: int = EMA_FAST_DEFAULT,
    ema_slow: int = EMA_SLOW_DEFAULT,
    universe_snapshots=None,
) -> EquityCurveResult:
    """
    Simulates ONE account (starting at initial_capital) trading the S8-3
    rotation over daily_dates, entering/re-ranking only on rebal_dates,
    checking exits every day. exit_rule in {"rank_only", "stop_loss",
    "ema_cross"} — "rank_only" reproduces the pre-committed baseline
    methodology exactly; the other two add one extra daily exit check on
    top of it, never replacing the rank-dropout exit.

    `universe_snapshots`, if given (a list of nifty500_reconstitution.
    UniverseSnapshot), restricts each rebalance's ranking to that week's
    true point-in-time Nifty 500 membership instead of every symbol in
    symbol_series — see nifty500_reconstitution.py for why. Omitting it
    reproduces the original survivorship-biased behavior exactly.
    """
    if exit_rule not in ("rank_only", "stop_loss", "ema_cross"):
        raise ValueError(f"Unknown exit_rule: {exit_rule!r}")

    ema_fast_series: dict[str, list[Optional[float]]] = {}
    ema_slow_series: dict[str, list[Optional[float]]] = {}
    if exit_rule == "ema_cross":
        for symbol, series in symbol_series.items():
            ema_fast_series[symbol] = _ema_series(series.closes, ema_fast)
            ema_slow_series[symbol] = _ema_series(series.closes, ema_slow)

    cash = initial_capital
    holdings: dict[str, dict] = {}   # symbol -> {qty, entry_price, entry_date}
    target_basket: list[str] = []
    curve: list[EquityCurvePoint] = []
    trades: list[ClosedTrade] = []

    for today in daily_dates:
        is_rebal = today in rebal_dates
        if is_rebal:
            eligible = (eligible_symbols_asof(universe_snapshots, today)
                        if universe_snapshots is not None else None)
            target_basket = rank_universe(symbol_series, today, top_n, eligible=eligible)

        # ── Exits (every day) ──────────────────────────────────────────
        for symbol in list(holdings.keys()):
            series = symbol_series[symbol]
            idx = _index_at(series, today)
            if idx is None:
                continue   # no bar today (halt/delisting gap) — keep holding, can't mark or trigger
            price = series.closes[idx]
            pos = holdings[symbol]

            reason = None
            if is_rebal and symbol not in target_basket:
                reason = "rank_dropout"
            else:
                ema_f = ema_fast_series.get(symbol, [None])[idx] if exit_rule == "ema_cross" else None
                ema_s = ema_slow_series.get(symbol, [None])[idx] if exit_rule == "ema_cross" else None
                reason = _extra_exit_reason(
                    exit_rule, price, pos["entry_price"], ema_f, ema_s, stop_loss_pct)

            if reason:
                costs = cost_model.cost_of(pos["entry_price"], price, pos["qty"], "BUY")
                cash += price * pos["qty"] - costs
                trades.append(ClosedTrade(
                    symbol=symbol, entry_date=pos["entry_date"], entry_price=pos["entry_price"],
                    exit_date=today, exit_price=price, qty=pos["qty"], exit_reason=reason,
                ))
                del holdings[symbol]

        # ── Entries (rebalance days only) ──────────────────────────────
        if is_rebal:
            plan = diff_target_basket(holdings.keys(), target_basket)
            price_lookup = {}
            for symbol in plan.buys:
                v = value_as_of(symbol_series[symbol], today)
                if v is not None:
                    price_lookup[symbol] = v[0]
            sized, _skipped = _size_new_entrants(plan.buys, price_lookup, cash, position_size)
            for symbol, qty in sized.items():
                price = price_lookup[symbol]
                cash -= price * qty
                holdings[symbol] = {"qty": qty, "entry_price": price, "entry_date": today}

        # ── Mark-to-market ──────────────────────────────────────────────
        holdings_value = 0.0
        for symbol, pos in holdings.items():
            v = value_as_of(symbol_series[symbol], today)
            if v is not None:
                holdings_value += v[0] * pos["qty"]
            else:
                holdings_value += pos["entry_price"] * pos["qty"]   # no bar yet — carry entry price
        curve.append(EquityCurvePoint(date=today, equity=cash + holdings_value))

    # Force-close anything still open at the end, so final_equity is fully cash.
    if daily_dates:
        final_date = daily_dates[-1]
        for symbol, pos in list(holdings.items()):
            series = symbol_series[symbol]
            v = value_as_of(series, final_date)
            price = v[0] if v is not None else pos["entry_price"]
            costs = cost_model.cost_of(pos["entry_price"], price, pos["qty"], "BUY")
            cash += price * pos["qty"] - costs
            trades.append(ClosedTrade(
                symbol=symbol, entry_date=pos["entry_date"], entry_price=pos["entry_price"],
                exit_date=final_date, exit_price=price, qty=pos["qty"], exit_reason="final_close",
            ))
        holdings.clear()
        if curve:
            curve[-1] = EquityCurvePoint(date=final_date, equity=cash)

    return _finalize_result(exit_rule, initial_capital, curve, trades)


def _finalize_result(exit_rule: str, initial_capital: float,
                      curve: list[EquityCurvePoint], trades: list[ClosedTrade]) -> EquityCurveResult:
    if not curve:
        return EquityCurveResult(exit_rule=exit_rule, initial_capital=initial_capital,
                                  final_equity=initial_capital)

    final_equity = curve[-1].equity
    total_return_pct = (final_equity - initial_capital) / initial_capital * 100

    days_span = max(1, (curve[-1].date - curve[0].date).days)
    years = days_span / 365.0
    cagr_pct = ((final_equity / initial_capital) ** (1 / years) - 1) * 100 if years > 0 and final_equity > 0 else 0.0

    daily_returns = []
    for i in range(1, len(curve)):
        prev = curve[i - 1].equity
        if prev > 0:
            daily_returns.append((curve[i].equity - prev) / prev)
    sharpe = _sharpe(daily_returns)

    dd_pct, dd_rs = _max_drawdown(curve)

    return EquityCurveResult(
        exit_rule=exit_rule, initial_capital=initial_capital, final_equity=round(final_equity, 2),
        curve=curve, trades=trades, cagr_pct=round(cagr_pct, 2), sharpe=round(sharpe, 3),
        max_drawdown_pct=round(dd_pct, 2), max_drawdown_rs=round(dd_rs, 2),
        total_return_pct=round(total_return_pct, 2),
    )


def _sharpe(daily_returns: list[float], risk_free: float = 0.0) -> float:
    if len(daily_returns) < 2:
        return 0.0
    mean = sum(daily_returns) / len(daily_returns)
    variance = sum((r - mean) ** 2 for r in daily_returns) / (len(daily_returns) - 1)
    std = variance ** 0.5
    if std < 1e-12:
        return 0.0
    import math
    return (mean - risk_free) / std * math.sqrt(252)


def _max_drawdown(curve: list[EquityCurvePoint]) -> tuple[float, float]:
    """Returns (drawdown_pct, drawdown_rs) — bounded to [0, 100]% by
    construction, since this walks real equity levels rather than summing
    independent trade percentages."""
    peak = curve[0].equity
    max_dd_pct = 0.0
    max_dd_rs = 0.0
    for point in curve:
        peak = max(peak, point.equity)
        dd_rs = peak - point.equity
        dd_pct = (dd_rs / peak * 100) if peak > 0 else 0.0
        if dd_pct > max_dd_pct:
            max_dd_pct = dd_pct
            max_dd_rs = dd_rs
    return max_dd_pct, max_dd_rs


# ─── Benchmark: buy-and-hold any index over the same window/capital ─────────
# Index-agnostic on purpose: used for both the Nifty 500 benchmark and the
# Nifty Alpha 50 benchmark (backtest_equity_curve.py calls it twice). Unlike
# the strategy's own trading universe, a passive buy-and-hold benchmark
# needs only the index's historical price level, not point-in-time
# constituent membership, so it doesn't need nifty500_reconstitution.py-style
# treatment even though Alpha 50's own membership changes quarterly.

@dataclass
class BenchmarkResult:
    initial_capital:   float
    final_equity:       float
    curve:              list[EquityCurvePoint] = field(default_factory=list)
    cagr_pct:           float = 0.0
    sharpe:             float = 0.0
    max_drawdown_pct:   float = 0.0
    max_drawdown_rs:    float = 0.0
    total_return_pct:   float = 0.0


def simulate_index_buy_and_hold(index_closes: list[tuple], initial_capital: float) -> BenchmarkResult:
    """index_closes: [(date, close), ...] sorted ascending, same date range
    as the rotation simulation. Buys as many "units" as initial_capital
    affords at the first close, marks to market daily, no transaction
    costs (a single buy-and-hold trade's costs are immaterial at this
    horizon and would just be a constant offset)."""
    if not index_closes:
        return BenchmarkResult(initial_capital=initial_capital, final_equity=initial_capital)

    first_close = index_closes[0][1]
    units = initial_capital / first_close
    curve = [EquityCurvePoint(date=d, equity=units * close) for d, close in index_closes]

    return BenchmarkResult(
        initial_capital=initial_capital,
        final_equity=round(curve[-1].equity, 2),
        curve=curve,
        **_benchmark_metrics(curve, initial_capital),
    )


def _benchmark_metrics(curve: list[EquityCurvePoint], initial_capital: float) -> dict:
    final_equity = curve[-1].equity
    days_span = max(1, (curve[-1].date - curve[0].date).days)
    years = days_span / 365.0
    cagr_pct = ((final_equity / initial_capital) ** (1 / years) - 1) * 100 if years > 0 else 0.0
    total_return_pct = (final_equity - initial_capital) / initial_capital * 100

    daily_returns = []
    for i in range(1, len(curve)):
        prev = curve[i - 1].equity
        if prev > 0:
            daily_returns.append((curve[i].equity - prev) / prev)
    sharpe = _sharpe(daily_returns)
    dd_pct, dd_rs = _max_drawdown(curve)

    return dict(cagr_pct=round(cagr_pct, 2), sharpe=round(sharpe, 3),
                max_drawdown_pct=round(dd_pct, 2), max_drawdown_rs=round(dd_rs, 2),
                total_return_pct=round(total_return_pct, 2))


def compute_alpha(strategy: EquityCurveResult, benchmark: BenchmarkResult) -> dict:
    """Simple total-return alpha (strategy - benchmark) over the identical
    window/capital, plus each side's own CAGR/Sharpe/drawdown for context.
    Callable against any BenchmarkResult (Nifty 500, Nifty Alpha 50, ...) —
    not Nifty-specific despite historically only ever being called with one."""
    return {
        "alpha_total_return_pct": round(strategy.total_return_pct - benchmark.total_return_pct, 2),
        "alpha_cagr_pct": round(strategy.cagr_pct - benchmark.cagr_pct, 2),
        "strategy_beats_benchmark": strategy.total_return_pct > benchmark.total_return_pct,
    }
