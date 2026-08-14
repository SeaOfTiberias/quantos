"""
QuantOS — Obsidian Vault: the three layers
───────────────────────────────────────────
The vault follows Karpathy's LLM-wiki pattern (April 2026) — immutable
sources in `raw/`, an agent-compiled wiki of interlinked entity pages in
`wiki/` — with one layer added on top:

    obsidian_vault/QuantOS/
      brain/     human-authored canon.   EXECUTABLE.
      raw/       immutable sources.      never executable, never edited.
      wiki/      LLM-compiled pages.     never executable.

Why `brain/` exists and why the split is enforced in code
─────────────────────────────────────────────────────────
Karpathy's pattern has two layers because its output is read by a human. This
vault's output is also read by a rule engine that can veto real orders, and
that changes the stakes of "the agent maintains the wiki".

`wiki/` is written by a language model. If a compiled page could carry a
```quantos-rules``` block, the model would be authoring the conditions that
gate money — reviewed by nobody, appearing in no diff anybody reads. That is
the same failure this repo removed from core/options/recommender.py on
2026-07-25, one step worse: not a model narrating a weak signal, but a model
defining the signal.

So the rule is absolute and lives in `Layer.is_executable`:

  • `brain/` — you write it, you review it in a diff, `git log` is its
    changelog. The auditor reads rule blocks from here and nowhere else.
  • `wiki/` — the agent writes it. Searchable, linkable, quotable, excellent
    context for a narrator or a human. A rule block here is a LINT ERROR
    (see core/vault/lint.py), not a rule.
  • `raw/` — whatever you dropped in, normalised and stamped with provenance.
    Never edited after landing, so a wiki page's citation stays meaningful.

The practical consequence: an agent can ingest a Minervini PDF, compile a
`wiki/concepts/volatility-contraction.md` explaining it, and link it — but
turning any of that into something that blocks a trade remains a human edit
to `brain/`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional


class Layer(str, Enum):
    """Which layer of the vault a note belongs to."""

    BRAIN = "brain"
    RAW = "raw"
    WIKI = "wiki"
    LOOSE = "loose"      # a .md sitting outside all three — indexed, inert

    @property
    def is_executable(self) -> bool:
        """Whether rule blocks in this layer may be evaluated.

        BRAIN only. See this module's docstring — this single line is the
        boundary between "a model can describe a strategy" and "a model can
        author the condition that releases an order".
        """
        return self is Layer.BRAIN

    @property
    def is_agent_written(self) -> bool:
        """Whether an agent may create or overwrite files here.

        WIKI only. `brain/` is hand-authored; `raw/` is append-only and
        immutable once a source has landed.
        """
        return self is Layer.WIKI

    @property
    def description(self) -> str:
        return _DESCRIPTIONS[self]


_DESCRIPTIONS = {
    Layer.BRAIN: "human-authored canon — the only layer whose rules execute",
    Layer.RAW:   "immutable ingested sources — never edited after landing",
    Layer.WIKI:  "agent-compiled entity pages — context and retrieval only",
    Layer.LOOSE: "outside the three layers — indexed for search, never executed",
}

# Directory names, relative to the vault root.
BRAIN_DIR = "brain"
RAW_DIR = "raw"
WIKI_DIR = "wiki"

# Where a drag-and-drop lands before `vault ingest` normalises it.
INBOX_DIR = f"{RAW_DIR}/_inbox"

# The wiki's two special pages, per Karpathy's pattern.
WIKI_INDEX = f"{WIKI_DIR}/index.md"
WIKI_LOG = f"{WIKI_DIR}/log.md"

# The conventions document. Karpathy's pattern puts this in CLAUDE.md; here it
# lives in the vault itself so it travels with the notes and is readable in
# Obsidian alongside them.
SCHEMA_FILE = "SCHEMA.md"


def layer_of(path: Path, vault_dir: Path) -> Layer:
    """Which layer `path` sits in, by its first path component under the vault.

    Falls back to LOOSE for anything outside the three directories — including
    a note left at the vault root, which is what an existing single-folder
    vault looks like before migration. LOOSE is indexed and searchable but
    never executable, so an un-migrated vault degrades to "nothing runs"
    rather than "everything runs".
    """
    try:
        parts = path.resolve().relative_to(Path(vault_dir).resolve()).parts
    except ValueError:
        return Layer.LOOSE
    if not parts:
        return Layer.LOOSE
    head = parts[0].lower()
    for layer in (Layer.BRAIN, Layer.RAW, Layer.WIKI):
        if head == layer.value:
            return layer
    return Layer.LOOSE


@dataclass(frozen=True)
class VaultPaths:
    """Resolved absolute paths for one vault. Constructing this does not touch
    the filesystem; call `ensure()` to create anything missing."""

    root: Path

    @property
    def brain(self) -> Path:
        return self.root / BRAIN_DIR

    @property
    def raw(self) -> Path:
        return self.root / RAW_DIR

    @property
    def inbox(self) -> Path:
        return self.root / INBOX_DIR

    @property
    def wiki(self) -> Path:
        return self.root / WIKI_DIR

    @property
    def wiki_concepts(self) -> Path:
        return self.wiki / "concepts"

    @property
    def index_page(self) -> Path:
        return self.root / WIKI_INDEX

    @property
    def log_page(self) -> Path:
        return self.root / WIKI_LOG

    @property
    def schema(self) -> Path:
        return self.root / SCHEMA_FILE

    def ensure(self) -> "VaultPaths":
        """Create the layer directories if absent. Idempotent, and safe to
        call against an existing vault — it never touches files."""
        for directory in (self.brain, self.raw, self.inbox, self.wiki, self.wiki_concepts):
            directory.mkdir(parents=True, exist_ok=True)
        return self

    def for_layer(self, layer: Layer) -> Optional[Path]:
        return {
            Layer.BRAIN: self.brain,
            Layer.RAW: self.raw,
            Layer.WIKI: self.wiki,
            Layer.LOOSE: self.root,
        }.get(layer)
