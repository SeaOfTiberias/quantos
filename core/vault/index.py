"""
QuantOS — Obsidian Vault: the index
────────────────────────────────────
Loads a vault directory into memory and answers three kinds of question:

  • `get(name)`          — direct lookup, used by the audit gates, which know
                           exactly which strategy they are checking against.
  • `by_tag(tag)`        — every note carrying a frontmatter tag.
  • `search(query, ...)` — BM25-ranked retrieval. This is the RAG half: it
                           finds the passages worth handing to a model when a
                           human asks a qualitative question of their notes.

Why BM25 and not embeddings
───────────────────────────
At vault scale — tens of notes, not millions — lexical retrieval is not a
compromise, it is the better tool. It is exact, reproducible run to run,
needs no model download, no API key, and no network. Notes are also written
in the vocabulary they will be queried in ("volatility contraction", "stage
2", "volume dry-up"), which is precisely the regime where term matching wins.

The cost of that choice is genuine: BM25 will not connect "shrinking pullback
depth" to "volatility contraction" without a shared word. `retrieve()` is the
single seam where that trade is made, so swapping in a vector store later
means replacing one method, not rewriting the callers.

Freshness
─────────
Notes are read once and cached, keyed by (path, mtime, size). A vault edited
in Obsidian while a long-running agent holds an index would otherwise serve
stale rules indefinitely; `reload_if_changed()` makes the daily jobs pick up
committed edits without a restart.
"""

from __future__ import annotations

import logging
import math
import os
import re
from collections import Counter
from pathlib import Path
from typing import Iterable, Optional

from core.vault.models import SearchHit, StrategyNote
from core.vault.parser import VaultParseError, parse_note

logger = logging.getLogger(__name__)

# Repo-root/obsidian_vault/QuantOS by default (…/core/vault/index.py →
# parents[2] == repo root). Overridable per-deploy, exactly like
# core/prompts/loader.py's PROMPTS_DIR.
_DEFAULT_DIR = Path(__file__).resolve().parents[2] / "obsidian_vault" / "QuantOS"
VAULT_DIR = Path(os.getenv("QUANTOS_VAULT_DIR", str(_DEFAULT_DIR)))

# Obsidian's own config directory, plus the usual template/attachment folders.
# Skipped wholesale — .obsidian/workspace.json in particular rewrites itself
# every time a pane moves, and it is not a strategy note.
_SKIP_DIRS = {".obsidian", ".trash", ".git", "templates", "attachments"}

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Standard Okapi BM25 constants: k1 controls term-frequency saturation, b how
# hard length normalisation bites. These are the textbook defaults and are not
# tuned — with a vault this size, tuning them would be fitting noise.
_BM25_K1 = 1.5
_BM25_B = 0.75


class VaultNotFoundError(FileNotFoundError):
    """The vault directory does not exist."""


class NoteNotFoundError(KeyError):
    """No note by that name or strategy id."""


def tokenize(text: str) -> list[str]:
    """Lowercase alphanumeric runs. Deliberately crude — no stemming, so
    'contraction' and 'contractions' are distinct terms. At this scale a
    stemmer's false merges cost more than its recall gains."""
    return _TOKEN_RE.findall(text.lower())


