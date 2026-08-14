"""
QuantOS — Obsidian Vault: wiki-links and the note graph
────────────────────────────────────────────────────────
Parses Obsidian's `[[Note]]`, `[[Note|alias]]`, `[[Note#Heading]]` and
`![[Embed]]` syntax, and assembles the forward/backlink graph over an indexed
vault.

The graph is the point of using Obsidian as the store rather than a folder of
loose markdown. Karpathy's LLM-wiki pattern leans on it hard: the compile step
"auto-maintains the link graph between concepts", and a query is answered by
landing on a page and walking outward. Without link parsing, retrieval can
only ever return isolated documents — which is what this vault did before this
module existed.

Two conventions, both Obsidian's own rather than invented here:

  • Targets resolve by file STEM, case-insensitively, ignoring directory. A
    vault may not hold two notes with the same stem in different folders
    without ambiguity, and Obsidian itself warns about that.
  • A link to a page that does not exist yet is NOT an error. Obsidian calls
    these unresolved links and treats writing one as a way of marking a page
    worth creating later. `unresolved_links()` reports them so `vault lint`
    can list them as work, not as breakage.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable, Optional

# [[Target]] | [[Target|alias]] | [[Target#Heading]] | [[Target#Heading|alias]]
# The leading (!)? captures embeds, which Obsidian renders inline but which
# link the same way.
_WIKILINK_RE = re.compile(r"(!)?\[\[([^\[\]|#]+)(#[^\[\]|]+)?(?:\|([^\[\]]+))?\]\]")

# Fenced code blocks are stripped before parsing: a ```quantos-rules``` block
# cannot contain a link, and a markdown sample inside a note that documents
# link syntax must not register as a real edge.
_FENCE_RE = re.compile(r"^```.*?^```", re.DOTALL | re.MULTILINE)
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")


@dataclass(frozen=True)
class WikiLink:
    """One `[[...]]` occurrence."""
    target: str                      # the note stem, as written
    alias: Optional[str] = None      # display text after `|`
    heading: Optional[str] = None    # section after `#`, without the `#`
    is_embed: bool = False           # written as `![[...]]`

    @property
    def key(self) -> str:
        """Normalised lookup key — case-insensitive, whitespace-trimmed."""
        return normalise(self.target)

    def __str__(self) -> str:
        rendered = self.target
        if self.heading:
            rendered += f"#{self.heading}"
        if self.alias:
            rendered += f"|{self.alias}"
        return f"{'!' if self.is_embed else ''}[[{rendered}]]"


def normalise(name: str) -> str:
    """The key a link target and a note name are matched on."""
    return name.strip().casefold()


def strip_code(text: str) -> str:
    """Blank out fenced and inline code so their contents cannot form edges."""
    without_fences = _FENCE_RE.sub("", text)
    return _INLINE_CODE_RE.sub("", without_fences)


def parse_links(text: str) -> tuple[WikiLink, ...]:
    """Every wiki-link in `text`, in order, code blocks excluded.

    Duplicates are preserved — a page linking the same concept three times is
    a real signal about that page, and `NoteGraph` dedupes where it matters.
    """
    links = []
    for embed, target, heading, alias in _WIKILINK_RE.findall(strip_code(text)):
        if not target.strip():
            continue
        links.append(WikiLink(
            target=target.strip(),
            alias=alias.strip() or None if alias else None,
            heading=heading.lstrip("#").strip() or None if heading else None,
            is_embed=bool(embed),
        ))
    return tuple(links)


@dataclass
class NoteGraph:
    """Forward links and backlinks across an indexed vault.

    Built from notes that already carry their parsed links, so this class does
    no I/O and no parsing of its own — it is pure graph assembly and can be
    rebuilt cheaply whenever the index reloads.
    """

    # normalised note key -> the note's real name
    _names: dict[str, str] = field(default_factory=dict)
    # normalised source key -> set of normalised target keys
    _forward: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    # normalised target key -> set of normalised source keys
    _back: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))

    @classmethod
    def build(cls, notes: Iterable) -> "NoteGraph":
        """`notes` is any iterable of objects with `.name` and `.links`."""
        graph = cls()
        for note in notes:
            key = normalise(note.name)
            graph._names[key] = note.name
            for link in getattr(note, "links", ()):
                graph._forward[key].add(link.key)
                graph._back[link.key].add(key)
        return graph

    # ── queries ───────────────────────────────────────────────────────────

    def links_from(self, name: str) -> list[str]:
        """Names this note links TO. Unresolved targets are returned as
        written, since a link to a page that does not exist yet is a normal
        Obsidian state, not an error."""
        return sorted(self._names.get(k, k) for k in self._forward.get(normalise(name), set()))

    def links_to(self, name: str) -> list[str]:
        """Names that link TO this note — Obsidian's backlinks pane."""
        return sorted(self._names.get(k, k) for k in self._back.get(normalise(name), set()))

    def neighbours(self, name: str) -> list[str]:
        """Both directions, deduped. The unit retrieval expands over."""
        key = normalise(name)
        combined = self._forward.get(key, set()) | self._back.get(key, set())
        combined.discard(key)                       # a self-link is not a neighbour
        return sorted(self._names.get(k, k) for k in combined)

    def expand(self, names: Iterable[str], *, hops: int = 1) -> list[str]:
        """Breadth-first expansion from a seed set, `hops` deep.

        This is what turns a BM25 hit into context: land on the page that
        matched, then pull in what it is connected to. Only RESOLVED notes are
        returned — an unresolved target has no content to retrieve.
        """
        seen = {normalise(n) for n in names}
        frontier = set(seen)
        for _ in range(max(0, hops)):
            nxt: set[str] = set()
            for key in frontier:
                nxt |= self._forward.get(key, set()) | self._back.get(key, set())
            frontier = {k for k in nxt if k not in seen and k in self._names}
            if not frontier:
                break
            seen |= frontier
        return sorted(self._names[k] for k in seen if k in self._names)

    def unresolved_links(self) -> dict[str, list[str]]:
        """Targets that no note satisfies, mapped to the notes linking them.

        Reported by `vault lint` as pages worth writing — Obsidian's own
        reading of an unresolved link — not as a fault.
        """
        missing: dict[str, list[str]] = {}
        for target, sources in self._back.items():
            if target in self._names:
                continue
            missing[target] = sorted(self._names.get(s, s) for s in sources)
        return dict(sorted(missing.items()))

    def orphans(self) -> list[str]:
        """Notes nothing links to and which link nowhere — invisible in the
        graph view and unreachable by expansion."""
        return sorted(
            name for key, name in self._names.items()
            if not self._forward.get(key) and not self._back.get(key)
        )

    def __len__(self) -> int:
        return len(self._names)

    def __repr__(self) -> str:
        edges = sum(len(v) for v in self._forward.values())
        return f"<NoteGraph {len(self._names)} notes, {edges} links>"
