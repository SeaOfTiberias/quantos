"""
QuantOS — Generic Account-style equity-curve simulator
────────────────────────────────────────────────────────────
Answers "what does ₹X real capital actually become" for a strategy,
properly -- real position sizing against available cash, real
compounding, real mark-to-market, real drawdown bounded to [0,100]% by
construction (walking real equity levels, not summing independent
per-trade percentages the way `core/backtest/parser.py`'s pooled stats
do -- see that module's own trap, documented in
`core/rotation/equity_curve.py`'s module docstring, which this project
already hit once with S8-3).

Why this is a NEW module and not a reuse of `core/rotation/equity_curve.py`
────────────────────────────────────────────────────────────────────────
That module is built entirely around S8-3's own semantics: weekly
`rebal_dates`, `rank_universe`/`target_basket_fn`-based entries, and
`SymbolSeries`-shaped price history. Confirmed unsuitable for either of
this module's target use cases before writing this (see
docs/SHARPE_SWEEP_AND_EQUITY_CURVE_PLAN.md's "why not reuse" section):
- Candidate 18 (ORB options scalping) trades intraday, same-day entry/exit,
  sized by lot count x option premium (not a share count), with NIFTY and
  BankNifty potentially firing the same day and competing for one cash
  pool -- there is no "weekly rebalance" or "rank universe" here at all.
- The Darvas ATR-stop candidate holds independent, overlapping equity
  positions triggered by individual breakout signals, not a fixed top-N
  rotation -- entries happen whenever a signal fires, not on a fixed
  calendar.

This module has NO knowledge of ranking, rebalancing, or equities
specifically: it is a plain cash + arbitrary-instrument ledger, marked to
market on demand. A thin, strategy-specific adapter per candidate decides
position sizing and reads that strategy's own existing signal/trade
generation code; this module only tracks cash and marks positions.

Multiple positions in the same instrument_id are never merged -- each
`Account.open()` call creates an independent position with its own entry
price, so overlapping positions (two option trades in the same underlying
on different days, two Darvas breakouts in the same stock) are tracked
distinctly rather than silently averaged together.
"""

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional


@dataclass
class Position:
    instrument_id: str
    qty: float
    entry_price: float
    entry_date: datetime
    meta: dict = field(default_factory=dict)


@dataclass
class ClosedPosition:
    instrument_id: str
    qty: float
    entry_price: float
    entry_date: datetime
    exit_price: float
    exit_date: datetime
    costs: float = 0.0
    exit_reason: str = ""
    meta: dict = field(default_factory=dict)

    @property
    def realized_pnl(self) -> float:
        """Net of `costs`, long-only convention (profit = (exit - entry) *
        qty) -- correct for the two target candidates (long options,
        long equities); a short-selling adapter would need its own sign
        convention, not yet needed by either."""
        return (self.exit_price - self.entry_price) * self.qty - self.costs


@dataclass
class EquityCurvePoint:
    date: datetime
    cash: float
    positions_value: float

    @property
    def equity(self) -> float:
        return self.cash + self.positions_value


@dataclass
class EquityCurveResult:
    initial_capital:   float
    final_equity:       float
    curve:              list[EquityCurvePoint] = field(default_factory=list)
    closed_positions:   list[ClosedPosition] = field(default_factory=list)
    cagr_pct:           float = 0.0
    sharpe:             float = 0.0
    sortino:            float = 0.0
    calmar:             float = 0.0
    ulcer_index:        float = 0.0
    max_drawdown_pct:   float = 0.0
    max_drawdown_rs:    float = 0.0
    max_drawdown_duration_days: int = 0
    total_return_pct:   float = 0.0


class InsufficientCash(Exception):
    """Raised by `Account.open` when `strict=True` (the default) and cash
    can't cover the position's full upfront cost."""


