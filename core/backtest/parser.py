"""
QuantOS — Pine Script Backtest Interpreter
─────────────────────────────────────────────
US-11: Parses TradingView backtest CSV exports, computes statistical
performance metrics, and prepares the context for Claude's analysis.

TradingView Strategy Tester exports two CSVs:
  1. Trade list: each individual trade (entry/exit, P&L, bars held)
  2. Overview: summary stats (net profit, Sharpe, max DD, etc.)

We ingest the trade list — it's richer and lets us split performance
by time period, regime, or market condition.
"""

import csv
import io
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from core.risk.costs import CostModel, DEFAULT_COST_MODEL

logger = logging.getLogger(__name__)


@dataclass
class BacktestTrade:
    """A single trade from the TradingView trade list export.

    TradingView reports GROSS `profit`/`profit_pct` (its Strategy Tester ignores
    Indian brokerage/STT/GST unless a commission is configured). `costs` holds
    the round-trip transaction cost we apply, and every metric downstream reads
    the net_* views so backtested edge matches what actually trades (S5-1)."""
    trade_num:      int
    direction:      str        # "Long" or "Short"
    qty:            float
    entry_date:     datetime
    entry_price:    float
    exit_date:      datetime
    exit_price:     float
    profit:         float      # GROSS absolute P&L in quote currency (from TV)
    profit_pct:     float      # GROSS % P&L (from TV)
    cum_profit:     float      # cumulative gross P&L to this trade
    bars_held:      int
    costs:          float = 0.0   # round-trip transaction cost (INR), from CostModel

    @property
    def net_profit(self) -> float:
        """Absolute P&L after transaction costs."""
        return self.profit - self.costs

    @property
    def costs_pct(self) -> float:
        """Costs as a % of entry notional (same basis as profit_pct)."""
        notional = abs(self.entry_price) * abs(self.qty)
        if notional == 0:
            return 0.0
        return self.costs / notional * 100.0

    @property
    def net_profit_pct(self) -> float:
        """% P&L after transaction costs."""
        return self.profit_pct - self.costs_pct

    @property
    def is_win(self) -> bool:
        """Net of costs — a trade wins only if it clears its own frictions."""
        return self.net_profit > 0

    @property
    def duration_days(self) -> float:
        return (self.exit_date - self.entry_date).days


@dataclass
class BacktestMetrics:
    """Statistical summary of a set of trades."""
    total_trades:      int
    win_rate:          float
    avg_win_pct:       float
    avg_loss_pct:      float
    win_loss_ratio:    float
    profit_factor:     float    # gross profit / gross loss
    sharpe_ratio:      float
    max_drawdown_pct:  float
    net_profit_pct:    float
    avg_bars_held:     float
    trades_per_month:  float

    @property
    def is_overfit_risk(self) -> bool:
        """
        Basic overfitting signal — win rate > 70% AND < 30 trades
        is suspicious (too few trades to be statistically significant).
        """
        return self.win_rate > 0.70 and self.total_trades < 30

    @property
    def has_positive_edge(self) -> bool:
        return self.profit_factor > 1.0 and self.sharpe_ratio > 0.5


@dataclass
class BacktestReport:
    """Full structured report ready for Claude to analyse."""
    strategy_name:    str
    total_trades:     list[BacktestTrade]
    overall:          BacktestMetrics
    first_half:       Optional[BacktestMetrics]    # walk-forward split 1
    second_half:      Optional[BacktestMetrics]    # walk-forward split 2
    by_year:          dict[int, BacktestMetrics] = field(default_factory=dict)
    notes:            list[str] = field(default_factory=list)

    @property
    def has_degradation(self) -> bool:
        """True if second-half Sharpe is significantly worse than first-half — possible overfit."""
        if not self.first_half or not self.second_half:
            return False
        degradation = self.first_half.sharpe_ratio - self.second_half.sharpe_ratio
        return degradation > 0.5


