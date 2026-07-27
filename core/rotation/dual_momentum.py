"""
QuantOS — Strategy 1: Regime-Filtered Dual-Momentum
─────────────────────────────────────────────────────
Pure, no-I/O logic for docs/S1_DUAL_MOMENTUM_METHODOLOGY.md. Deliberately
NOT built on core/rotation/ranker.py or equity_curve.py's simulate_portfolio
-- ranker.py's own docstring says live execution (core/rotation/executor.py)
imports it directly and its formula must never silently drift; this
strategy needs a different ranking formula, a different trend filter, and
a different (ATR/Chandelier) exit mechanic entirely, so it gets its own
module rather than risking that live-critical path. Copies
equity_curve.py's well-tested day-by-day mark-to-market loop shape, and
reuses its generic (non-S8-3-specific) pieces directly: `_sharpe`,
`_max_drawdown`, and `core.rotation.executor._size_new_entrants`.
"""

import bisect
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from core.brokers.base import OHLCV
from core.regime.fetcher import _ema
from core.risk.costs import CostModel
from core.rotation.equity_curve import EquityCurvePoint, EquityCurveResult, _max_drawdown, _sharpe
from core.rotation.executor import _size_new_entrants
from core.rotation.ranker import RebalancePlan, diff_target_basket

ENTRY_TOP_N = 15
EXIT_TOP_N = 25
RETURN_WINDOW_90D = 90
RETURN_WINDOW_180D = 180
EMA_TREND_FAST = 50
EMA_TREND_SLOW = 200
ATR_PERIOD = 14
INITIAL_STOP_ATR_MULT = 2.5
CHANDELIER_ATR_MULT = 2.0


# ─── Indicators (pure, no I/O) ──────────────────────────────────────────────

@dataclass
class SymbolIndicators:
    dates:   list[datetime]
    closes:  list[float]
    opens:   list[float]
    highs:   list[float]
    lows:    list[float]
    ema50:   list[Optional[float]]
    ema200:  list[Optional[float]]
    atr14:   list[Optional[float]]
    score:   list[Optional[float]]   # 0.5*ret90d + 0.5*ret180d, None until warmed up


def walk_forward_ema(closes: list[float], period: int) -> list[Optional[float]]:
    """EMA at each index using only closes up to and including that index —
    same walk-forward pattern as core/meanreversion/gutcheck.py's
    walk_forward_emas, reusing core.regime.fetcher._ema directly."""
    n = len(closes)
    result: list[Optional[float]] = [None] * n
    for i in range(n):
        if i + 1 >= period:
            result[i] = _ema(closes[: i + 1], period)
    return result


def wilder_atr(
    highs: list[float], lows: list[float], closes: list[float], period: int = ATR_PERIOD,
) -> list[Optional[float]]:
    """Wilder's ATR: true range = max(H-L, |H-prevClose|, |L-prevClose|),
    seeded with a simple average of the first `period` true ranges then
    Wilder-smoothed (alpha=1/period) — same smoothing shape as this
    session's rsi14 in core/meanreversion/gutcheck.py, applied to true
    range instead of gain/loss."""
    n = len(closes)
    result: list[Optional[float]] = [None] * n
    if n <= period:
        return result
    trs = [
        max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        for i in range(1, n)
    ]
    avg = sum(trs[:period]) / period
    result[period] = avg
    for i in range(period, len(trs)):
        avg = (avg * (period - 1) + trs[i]) / period
        result[i + 1] = avg
    return result


def _trading_day_return_pct(closes: list[float], idx: int, window: int) -> Optional[float]:
    prev_i = idx - window
    if prev_i < 0:
        return None
    prev = closes[prev_i]
    if prev <= 0:
        return None
    return (closes[idx] / prev - 1) * 100


