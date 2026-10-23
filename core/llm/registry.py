"""
QuantOS — model registry (docs/TERMINAL_ARCHITECTURE.md §5.2, ADR-14)
──────────────────────────────────────────────────────────────────────
Every feature that calls Claude asks `model_for("<feature>")` instead of
hard-coding a model id. config/models.yaml maps feature -> role -> model;
QUANTOS_MODEL_<FEATURE> overrides one feature from the environment.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml

REGISTRY_PATH = Path(__file__).resolve().parents[2] / "config" / "models.yaml"
FALLBACK_MODEL = "claude-sonnet-4-6"      # only if the registry file is missing or the feature unknown


@lru_cache(maxsize=1)
def _load() -> dict:
    try:
        return yaml.safe_load(REGISTRY_PATH.read_text()) or {}
    except OSError:
        return {}


def model_for(feature: str) -> str:
    env = os.getenv(f"QUANTOS_MODEL_{feature.upper()}")
    if env:
        return env
    reg = _load()
    role = (reg.get("features") or {}).get(feature)
    return (reg.get("roles") or {}).get(role, FALLBACK_MODEL) if role else FALLBACK_MODEL


def prices() -> dict[str, tuple[float, float]]:
    """model id -> (input, output) USD per million tokens."""
    return {m: (float(p[0]), float(p[1])) for m, p in ((_load().get("prices")) or {}).items()}