class Account:
    """A single simulated account: cash balance + arbitrary open positions.

    Every open position is paid for in full, upfront cash (qty * price,
    no margin) -- correct for long options and long equities, the only two
    position types either target candidate needs. Positions are keyed
    internally by an auto-incrementing id returned from `open()`, which the
    caller must hold onto to `close()` the right one later.
    """

    def __init__(self, initial_capital: float):
        if initial_capital <= 0:
            raise ValueError("initial_capital must be positive")
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self._next_id = 0
        self.open_positions: dict[int, Position] = {}
        self.closed_positions: list[ClosedPosition] = []
        self.curve: list[EquityCurvePoint] = []

    def cost_to_open(self, qty: float, price: float) -> float:
        return qty * price

    def can_afford(self, qty: float, price: float) -> bool:
        return self.cost_to_open(qty, price) <= self.cash + 1e-9

    def open(self, instrument_id: str, qty: float, price: float, when: datetime,
              meta: Optional[dict] = None, strict: bool = True) -> Optional[int]:
        """Opens a new position, paying `qty * price` in cash upfront.
        Returns the new position's id.

        If cash is insufficient: raises `InsufficientCash` when
        `strict=True` (the default -- forces the caller to have an
        explicit sizing/skip policy rather than silently going negative);
        returns `None` when `strict=False` (for a caller that wants to
        just skip an unaffordable signal and move on)."""
        if qty <= 0:
            raise ValueError(f"qty must be positive, got {qty}")
        cost = self.cost_to_open(qty, price)
        if cost > self.cash + 1e-9:
            if strict:
                raise InsufficientCash(
                    f"need {cost:.2f}, have {self.cash:.2f} for {qty}x{instrument_id}@{price}")
            return None
        self.cash -= cost
        pos_id = self._next_id
        self._next_id += 1
        self.open_positions[pos_id] = Position(
            instrument_id=instrument_id, qty=qty, entry_price=price,
            entry_date=when, meta=meta or {})
        return pos_id

    def close(self, pos_id: int, price: float, when: datetime,
              costs: float = 0.0, exit_reason: str = "") -> ClosedPosition:
        """Closes an open position, crediting `qty * price - costs` to cash."""
        pos = self.open_positions.pop(pos_id)
        proceeds = pos.qty * price - costs
        self.cash += proceeds
        closed = ClosedPosition(
            instrument_id=pos.instrument_id, qty=pos.qty, entry_price=pos.entry_price,
            entry_date=pos.entry_date, exit_price=price, exit_date=when,
            costs=costs, exit_reason=exit_reason, meta=pos.meta)
        self.closed_positions.append(closed)
        return closed

    def mark(self, when: datetime, mark_prices: dict) -> EquityCurvePoint:
        """Appends one equity-curve point for `when`. `mark_prices` maps
        instrument_id -> price for every instrument this account might be
        holding; a position whose instrument_id is missing from the dict
        is carried at its own entry_price -- no fresher mark available,
        same fallback convention `core/rotation/equity_curve.py` uses for
        a listing-gap/halt day. Call once per simulated day, after that
        day's opens/closes."""
        positions_value = 0.0
        for pos in self.open_positions.values():
            price = mark_prices.get(pos.instrument_id, pos.entry_price)
            positions_value += pos.qty * price
        point = EquityCurvePoint(date=when, cash=self.cash, positions_value=positions_value)
        self.curve.append(point)
        return point

    def force_close_all(self, when: datetime, mark_prices: dict,
                         exit_reason: str = "final_close") -> None:
        """Closes every still-open position at `when`'s mark price (or its
        own entry price if unavailable), zero costs -- used only so
        `final_equity` is fully realized cash at the end of a run, matching
        `core/rotation/equity_curve.py`'s own end-of-run convention. Call
        this before the final `mark()` if a run must end fully in cash."""
        for pos_id in list(self.open_positions.keys()):
            pos = self.open_positions[pos_id]
            price = mark_prices.get(pos.instrument_id, pos.entry_price)
            self.close(pos_id, price, when, costs=0.0, exit_reason=exit_reason)

    def finalize(self) -> EquityCurveResult:
        """Computes CAGR/Sharpe/max-drawdown from the recorded curve.
        Requires at least one `mark()` call to have happened; returns a
        curve-less, no-op result (final_equity == initial_capital) if
        `mark()` was never called."""
        if not self.curve:
            return EquityCurveResult(initial_capital=self.initial_capital,
                                      final_equity=self.initial_capital)

        final_equity = self.curve[-1].equity
        total_return_pct = (final_equity - self.initial_capital) / self.initial_capital * 100

        days_span = max(1, (self.curve[-1].date - self.curve[0].date).days)
        years = days_span / 365.0
        cagr_pct = (((final_equity / self.initial_capital) ** (1 / years) - 1) * 100
                    if years > 0 and final_equity > 0 else 0.0)

        daily_returns = []
        for i in range(1, len(self.curve)):
            prev = self.curve[i - 1].equity
            if prev > 0:
                daily_returns.append((self.curve[i].equity - prev) / prev)
        sharpe = _sharpe(daily_returns)
        sortino = _sortino(daily_returns)
        dd_pct, dd_rs = _max_drawdown(self.curve)
        calmar = (cagr_pct / dd_pct) if dd_pct > 0 else 0.0
        ulcer = _ulcer_index(self.curve)
        dd_duration = _max_drawdown_duration_days(self.curve)

        return EquityCurveResult(
            initial_capital=self.initial_capital, final_equity=round(final_equity, 2),
            curve=self.curve, closed_positions=self.closed_positions,
            cagr_pct=round(cagr_pct, 2), sharpe=round(sharpe, 3), sortino=round(sortino, 3),
            calmar=round(calmar, 3), ulcer_index=round(ulcer, 3),
            max_drawdown_pct=round(dd_pct, 2), max_drawdown_rs=round(dd_rs, 2),
            max_drawdown_duration_days=dd_duration,
            total_return_pct=round(total_return_pct, 2),
        )


