"""
QuantOS — Options Strategy Backtester
──────────────────────────────────────────
US-18: Tests regime-conditioned options strategies on NSE historical data.

"When Ranging + IVR > 60, sell iron condor — did it work?"

Approach:
  - Replay historical periods classified by regime
  - For each qualifying period, simulate the options strategy at entry
  - Compute P&L at expiry using Black-Scholes (no historical options data needed)
  - Claude interprets results: curve-fitting risk, Sharpe, regime breakdown
"""

import logging
import math
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from core.options.greeks import compute_greeks
from core.options.models import OptionType, StrategyTemplate

logger = logging.getLogger(__name__)


@dataclass
class BacktestPeriod:
    """One historical period that met the entry conditions."""
    entry_date:    date
    expiry_date:   date
    underlying:    str
    spot_at_entry: float
    iv_rank:       float
    regime:        str
    pnl:           float       # simulated P&L at expiry
    pnl_pct:       float       # % of premium collected
    strategy:      StrategyTemplate
    notes:         str = ""


@dataclass
class OptionsBacktestResult:
    """Full backtest result for one strategy + regime condition."""
    strategy:         StrategyTemplate
    regime_filter:    str
    iv_rank_min:      float
    periods:          list[BacktestPeriod]
    total_periods:    int
    win_rate:         float
    avg_pnl_pct:      float
    sharpe:           float
    max_drawdown_pct: float
    overfitting_flag: bool
    notes:            list[str] = field(default_factory=list)

    @property
    def is_viable(self) -> bool:
        return self.win_rate > 0.55 and self.sharpe > 0.5 and not self.overfitting_flag


def simulate_iron_condor_period(
    spot:          float,
    iv:            float,
    days_to_expiry: int,
    spot_at_expiry: float,
    short_call_delta: float = 0.20,
    short_put_delta:  float = 0.20,
    wing_width_pct:   float = 0.02,
) -> tuple[float, float]:
    """
    Simulate an iron condor's P&L at expiry using Black-Scholes pricing.

    Returns:
        (net_premium_collected, pnl_at_expiry) — both in points
    """
    # Find strikes from deltas
    from core.options.greeks import _norm_cdf
    import math as _math

    def find_strike_for_delta(target_delta: float, is_call: bool) -> float:
        """Binary search for strike that produces target delta."""
        lo, hi = spot * 0.5, spot * 1.5
        for _ in range(50):
            mid = (lo + hi) / 2
            g = compute_greeks(spot, mid, max(1, days_to_expiry), iv,
                               OptionType.CALL if is_call else OptionType.PUT)
            d = g.delta if is_call else abs(g.delta)
            if abs(d - target_delta) < 0.001:
                break
            if d > target_delta:
                hi = mid if is_call else lo
                lo = lo if is_call else mid
            else:
                lo = mid if is_call else hi
                hi = hi if is_call else lo
        return mid

    short_call_k = find_strike_for_delta(short_call_delta, is_call=True)
    short_put_k  = find_strike_for_delta(short_put_delta, is_call=False)
    long_call_k  = short_call_k * (1 + wing_width_pct)
    long_put_k   = short_put_k  * (1 - wing_width_pct)

    def premium(strike: float, opt: OptionType) -> float:
        g = compute_greeks(spot, strike, max(1, days_to_expiry), iv, opt)
        return g.theoretical_price

    net_credit = (
        premium(short_call_k, OptionType.CALL)
        - premium(long_call_k,  OptionType.CALL)
        + premium(short_put_k,  OptionType.PUT)
        - premium(long_put_k,   OptionType.PUT)
    )

    # P&L at expiry (intrinsic value)
    def intrinsic(strike: float, opt: OptionType) -> float:
        if opt == OptionType.CALL:
            return max(0.0, spot_at_expiry - strike)
        return max(0.0, strike - spot_at_expiry)

    loss_at_expiry = (
        intrinsic(short_call_k, OptionType.CALL)
        - intrinsic(long_call_k, OptionType.CALL)
        + intrinsic(short_put_k, OptionType.PUT)
        - intrinsic(long_put_k, OptionType.PUT)
    )
    pnl = net_credit - loss_at_expiry
    return net_credit, pnl


