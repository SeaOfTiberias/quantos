"""
QuantOS — Obsidian Vault: the narrator (optional)
──────────────────────────────────────────────────
Writes prose over an AUDIT THAT HAS ALREADY BEEN DECIDED. It is handed a
finished `AuditReport` — verdict computed, every rule evaluated with its live
numbers — and returns a paragraph of explanation. It cannot change the
verdict, and there is no code path by which its output feeds back into one.

This constraint is the reason the module is shaped this way, and it is not
stylistic. `core/options/recommender.py` in this repo was stripped of exactly
this capability on 2026-07-25, and its docstring records why: a fluent
model-written rationale plus a numeric confidence score, wrapped around a
label that had failed validation, "reads as grounded analysis when it isn't —
a stronger over-trust trigger than a bare unlabeled number, not a weaker
one." The lesson generalises. A narrator that could nudge a FAIL toward "but
consider…" would reintroduce precisely that failure.

So:

  • Input is the report, never the raw bars. The model cannot re-derive a
    different answer because it is never given the material to do so.
  • Output is a string, assigned to `AuditReport.narration` — a field nothing
    branches on. `Verdict.is_clear_to_proceed` reads `verdict` only.
  • No API key, no network, an API error, an empty response: narration is
    None and the audit is unaffected. Narration is never load-bearing.

The prompt lives in prompts/ like every other prompt in this project, so its
history is reviewable in git diffs (see core/prompts/loader.py).
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from core.prompts import loader as prompts
from core.vault.models import AuditReport, StrategyNote

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 400

SYSTEM_PROMPT = "vault_audit_narrator_system"
USER_PROMPT = "vault_audit_narrator_user"

# How much of the note to quote back as context. Enough for the model to use
# the author's own vocabulary; short enough that a long note cannot crowd out
# the rule results, which are the part that actually matters.
_NOTE_EXCERPT_CHARS = 2000


def narrate(report: AuditReport, note: Optional[StrategyNote] = None,
            *, client=None) -> Optional[AuditReport]:
    """Return a copy of `report` with `narration` filled in, or the report
    unchanged if narration is unavailable.

    Never raises. Every failure mode — no key, no SDK, API error, empty
    completion — degrades to the original report, because an audit that
    stands on its own is the invariant and the prose is the optional part.
    """
    text = _generate(report, note, client=client)
    if not text:
        return report
    # dataclasses.replace would work, but constructing explicitly makes it
    # visible that `verdict` is carried across untouched.
    return AuditReport(
        symbol=report.symbol,
        note_name=report.note_name,
        verdict=report.verdict,          # <- unchanged, deliberately
        reason=report.reason,
        results=report.results,
        narration=text,
    )


def _generate(report: AuditReport, note: Optional[StrategyNote],
              *, client=None) -> Optional[str]:
    if client is None:
        client = _default_client()
    if client is None:
        return None

    try:
        system = prompts.load(SYSTEM_PROMPT)
        user = prompts.render(
            USER_PROMPT,
            symbol=report.symbol,
            note_name=report.note_name,
            verdict=report.verdict.value,
            reason=report.reason,
            rule_table=_render_rules(report),
            note_excerpt=(note.body[:_NOTE_EXCERPT_CHARS] if note else "(note text unavailable)"),
        )
    except (prompts.PromptNotFoundError, KeyError) as e:
        logger.warning("Vault narrator: prompt unavailable (%s) — skipping narration", e)
        return None

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        parts = [block.text for block in response.content if getattr(block, "type", "") == "text"]
        return "\n".join(parts).strip() or None
    except Exception as e:
        logger.warning("Vault narrator: Claude call failed (%s) — the audit stands "
                       "without narration", e)
        return None


def _render_rules(report: AuditReport) -> str:
    """The rule results as a plain table, values already substituted.

    The model is shown outcomes, not inputs it could reinterpret.
    """
    lines = []
    for result in report.results:
        if result.passed is True:
            mark = "PASS"
        elif result.passed is False:
            mark = "FAIL"
        else:
            mark = "UNEVALUATED"
        lines.append(f"[{mark}] {result.detail}")
    return "\n".join(lines) or "(no rules)"


def _default_client():
    """Build an Anthropic client from the environment, or None.

    Imported lazily so core.vault stays importable — and every gate stays
    functional — on a machine with no anthropic SDK installed at all.
    """
    if not os.getenv("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic
    except ImportError:
        logger.debug("Vault narrator: anthropic SDK not installed — no narration")
        return None
    return anthropic.Anthropic()
