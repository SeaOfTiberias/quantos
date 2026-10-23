"""
QuantOS — the live Market behind the MCP tools: Fyers quotes, daily bars and
option chains, and the NSE F&O bhavcopy cache. Built for the VM, where the
Fyers token is refreshed every morning and the bhavcopies are cached.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

BHAVCOPY_DIR = Path.home() / ".quantos" / "nse_fo_bhavcopy"


class LiveMarket:
    def __init__(self, config_path: str = "agent/config.yaml"):
        from agent.main import load_config
        from core.brokers import get_broker
        self.broker = get_broker(load_config(config_path))
        if not self.broker.connect():
            raise RuntimeError("Fyers connect failed -- refresh the token in the cockpit")
        self.client = self.broker._client
        self._days: dict = {}

    def quotes(self, fyers_symbols: list[str]) -> dict[str, dict]:
        out = {}
        for i in range(0, len(fyers_symbols), 50):
            r = self.client.quotes({"symbols": ",".join(fyers_symbols[i:i + 50])})
            for x in r.get("d", []) or []:
                out[x.get("n")] = x.get("v") or {}
        return out

    def daily(self, symbol: str, days: int):
        now = datetime.now(timezone.utc)
        return sorted(self.broker.get_historical_data(symbol, "1d", now - timedelta(days=min(days, 365)), now) or [],
                      key=lambda c: c.timestamp)

    def chain(self, symbol: str, steps: int):
        from core.ideas.chain import fetch_chain
        return fetch_chain(self.client, symbol, steps)

    def fno_day(self, d: date):
        if d not in self._days:
            from core.fno_screener.bhavcopy import parse_fno_day
            from core.options.vrp.bhavcopy import BhavcopyNotAvailable, fetch_raw
            BHAVCOPY_DIR.mkdir(parents=True, exist_ok=True)
            try:
                self._days[d] = parse_fno_day(fetch_raw(d, BHAVCOPY_DIR), d)
            except BhavcopyNotAvailable:
                self._days[d] = None
        return self._days[d]
