#!/usr/bin/env python3
"""
QuantOS MCP server -- tier T0 market tools (docs/TERMINAL_ARCHITECTURE.md §5.3).

Read-only: public market data and research files. No account data, no
alerts, no orders (those are T1-T3 and are not exposed here). The tool logic
lives in core/mcp_tools/market.py; this file only registers it.

Runs on the VM (Fyers token + bhavcopy cache), over stdio. Claude Code on the
laptop starts it through SSH -- see .mcp.json:
    ssh -i ~/.ssh/oracle.key ubuntu@161.118.189.29 /home/ubuntu/quantos/scripts/quantos-mcp.sh
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# stdout is the MCP channel: every log line must go to stderr.
logging.basicConfig(stream=sys.stderr, level=logging.WARNING)

from mcp.server.mcpserver import MCPServer  # noqa: E402
from mcp.types import ToolAnnotations  # noqa: E402

from core.mcp_tools import market as mt  # noqa: E402

READ = ToolAnnotations(read_only_hint=True, open_world_hint=True)

server = MCPServer(
    name="quantos",
    instructions=("QuantOS market tools for NSE stocks and F&O (tier T0, read-only). Symbols are NSE tickers "
                  "(TCS, HDFCBANK, KOTAKBANK) or NIFTY / BANKNIFTY. Every number comes from live Fyers quotes, "
                  "daily bars or the NSE bhavcopy -- quote them, don't estimate. No account, alert or order tools."),
)
_market = None


def market():
    global _market
    if _market is None:
        from core.mcp_tools.live import LiveMarket
        _market = LiveMarket(str(ROOT / "agent" / "config.yaml"))
    return _market


@server.tool(annotations=READ)
def quote(symbols: list[str]) -> list[dict]:
    """Live quotes: ltp, day open/high/low, previous close, % change, bid/ask, volume, session date."""
    return mt.quote(market(), symbols)


@server.tool(annotations=READ)
def levels(symbol: str) -> dict:
    """Daily trend and levels for one stock: ATR(14), EMA9/21, SMA50/200, 52-week high/low, the last
    10 sessions, the weekly Darvas box (ceiling, and the floor seen from the put side) and the
    screener's retest plan per side (limit, daily-close stop, 1R target). Only the put plan has a
    measured edge (1-year backtest)."""
    return mt.levels(market(), symbol)


@server.tool(annotations=READ)
def option_chain(symbol: str, expiry: Optional[str] = None, right: Optional[str] = None, strikes: int = 8) -> dict:
    """Option chain around spot for one expiry (default: nearest): bid/ask, mid, bid-ask %, implied
    vol, ITM flag, and the previous session's OI (lots) and volume. right = CE or PE to filter.
    Also the lot size, days to expiry and the future's bid/ask."""
    return mt.option_chain(market(), symbol, expiry, right, strikes)


@server.tool(annotations=READ)
def price_spread(symbol: str, expiry: str, right: str, long_strike: float, short_strike: float) -> dict:
    """Price a debit vertical the way it fills (buy the long at the ask, sell the short at the bid):
    debit, mid debit, round-trip bid-ask cost %, max loss/profit per lot, reward:risk, breakeven.
    expiry is YYYY-MM-DD, right is CE or PE."""
    return mt.price_spread(market(), symbol, expiry, right, long_strike, short_strike)


@server.tool(annotations=READ)
def pick_structure(symbol: str, direction: str, target: float, stop: float, days: int, budget: float = 0,
                   p: float = 0.5, intraday: bool = False, gap_pct: Optional[float] = None,
                   thesis: str = "move") -> dict:
    """Rank futures, single options, debit and credit verticals for a view (direction bull/bear,
    target and stop as stock prices, horizon in trading days) by the hit rate each needs to break
    even (needs_p) and EV per worst-case rupee. budget 0 = no budget filter. thesis "move" (reaches
    the target) or "hold" (won't cross the stop level). Each row carries the strike-rule flags
    (R1-R6) and the no-move (if_flat) outcome; rule-passing rows rank first."""
    return mt.pick_structure(market(), symbol, direction, target, stop, days, budget, p, intraday, gap_pct, thesis)


@server.tool(annotations=READ)
def oi_buildup(symbol: str, lookback: int = 5) -> dict:
    """Futures OI build-up over the last `lookback` sessions from NSE bhavcopies: long build-up,
    short build-up, short covering, long unwinding or OI flat, with price and OI % change."""
    return mt.oi_buildup(market(), symbol, lookback)


@server.tool(annotations=READ)
def screener(side: Optional[str] = None) -> dict:
    """The F&O screener's latest evening run: calls, puts, the watchlist (not broken yet), names
    without a liquid option, and the Nifty-vs-EMA20 label. side = CE or PE to filter."""
    return mt.screener(side=side)


@server.tool(annotations=READ)
def ideas(symbol: Optional[str] = None, open_only: bool = False) -> list[dict]:
    """The trade-idea log: every logged idea with its levels, status as scored daily at 15:25 IST,
    paper P&L and what the user actually took. Read-only."""
    return mt.ideas(symbol=symbol, open_only=open_only)


if __name__ == "__main__":
    server.run("stdio")
