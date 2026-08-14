"""
QuantOS — Obsidian Vault: lint
───────────────────────────────
The third of Karpathy's LLM-wiki operations: check index integrity, links, and
general wiki health.

Findings are graded, and the grading is the useful part. A vault accumulates
untidiness constantly — that is what a working notebook looks like — so a lint
that shouts about everything gets ignored, and then the one finding that
mattered gets ignored with it.

  ERROR    something is actively wrong or unsafe. A rule block sitting in a
           layer that cannot execute it. A raw source whose bytes no longer
           match the checksum a wiki page cited. A rule that will not parse.
  WARNING  something will degrade behaviour if left. Duplicate note stems
           (wiki-links become ambiguous), a stale index.
  INFO     normal working state, reported so it is visible. Unresolved links —
           which in Obsidian mean "page worth writing", not "broken" — and
           orphans.

The executability check is the reason this module exists at all. Everything
else here is hygiene; that one is the safety property from
core/vault/layers.py, verified rather than assumed.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from core.vault.index import VaultIndex
from core.vault.ingest import body_checksum
from core.vault.layers import Layer
from core.vault.rules import RuleSyntaxError, parse_expression

logger = logging.getLogger(__name__)

_CHECKSUM_RE = re.compile(r"^checksum:\s*([0-9a-f]{64})\s*$", re.MULTILINE)
_FRONTMATTER_RE = re.compile(r"\A---\r?\n.*?\r?\n---\r?\n?", re.DOTALL)


class Severity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


@dataclass(frozen=True)
class Finding:
    severity: Severity
    code: str
    message: str
    note: Optional[str] = None
    path: Optional[Path] = None

    def __str__(self) -> str:
        where = f" ({self.note})" if self.note else ""
        return f"[{self.severity.value}] {self.code}{where}: {self.message}"


@dataclass
class LintReport:
    findings: list[Finding]

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity is Severity.ERROR]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity is Severity.WARNING]

    @property
    def infos(self) -> list[Finding]:
        return [f for f in self.findings if f.severity is Severity.INFO]

    @property
    def ok(self) -> bool:
        """Errors only. Warnings and infos are the normal state of a vault
        somebody is actually using."""
        return not self.errors

    def summary(self) -> str:
        return (f"{len(self.errors)} error(s), {len(self.warnings)} warning(s), "
                f"{len(self.infos)} note(s)")


def lint_vault(index: VaultIndex) -> LintReport:
    """Run every check against an already-loaded index."""
    findings: list[Finding] = []
    findings += _check_executability(index)
    findings += _check_rule_syntax(index)
    findings += _check_raw_immutability(index)
    findings += _check_duplicate_stems(index)
    findings += _check_index_freshness(index)
    findings += _check_links(index)
    findings += _check_layer_placement(index)

    report = LintReport(findings=findings)
    logger.info("Vault lint: %s", report.summary())
    return report


def _check_executability(index: VaultIndex) -> list[Finding]:
    """Rule blocks outside `brain/`.

    The safety check. A rule here does nothing — which is the correct
    behaviour — but its author probably believes it does something, and a
    silently-inert gate is exactly the class of problem this package is built
    to avoid.
    """
    findings = []
    for note in index.notes:
        if not note.has_unexecutable_rules:
            continue
        layer = note.layer.value if note.layer else "unknown"
        findings.append(Finding(
            severity=Severity.ERROR,
            code="rules-outside-brain",
            note=note.name,
            path=note.path,
            message=(
                f"{len(note.rules)} rule(s) in the {layer}/ layer, which never "
                f"executes. These conditions do nothing. Move the note to brain/ "
                f"if you wrote them and want them enforced; delete them if an "
                f"agent generated them."
            ),
        ))
    return findings


def _check_rule_syntax(index: VaultIndex) -> list[Finding]:
    """Every rule in an executable note must parse.

    Caught here rather than at audit time so a typo surfaces when you lint,
    not on the morning a signal fires and the gate blocks for a reason nobody
    can read.
    """
    findings = []
    for note in index.auditable_notes:
        for rule in note.rules:
            try:
                parse_expression(rule.expression)
            except RuleSyntaxError as e:
                findings.append(Finding(
                    severity=Severity.ERROR, code="rule-syntax", note=note.name,
                    path=note.path,
                    message=f"line {rule.line_number}: {e}",
                ))
    return findings


def _check_raw_immutability(index: VaultIndex) -> list[Finding]:
    """Re-hash each ingested source against the checksum in its frontmatter.

    `raw/` is immutable so that a wiki page's citation stays meaningful. If
    the bytes moved, every claim compiled from this file is now citing
    something that no longer says what it said.
    """
    findings = []
    for note in index.by_layer(Layer.RAW):
        try:
            text = note.path.read_text(encoding="utf-8")
        except OSError as e:
            findings.append(Finding(severity=Severity.ERROR, code="raw-unreadable",
                                    note=note.name, path=note.path, message=str(e)))
            continue

        match = _CHECKSUM_RE.search(text)
        if not match:
            findings.append(Finding(
                severity=Severity.WARNING, code="raw-no-checksum", note=note.name,
                path=note.path,
                message="no checksum in frontmatter — was this filed by hand rather "
                        "than by `vault ingest`? Its provenance cannot be verified.",
            ))
            continue

        # The stored checksum is of the ORIGINAL source bytes, which are not
        # recoverable from the rendered note. What is verifiable is that the
        # body has not changed since ingest, tracked by re-hashing the body
        # below the frontmatter and comparing to a body-hash line if present.
        stored_body = re.search(r"^body_checksum:\s*([0-9a-f]{64})\s*$", text, re.MULTILINE)
        if stored_body and stored_body.group(1) != body_checksum(text):
            findings.append(Finding(
                severity=Severity.ERROR, code="raw-modified", note=note.name,
                path=note.path,
                message="the body has changed since ingest. raw/ is append-only — "
                        "wiki pages cite this file. Restore it, or re-ingest the "
                        "new version as a separate dated source.",
            ))
    return findings


def _check_duplicate_stems(index: VaultIndex) -> list[Finding]:
    """Two notes sharing a filename stem make every `[[link]]` to that name
    ambiguous — Obsidian resolves it arbitrarily, and so does this package's
    graph."""
    findings = []
    for stem, paths in sorted(index.duplicate_stems.items()):
        where = ", ".join(f"{p.parent.name}/" for p in paths)
        findings.append(Finding(
            severity=Severity.WARNING, code="duplicate-stem", note=stem,
            message=f"{len(paths)} notes share the stem {stem!r} ({where}) — "
                    f"wiki-links to it are ambiguous, and the index keeps only "
                    f"the last one loaded",
        ))
    return findings


def _check_index_freshness(index: VaultIndex) -> list[Finding]:
    """`wiki/index.md` should list every note. It is generated, so drift means
    somebody added notes and did not regenerate."""
    index_page = index.paths.index_page
    if not index_page.is_file():
        return [Finding(
            severity=Severity.INFO, code="no-index",
            message="wiki/index.md does not exist — run `python scripts/vault.py index`",
        )]

    try:
        listed = set(re.findall(r"\[\[([^\]|#]+)", index_page.read_text(encoding="utf-8")))
    except OSError as e:
        return [Finding(severity=Severity.WARNING, code="index-unreadable",
                        message=str(e), path=index_page)]

    missing = sorted({n.name for n in index.notes} - {s.strip() for s in listed}
                     - {index_page.stem})
    if missing:
        shown = ", ".join(missing[:6]) + (" …" if len(missing) > 6 else "")
        return [Finding(
            severity=Severity.WARNING, code="index-stale",
            message=f"{len(missing)} note(s) missing from wiki/index.md ({shown}) — "
                    f"run `python scripts/vault.py index`",
            path=index_page,
        )]
    return []


def _check_links(index: VaultIndex) -> list[Finding]:
    """Unresolved links and orphans — both INFO.

    An unresolved `[[link]]` is how Obsidian users mark a page worth writing.
    Reporting it as breakage would be wrong, but not reporting it at all
    wastes the signal.
    """
    findings = []
    for target, sources in index.graph.unresolved_links().items():
        shown = ", ".join(sources[:4]) + (" …" if len(sources) > 4 else "")
        findings.append(Finding(
            severity=Severity.INFO, code="unresolved-link",
            message=f"[[{target}]] has no note — linked from {shown}",
        ))

    orphans = index.graph.orphans()
    if orphans:
        shown = ", ".join(orphans[:6]) + (" …" if len(orphans) > 6 else "")
        findings.append(Finding(
            severity=Severity.INFO, code="orphan",
            message=f"{len(orphans)} note(s) neither link out nor are linked to "
                    f"({shown}) — unreachable by graph expansion",
        ))
    return findings


def _check_layer_placement(index: VaultIndex) -> list[Finding]:
    """Notes sitting outside the three layers.

    LOOSE is safe (nothing executes) but invisible to the layer model, and it
    is what a pre-migration vault looks like — worth saying once rather than
    leaving someone to wonder why their rules stopped firing.
    """
    # SCHEMA.md lives at the vault root on purpose — it is the conventions
    # document (Karpathy's pattern keeps it beside the layers, not inside one),
    # so it is meta rather than an un-migrated note.
    schema_stem = index.paths.schema.stem
    loose = [n for n in index.by_layer(Layer.LOOSE) if n.name != schema_stem]
    if not loose:
        return []
    with_rules = [n for n in loose if n.rules]
    severity = Severity.ERROR if with_rules else Severity.WARNING
    detail = ""
    if with_rules:
        detail = (f" {len(with_rules)} of them contain rule blocks that are NOT "
                  f"being executed: {', '.join(n.name for n in with_rules[:4])}")
    return [Finding(
        severity=severity, code="unlayered-note",
        message=f"{len(loose)} note(s) sit outside brain/, raw/ and wiki/.{detail}",
    )]