def _sharpe(daily_returns: list[float], risk_free: float = 0.0) -> float:
    """Daily-returns Sharpe, annualized by a fixed sqrt(252) trading days
    -- NOT the trades-per-year annualization `core/backtest/parser.py`
    uses for pooled per-trade stats (see docs/SHARPE_SWEEP_AND_EQUITY_CURVE_PLAN.md's
    Track 1 finding that these are two genuinely separate calculations).
    This is deliberately identical to `core/rotation/equity_curve.py`'s
    own `_sharpe` -- a daily equity curve is always annualized by trading
    days elapsed, regardless of how many discrete trades produced it."""
    if len(daily_returns) < 2:
        return 0.0
    mean = sum(daily_returns) / len(daily_returns)
    variance = sum((r - mean) ** 2 for r in daily_returns) / (len(daily_returns) - 1)
    std = math.sqrt(variance)
    if std < 1e-12:
        return 0.0
    return (mean - risk_free) / std * math.sqrt(252)


def _sortino(daily_returns: list[float], risk_free: float = 0.0) -> float:
    """Sharpe's asymmetric sibling: same numerator (mean excess return),
    but the denominator only counts DOWNSIDE deviation (returns below
    `risk_free`, zero contribution from an up day) instead of full
    variance. A strategy with occasional large UP days gets penalized by
    Sharpe for that "volatility" even though nobody minds a big win --
    Sortino doesn't make that mistake, which is why it's a standard
    companion metric, not a replacement, in institutional reporting."""
    if len(daily_returns) < 2:
        return 0.0
    mean = sum(daily_returns) / len(daily_returns)
    downside = [min(0.0, r - risk_free) for r in daily_returns]
    downside_variance = sum(d ** 2 for d in downside) / (len(downside) - 1)
    downside_std = math.sqrt(downside_variance)
    if downside_std < 1e-12:
        return 0.0
    return (mean - risk_free) / downside_std * math.sqrt(252)


def _ulcer_index(curve: list[EquityCurvePoint]) -> float:
    """Root-mean-square of the drawdown-from-running-peak (as %) at EVERY
    point on the curve, not just the single worst point max_drawdown_pct
    reports. Two curves can share the same max drawdown while one recovers
    in a week and the other grinds underwater for two years -- Ulcer Index
    is higher for the second, which max_drawdown_pct alone can't tell you.
    Popular with trend-following/CTA shops for exactly this reason (a
    long grinding drawdown is what actually drives investor redemptions,
    not necessarily the single deepest one)."""
    if not curve:
        return 0.0
    peak = curve[0].equity
    sq_sum = 0.0
    for point in curve:
        peak = max(peak, point.equity)
        dd_pct = (peak - point.equity) / peak * 100 if peak > 0 else 0.0
        sq_sum += dd_pct ** 2
    return math.sqrt(sq_sum / len(curve))


def _max_drawdown_duration_days(curve: list[EquityCurvePoint]) -> int:
    """Longest stretch (in days) from a new equity peak until the curve
    recovers to at least that peak again. A drawdown still open at the end
    of the curve counts as running through the curve's last date -- it
    isn't excluded just because the window ended before it recovered."""
    if len(curve) < 2:
        return 0
    peak = curve[0].equity
    peak_date = curve[0].date
    underwater_since = None
    max_days = 0
    for point in curve:
        if point.equity >= peak:
            if underwater_since is not None:
                max_days = max(max_days, (point.date - underwater_since).days)
                underwater_since = None
            peak = point.equity
            peak_date = point.date
        elif underwater_since is None:
            underwater_since = peak_date
    if underwater_since is not None:
        max_days = max(max_days, (curve[-1].date - underwater_since).days)
    return max_days


