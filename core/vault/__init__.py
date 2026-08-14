"""
QuantOS — Obsidian vault integration.

Uses a local Obsidian note vault as the system's qualitative memory: strategy
write-ups (Minervini's SEPA/VCP, Weinstein's Stage Analysis) carry both the
prose a human reads and a machine-readable rule block a signal can be audited
against before it reaches an execution path.

Read core/vault/models.py first — `Verdict.is_clear_to_proceed` is the safety
contract the rest of the package exists to honour.

    from core.vault.gates import audit_gate

    decision = audit_gate("TVSMOTOR", daily_bars, ["minervini_vcp"])
    if not decision.allowed:
        logger.info(decision.log_line())
        return
"""

from core.vault.auditor import StrategyAuditor, load_auditor
from core.vault.gates import audit_gate, get_shared_auditor, rs_rating_from_rank
from core.vault.index import NoteNotFoundError, VaultIndex, VaultNotFoundError
from core.vault.models import (
    AuditReport, GateDecision, Rule, RuleResult, SearchHit, StrategyNote, Verdict,
)

__all__ = [
    "AuditReport", "GateDecision", "NoteNotFoundError", "Rule", "RuleResult",
    "SearchHit", "StrategyAuditor", "StrategyNote", "VaultIndex",
    "VaultNotFoundError", "Verdict", "audit_gate", "get_shared_auditor",
    "load_auditor", "rs_rating_from_rank",
]