def parse_tradingview_csv(
    csv_content: str,
    strategy_name: str = "Unknown",
    cost_model: CostModel = DEFAULT_COST_MODEL,
) -> BacktestReport:
    """
    Parse TradingView trade list CSV and return a BacktestReport.

    Expected columns (TradingView default export):
      Trade #, Type, Signal, Date/Time, Price, Contracts, Profit, Cum. Profit, Run-up, Drawdown

    `cost_model` applies the NSE transaction-cost stack to every trade so the
    metrics are net-of-cost. Pass a model with `slippage_bps > 0` to also charge
    slippage — backtest fills are frictionless, unlike live fills which already
    embed it (which is why the default model's slippage is 0).
    """
    trades = _parse_trades(csv_content, cost_model)
    if not trades:
        raise ValueError("No trades found in CSV — check the format")

    overall = _compute_metrics(trades)
    mid = len(trades) // 2
    first_half  = _compute_metrics(trades[:mid]) if mid >= 5 else None
    second_half = _compute_metrics(trades[mid:]) if len(trades) - mid >= 5 else None

    # Group by year
    by_year: dict[int, list[BacktestTrade]] = {}
    for t in trades:
        y = t.exit_date.year
        by_year.setdefault(y, []).append(t)
    year_metrics = {y: _compute_metrics(ts) for y, ts in by_year.items() if len(ts) >= 3}

    notes = []
    if overall.is_overfit_risk:
        notes.append(f"⚠️  Overfitting risk: {overall.win_rate:.0%} win rate on only {overall.total_trades} trades")
    if len(trades) < 20:
        notes.append(f"⚠️  Low sample size ({len(trades)} trades) — statistical significance uncertain")
    if overall.sharpe_ratio < 0.5:
        notes.append(f"⚠️  Low Sharpe ratio ({overall.sharpe_ratio:.2f}) — strategy barely better than random")
    total_costs = sum(t.costs for t in trades)
    if total_costs > 0:
        slip = f", slippage {cost_model.slippage_bps:.1f}bps" if cost_model.slippage_bps else ""
        notes.append(
            f"Metrics are NET of ₹{total_costs:,.0f} transaction costs "
            f"across {len(trades)} trades (NSE stack{slip})."
        )

    return BacktestReport(
        strategy_name=strategy_name,
        total_trades=trades,
        overall=overall,
        first_half=first_half,
        second_half=second_half,
        by_year=year_metrics,
        notes=notes,
    )


def _parse_trades(csv_content: str, cost_model: CostModel = DEFAULT_COST_MODEL) -> list[BacktestTrade]:
    """Parse raw CSV into BacktestTrade objects."""
    reader = csv.DictReader(io.StringIO(csv_content))
    if not reader.fieldnames:
        return []

    trades = []
    entry_row = None   # TradingView splits entry and exit into separate rows
    trade_num = 0

    for row in reader:
        # Detect entry vs exit row (TradingView format)
        trade_type = (row.get("Type", "") or row.get("type", "")).strip()
        if not trade_type:
            continue

        if "Entry" in trade_type or "entry" in trade_type.lower():
            entry_row = row
            trade_num += 1
            continue

        if ("Exit" in trade_type or "exit" in trade_type.lower()) and entry_row:
            trade = _parse_trade_pair(trade_num, entry_row, row, cost_model)
            if trade:
                trades.append(trade)
            entry_row = None

    logger.info("Parsed %d trades from TradingView CSV", len(trades))
    return trades


