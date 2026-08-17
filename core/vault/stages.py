"""
QuantOS — Obsidian Vault: the stage classifier
───────────────────────────────────────────────
Answers "where in Weinstein's four-stage cycle is this name?" — as opposed to
core/vault/auditor.py, which answers "do this note's conditions hold?".

Why this is a separate mechanism and not another rule block
────────────────────────────────────────────────────────────
A ```quantos-rules``` block is **conjunctive**: every rule must hold, and the
result is one PASS/FAIL. Stages are **mutually exclusive**: exactly one of
1/2/3/4 applies, and asking "did all four hold" is meaningless. So a
```quantos-stages``` block is evaluated **first-match-wins**, in the order the
note writes it, and the note's line order is the tie-break.

Everything else is shared. The clause expressions are parsed and evaluated by
core/vault/rules.py against the same `MarketFacts` — same whitelist, same
`InsufficientData` handling, same refusal to `eval()` text out of a markdown
file. This module adds the aggregation and nothing else.

The Stage 1 / Stage 3 problem
─────────────────────────────
Both are "flat 30-week MA, price chopping across it". In a snapshot they are
indistinguishable; the only thing separating a base from a top is what came
BEFORE — Stage 1 follows a decline, Stage 3 follows an advance. That is
path-dependence, and a stateless snapshot evaluator cannot express it.

It does not need a new primitive. The DSL's `[n]` bar-lag already reaches
back: `sma(150)[25] > sma(150)[125]` reads "the 30-week average was higher
five weeks ago than it was six months before that", i.e. the prior trend was
up, i.e. this flat patch is a top. Reverse the comparison and it is a base.

This is the one place the classifier's history requirement bites, and it is
tight on purpose: `sma(150)[125]` needs 150 + 125 = 275 warmed-up bars, and
scripts/run_momentum_shortlist.py fetches FETCH_WINDOW_DAYS = 400 calendar
days ≈ 275 trading bars. It fits with nothing to spare. Lengthening that lag
means widening the fetch, which means more calls under Fyers' 366-day chunk
cap across ~500 symbols every morning. Do not lengthen it casually.

Not a gate
──────────
`GateDecision` does not read this module and must not start. A verdict has a
safe default — block — and fails closed. A stage has no safe default; there
is no conservative answer to "which stage". When a clause cannot be
evaluated, the answer is `stage=None`, meaning *not classified*, which is
neither a stage nor a permission. Callers render it; nothing acts on it.
"""

from __future__ import annotations

import logging
import re
from typing import Iterator, Optional, Sequence

from core.vault.facts import MarketFacts
from core.vault.models import Stage, StageClause, StageResult
from core.vault.rules import (
    InsufficientData,
    RuleSyntaxError,
    evaluate_expression,
    parse_expression,
)

logger = logging.getLogger(__name__)

STAGE_BLOCK_LANGUAGE = "quantos-stages"

# `stage <n> [<phase>] [when <expression>]`
#   stage 2 when sma(150) > sma(150)[25] * 1.01
#   stage 2 pivot when ...
#   stage 1
# The phase is an optional bare identifier; anything after `when` is handed
# to the rule DSL untouched.
_CLAUSE_RE = re.compile(
    r"""^stage \s+ (?P<stage>[1-4]) \s*
        (?P<phase>[A-Za-z][\w-]*)? \s*
        (?: when \s+ (?P<expression>.+) )? \s*$""",
    re.VERBOSE | re.IGNORECASE,
)


class StageSyntaxError(ValueError):
    """A line in a ```quantos-stages``` block is not a valid clause."""


def parse_stage_clause(line: str, *, note_name: str, line_number: int,
                       comment: str = "") -> StageClause:
    """Parse one `stage N [phase] [when expr]` line. Raises `StageSyntaxError`.

    The expression half is validated eagerly by the rule DSL's own parser, so
    a typo in a stage clause is caught when the vault loads rather than on the
    morning someone reads the chart.
    """
    match = _CLAUSE_RE.match(line.strip())
    if not match:
        raise StageSyntaxError(
            f"{note_name}:{line_number}: {line.strip()!r} is not a stage clause. "
            f"Expected 'stage <1-4> [phase] [when <expression>]', "
            f"e.g. 'stage 2 pivot when close > sma(150)'"
        )

    expression = (match.group("expression") or "").strip() or None
    if expression is not None:
        try:
            parse_expression(expression)
        except RuleSyntaxError as e:
            raise StageSyntaxError(f"{note_name}:{line_number}: {e}") from e

    return StageClause(
        stage=Stage(int(match.group("stage"))),
        expression=expression,
        note_name=note_name,
        line_number=line_number,
        phase=(match.group("phase") or "").lower(),
        comment=comment,
    )


def validate_clauses(clauses: Sequence[StageClause]) -> list[str]:
    """Structural problems with a whole block, as human-readable strings.

    Returned rather than raised: a note with an unreachable clause is still
    usable, and `vault lint` wants to report every problem at once instead of
    stopping at the first. `classify` enforces the one that actually changes
    an answer (a default that is not last) by ignoring anything after it.
    """
    problems: list[str] = []
    if not clauses:
        return problems

    for index, clause in enumerate(clauses):
        if clause.is_default and index != len(clauses) - 1:
            unreachable = len(clauses) - index - 1
            problems.append(
                f"{clause.note_name}:{clause.line_number}: '{clause.display}' has no "
                f"`when`, so it matches everything — the {unreachable} clause(s) after "
                f"it can never be reached"
            )

    if not clauses[-1].is_default:
        problems.append(
            f"{clauses[-1].note_name}: the block has no terminal default (a bare "
            f"`stage N` on the last line), so a symbol matching none of the clauses "
            f"is reported unclassified rather than assigned a stage"
        )
    return problems


