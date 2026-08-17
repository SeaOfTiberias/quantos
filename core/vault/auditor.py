"""
QuantOS — Obsidian Vault: the auditor
──────────────────────────────────────
Joins the three halves — a note's rules, a symbol's bars, the rule engine —
into an `AuditReport`.

Verdict precedence, and why it is ordered this way:

    UNAVAILABLE        > everything    (the audit could not be attempted)
    INSUFFICIENT_DATA  > FAIL, PASS    (a rule could not be evaluated)
    FAIL               > PASS          (a rule was evaluated and rejected)
    PASS                              (every rule evaluated and held)

INSUFFICIENT_DATA deliberately outranks FAIL. It would be tidier to report
"failed" whenever any rule did not pass, but the two mean opposite things to
whoever reads the report: FAIL says the market rejected the setup,
INSUFFICIENT_DATA says the audit did not happen. Collapsing them would hide
a broken data feed inside a stream of plausible-looking rejections — which is
this project's canonical failure mode (memory: quantos-health-signals-mask-
dead-broker). Both block, so the distinction costs nothing in safety and buys
a great deal in diagnosis.
"""

from __future__ import annotations

import logging
from typing import Optional, Sequence

from core.brokers.base import OHLCV
from core.vault.facts import MarketFacts
from core.vault.index import NoteNotFoundError, VaultIndex
from core.vault.models import (
    AuditReport,
    RuleResult,
    StageResult,
    StrategyNote,
    Verdict,
)
from core.vault.rules import evaluate_rule
from core.vault.stages import classify

logger = logging.getLogger(__name__)


class StrategyAuditor:
    """Audits symbols against the rule blocks in an Obsidian vault."""

    def __init__(self, index: VaultIndex) -> None:
        self.index = index

    def audit(
        self,
        symbol: str,
        daily: Sequence[OHLCV],
        note_name: str,
        *,
        rs_rating: Optional[float] = None,
    ) -> AuditReport:
        """Audit one symbol against one note.

        `rs_rating` is the cross-sectional strength percentile (0-100). Omit
        it and any rule referencing `rs_rating` becomes unevaluable — which
        is the honest outcome, since it cannot be derived from one symbol's
        own bars. See core/vault/facts.py.
        """
        try:
            note = self.index.get(note_name)
        except NoteNotFoundError as e:
            return AuditReport(
                symbol=symbol, note_name=note_name, verdict=Verdict.UNAVAILABLE,
                reason=str(e),
            )

        label, strategy_id = note.display_label, note.strategy_id

        if not note.is_auditable:
            return AuditReport(
                symbol=symbol, note_name=note.name, verdict=Verdict.UNAVAILABLE,
                reason=(f"{note.name} has no ```quantos-rules``` block, so it carries "
                        f"no machine-checkable conditions"),
                note_label=label, strategy_id=strategy_id,
            )

        if not daily:
            return AuditReport(
                symbol=symbol, note_name=note.name, verdict=Verdict.INSUFFICIENT_DATA,
                reason=f"no price history supplied for {symbol}",
                note_label=label, strategy_id=strategy_id,
            )

        facts = MarketFacts(symbol, list(daily), rs_rating=rs_rating)
        results = tuple(evaluate_rule(rule, facts) for rule in note.rules)
        verdict, reason = _verdict_of(results, facts.bar_count)

        return AuditReport(symbol=symbol, note_name=note.name, verdict=verdict,
                           reason=reason, results=results,
                           note_label=label, strategy_id=strategy_id)

    def audit_all(
        self,
        symbol: str,
        daily: Sequence[OHLCV],
        note_names: Sequence[str],
        *,
        rs_rating: Optional[float] = None,
    ) -> tuple[AuditReport, ...]:
        """Audit one symbol against several notes — e.g. requiring a name to
        satisfy both Minervini's trend template and Weinstein's Stage 2."""
        return tuple(
            self.audit(symbol, daily, name, rs_rating=rs_rating)
            for name in note_names
        )

    def classify_stage(
        self,
        symbol: str,
        daily: Sequence[OHLCV],
        note_name: str,
        *,
        rs_rating: Optional[float] = None,
        timeline_bars: int = 0,
    ) -> StageResult:
        """Which stage `symbol` is in, per `note_name`'s stage block.

        Reporting only. This never feeds `GateDecision` — see the module
        docstring of core/vault/stages.py for why a classifier and a
        fail-closed gate must not share a channel. A caller wanting both
        calls `audit` and this, and shows them side by side.

        `timeline_bars` > 0 also walks the classifier back that many sessions;
        the result is discarded here and callers wanting it should use
        `core.vault.stages.stage_timeline` directly. It exists as a parameter
        only so the cost is visible at the call site.
        """
        try:
            note = self.index.get(note_name)
        except NoteNotFoundError as e:
            return StageResult(symbol=symbol, note_name=note_name, reason=str(e))

        if not note.is_stage_classifier:
            return StageResult(
                symbol=symbol, note_name=note.name,
                reason=(f"{note.name} has no ```quantos-stages``` block, so it cannot "
                        f"place a symbol in a stage"),
            )
        if not daily:
            return StageResult(symbol=symbol, note_name=note.name,
                               reason=f"no price history supplied for {symbol}")

        facts = MarketFacts(symbol, list(daily), rs_rating=rs_rating)
        return classify(note.stage_clauses, facts, note_name=note.name)

    def auditable_note_names(self) -> list[str]:
        return sorted(n.name for n in self.index.auditable_notes)

    def stage_classifier_note_names(self) -> list[str]:
        return sorted(n.name for n in self.index.notes if n.is_stage_classifier)


def _verdict_of(results: Sequence[RuleResult], bar_count: int) -> tuple[Verdict, str]:
    """Reduce per-rule outcomes to a single verdict plus a human reason."""
    if not results:
        return Verdict.UNAVAILABLE, "the note's rule block is empty"

    unevaluated = [r for r in results if r.passed is None]
    if unevaluated:
        first = unevaluated[0]
        return Verdict.INSUFFICIENT_DATA, (
            f"{len(unevaluated)} of {len(results)} rules could not be evaluated "
            f"against {bar_count} bars of history — first: {first.detail}"
        )

    failed = [r for r in results if r.passed is False]
    if failed:
        # Name every failing rule. A report saying only "3 rules failed"
        # forces the reader back to the note to work out which, and the whole
        # point of auditing against written rules is that the answer cites
        # the rule it came from.
        detail = "; ".join(r.detail for r in failed)
        return Verdict.FAIL, (
            f"{len(failed)} of {len(results)} rules failed — {detail}"
        )

    return Verdict.PASS, f"all {len(results)} rules hold"


def load_auditor(vault_dir=None) -> StrategyAuditor:
    """Convenience constructor. Propagates `VaultNotFoundError` — callers that
    must not crash should use core/vault/gates.py, which converts a missing
    vault into a blocking UNAVAILABLE decision instead."""
    return StrategyAuditor(VaultIndex.load(vault_dir))
