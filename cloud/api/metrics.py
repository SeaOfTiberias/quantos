"""
QuantOS — In-Process Operational Metrics (S5-6 / P2-8)
────────────────────────────────────────────────────────
Lightweight, dependency-free counters the observability cockpit reads:
webhook + Claude call latency, and a per-day Claude spend estimate.

Deliberately in-memory and process-local — like the discovery/regime
mirrors, these reset on every Railway redeploy. That's fine: the cockpit
wants "how is the system behaving right now", not durable time-series (a
real metrics backend is out of scope for a single-user system). Latency is
kept as a bounded rolling window; spend is accumulated per UTC day so a
day's estimate survives as long as the process does.

Spend is an ESTIMATE from token usage × configurable per-Mtok prices
(defaults are Claude Sonnet list prices); tune via env if the model or
pricing changes. No network, no locks needed — the API is single-process
async and these ops are trivial and non-awaiting.
"""

from __future__ import annotations

import os
from collections import deque
from datetime import datetime, timezone

# Rolling window of recent latency samples per instrumented path. 200 keeps
# the percentiles meaningful without unbounded growth on a busy day.
_WINDOW = 200

# Claude pricing (USD per million tokens). Defaults ≈ Sonnet list price;
# override via env when the model/pricing changes — this only affects the
# cockpit's spend ESTIMATE, never any trading decision.
INPUT_PRICE_PER_MTOK = float(os.getenv("CLAUDE_INPUT_PRICE_PER_MTOK", "3.0"))
OUTPUT_PRICE_PER_MTOK = float(os.getenv("CLAUDE_OUTPUT_PRICE_PER_MTOK", "15.0"))


class _Rolling:
    """A bounded window of latency samples (milliseconds) with percentiles."""

    def __init__(self) -> None:
        self._samples: deque[float] = deque(maxlen=_WINDOW)

    def record(self, ms: float) -> None:
        self._samples.append(float(ms))

    def snapshot(self) -> dict:
        n = len(self._samples)
        if n == 0:
            return {"count": 0, "p50_ms": None, "p95_ms": None, "last_ms": None}
        ordered = sorted(self._samples)

        def pct(p: float) -> float:
            # Nearest-rank percentile; index clamped into range.
            idx = min(n - 1, max(0, int(round(p * (n - 1)))))
            return ordered[idx]

        return {
            "count":   n,
            "p50_ms":  round(pct(0.50), 1),
            "p95_ms":  round(pct(0.95), 1),
            "last_ms": round(self._samples[-1], 1),
        }


_webhook = _Rolling()
_claude = _Rolling()

# date (ISO) -> accumulated Claude usage for that UTC day.
_spend: dict[str, dict] = {}


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def record_webhook_ms(elapsed_ms: float) -> None:
    """Record one /webhook/tradingview round-trip latency (ms)."""
    _webhook.record(elapsed_ms)


def record_claude(elapsed_ms: float, input_tokens: int = 0, output_tokens: int = 0) -> None:
    """Record one Claude call: its latency and (for spend) token usage."""
    _claude.record(elapsed_ms)
    day = _spend.setdefault(_today(), {"calls": 0, "input_tokens": 0, "output_tokens": 0})
    day["calls"] += 1
    day["input_tokens"] += int(input_tokens or 0)
    day["output_tokens"] += int(output_tokens or 0)


def _estimate_usd(usage: dict) -> float:
    return (usage["input_tokens"] / 1_000_000 * INPUT_PRICE_PER_MTOK
            + usage["output_tokens"] / 1_000_000 * OUTPUT_PRICE_PER_MTOK)


def snapshot() -> dict:
    """The full metrics view for the observability endpoint."""
    today = _spend.get(_today(), {"calls": 0, "input_tokens": 0, "output_tokens": 0})
    return {
        "webhook_latency": _webhook.snapshot(),
        "claude_latency":  _claude.snapshot(),
        "claude_spend_today": {
            "calls":         today["calls"],
            "input_tokens":  today["input_tokens"],
            "output_tokens": today["output_tokens"],
            "est_usd":       round(_estimate_usd(today), 4),
            "input_price_per_mtok":  INPUT_PRICE_PER_MTOK,
            "output_price_per_mtok": OUTPUT_PRICE_PER_MTOK,
        },
    }


def reset() -> None:
    """Clear all metrics — test hook only."""
    _webhook._samples.clear()
    _claude._samples.clear()
    _spend.clear()