def build_indicators(daily: list[OHLCV]) -> SymbolIndicators:
    dates = [c.timestamp for c in daily]
    closes = [c.close for c in daily]
    opens = [c.open for c in daily]
    highs = [c.high for c in daily]
    lows = [c.low for c in daily]
    ema50 = walk_forward_ema(closes, EMA_TREND_FAST)
    ema200 = walk_forward_ema(closes, EMA_TREND_SLOW)
    atr14 = wilder_atr(highs, lows, closes, ATR_PERIOD)
    score: list[Optional[float]] = []
    for i in range(len(closes)):
        r90 = _trading_day_return_pct(closes, i, RETURN_WINDOW_90D)
        r180 = _trading_day_return_pct(closes, i, RETURN_WINDOW_180D)
        score.append(0.5 * r90 + 0.5 * r180 if r90 is not None and r180 is not None else None)
    return SymbolIndicators(
        dates=dates, closes=closes, opens=opens, highs=highs, lows=lows,
        ema50=ema50, ema200=ema200, atr14=atr14, score=score,
    )


def _index_at_or_before(dates: list[datetime], target_date: datetime) -> Optional[int]:
    idx = bisect.bisect_right(dates, target_date) - 1
    return idx if idx >= 0 else None


def _index_at_exact(dates: list[datetime], target_date: datetime) -> Optional[int]:
    idx = bisect.bisect_right(dates, target_date) - 1
    if idx < 0 or dates[idx] != target_date:
        return None
    return idx


# ─── Ranking (Filter 1 trend + Filter 2 composite score) ────────────────────

def ranked_eligible_symbols(
    indicators: dict[str, SymbolIndicators], as_of_date: datetime,
    eligible: Optional[frozenset] = None,
) -> list[str]:
    """Full trend-filtered (EMA50>EMA200), score-sorted list, best first —
    NOT truncated to top_n. Caller slices [:ENTRY_TOP_N] for the entry
    basket and set([:EXIT_TOP_N]) for hold-eligibility, so both bands come
    from one consistent re-rank, matching the strategy spec's "drops out
    of Top 25 in the weekly re-rank" (the SAME re-rank that produces the
    Top 15, just read further down the list)."""
    scored = []
    for symbol, ind in indicators.items():
        if eligible is not None and symbol not in eligible:
            continue
        idx = _index_at_or_before(ind.dates, as_of_date)
        if idx is None or ind.score[idx] is None:
            continue
        e50, e200 = ind.ema50[idx], ind.ema200[idx]
        if e50 is None or e200 is None or e50 <= e200:
            continue   # Filter 1 fails
        scored.append((symbol, ind.score[idx]))
    scored.sort(key=lambda x: -x[1])
    return [s for s, _ in scored]


# ─── Stop-loss (initial ATR stop + Chandelier trail) ────────────────────────

def stop_level(
    entry_price: float, atr_at_entry: float, highest_high_since_entry: float, atr_now: float,
) -> float:
    """A stop that only ever ratchets up, never loosens. Note a real,
    checked-by-test mathematical property of these specific multipliers
    (2.5 initial vs 2.0 Chandelier): with highest_high initialized to
    entry_price and stable ATR, the Chandelier line is ALREADY at or
    above (tighter than) the initial stop from the moment of entry, since
    2.0 < 2.5 — the initial stop only actually binds when ATR expands more
    than 25% right after entry with no favorable move yet (see
    test_dual_momentum.py's two stop_level tests for the exact algebra).
    This isn't a bug: it means the Chandelier line is the operative stop
    almost all the time given these parameters, and the initial stop is a
    volatility-expansion backstop, not typically the day-to-day governor —
    a real, disclosed property of the spec's own chosen multipliers, not
    tuned after seeing a result. See methodology doc's 'combined stop
    level' section."""
    initial_stop = entry_price - INITIAL_STOP_ATR_MULT * atr_at_entry
    chandelier = highest_high_since_entry - CHANDELIER_ATR_MULT * atr_now
    return max(initial_stop, chandelier)


def _atr_at_entry(ind: SymbolIndicators, fill_idx: Optional[int]) -> float:
    """ATR14 as of the PRIOR trading day, not the fill day's own —  at the
    moment of a market-open fill, that day's own high/low/close aren't
    known yet, so using ATR14[fill_idx] (which incorporates them) would be
    a same-day lookahead into the very bar the entry is filling on (caught
    by independent review, Fable, 2026-07-24; see
    test_simulate_atr_at_entry_uses_prior_day_not_entry_day)."""
    if fill_idx is None or fill_idx == 0:
        return 0.0
    return ind.atr14[fill_idx - 1] or 0.0