def kelly_fraction(returns: list[float], step: float = 0.001, max_fraction: float = 1.0) -> float:
    """Numerically finds the fixed fraction `f` in [0, max_fraction] of the
    capital ALLOCATED TO EACH TRADE (not total account equity) that
    maximizes long-run geometric growth: mean(log(1 + f * r)) over
    `returns`, each trade's own fractional return on what was risked in
    it (e.g. a BacktestTrade's net_profit_pct / 100).

    This is the generalized Kelly criterion for an arbitrary sequence of
    realized per-trade returns, not the textbook binary win/loss formula
    (f* = p/a - q/b) -- that formula is the special case where every
    `returns` entry is either +b or -a; this grid search recovers the
    same optimum for that case (see this module's own tests) while also
    working for a real strategy's messy, non-binary return distribution
    without assuming one.

    Every `returns` entry must be >= -1.0 (can't lose more than 100% of
    what was allocated to a single trade -- true for a long option or a
    long equity position, the only two position types this project's
    Account needs); a smaller value raises ValueError since it would make
    `log(1 + f * r)` undefined for some f in [0, max_fraction].

    This is a THEORETICALLY-motivated fixed fraction, derived by
    maximizing expected log-growth (not by trying many fractions against
    a full equity curve and picking whichever one happened to look best
    in hindsight -- that would be fitting the one historical path this
    project only has one of). Any caller applying this fraction OUT OF
    SAMPLE (computed on a mining window, applied to a holdout window) is
    following this project's own established mining/holdout discipline
    (see docs/ORB_CONDITION_MINING_METHODOLOGY.md); computing it on the
    same data it's then evaluated on is in-sample and should be labeled
    as such, not presented as a validated result."""
    if any(r < -1.0 for r in returns):
        raise ValueError("a per-trade return below -100% is not representable by this model")
    if not returns:
        return 0.0

    best_f, best_growth = 0.0, 0.0
    n = len(returns)
    f = step
    while f <= max_fraction + 1e-9:
        # A fraction that would zero out (or invert) the account on any
        # single historical trade (1 + f*r <= 0, only reachable when a
        # -100% return exists and f approaches 1.0) is excluded outright
        # -- infinite/undefined log-growth, never a real candidate.
        bases = [1 + f * r for r in returns]
        if any(b <= 0 for b in bases):
            f += step
            continue
        growth = sum(math.log(b) for b in bases) / n
        if growth > best_growth:
            best_growth, best_f = growth, f
        f += step
    return round(best_f, 4)


def optimal_fraction_by_growth(
    simulate_fn: Callable[[float], EquityCurveResult], fractions: list[float],
) -> tuple[float, EquityCurveResult]:
    """Finds the equity-fraction that maximizes REALIZED log-growth
    (log(final_equity / initial_capital)) of an ACTUAL portfolio
    simulation, not the single-trade-at-a-time approximation
    `kelly_fraction()` uses.

    Why this exists: `kelly_fraction()` treats every trade as if it were a
    sequential bet against the FULL bankroll, one at a time. That's wrong
    for a strategy that holds many positions CONCURRENTLY sharing one cash
    pool (confirmed for the Darvas ATR-stop candidate: mean ~12, max 29
    simultaneously open Bucket B positions in its own mining window) --
    single-trade Kelly math has no way to know that 12 signals at its
    "optimal" fraction would try to commit 12x that fraction of capital at
    once. This function instead asks the right question directly: given
    the REAL historical sequence of overlapping trades and the REAL cash
    constraint (`Account.open`'s own affordability check), which fixed
    equity-fraction-per-trade actually produced the best growth when
    played out for real? Concurrency, correlation between overlapping
    positions, and the cash ceiling are all automatically accounted for
    because this runs the real simulation -- not derived analytically.

    `simulate_fn(fraction) -> EquityCurveResult` is a caller-supplied
    closure over one candidate/window's own trades, trading-day calendar,
    and starting capital -- this function only owns the search.

    THIS IS AN IN-SAMPLE OPTIMIZATION over whatever trades `simulate_fn`
    was built from -- a grid search for "whichever fraction happened to
    perform best on one historical path" is exactly the overfitting shape
    this project has rejected everywhere else (see
    docs/SHARPE_SWEEP_AND_EQUITY_CURVE_PLAN.md). The caller MUST build
    `simulate_fn` from a MINING window only and validate the returned
    fraction on an untouched HOLDOUT window separately -- this function
    has no way to enforce that itself, and returns whatever fraction
    looks best on whatever trades it's given, in-sample, by design."""
    best_fraction, best_result, best_growth = 0.0, None, float("-inf")
    for fraction in fractions:
        result = simulate_fn(fraction)
        if result.final_equity <= 0 or result.initial_capital <= 0:
            growth = float("-inf")     # ruin is the worst possible outcome, same as Kelly's own log(0)
        else:
            growth = math.log(result.final_equity / result.initial_capital)
        if growth > best_growth:
            best_growth, best_fraction, best_result = growth, fraction, result
    if best_result is None:
        raise ValueError("fractions must be non-empty")
    return best_fraction, best_result


def _max_drawdown(curve: list[EquityCurvePoint]) -> tuple[float, float]:
    """Returns (drawdown_pct, drawdown_rs), bounded to [0, 100]% by
    construction since this walks real equity levels."""
    peak = curve[0].equity
    max_dd_pct = 0.0
    max_dd_rs = 0.0
    for point in curve:
        eq = point.equity
        peak = max(peak, eq)
        dd_rs = peak - eq
        dd_pct = (dd_rs / peak * 100) if peak > 0 else 0.0
        if dd_pct > max_dd_pct:
            max_dd_pct = dd_pct
            max_dd_rs = dd_rs
    return max_dd_pct, max_dd_rs
