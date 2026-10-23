"""
QuantOS — LLM call log (docs/TERMINAL_ARCHITECTURE.md §5.3, ADR-19)
────────────────────────────────────────────────────────────────────
One JSON line per Claude call in ~/.quantos/llm_calls.jsonl: feature, model,
tokens (incl. cache), estimated USD, latency, outcome, request id. Metadata
only -- never prompt or response text, so household data (P2) can't leak
into the log. Also feeds the in-process cockpit metrics (cloud/api/metrics.py).
Never raises: logging must not break the feature it observes.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from core.llm.registry import prices


WEB_SEARCH_USD = 0.01          # $10 per 1,000 searches


def _log_path() -> Path:
    base = os.getenv("QUANTOS_HOME_DIR")
    return (Path(base) if base else Path.home() / ".quantos") / "llm_calls.jsonl"


def estimate_usd(model: str, input_tokens: int, output_tokens: int,
                 cache_read: int = 0, cache_write: int = 0) -> Optional[float]:
    p = prices().get(model)
    if p is None:
        return None
    inp, out = p
    return round((input_tokens * inp + cache_read * inp * 0.1 + cache_write * inp * 1.25
                  + output_tokens * out) / 1_000_000, 6)


def log_call(feature: str, model: str, response: Any = None, started: Optional[float] = None,
             error: Optional[BaseException] = None) -> None:
    """Call in a `finally` after messages.create: `started` = time.perf_counter() before it.
    An exception propagating through that `finally` is picked up by itself."""
    if error is None:
        error = sys.exc_info()[1]
    ms, tok, usage = None, {}, None
    try:
        ms = (time.perf_counter() - started) * 1000.0 if started is not None else None
        usage = getattr(response, "usage", None)
        tok = {k: int(getattr(usage, k, 0) or 0) for k in
               ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")}
        searches = int(getattr(getattr(usage, "server_tool_use", None), "web_search_requests", 0) or 0)
        row = {
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "feature": feature, "model": model,
            "ok": response is not None and error is None,
            "stop_reason": getattr(response, "stop_reason", None),
            "latency_ms": round(ms, 1) if ms is not None else None,
            **tok,
            "web_searches": searches,
            "usd": (lambda u: None if u is None else round(u + searches * WEB_SEARCH_USD, 6))(
                estimate_usd(model, tok["input_tokens"], tok["output_tokens"],
                             tok["cache_read_input_tokens"], tok["cache_creation_input_tokens"])),
            "request_id": getattr(response, "_request_id", None),
            "error": type(error).__name__ if error is not None else None,
        }
        path = _log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
    except Exception:
        pass
    try:
        from cloud.api.metrics import record_claude
        record_claude(ms or 0.0, model=model, input_tokens=tok["input_tokens"] if usage else 0,
                      output_tokens=tok["output_tokens"] if usage else 0)
    except Exception:
        pass