# ─── Simulation (day-by-day, mirrors equity_curve.py's loop shape) ─────────

@dataclass
class ClosedTrade:
    symbol:      str
    entry_date:  datetime
    entry_price: float
    exit_date:   datetime
    exit_price:  float
    qty:         int
    exit_reason: str   # "atr_stop" | "rank_dropout" | "final_close"
    costs:       float = 0.0   # round-trip transaction cost (INR), from CostModel


def simulate_dual_momentum(
    daily_dates: list[datetime],
    rebal_dates: set,
    indicators: dict[str, SymbolIndicators],
    initial_capital: float,
    position_size: float,
    cost_model: CostModel,
    eligible_asof_fn=None,
    regime_ok_by_date: Optional[dict] = None,
) -> EquityCurveResult:
    """One simulated account. Ranking/rebalance happens on rebal_dates;
    NEW entries fill at the NEXT trading day's open (queued, not
    same-day — see methodology doc's "Monday open" entry rule); stop-loss
    is checked every trading day against the daily close; rank-dropout
    (falling out of the top EXIT_TOP_N) is checked only on rebal_dates,
    matching S8-3's own weekly-only rank-dropout cadence.

    `eligible_asof_fn`, if given, is a `datetime -> frozenset` callable
    (e.g. `functools.partial(nifty200_eligible_asof, snapshots)`) called
    freshly on EVERY rebalance date — a single static frozenset would be
    survivorship-biased (today's membership applied retroactively, S8-3's
    original mistake); the real point-in-time universe changes over the
    backtest window, so it must be re-resolved per rebalance, not passed
    once. Deliberately NOT a plain frozenset parameter for this reason —
    see the earlier bug this replaced, caught before running, in
    docs/S1_DUAL_MOMENTUM_METHODOLOGY.md's coverage-limitation section.

    `regime_ok_by_date`, if given (date -> bool, e.g. "is NIFTY 50 above
    its own EMA200 as of this date"), blocks NEW entries on rebalance
    dates where it's False — per docs/S1_DUAL_MOMENTUM_METHODOLOGY.md this
    is INFORMATIONAL ONLY (the headline run omits this entirely); existing
    positions are never force-exited by a regime flip, only "aggressively
    trailed" — which the always-active Chandelier stop already does, no
    separate logic needed for that half of the spec's Filter 3 rule.
    """
    cash = initial_capital
    holdings: dict[str, dict] = {}   # symbol -> {qty, entry_price, entry_date, atr_at_entry, highest_high}
    pending_buys: list[str] = []
    curve: list[EquityCurvePoint] = []
    trades: list[ClosedTrade] = []

    for day_i, today in enumerate(daily_dates):
        is_rebal = today in rebal_dates

        # ── Fill any entries queued from the PRIOR rebalance day, at TODAY's open ──
        if pending_buys:
            price_lookup = {}
            for symbol in pending_buys:
                idx = _index_at_exact(indicators[symbol].dates, today)
                if idx is not None:
                    price_lookup[symbol] = indicators[symbol].opens[idx]
            sized, _skipped = _size_new_entrants(pending_buys, price_lookup, cash, position_size)
            for symbol, qty in sized.items():
                price = price_lookup[symbol]
                cash -= price * qty
                idx = _index_at_exact(indicators[symbol].dates, today)
                atr_at_entry = _atr_at_entry(indicators[symbol], idx)
                holdings[symbol] = {
                    "qty": qty, "entry_price": price, "entry_date": today,
                    "atr_at_entry": atr_at_entry or 0.0, "highest_high": price,
                }
            pending_buys = []

        # ── Update highest-high-since-entry + check stop-loss (every day) ──
        for symbol in list(holdings.keys()):
            ind = indicators[symbol]
            idx = _index_at_exact(ind.dates, today)
            if idx is None:
                continue   # no bar today (halt/listing gap) — keep holding, can't mark or trigger
            pos = holdings[symbol]
            pos["highest_high"] = max(pos["highest_high"], ind.highs[idx])
            atr_now = ind.atr14[idx]
            close = ind.closes[idx]
            if atr_now is not None:
                level = stop_level(pos["entry_price"], pos["atr_at_entry"], pos["highest_high"], atr_now)
                if close <= level:
                    costs = cost_model.cost_of(pos["entry_price"], close, pos["qty"], "BUY")
                    cash += close * pos["qty"] - costs
                    trades.append(ClosedTrade(
                        symbol=symbol, entry_date=pos["entry_date"], entry_price=pos["entry_price"],
                        exit_date=today, exit_price=close, qty=pos["qty"], exit_reason="atr_stop",
                        costs=costs,
                    ))
                    del holdings[symbol]

        # ── Rebalance: rank, exit rank-dropouts, queue new entries ──────────
        if is_rebal:
            eligible_today = eligible_asof_fn(today) if eligible_asof_fn is not None else None
            ranked = ranked_eligible_symbols(indicators, today, eligible=eligible_today)
            hold_eligible = set(ranked[:EXIT_TOP_N])
            regime_ok = regime_ok_by_date is None or regime_ok_by_date.get(today, True)
            entry_basket = ranked[:ENTRY_TOP_N] if regime_ok else []

            for symbol in list(holdings.keys()):
                if symbol not in hold_eligible:
                    ind = indicators[symbol]
                    idx = _index_at_exact(ind.dates, today)
                    if idx is None:
                        continue
                    pos = holdings[symbol]
                    close = ind.closes[idx]
                    costs = cost_model.cost_of(pos["entry_price"], close, pos["qty"], "BUY")
                    cash += close * pos["qty"] - costs
                    trades.append(ClosedTrade(
                        symbol=symbol, entry_date=pos["entry_date"], entry_price=pos["entry_price"],
                        exit_date=today, exit_price=close, qty=pos["qty"], exit_reason="rank_dropout",
                        costs=costs,
                    ))
                    del holdings[symbol]

            plan: RebalancePlan = diff_target_basket(holdings.keys(), entry_basket)
            pending_buys = plan.buys   # filled next trading day's open, above

        # ── Mark-to-market ──────────────────────────────────────────────────
        holdings_value = 0.0
        for symbol, pos in holdings.items():
            ind = indicators[symbol]
            idx = _index_at_or_before(ind.dates, today)
            price = ind.closes[idx] if idx is not None else pos["entry_price"]
            holdings_value += price * pos["qty"]
        curve.append(EquityCurvePoint(date=today, equity=cash + holdings_value))

    # Force-close anything still open at the end.
    if daily_dates:
        final_date = daily_dates[-1]
        for symbol, pos in list(holdings.items()):
            ind = indicators[symbol]
            idx = _index_at_or_before(ind.dates, final_date)
            price = ind.closes[idx] if idx is not None else pos["entry_price"]
            costs = cost_model.cost_of(pos["entry_price"], price, pos["qty"], "BUY")
            cash += price * pos["qty"] - costs
            trades.append(ClosedTrade(
                symbol=symbol, entry_date=pos["entry_date"], entry_price=pos["entry_price"],
                exit_date=final_date, exit_price=price, qty=pos["qty"], exit_reason="final_close",
                costs=costs,
            ))
        holdings.clear()
        if curve:
            curve[-1] = EquityCurvePoint(date=final_date, equity=cash)

    return _finalize_result(initial_capital, curve, trades)


def _finalize_result(
    initial_capital: float, curve: list[EquityCurvePoint], trades: list[ClosedTrade],
) -> EquityCurveResult:
    if not curve:
        return EquityCurveResult(exit_rule="atr_chandelier", initial_capital=initial_capital,
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
        exit_rule="atr_chandelier", initial_capital=initial_capital, final_equity=round(final_equity, 2),
        curve=curve, trades=trades, cagr_pct=round(cagr_pct, 2), sharpe=round(sharpe, 3),
        max_drawdown_pct=round(dd_pct, 2), max_drawdown_rs=round(dd_rs, 2),
        total_return_pct=round(total_return_pct, 2),
    )
