"""
QuantOS — Obsidian Vault: types
────────────────────────────────
The data model shared by the vault parser, rule engine, auditor and gates.

The one load-bearing decision in this file is `Verdict.is_clear_to_proceed`:
ONLY `PASS` clears. `INSUFFICIENT_DATA` and `UNAVAILABLE` are distinct from
`FAIL` for reporting, but every one of them blocks. That is deliberate, and
it is the whole safety argument for putting this in front of an execution
path — a missing vault, an unparseable rule, or a symbol with 40 bars of
history must never read the same as "the strategy's conditions were met".

This project has already been bitten by exactly that failure shape: systemd,
the heartbeat and /regime/status all reported green for over an hour while
the broker connection was dead (memory: quantos-health-signals-mask-dead-
broker). A gate that silently degrades to "allow" is worse than no gate,
because it manufactures confidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:      # import-cycle guard: layers/wikilinks do not import models
    from core.vault.layers import Layer
    from core.vault.wikilinks import WikiLink


class Verdict(str, Enum):
    """Outcome of auditing one symbol against one strategy note."""

    PASS = "PASS"
    """Every rule in the note evaluated True against real data."""

    FAIL = "FAIL"
    """At least one rule evaluated False. The setup is genuinely rejected."""

    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    """A rule could not be evaluated — not enough bars to warm up an SMA(200),
    or a fact the note asks for (e.g. rs_rating) was never supplied. Says
    nothing about the setup's quality; the audit simply did not happen."""

    UNAVAILABLE = "UNAVAILABLE"
    """The audit could not be attempted at all — vault directory missing, note
    not found, rule block absent or unparseable. An infrastructure fault, not
    a market judgement."""

    @property
    def is_clear_to_proceed(self) -> bool:
        """True only for PASS. See this module's docstring — fail closed."""
        return self is Verdict.PASS


@dataclass(frozen=True)
class Rule:
    """One line from a note's ```quantos-rules``` block.

    `expression` is the raw source text, kept verbatim so an audit report can
    quote the note back to the reader exactly as they wrote it.
    """
    expression: str
    note_name: str
    line_number: int          # 1-based, within the rule block — for error messages
    comment: str = ""         # trailing `# ...` on the rule line, if any


@dataclass(frozen=True)
class RuleResult:
    """Outcome of evaluating one `Rule` against one symbol's `MarketFacts`."""
    rule: Rule
    passed: Optional[bool]    # None = could not be evaluated (see `error`)
    substitutions: dict[str, float] = field(default_factory=dict)
    error: Optional[str] = None

    @property
    def detail(self) -> str:
        """The rule with its live numbers spelled out, e.g.
        `close > sma(50)  [close=4350.20, sma(50)=4102.75]`.

        This is what makes an audit auditable — a bare PASS/FAIL tells a
        reader nothing about how close the call was.
        """
        if self.error:
            return f"{self.rule.expression}  [{self.error}]"
        if not self.substitutions:
            return self.rule.expression
        rendered = ", ".join(
            f"{term}={value:,.2f}" for term, value in self.substitutions.items()
        )
        return f"{self.rule.expression}  [{rendered}]"


