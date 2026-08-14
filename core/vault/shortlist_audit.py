"""
QuantOS — Obsidian Vault: momentum shortlist annotator
───────────────────────────────────────────────────────
Adds a vault-audit column to the daily momentum shortlist
(core/discovery/momentum_shortlist.py). This is the gate with the widest
reach and the least consequence: the shortlist has no execution path at all,
so an audit here informs a human's morning reading and can cost nothing.

Direction of dependency matters. `core/discovery/momentum_shortlist.py` knows
nothing about the vault — it stays pure and I/O-free, exactly as its own
docstring promises — and this module reaches *in* to annotate its output
afterwards. Reversing that would put a filesystem read inside a function
whose tests rely on it having none.

Where the RS rating comes from
──────────────────────────────
Both bundled notes ask for `rs_rating`, which cannot be computed from one
symbol's bars. The shortlist happens to hold precisely the missing
ingredient: it has already ranked the whole universe by 52-week-high
proximity, so `momentum_rank` out of `len(entries)` converts straight to a
percentile via `rs_rating_from_rank`.

Read `rs_rating_from_rank`'s docstring before trusting a threshold: this is a
percentile of THIS universe by THIS measure, not IBD's RS Rating, and
Minervini's `>= 70` was written for IBD's.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Optional, Sequence

from core.brokers.base import OHLCV
from core.discovery.momentum_shortlist import ShortlistEntry, VaultNoteScore
from core.vault.auditor import StrategyAuditor
from core.vault.gates import rs_rating_from_rank
from core.vault.index import VaultIndex, VaultNotFoundError
from core.vault.models import AuditReport, Verdict

logger = logging.getLogger(__name__)

# Worst-first, matching core/vault/gates.py. An entry's headline verdict is
# the worst of its per-note verdicts, so a row reading PASS means it cleared
# every note it was audited against.
_PRECEDENCE = (Verdict.UNAVAILABLE, Verdict.INSUFFICIENT_DATA, Verdict.FAIL, Verdict.PASS)


def annotate_with_vault_audit(
    entries: Sequence[ShortlistEntry],
    daily_by_symbol: dict[str, list[OHLCV]],
    note_names: Sequence[str],
    *,
    vault_dir=None,
    auditor: Optional[StrategyAuditor] = None,
) -> list[ShortlistEntry]:
    """Return `entries` with `vault_verdict`/`vault_detail` filled in.

    Never raises and never drops a row. A missing vault, an unreadable note,
    or an exception mid-audit leaves every entry's verdict as UNAVAILABLE
    with the cause in `vault_detail` — the shortlist itself is unaffected,
    because a research aid that disappears when an optional annotation breaks
    would be a worse tool than one with a blank column.
    """
    if not entries:
        return list(entries)

    if not note_names:
        return _all_unavailable(entries, "no strategy notes configured")

    if auditor is None:
        try:
            auditor = StrategyAuditor(VaultIndex.load(vault_dir))
        except VaultNotFoundError as e:
            logger.warning("Shortlist vault audit: %s — leaving the column blank", e)
            return _all_unavailable(entries, str(e))
        except Exception as e:
            logger.exception("Shortlist vault audit: could not load the vault")
            return _all_unavailable(entries, f"vault load failed: {e}")

    # Derived from the ranks themselves, not len(entries). For the whole
    # shortlist the two are identical, but a caller passing a filtered subset
    # (just the LEADER bucket, say) would otherwise have every rank fall
    # outside the range and silently turn the entire column into
    # INSUFFICIENT_DATA.
    universe_size = max(e.momentum_rank for e in entries)
    annotated: list[ShortlistEntry] = []
    counts: dict[str, int] = {}

    for entry in entries:
        daily = daily_by_symbol.get(entry.symbol) or []
        rs_rating = rs_rating_from_rank(entry.momentum_rank, universe_size)
        try:
            reports = auditor.audit_all(entry.symbol, daily, note_names, rs_rating=rs_rating)
        except Exception as e:
            logger.warning("Shortlist vault audit: %s raised %s — marking UNAVAILABLE",
                           entry.symbol, e)
            annotated.append(replace(entry, vault_verdict=Verdict.UNAVAILABLE.value,
                                     vault_detail=f"audit raised {type(e).__name__}: {e}"))
            counts[Verdict.UNAVAILABLE.value] = counts.get(Verdict.UNAVAILABLE.value, 0) + 1
            continue

        verdict = _worst(reports)
        annotated.append(replace(
            entry,
            vault_verdict=verdict.value,
            vault_detail=_detail(reports),
            vault_rules_passed=sum(r.rules_passed for r in reports),
            vault_rules_total=sum(r.rules_total for r in reports),
            vault_notes=_note_scores(reports),
        ))
        counts[verdict.value] = counts.get(verdict.value, 0) + 1

    logger.info("Shortlist vault audit: %s across %d symbols vs %s",
                ", ".join(f"{v}={n}" for v, n in sorted(counts.items())),
                len(entries), ", ".join(note_names))
    return annotated


def _note_scores(reports: Sequence[AuditReport]) -> tuple[VaultNoteScore, ...]:
    """One score per note, in the order the notes were configured.

    This is what the cockpit renders, and it exists because the aggregate
    cannot be read as a quality score. Measured 2026-08-14 across 482 Nifty
    500 names: 5 cleared Minervini, 11 cleared Weinstein, and **none cleared
    both**. Minervini's sixth rule wants volume drying up; Weinstein's fourth
    wants volume expanding. Those describe consecutive phases — the quiet
    pivot before a breakout, and the breakout itself — so requiring both at
    once asks for a state a name is almost never in. Side by side the two
    verdicts each say something; summed they say very little.
    """
    return tuple(
        VaultNoteScore(
            label=r.note_label or r.note_name,
            strategy_id=r.strategy_id or r.note_name,
            verdict=r.verdict.value,
            rules_passed=r.rules_passed,
            rules_total=r.rules_total,
        )
        for r in reports
    )


def _worst(reports: Sequence[AuditReport]) -> Verdict:
    seen = {r.verdict for r in reports}
    for verdict in _PRECEDENCE:
        if verdict in seen:
            return verdict
    return Verdict.UNAVAILABLE


def _detail(reports: Sequence[AuditReport]) -> str:
    """One line per note, with each note's rule tally.

    The tally is the point. Both bundled notes are strict conjunctive screens,
    so the headline verdict reads FAIL for nearly every name on nearly every
    day — measured 2026-08-14: 0 of 50 Alpha 50 names cleared both. A binary
    column that is always the same value carries no information, whereas
    "5/6 | 4/5" separates a name that missed on one rule from one that is
    nowhere near. The full rule-by-rule breakdown is what
    scripts/audit_symbol.py is for.
    """
    return " | ".join(f"{r.note_name}: {r.verdict.value} "
                      f"({r.rules_passed}/{r.rules_total})" for r in reports)


def _all_unavailable(entries: Sequence[ShortlistEntry], reason: str) -> list[ShortlistEntry]:
    return [replace(e, vault_verdict=Verdict.UNAVAILABLE.value, vault_detail=reason)
            for e in entries]
