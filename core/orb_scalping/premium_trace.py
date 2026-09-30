"""
QuantOS — ORB real-premium trace (observability only)
──────────────────────────────────────────────────────
Every 5 minutes while an ORB position is open (paper 18, 18b, or the live
pilot), records the option's REAL price beside the index level and India VIX,
in one batched quote call. Added 2026-09-30 after Fable's review of the fix-2
pricing correction: the backtest reconstructs premiums with Black-Scholes, and
whether time decay should run on calendar time or trading time moves candidate
18's backtest from "passes" to "fails". This trace is the direct test. With the
index level and VIX logged, the model premium can be recomputed afterwards
under any time convention and compared against what the option really traded
at, at the same moment.

Never drives a trading decision; a failed sample is skipped, never guessed.
Append-only JSON lines, same conventions as dry_run_log.py.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

VIX_SYMBOL = "INDIA VIX"
SAMPLE_EVERY_MINUTES = 5


def premium_trace_path() -> Path:
    return Path.home() / ".quantos" / "orb_premium_trace.jsonl"


@dataclass(frozen=True)
class PremiumSample:
    timestamp:     str             # ISO UTC, when sampled
    strategy:      str             # orb_scalping | orb_scalping_filtered | orb_scalping_pilot
    underlying:    str
    option_symbol: str
    option_type:   str             # CE | PE
    strike:        float
    expiry:        str             # ISO date
    option_ltp:    Optional[float]
    index_ltp:     Optional[float]
    vix:           Optional[float]


def append_sample(sample: PremiumSample, path: Optional[Path] = None) -> None:
    path = path or premium_trace_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(sample)) + "\n")


def load_samples(path: Optional[Path] = None) -> list[PremiumSample]:
    path = path or premium_trace_path()
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            out.append(PremiumSample(**json.loads(line)))
        except (json.JSONDecodeError, TypeError):
            continue
    return out
