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
from typing import Optional


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
    max_drawdown_pct:   float = 0.0
    max_drawdown_rs:    float = 0.0
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
        dd_pct, dd_rs = _max_drawdown(self.curve)

        return EquityCurveResult(
            initial_capital=self.initial_capital, final_equity=round(final_equity, 2),
            curve=self.curve, closed_positions=self.closed_positions,
            cagr_pct=round(cagr_pct, 2), sharpe=round(sharpe, 3),
            max_drawdown_pct=round(dd_pct, 2), max_drawdown_rs=round(dd_rs, 2),
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
