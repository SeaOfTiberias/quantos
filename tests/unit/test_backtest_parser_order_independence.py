"""_compute_metrics must not depend on the order trades are passed in (2026-10-05)."""
import random
from datetime import datetime, timedelta

from core.backtest.parser import BacktestTrade, _compute_metrics


def _trade(n, start, days, pct):
    entry = datetime(2020, 1, 1) + timedelta(days=start)
    return BacktestTrade(trade_num=n, direction="Long", qty=10, entry_date=entry, entry_price=100.0,
                         exit_date=entry + timedelta(days=days), exit_price=100.0 * (1 + pct),
                         profit=1000 * pct, profit_pct=100 * pct, cum_profit=0.0, bars_held=days, costs=0.0)


def test_metrics_identical_for_chronological_and_shuffled_trades():
    rng = random.Random(7)
    trades = [_trade(i, start=i * 7, days=20, pct=rng.uniform(-0.05, 0.08)) for i in range(200)]
    shuffled = trades[:]
    rng.shuffle(shuffled)
    a, b = _compute_metrics(trades), _compute_metrics(shuffled)
    assert a.sharpe_ratio == b.sharpe_ratio
    assert a.max_drawdown_pct == b.max_drawdown_pct
    assert a.trades_per_month == b.trades_per_month


def test_span_uses_earliest_entry_and_latest_exit():
    # Listed "by symbol": the first listed trade is the latest one.
    late, early = _trade(1, start=1000, days=10, pct=0.01), _trade(2, start=0, days=10, pct=0.02)
    m = _compute_metrics([late, early])
    assert m.trades_per_month < 1.0        # ~2 trades over ~1010 days, not 2 over a few days