class VaultIndex:
    """An in-memory index over a vault directory."""

    def __init__(self, notes: Iterable[StrategyNote], vault_dir: Path) -> None:
        self.vault_dir = vault_dir
        self._notes: dict[str, StrategyNote] = {}
        self._by_id: dict[str, StrategyNote] = {}
        for note in notes:
            self._notes[note.name] = note
            self._by_id[note.strategy_id] = note
        self._stamps = {n.path: _stamp(n.path) for n in self._notes.values()}
        self._build_bm25()

    # ── loading ───────────────────────────────────────────────────────────

    @classmethod
    def load(cls, vault_dir: Optional[Path] = None) -> "VaultIndex":
        """Read every `.md` under `vault_dir`. Raises `VaultNotFoundError`.

        An individual note that fails to parse is logged and skipped rather
        than taking the whole vault down — one broken file should not disable
        every gate. A gate whose OWN note is the broken one still blocks,
        because `get()` will not find it.
        """
        directory = Path(vault_dir) if vault_dir else VAULT_DIR
        if not directory.is_dir():
            raise VaultNotFoundError(
                f"Vault directory not found: {directory}. Set QUANTOS_VAULT_DIR "
                f"or create the directory."
            )

        notes: list[StrategyNote] = []
        for path in sorted(directory.rglob("*.md")):
            if any(part in _SKIP_DIRS for part in path.relative_to(directory).parts[:-1]):
                continue
            try:
                notes.append(parse_note(path))
            except VaultParseError as e:
                logger.warning("Vault: skipping %s — %s", path.name, e)

        logger.info("Vault: indexed %d notes from %s (%d with rule blocks)",
                    len(notes), directory, sum(1 for n in notes if n.is_auditable))
        return cls(notes, directory)

    def reload_if_changed(self) -> bool:
        """Re-read the vault if any file's mtime/size moved, or files were
        added or removed. Returns True if anything was reloaded.

        Cheap enough (one stat per note) to call at the top of a daily job.
        """
        try:
            current = {
                p: _stamp(p)
                for p in sorted(self.vault_dir.rglob("*.md"))
                if not any(part in _SKIP_DIRS
                           for part in p.relative_to(self.vault_dir).parts[:-1])
            }
        except OSError as e:
            logger.warning("Vault: could not stat %s (%s) — keeping the cached index",
                           self.vault_dir, e)
            return False

        if current == self._stamps:
            return False

        fresh = VaultIndex.load(self.vault_dir)
        self._notes, self._by_id = fresh._notes, fresh._by_id
        self._stamps = fresh._stamps
        self._build_bm25()
        logger.info("Vault: reloaded after detecting a change on disk")
        return True

    # ── lookup ────────────────────────────────────────────────────────────

    def get(self, name: str) -> StrategyNote:
        """Look up by filename stem or by frontmatter `quantos.id`.

        Both are accepted because callers pin gates to a stable id while
        humans think in filenames, and having one of the two silently miss
        would be a gate that blocks forever for a reason nobody can see.
        """
        if name in self._notes:
            return self._notes[name]
        if name in self._by_id:
            return self._by_id[name]
        raise NoteNotFoundError(
            f"No note named {name!r} in {self.vault_dir}. "
            f"Known: {', '.join(sorted(self._notes)) or '(vault is empty)'}"
        )

    def has(self, name: str) -> bool:
        return name in self._notes or name in self._by_id

    def by_tag(self, tag: str) -> list[StrategyNote]:
        """Notes carrying `tag`, or any tag nested beneath it: `strategy`
        matches `strategy/momentum`, matching Obsidian's own tag semantics."""
        needle = tag.lstrip("#").lower()
        return [
            n for n in self._notes.values()
            if any(t == needle or t.startswith(f"{needle}/") for t in n.tags)
        ]

    @property
    def notes(self) -> list[StrategyNote]:
        return list(self._notes.values())

    @property
    def auditable_notes(self) -> list[StrategyNote]:
        return [n for n in self._notes.values() if n.is_auditable]

    # ── BM25 retrieval ────────────────────────────────────────────────────

    def _build_bm25(self) -> None:
        self._docs: dict[str, Counter] = {}
        self._lengths: dict[str, int] = {}
        doc_freq: Counter = Counter()

        for name, note in self._notes.items():
            # Title and tags are repeated so a query naming the strategy
            # outranks a note that merely mentions it in passing. Three is a
            # judgement call, not a tuned constant.
            text = " ".join([note.title] * 3 + [" ".join(note.tags)] * 3 + [note.body])
            terms = tokenize(text)
            self._docs[name] = Counter(terms)
            self._lengths[name] = len(terms)
            doc_freq.update(set(terms))

        self._doc_freq = doc_freq
        self._avg_len = (sum(self._lengths.values()) / len(self._lengths)) if self._lengths else 0.0

    def search(self, query: str, *, tags: Optional[Iterable[str]] = None,
               limit: int = 5) -> list[SearchHit]:
        """BM25-rank notes against `query`, optionally restricted to `tags`.

        Tag filtering happens BEFORE scoring, so narrowing to
        `strategy/momentum` cannot be overridden by a high-scoring note from
        another discipline.
        """
        candidates = set(self._notes)
        if tags:
            allowed: set[str] = set()
            for tag in tags:
                allowed.update(n.name for n in self.by_tag(tag))
            candidates &= allowed

        terms = tokenize(query)
        if not terms or not candidates:
            return []

        total = len(self._notes)
        hits: list[SearchHit] = []
        for name in candidates:
            freqs = self._docs[name]
            length = self._lengths[name]
            score = 0.0
            matched: list[str] = []
            for term in terms:
                tf = freqs.get(term, 0)
                if tf == 0:
                    continue
                matched.append(term)
                # BM25 IDF, +0.5 smoothing, floored at zero so a term present
                # in every note contributes nothing rather than going negative
                # and penalising an otherwise good match.
                df = self._doc_freq[term]
                idf = max(0.0, math.log(1 + (total - df + 0.5) / (df + 0.5)))
                denom = tf + _BM25_K1 * (1 - _BM25_B + _BM25_B * length / (self._avg_len or 1))
                score += idf * (tf * (_BM25_K1 + 1)) / denom
            if score > 0:
                hits.append(SearchHit(note=self._notes[name], score=score,
                                      matched_terms=tuple(dict.fromkeys(matched))))

        hits.sort(key=lambda h: (-h.score, h.note.name))
        return hits[:limit]

    def __repr__(self) -> str:
        return f"<VaultIndex {len(self._notes)} notes from {self.vault_dir}>"


def _stamp(path: Path) -> tuple[float, int]:
    try:
        st = path.stat()
        return (st.st_mtime, st.st_size)
    except OSError:
        return (0.0, -1)
