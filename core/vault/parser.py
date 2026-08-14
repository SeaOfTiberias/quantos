"""
QuantOS — Obsidian Vault: note parser
──────────────────────────────────────
Turns one `.md` file into a `StrategyNote`: YAML frontmatter, body text, and
the machine-readable rules fenced in a ```quantos-rules``` block.

The format is chosen so a note stays a perfectly ordinary Obsidian document.
Frontmatter tags still drive Obsidian's own search and graph view; the rule
block renders as a plain code block in the editor. Nothing here requires a
plugin, and a note with no rule block is still valid — it is simply context
rather than a gate.

    ---
    tags:
      - strategy/momentum
      - trading/vcp
    quantos:
      id: minervini_vcp
    ---

    # Mark Minervini's VCP

    Prose, diagrams, links — anything at all.

    ```quantos-rules
    # Stage 2 uptrend — the SEPA trend template
    close > sma(50) > sma(150) > sma(200)
    sma(200) > sma(200)[20]              # 200-day sloping up over a month
    ```

Why the rules live in a fenced block rather than in frontmatter: they are the
part a human most needs to read and reason about, and burying a strategy's
actual conditions in YAML makes them invisible in Obsidian's reading view.
The block also keeps line numbers meaningful, so a parse error can point at
the offending line.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Optional

import yaml

from core.vault.models import Rule, StrategyNote

logger = logging.getLogger(__name__)

RULE_BLOCK_LANGUAGE = "quantos-rules"

_FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?", re.DOTALL)
_RULE_BLOCK_RE = re.compile(
    rf"^```{RULE_BLOCK_LANGUAGE}[ \t]*\r?\n(.*?)^```",
    re.DOTALL | re.MULTILINE,
)
_H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)


class VaultParseError(ValueError):
    """The file could not be read as a strategy note."""


def parse_note(path: Path) -> StrategyNote:
    """Read and parse one markdown file. Raises `VaultParseError`.

    Malformed frontmatter is a warning, not a failure — a note whose YAML has
    a stray tab is still useful as retrieval context, and refusing to load
    the whole vault over it would take every gate down with it. A malformed
    *rule* is different and is left to the rule engine, which reports it as
    unevaluable so the gate blocks.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise VaultParseError(f"could not read {path}: {e}") from e

    frontmatter, body = _split_frontmatter(text, path)
    rules = tuple(_extract_rules(body, note_name=path.stem))

    heading = _H1_RE.search(body)
    title = heading.group(1).strip() if heading else path.stem.replace("_", " ")

    return StrategyNote(
        name=path.stem,
        path=path,
        title=title,
        tags=_normalise_tags(frontmatter.get("tags")),
        body=body,
        rules=rules,
        frontmatter=frontmatter,
    )


def _split_frontmatter(text: str, path: Path) -> tuple[dict[str, Any], str]:
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text

    raw = match.group(1)
    body = text[match.end():]
    try:
        loaded = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        logger.warning("Vault: %s has unreadable frontmatter (%s) — indexing it "
                       "as untagged context; its tags and quantos.id are lost", path.name, e)
        return {}, body

    if loaded is None:
        return {}, body
    if not isinstance(loaded, dict):
        logger.warning("Vault: %s frontmatter is %s, expected a mapping — ignoring it",
                       path.name, type(loaded).__name__)
        return {}, body
    return loaded, body


def _normalise_tags(raw: Any) -> tuple[str, ...]:
    """Accept both YAML list form and Obsidian's inline `tags: a, b` form."""
    if raw is None:
        return ()
    if isinstance(raw, str):
        parts = [p.strip() for p in raw.replace(",", " ").split()]
    elif isinstance(raw, (list, tuple)):
        parts = [str(p).strip() for p in raw]
    else:
        return ()
    return tuple(p.lstrip("#").lower() for p in parts if p)


def _extract_rules(body: str, *, note_name: str) -> list[Rule]:
    """Pull every rule line out of every ```quantos-rules``` block in the note.

    Multiple blocks are allowed and are concatenated — it reads better to put
    the trend-template rules next to the trend-template prose and the volume
    rules next to the volume prose than to collect them all at the bottom.
    Line numbers are counted within each block so an error message points
    somewhere a human can actually look.
    """
    rules: list[Rule] = []
    for block in _RULE_BLOCK_RE.finditer(body):
        for offset, raw_line in enumerate(block.group(1).splitlines(), start=1):
            expression, comment = _strip_comment(raw_line)
            if not expression:
                continue
            rules.append(Rule(
                expression=expression,
                note_name=note_name,
                line_number=offset,
                comment=comment,
            ))
    return rules


def _strip_comment(line: str) -> tuple[str, str]:
    """Split `close > sma(50)   # the trend gate` into rule and comment.

    `#` is safe as a comment marker because the DSL has no string literals
    and no operator containing it — see core/vault/rules.py's grammar.
    """
    head, sep, tail = line.partition("#")
    return head.strip(), tail.strip() if sep else ""
