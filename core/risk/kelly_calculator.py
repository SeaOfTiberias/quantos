"""
QuantOS — Kelly Calculator
─────────────────────────────
Pure calculation logic, separated from the trade history service
for easy unit testing.
"""

import logging

from core.risk.kelly import (
    ClosedTrade, KellyStats, SizingResult,
    MIN_TRADES_FOR_KELLY, LOOKBACK_TRADES, KELLY_FRACTION,
    MIN_SIZE_PCT, MAX_SIZE_PCT, FALLBACK_SIZE_PCT,
)

logger = logging.getLogger(__name__)


def compute_kelly_stats(trades: list[ClosedTrade]) -> KellyStats:
    """
    Compute win rate, average win/loss, and raw Kelly fraction
    from a list of closed trades.
    """
    n = len(trades)

    if n < MIN_TRADES_FOR_KELLY:
        return KellyStats(
            sample_size=n, win_rate=0.0, avg_win_pct=0.0, avg_loss_pct=0.0,
            win_loss_ratio=0.0, raw_kelly=0.0, has_sufficient_data=False,
        )

    wins   = [t for t in trades if t.is_win]
    losses = [t for t in trades if not t.is_win]

    win_rate = len(wins) / n

    avg_win_pct  = sum(abs(t.pnl_pct) for t in wins) / len(wins) if wins else 0.0
    avg_loss_pct = sum(abs(t.pnl_pct) for t in losses) / len(losses) if losses else 0.0

    # Avoid division by zero — if no losses recorded (unlikely but possible
    # in a small/lucky sample), treat win/loss ratio as capped high value
    if avg_loss_pct == 0:
        win_loss_ratio = 10.0 if avg_win_pct > 0 else 0.0
    else:
        win_loss_ratio = avg_win_pct / avg_loss_pct

    raw_kelly = _kelly_formula(win_rate, win_loss_ratio)

    return KellyStats(
        sample_size=n,
        win_rate=round(win_rate, 4),
        avg_win_pct=round(avg_win_pct, 4),
        avg_loss_pct=round(avg_loss_pct, 4),
        win_loss_ratio=round(win_loss_ratio, 4),
        raw_kelly=round(raw_kelly, 4),
        has_sufficient_data=True,
    )


def _kelly_formula(win_rate: float, win_loss_ratio: float) -> float:
    """
    f* = W - (1 - W) / R

    Returns the raw (uncapped, full-Kelly) fraction. Can be negative
    if the system has a negative edge (more loss-adjusted than win-adjusted).
    """
    if win_loss_ratio <= 0:
        return 0.0
    return win_rate - (1 - win_rate) / win_loss_ratio


def calculate_position_size(
    trades: list[ClosedTrade],
    capital: float,
    symbol: str,
    lookback: int = LOOKBACK_TRADES,
    kelly_fraction: float = KELLY_FRACTION,
) -> SizingResult:
    """
    Main entry point — calculate the recommended position size for
    the next trade based on rolling trade history.

    Args:
        trades: full closed trade history (will be windowed to `lookback`)
        capital: current trading capital in INR
        symbol: symbol about to be traded (for logging/context)
        lookback: rolling window size (default 50)
        kelly_fraction: 0.5 = half-Kelly (default), 1.0 = full Kelly

    Returns:
        SizingResult with size_pct, risk_amount, and full audit trail
    """
    notes = []

    # Use only the most recent `lookback` trades, sorted by exit date
    sorted_trades = sorted(trades, key=lambda t: t.exit_date)
    windowed = sorted_trades[-lookback:] if len(sorted_trades) > lookback else sorted_trades

    stats = compute_kelly_stats(windowed)

    # ── Insufficient data → fixed fallback ───────────────────────────────────
    if not stats.has_sufficient_data:
        notes.append(
            f"Insufficient trade history ({stats.sample_size}/{MIN_TRADES_FOR_KELLY} "
            f"required) — using fixed {FALLBACK_SIZE_PCT:.1%} fallback"
        )
        return SizingResult(
            symbol=symbol, capital=capital,
            size_pct=FALLBACK_SIZE_PCT,
            risk_amount=round(capital * FALLBACK_SIZE_PCT, 2),
            method="FIXED_FALLBACK",
            kelly_stats=stats,
            notes=notes,
        )

    # ── Negative edge → refuse to size, don't floor into it ──────────────────
    # A negative raw_kelly means the last `lookback` trades measured a losing
    # system. Flooring at MIN_SIZE_PCT here would guarantee continued exposure
    # to a measured negative edge — the floor exists to keep a POSITIVE edge
    # from being sized to zero by an overly conservative cap, not to keep
    # trading through a negative one. size_pct=0 flows through to qty=0 in
    # `SizingResult.position_quantity`, which agent/main.py already treats as
    # a hard refusal (raises BrokerError) rather than a silent skip.
    if not stats.is_positive_edge:
        notes.append(
            f"Negative Kelly edge ({stats.raw_kelly:.3f}) — "
            f"win_rate={stats.win_rate:.1%}, W/L ratio={stats.win_loss_ratio:.2f}. "
            f"Refusing to size (0%) — review strategy before trading again."
        )
        return SizingResult(
            symbol=symbol, capital=capital,
            size_pct=0.0,
            risk_amount=0.0,
            method="ZERO_EDGE",
            kelly_stats=stats,
            notes=notes,
        )

    # ── Positive edge → apply half-Kelly with guardrails ─────────────────────
    adjusted_kelly = stats.raw_kelly * kelly_fraction
    capped_size = max(MIN_SIZE_PCT, min(MAX_SIZE_PCT, adjusted_kelly))

    if adjusted_kelly > MAX_SIZE_PCT:
        notes.append(
            f"Kelly suggests {adjusted_kelly:.1%} — capped at max {MAX_SIZE_PCT:.1%}"
        )
    elif adjusted_kelly < MIN_SIZE_PCT:
        notes.append(
            f"Kelly suggests {adjusted_kelly:.1%} — floored at min {MIN_SIZE_PCT:.1%}"
        )
    else:
        notes.append(
            f"Half-Kelly sizing: {kelly_fraction:.0%} of {stats.raw_kelly:.1%} "
            f"raw Kelly = {adjusted_kelly:.1%}"
        )

    notes.append(
        f"Based on {stats.sample_size} trades: "
        f"win_rate={stats.win_rate:.1%}, "
        f"avg_win={stats.avg_win_pct:.1%}, avg_loss={stats.avg_loss_pct:.1%}, "
        f"W/L ratio={stats.win_loss_ratio:.2f}"
    )

    logger.info(
        "Kelly sizing for %s: %.2f%% of capital (raw_kelly=%.3f, n=%d)",
        symbol, capped_size * 100, stats.raw_kelly, stats.sample_size,
    )

    return SizingResult(
        symbol=symbol, capital=capital,
        size_pct=round(capped_size, 4),
        risk_amount=round(capital * capped_size, 2),
        method="KELLY",
        kelly_stats=stats,
        notes=notes,
    )
