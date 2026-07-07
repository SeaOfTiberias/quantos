"""
QuantOS — Trade History Service
───────────────────────────────────
US-07: Stores closed trades and exposes the recalc-on-close trigger.

Persistence is opt-in via `persist_path` (the agent passes
~/.quantos/trade_history.json — Kelly's 20-trade minimum is unreachable
if history dies with each daily agent restart). Without a path it stays
a pure in-memory store (cloud usage; the Postgres copy synced via
/signals/{id}/closed is the analytics mirror, this file is the sizing
source of truth per ADR-01: sizing must work offline).
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from core.risk.kelly import ClosedTrade, SizingResult
from core.risk.kelly_calculator import calculate_position_size

logger = logging.getLogger(__name__)


class TradeHistoryService:
    """
    Tracks closed trades and provides the current Kelly-based
    position sizing recommendation. One instance per user in
    multi-tenant deployment (ADR-03); for now, single global instance.
    """

    def __init__(self, persist_path: Path | str | None = None):
        self._trades: list[ClosedTrade] = []
        self._last_sizing: dict[str, SizingResult] = {}  # cache per symbol
        self._persist_path = Path(persist_path) if persist_path else None
        if self._persist_path:
            self._load()

    def record_closed_trade(self, trade: ClosedTrade) -> SizingResult:
        """
        Record a newly closed trade and immediately recalculate sizing.
        This is the "recalc trigger on trade close" from ADR / US-07 spec.
        """
        self._trades.append(trade)
        self._save()
        logger.info(
            "Trade closed: %s %s pnl=%.2f (%.2f%%) — recalculating Kelly sizing",
            trade.symbol, trade.direction, trade.pnl, trade.pnl_pct * 100,
        )

        # Recalculate sizing for this symbol (caller can also query for others)
        result = self.get_current_sizing(trade.symbol, capital=self._estimate_capital())
        self._last_sizing[trade.symbol] = result
        return result

    def get_trade_history(self, symbol: str | None = None) -> list[ClosedTrade]:
        """Get all trades, optionally filtered by symbol."""
        if symbol:
            return [t for t in self._trades if t.symbol == symbol.upper()]
        return list(self._trades)

    def get_current_sizing(
        self,
        symbol: str,
        capital: float,
        use_symbol_specific: bool = False,
    ) -> SizingResult:
        """
        Get the current position sizing recommendation.

        Args:
            symbol: symbol about to be traded
            capital: current trading capital
            use_symbol_specific: if True, only use this symbol's own trade
                history (smaller sample, more specific). If False (default),
                use the full strategy history across all symbols (larger
                sample, more statistically reliable — recommended).
        """
        trades = (
            self.get_trade_history(symbol)
            if use_symbol_specific
            else self.get_trade_history()
        )
        return calculate_position_size(trades, capital=capital, symbol=symbol)

    def get_last_sizing(self, symbol: str) -> SizingResult | None:
        """Get the cached sizing result from the last recalc, if any."""
        return self._last_sizing.get(symbol)

    def stats_summary(self) -> dict:
        """Quick stats for the cockpit dashboard."""
        if not self._trades:
            return {"total_trades": 0, "win_rate": None, "total_pnl": 0.0}

        wins = sum(1 for t in self._trades if t.is_win)
        total_pnl = sum(t.pnl for t in self._trades)

        return {
            "total_trades": len(self._trades),
            "win_rate": round(wins / len(self._trades), 4),
            "total_pnl": round(total_pnl, 2),
        }

    def _load(self) -> None:
        """Load persisted trades. A corrupt/unreadable file is logged and
        skipped rather than crashing the agent at startup — sizing then
        rebuilds from FIXED_FALLBACK, which is safe (smaller, not larger)."""
        if not self._persist_path.exists():
            return
        try:
            raw = json.loads(self._persist_path.read_text())
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Could not read trade history %s: %s — starting empty",
                           self._persist_path, e)
            return
        for item in raw:
            item["entry_date"] = datetime.fromisoformat(item["entry_date"])
            item["exit_date"] = datetime.fromisoformat(item["exit_date"])
            self._trades.append(ClosedTrade(**item))
        logger.info("Loaded %d closed trade(s) from %s",
                    len(self._trades), self._persist_path)

    def _save(self) -> None:
        if not self._persist_path:
            return
        self._persist_path.parent.mkdir(parents=True, exist_ok=True)
        data = []
        for t in self._trades:
            d = asdict(t)
            d["entry_date"] = t.entry_date.isoformat()
            d["exit_date"] = t.exit_date.isoformat()
            data.append(d)
        self._persist_path.write_text(json.dumps(data, indent=2))

    def _estimate_capital(self) -> float:
        """
        Placeholder capital estimate. In production this reads from
        broker.get_funds() via the BrokerAdapter. For now uses a
        configurable default.
        """
        import os
        return float(os.getenv("DEFAULT_CAPITAL", "500000"))


def format_sizing_whatsapp(result: SizingResult) -> str:
    """Format a sizing recommendation for WhatsApp delivery."""
    method_label = {
        "KELLY": "📊 Kelly-Optimized",
        "FIXED_FALLBACK": "🔒 Fixed (Building History)",
        "ZERO_EDGE": "⚠️ Minimum (Negative Edge)",
    }.get(result.method, result.method)

    lines = [
        f"💰 Position Sizing Update",
        f"--------------------",
        f"Symbol:  {result.symbol}",
        f"Method:  {method_label}",
        f"Size:    {result.size_pct:.2%} of capital",
        f"Risk:    INR {result.risk_amount:,.0f}",
    ]

    if result.kelly_stats and result.kelly_stats.has_sufficient_data:
        s = result.kelly_stats
        lines += [
            f"--------------------",
            f"Sample:    {s.sample_size} trades",
            f"Win rate:  {s.win_rate:.1%}",
            f"W/L ratio: {s.win_loss_ratio:.2f}",
        ]

    if result.notes:
        lines.append("--------------------")
        for note in result.notes:
            lines.append(f"  {note}")

    return "\n".join(lines)