def _parse_trade_pair(
    num: int, entry: dict, exit_: dict, cost_model: CostModel = DEFAULT_COST_MODEL,
) -> Optional[BacktestTrade]:
    """Build a BacktestTrade from an entry/exit row pair."""
    try:
        def parse_dt(s: str) -> datetime:
            for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
                try:
                    return datetime.strptime(s.strip(), fmt)
                except ValueError:
                    continue
            raise ValueError(f"Cannot parse datetime: {s}")

        def clean_float(s: str) -> float:
            return float(s.strip().replace(",", "").replace("%", "").replace("₹", "") or "0")

        entry_date  = parse_dt(entry.get("Date/Time", entry.get("date", "")))
        exit_date   = parse_dt(exit_.get("Date/Time", exit_.get("date", "")))
        entry_price = clean_float(entry.get("Price", "0"))
        exit_price  = clean_float(exit_.get("Price", "0"))
        profit      = clean_float(exit_.get("Profit", exit_.get("profit", "0")))
        profit_pct  = clean_float(exit_.get("Profit %", exit_.get("profit_pct", "0")))
        cum_profit  = clean_float(exit_.get("Cum. Profit", exit_.get("cum_profit", "0")))
        contracts   = clean_float(entry.get("Contracts", "1"))
        direction   = "Long" if "long" in entry.get("Type", "").lower() else "Short"

        bars_held = max(1, (exit_date - entry_date).days)

        # "Long" → BUY-side entry, anything else treated as a short.
        cost_direction = "BUY" if direction == "Long" else "SELL"
        costs = cost_model.cost_of(entry_price, exit_price, contracts, cost_direction)

        return BacktestTrade(
            trade_num=num, direction=direction, qty=contracts,
            entry_date=entry_date, entry_price=entry_price,
            exit_date=exit_date, exit_price=exit_price,
            profit=profit, profit_pct=profit_pct,
            cum_profit=cum_profit, bars_held=bars_held, costs=costs,
        )
    except Exception as e:
        logger.warning("Could not parse trade pair: %s", e)
        return None


def _compute_metrics(trades: list[BacktestTrade]) -> BacktestMetrics:
    """Compute statistical performance metrics for a set of trades."""
    if not trades:
        return BacktestMetrics(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)

    wins   = [t for t in trades if t.is_win]
    losses = [t for t in trades if not t.is_win]

    win_rate    = len(wins) / len(trades)
    # All figures net of transaction costs (see BacktestTrade.net_profit*).
    avg_win_pct = sum(abs(t.net_profit_pct) for t in wins) / len(wins) if wins else 0
    avg_loss_pct = sum(abs(t.net_profit_pct) for t in losses) / len(losses) if losses else 0
    wl_ratio    = avg_win_pct / avg_loss_pct if avg_loss_pct > 0 else float("inf")

    net_profit_sum = sum(t.net_profit for t in wins)
    net_loss_sum   = abs(sum(t.net_profit for t in losses))
    profit_factor = net_profit_sum / net_loss_sum if net_loss_sum > 0 else float("inf")

    returns = [t.net_profit_pct / 100 for t in trades]
    sharpe  = _sharpe_ratio(returns)
    max_dd  = _max_drawdown(trades)
    net_pct = sum(t.net_profit_pct for t in trades)

    avg_bars = sum(t.bars_held for t in trades) / len(trades)

    days_span = max(1, (trades[-1].exit_date - trades[0].entry_date).days)
    tpm = len(trades) / (days_span / 30.44)

    return BacktestMetrics(
        total_trades=len(trades),
        win_rate=round(win_rate, 4),
        avg_win_pct=round(avg_win_pct, 2),
        avg_loss_pct=round(avg_loss_pct, 2),
        win_loss_ratio=round(wl_ratio, 3),
        profit_factor=round(profit_factor, 3),
        sharpe_ratio=round(sharpe, 3),
        max_drawdown_pct=round(max_dd, 2),
        net_profit_pct=round(net_pct, 2),
        avg_bars_held=round(avg_bars, 1),
        trades_per_month=round(tpm, 2),
    )


def _sharpe_ratio(returns: list[float], risk_free: float = 0.0) -> float:
    """Annualised Sharpe ratio from a list of per-trade returns."""
    if len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    std = math.sqrt(variance)
    if std < 1e-9:
        return 0.0
    # Annualise assuming ~12 trades per month = 144/yr (rough for swing trading)
    return (mean - risk_free) / std * math.sqrt(144)


def _max_drawdown(trades: list[BacktestTrade]) -> float:
    """Maximum drawdown from peak cumulative P&L (as %)."""
    if not trades:
        return 0.0
    peak = cum = 0.0
    max_dd = 0.0
    for t in trades:
        cum += t.net_profit_pct
        if cum > peak:
            peak = cum
        dd = peak - cum
        if dd > max_dd:
            max_dd = dd
    return max_dd