def run_regime_conditioned_backtest(
    historical_periods: list[dict],
    strategy:           StrategyTemplate,
    regime_filter:      str,
    iv_rank_min:        float = 60.0,
) -> OptionsBacktestResult:
    """
    Run a regime-conditioned backtest over historical periods.

    Args:
        historical_periods: list of dicts with keys:
            entry_date, expiry_date, underlying, spot_at_entry, iv_rank,
            regime, spot_at_expiry, iv
        strategy: which strategy to simulate
        regime_filter: only run when regime matches this value
        iv_rank_min: only run when IV rank >= this value

    Returns:
        OptionsBacktestResult
    """
    qualifying = [
        p for p in historical_periods
        if p.get("regime") == regime_filter
        and p.get("iv_rank", 0) >= iv_rank_min
    ]

    if not qualifying:
        return OptionsBacktestResult(
            strategy=strategy, regime_filter=regime_filter, iv_rank_min=iv_rank_min,
            periods=[], total_periods=0, win_rate=0.0, avg_pnl_pct=0.0,
            sharpe=0.0, max_drawdown_pct=0.0, overfitting_flag=False,
            notes=[f"No qualifying periods: regime={regime_filter}, IVR≥{iv_rank_min}"],
        )

    results = []
    for period in qualifying:
        try:
            if strategy == StrategyTemplate.IRON_CONDOR:
                days_dte = (
                    date.fromisoformat(period["expiry_date"])
                    - date.fromisoformat(period["entry_date"])
                ).days
                net_credit, pnl = simulate_iron_condor_period(
                    spot=period["spot_at_entry"],
                    iv=period.get("iv", 0.18),
                    days_to_expiry=max(1, days_dte),
                    spot_at_expiry=period["spot_at_expiry"],
                )
                pnl_pct = (pnl / net_credit * 100) if net_credit > 0 else 0.0
                results.append(BacktestPeriod(
                    entry_date=date.fromisoformat(period["entry_date"]),
                    expiry_date=date.fromisoformat(period["expiry_date"]),
                    underlying=period.get("underlying", "NIFTY"),
                    spot_at_entry=period["spot_at_entry"],
                    iv_rank=period["iv_rank"],
                    regime=period["regime"],
                    pnl=pnl, pnl_pct=pnl_pct,
                    strategy=strategy,
                ))
            else:
                logger.warning("Backtester: strategy %s not yet implemented", strategy.value)
        except Exception as e:
            logger.warning("Period simulation failed: %s", e)

    win_rate    = sum(1 for r in results if r.pnl > 0) / len(results) if results else 0
    avg_pnl_pct = sum(r.pnl_pct for r in results) / len(results) if results else 0
    sharpe      = _compute_sharpe([r.pnl_pct / 100 for r in results])
    max_dd      = _compute_max_dd(results)

    overfitting_flag = (win_rate > 0.80 and len(results) < 20)

    notes = []
    if len(results) < 10:
        notes.append(f"⚠️  Low sample size ({len(results)} periods) — results not statistically significant")
    if overfitting_flag:
        notes.append(f"⚠️  High win rate ({win_rate:.0%}) on small sample — possible data mining bias")
    if sharpe > 2.0:
        notes.append(f"⚠️  Sharpe {sharpe:.2f} unusually high — check for look-ahead bias")

    return OptionsBacktestResult(
        strategy=strategy, regime_filter=regime_filter, iv_rank_min=iv_rank_min,
        periods=results, total_periods=len(results),
        win_rate=round(win_rate, 4), avg_pnl_pct=round(avg_pnl_pct, 2),
        sharpe=round(sharpe, 3), max_drawdown_pct=round(max_dd, 2),
        overfitting_flag=overfitting_flag, notes=notes,
    )


def _compute_sharpe(returns: list[float], rf: float = 0.0) -> float:
    if len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    std = math.sqrt(sum((r - mean) ** 2 for r in returns) / (len(returns) - 1))
    return (mean - rf) / std * math.sqrt(12) if std > 0 else 0.0


def _compute_max_dd(results: list[BacktestPeriod]) -> float:
    if not results:
        return 0.0
    peak = cum = 0.0
    max_dd = 0.0
    for r in results:
        cum += r.pnl_pct
        peak = max(peak, cum)
        max_dd = max(max_dd, peak - cum)
    return max_dd