@dataclass(frozen=True)
class StrategyNote:
    """A parsed Obsidian note.

    Notes WITHOUT a rule block are still indexed and still retrievable (they
    are useful context for the narrator and for `VaultIndex.search`); they
    just cannot produce a PASS/FAIL. `is_auditable` distinguishes the two —
    and note that it requires BOTH rules and an executable layer.
    """
    name: str                             # file stem, e.g. "Mark_Minervini_VCP_Strategy"
    path: Path
    title: str                            # first `# H1`, falling back to `name`
    tags: tuple[str, ...]                 # from YAML frontmatter `tags:`
    body: str                             # markdown with frontmatter stripped
    rules: tuple[Rule, ...] = ()
    frontmatter: dict[str, Any] = field(default_factory=dict)
    layer: "Layer" = None                 # brain | raw | wiki | loose
    links: tuple["WikiLink", ...] = ()    # outgoing [[wiki-links]]

    @property
    def is_auditable(self) -> bool:
        """Rules exist AND this layer is allowed to execute them.

        The layer half is the safety line: a wiki page compiled by an agent
        may contain a rule block (it is a lint error, but it can happen), and
        it must never become a gate. See core/vault/layers.py.
        """
        if not self.rules:
            return False
        return self.layer is None or self.layer.is_executable

    @property
    def has_unexecutable_rules(self) -> bool:
        """Rule block present in a layer that may not execute — surfaced by
        `vault lint` as an error, since it means someone (or something) wrote
        conditions that silently do nothing."""
        return bool(self.rules) and self.layer is not None and not self.layer.is_executable

    @property
    def strategy_id(self) -> str:
        """Stable identifier a caller can pin a gate to, independent of the
        filename. Falls back to the file stem when `quantos.id` is unset, so
        an un-annotated note still works."""
        quantos = self.frontmatter.get("quantos") or {}
        if isinstance(quantos, dict) and quantos.get("id"):
            return str(quantos["id"])
        return self.name

    @property
    def display_label(self) -> str:
        """Short name for a table column or a badge.

        Read from `quantos.label` so the note itself decides how it is
        labelled — the alternative is a note-name-to-column map living in the
        cockpit, which would silently mislabel any note the user adds. Falls
        back to the first token of the strategy id ("minervini_vcp" ->
        "Minervini"), which is right often enough that a note needs the
        explicit field only when it is not.
        """
        quantos = self.frontmatter.get("quantos") or {}
        if isinstance(quantos, dict) and quantos.get("label"):
            return str(quantos["label"])
        first = self.strategy_id.replace("-", "_").split("_")[0]
        return first.capitalize() if first.islower() else first


@dataclass(frozen=True)
class AuditReport:
    """The result of auditing one symbol against one note.

    `verdict` is computed from `results` alone, by the rule engine, before any
    language model is involved. `narration` is decoration written afterwards
    over an already-settled outcome — see core/vault/narrator.py for why that
    ordering is not negotiable.
    """
    symbol: str
    note_name: str
    verdict: Verdict
    reason: str
    results: tuple[RuleResult, ...] = ()
    narration: Optional[str] = None
    # Carried from the note so a consumer can label a column or pin a result
    # without holding the index. Defaulted, so every existing construction of
    # this dataclass stays valid.
    note_label: Optional[str] = None
    strategy_id: Optional[str] = None

    @property
    def failed_rules(self) -> tuple[RuleResult, ...]:
        return tuple(r for r in self.results if r.passed is False)

    @property
    def unevaluated_rules(self) -> tuple[RuleResult, ...]:
        return tuple(r for r in self.results if r.passed is None)

    @property
    def rules_passed(self) -> int:
        return sum(1 for r in self.results if r.passed is True)

    @property
    def rules_total(self) -> int:
        return len(self.results)

    def summary_line(self) -> str:
        return (f"{self.symbol} vs {self.note_name}: {self.verdict.value} "
                f"({self.rules_passed}/{self.rules_total} rules passed) — {self.reason}")


@dataclass(frozen=True)
class SearchHit:
    """A `VaultIndex.search` result: the note plus its BM25 score."""
    note: StrategyNote
    score: float
    matched_terms: tuple[str, ...] = ()


@dataclass(frozen=True)
class GateDecision:
    """The answer a live execution path actually consumes.

    `allowed` is the only field a caller needs to branch on. It is True in
    exactly two cases: every audit returned PASS, or the gate was explicitly
    disabled by configuration. A gate that could not do its job returns
    False — never True with a caveat attached.
    """
    allowed: bool
    verdict: Verdict
    reason: str
    reports: tuple[AuditReport, ...] = ()
    skipped: bool = False     # True when disabled by config, not by a result

    def log_line(self) -> str:
        if self.skipped:
            return f"vault gate SKIPPED (disabled by config) — {self.reason}"
        state = "ALLOW" if self.allowed else "BLOCK"
        return f"vault gate {state} [{self.verdict.value}] — {self.reason}"
