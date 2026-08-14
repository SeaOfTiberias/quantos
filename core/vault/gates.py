"""
QuantOS — Obsidian Vault: execution gates
──────────────────────────────────────────
The only entry point a live execution path should call. Everything below the
gate can raise; the gate itself never does. It converts every possible
outcome — including its own infrastructure failing — into a `GateDecision`
whose `allowed` flag is safe to branch on.

The fail-closed contract
────────────────────────
`allowed` is True in exactly two situations:

  1. every requested audit returned PASS, or
  2. the gate was explicitly disabled by configuration (`enabled=False`),
     in which case `skipped=True` and the caller can log the difference.

Everything else is False: a FAIL, an INSUFFICIENT_DATA, a missing vault, a
missing note, an unparseable rule, an unexpected exception anywhere in the
stack. There is no path that returns True with a caveat.

Note the asymmetry between (1) and (2). "Disabled" is a decision a human made
in config and can see in config. "Broken" is a decision nobody made. Treating
them the same would mean a deleted vault directory silently behaves like a
deliberate opt-out — the exact shape of the incident where systemd, the
heartbeat and /regime/status all read green while the broker was dead.

Caching
───────
`get_shared_auditor()` holds one process-wide index, refreshed by mtime on
each access. Loading the vault per signal would re-read and re-tokenise every
note on every tick; never refreshing would mean the long-running agent serves
whatever rules were on disk at boot, indefinitely.
"""

from __future__ import annotations

import logging
import threading
from typing import Optional, Sequence

from core.brokers.base import OHLCV
from core.vault.auditor import StrategyAuditor
from core.vault.index import VaultIndex, VaultNotFoundError
from core.vault.models import AuditReport, GateDecision, Verdict

logger = logging.getLogger(__name__)

_shared_lock = threading.Lock()
_shared_auditor: Optional[StrategyAuditor] = None


def get_shared_auditor(vault_dir=None) -> StrategyAuditor:
    """One auditor per process, re-reading the vault when files change.

    Raises `VaultNotFoundError` if the vault is missing — `audit_gate`
    catches that and blocks. Direct callers (the CLI) want the exception.
    """
    global _shared_auditor
    with _shared_lock:
        if _shared_auditor is None:
            _shared_auditor = StrategyAuditor(VaultIndex.load(vault_dir))
        else:
            _shared_auditor.index.reload_if_changed()
        return _shared_auditor


def reset_shared_auditor() -> None:
    """Drop the cached auditor — test hook, and useful after pointing
    QUANTOS_VAULT_DIR somewhere else at runtime."""
    global _shared_auditor
    with _shared_lock:
        _shared_auditor = None


def audit_gate(
    symbol: str,
    daily: Sequence[OHLCV],
    note_names: Sequence[str],
    *,
    rs_rating: Optional[float] = None,
    enabled: bool = True,
    vault_dir=None,
) -> GateDecision:
    """Audit `symbol` against every note in `note_names`. Never raises.

    All notes must PASS for `allowed` to be True — the notes are conjunctive,
    so listing both Minervini and Weinstein means a name has to satisfy both.
    """
    if not enabled:
        return GateDecision(
            allowed=True, verdict=Verdict.UNAVAILABLE, skipped=True,
            reason="vault audit disabled by configuration",
        )

    if not note_names:
        # An empty note list would otherwise vacuously pass ("all zero audits
        # returned PASS"), turning a config typo into an open gate.
        return GateDecision(
            allowed=False, verdict=Verdict.UNAVAILABLE,
            reason="vault audit is enabled but no strategy notes were configured",
        )

    try:
        auditor = get_shared_auditor(vault_dir)
    except VaultNotFoundError as e:
        logger.error("Vault gate: %s — blocking %s", e, symbol)
        return GateDecision(allowed=False, verdict=Verdict.UNAVAILABLE, reason=str(e))
    except Exception as e:
        logger.exception("Vault gate: unexpected failure loading the vault — blocking %s", symbol)
        return GateDecision(
            allowed=False, verdict=Verdict.UNAVAILABLE,
            reason=f"vault could not be loaded: {e}",
        )

    try:
        reports = auditor.audit_all(symbol, daily, note_names, rs_rating=rs_rating)
    except Exception as e:
        logger.exception("Vault gate: unexpected failure auditing %s — blocking", symbol)
        return GateDecision(
            allowed=False, verdict=Verdict.UNAVAILABLE,
            reason=f"audit raised {type(e).__name__}: {e}",
        )

    return _decide(reports)


def _decide(reports: Sequence[AuditReport]) -> GateDecision:
    """Combine per-note reports. Worst verdict wins, using the same
    precedence the auditor applies within a single note."""
    worst = _worst_verdict(r.verdict for r in reports)
    if worst is Verdict.PASS:
        names = ", ".join(r.note_name for r in reports)
        return GateDecision(
            allowed=True, verdict=Verdict.PASS, reports=tuple(reports),
            reason=f"cleared {len(reports)} strategy audit(s): {names}",
        )

    blocking = [r for r in reports if r.verdict is worst]
    reason = "; ".join(f"{r.note_name}: {r.reason}" for r in blocking)
    return GateDecision(
        allowed=False, verdict=worst, reports=tuple(reports),
        reason=reason,
    )


# Worst-first. Mirrors core/vault/auditor.py's within-note precedence: an
# audit that could not run outranks one that ran and rejected, because the
# two need different fixes.
_PRECEDENCE = (
    Verdict.UNAVAILABLE,
    Verdict.INSUFFICIENT_DATA,
    Verdict.FAIL,
    Verdict.PASS,
)


def _worst_verdict(verdicts) -> Verdict:
    seen = set(verdicts)
    for verdict in _PRECEDENCE:
        if verdict in seen:
            return verdict
    return Verdict.UNAVAILABLE      # empty input — block


def rs_rating_from_rank(rank: int, universe_size: int) -> Optional[float]:
    """Convert a 1-based momentum rank into a 0-100 percentile.

    IMPORTANT — what this is and is not. Minervini's RS Rating is IBD's
    12-month price-performance percentile against the entire market. This is
    a percentile of THIS universe's ranking by 52-week-high proximity
    (core/rotation/ranker.py), which is a different measure over a different
    population. It is a defensible stand-in when auditing a shortlist that
    was itself built from that ranking, and it is wrong to read a value from
    it as an IBD RS Rating.

    Any note whose threshold was calibrated against IBD's number should be
    re-read with that in mind before its rule is trusted.
    """
    if universe_size <= 0 or rank < 1 or rank > universe_size:
        return None
    if universe_size == 1:
        return 100.0
    return round(100.0 * (universe_size - rank) / (universe_size - 1), 2)