def classify(
    clauses: Sequence[StageClause],
    facts: MarketFacts,
    *,
    offset: int = 0,
    note_name: str = "",
) -> StageResult:
    """Classify one symbol at one bar. First clause whose expression holds wins.

    `offset` is a bar lag — 0 is the latest bar, 10 is ten sessions ago — which
    is what makes `stage_timeline` possible without a second implementation.

    An unevaluable clause does NOT fall through to the next one. Falling
    through would let a warm-up failure in the Stage 4 test silently promote a
    declining stock to Stage 2, which is the precise shape of error this
    project keeps having to design against: a missing input rendering as a
    confident answer. It stops, and returns unclassified.
    """
    name = note_name or (clauses[0].note_name if clauses else "")
    if not clauses:
        return StageResult(symbol=facts.symbol, note_name=name,
                           reason="the note has no ```quantos-stages``` block")

    for clause in clauses:
        if clause.is_default:
            return StageResult(
                symbol=facts.symbol, note_name=name, stage=clause.stage,
                phase=clause.phase, matched_clause=clause,
                reason=f"no earlier clause matched; fell through to the default "
                       f"on line {clause.line_number}",
            )

        substitutions: dict[str, float] = {}
        try:
            matched = evaluate_expression(clause.expression, facts, offset=offset,
                                          substitutions=substitutions)
        except InsufficientData as e:
            return StageResult(
                symbol=facts.symbol, note_name=name, substitutions=substitutions,
                reason=(f"'{clause.display}' on line {clause.line_number} could not be "
                        f"evaluated against {facts.bar_count} bars — {e.term} "
                        f"unavailable; classification stopped rather than falling "
                        f"through to a later clause"),
            )
        except RuleSyntaxError as e:
            return StageResult(
                symbol=facts.symbol, note_name=name,
                reason=f"line {clause.line_number} is not evaluable — {e}",
            )

        if matched:
            return StageResult(
                symbol=facts.symbol, note_name=name, stage=clause.stage,
                phase=clause.phase, matched_clause=clause,
                substitutions=substitutions,
                reason=_rendered(clause, substitutions),
            )

    return StageResult(
        symbol=facts.symbol, note_name=name,
        reason=(f"none of the {len(clauses)} clauses matched and the block has no "
                f"terminal default"),
    )


def stage_timeline(
    clauses: Sequence[StageClause],
    facts: MarketFacts,
    *,
    bars: int,
    note_name: str = "",
) -> list[tuple[int, StageResult]]:
    """Classify the last `bars` sessions, oldest first, as (offset, result).

    This is the "journey" — the same classifier walked backwards rather than a
    second implementation of it, which is the only reason the timeline and the
    live label cannot disagree.

    Unclassified bars are included, not dropped. The early part of any history
    is unclassifiable while `sma(150)[125]` warms up, and silently omitting
    those bars would make a chart look like the stock did not exist yet.
    """
    span = max(0, min(bars, facts.bar_count))
    return [
        (offset, classify(clauses, facts, offset=offset, note_name=note_name))
        for offset in range(span - 1, -1, -1)
    ]


def stage_transitions(
    timeline: Sequence[tuple[int, StageResult]],
) -> list[tuple[int, Optional[Stage], Optional[Stage]]]:
    """Reduce a timeline to its changes, as (offset, from_stage, to_stage).

    Only the stage number is compared, not the phase: a name moving from
    `2 · pivot` to `2 · advancing` has not changed stage, and reporting that
    as a transition would bury the four real ones in noise. Callers wanting
    phase changes have the full timeline.
    """
    changes: list[tuple[int, Optional[Stage], Optional[Stage]]] = []
    previous: Optional[Stage] = None
    for index, (offset, result) in enumerate(timeline):
        if index > 0 and result.stage != previous:
            changes.append((offset, previous, result.stage))
        previous = result.stage
    return changes


def bars_in_stage(timeline: Sequence[tuple[int, StageResult]]) -> Optional[int]:
    """How many consecutive bars, ending at the newest, share its stage.

    None when the newest bar is unclassified — "0 bars in no stage" would
    read as a fresh transition into something.
    """
    if not timeline:
        return None
    current = timeline[-1][1].stage
    if current is None:
        return None
    count = 0
    for _, result in reversed(timeline):
        if result.stage != current:
            break
        count += 1
    return count


def _rendered(clause: StageClause, substitutions: dict[str, float]) -> str:
    """The matching clause with its live numbers spelled out — same principle
    as `RuleResult.detail`: a bare 'Stage 2' tells a reader nothing about how
    close the call was to Stage 3."""
    if not substitutions:
        return clause.expression or ""
    values = ", ".join(f"{term}={value:,.2f}" for term, value in substitutions.items())
    return f"{clause.expression}  [{values}]"
