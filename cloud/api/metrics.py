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

Spend is an ESTIMATE from token usage × per-Mtok prices, priced PER MODEL —
this repo calls more than one (cloud/analyst/chat.py and pre_trade.py pin
Sonnet 4.6, cloud/analyst/shortlist_note.py defaults to Opus 5), and a single
blended rate silently mispriced whichever call didn't match it. 2026-08-27:
found under-reporting the shortlist note's Opus 5 spend by ~40% (Opus is
$5/$25 against the blended default of $3/$15, i.e. Sonnet's price) — the
first call recorded $0.056 against an actual ~$0.094. No network, no locks
needed — the API is single-process async and these ops are trivial and
non-awaiting.
"""

from __future__ import annotations

import os
from collections import deque
from datetime import datetime, timezone
from typing import Optional

# Rolling window of recent latency samples per instrumented path. 200 keeps
# the percentiles meaningful without unbounded growth on a busy day.
_WINDOW = 200

# Claude list prices (USD per million tokens), keyed by exact model id. Add an
# entry here whenever a new model is wired to record_claude — an untracked
# model falls back to DEFAULT_*_PRICE_PER_MTOK below rather than silently
# pricing at the wrong model's rate.
MODEL_PRICES: dict[str, tuple[float, float]] = {
    "claude-opus-5":      (5.0, 25.0),
    "claude-sonnet-5":    (2.0, 10.0),
    "claude-sonnet-4-6":  (3.0, 15.0),
    "claude-haiku-4-5":   (1.0, 5.0),
}

# Used only for a call that didn't pass `model`, or passed one not in the
# table above. Override via env when this default itself needs to change —
# it no longer describes every call the way it used to, only the fallback.
DEFAULT_INPUT_PRICE_PER_MTOK = float(os.getenv("CLAUDE_INPUT_PRICE_PER_MTOK", "3.0"))
DEFAULT_OUTPUT_PRICE_PER_MTOK = float(os.getenv("CLAUDE_OUTPUT_PRICE_PER_MTOK", "15.0"))

_UNKNOWN_MODEL = "_unpriced"


def _prices_for(model_key: str) -> tuple[float, float]:
    return MODEL_PRICES.get(model_key,
                            (DEFAULT_INPUT_PRICE_PER_MTOK, DEFAULT_OUTPUT_PRICE_PER_MTOK))


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

# date (ISO) -> {"calls", "input_tokens", "output_tokens" (blended totals,
# for display only — never priced directly), "by_model": {model_key -> usage}}.
# model_key is the exact model id passed to record_claude, or _UNKNOWN_MODEL
# for a call that didn't pass one. Splitting by model is what makes est_usd
# correct when the day's calls span more than one model.
_spend: dict[str, dict] = {}


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def record_webhook_ms(elapsed_ms: float) -> None:
    """Record one /webhook/tradingview round-trip latency (ms)."""
    _webhook.record(elapsed_ms)


def record_claude(elapsed_ms: float, model: Optional[str] = None,
                  input_tokens: int = 0, output_tokens: int = 0) -> None:
    """Record one Claude call: its latency and (for spend) token usage.

    Pass `model` with the exact id sent to the API (e.g. "claude-opus-5") so
    the call is priced correctly — a call that omits it is priced at the
    DEFAULT_*_PRICE_PER_MTOK fallback, which may not match what it actually
    cost."""
    _claude.record(elapsed_ms)
    day = _spend.setdefault(_today(), {
        "calls": 0, "input_tokens": 0, "output_tokens": 0, "by_model": {},
    })
    day["calls"] += 1
    day["input_tokens"] += int(input_tokens or 0)
    day["output_tokens"] += int(output_tokens or 0)

    bucket = day["by_model"].setdefault(model or _UNKNOWN_MODEL, {
        "calls": 0, "input_tokens": 0, "output_tokens": 0,
    })
    bucket["calls"] += 1
    bucket["input_tokens"] += int(input_tokens or 0)
    bucket["output_tokens"] += int(output_tokens or 0)


def _bucket_usd(bucket: dict, model_key: str) -> float:
    in_price, out_price = _prices_for(model_key)
    return (bucket["input_tokens"] / 1_000_000 * in_price
            + bucket["output_tokens"] / 1_000_000 * out_price)


def snapshot() -> dict:
    """The full metrics view for the observability endpoint."""
    today = _spend.get(_today(), {"calls": 0, "input_tokens": 0,
                                  "output_tokens": 0, "by_model": {}})
    by_model = {}
    total_usd = 0.0
    for model_key, bucket in today["by_model"].items():
        usd = _bucket_usd(bucket, model_key)
        total_usd += usd
        in_price, out_price = _prices_for(model_key)
        by_model[model_key] = {
            "calls":         bucket["calls"],
            "input_tokens":  bucket["input_tokens"],
            "output_tokens": bucket["output_tokens"],
            "est_usd":       round(usd, 4),
            "input_price_per_mtok":  in_price,
            "output_price_per_mtok": out_price,
        }

    return {
        "webhook_latency": _webhook.snapshot(),
        "claude_latency":  _claude.snapshot(),
        "claude_spend_today": {
            "calls":         today["calls"],
            "input_tokens":  today["input_tokens"],
            "output_tokens": today["output_tokens"],
            "est_usd":       round(total_usd, 4),
            "by_model":      by_model,
        },
    }


def reset() -> None:
    """Clear all metrics — test hook only."""
    _webhook._samples.clear()
    _claude._samples.clear()
    _spend.clear()
