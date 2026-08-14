"""
QuantOS — Obsidian Vault: compile (raw/ → wiki/)
─────────────────────────────────────────────────
The second of Karpathy's three LLM-wiki operations, and the one that makes the
knowledge base compound. Instead of re-reading `raw/` on every question, an
agent reads it ONCE and writes durable entity pages into `wiki/` — one page per
concept, interlinked with `[[wiki-links]]`, each claim citing the source it
came from.

The difference from RAG is the whole point. RAG re-derives an answer from
fragments every time and accumulates nothing. A compiled wiki gets richer with
every source added: the second article about volatility contraction UPDATES
the existing page rather than sitting beside it as another chunk to retrieve.

What this module does and does not decide
─────────────────────────────────────────
It writes to `wiki/` only. It cannot write to `brain/` and it cannot write to
`raw/`. That is enforced in `_safe_target()`, not merely intended — see
core/vault/layers.py for why an agent that could author `brain/` would be an
agent authoring the conditions that release real orders.

Compiled pages are also stripped of ```quantos-rules``` blocks before they are
written. A model asked to summarise Minervini will quite reasonably produce
one, and it must not silently become inert-looking-but-present in the vault.
`vault lint` reports any that survive.

Cost and idempotency
────────────────────
Compiling calls Claude once per source. Sources already recorded in
`wiki/log.md` are skipped unless `force=True`, so re-running after adding one
article costs one call, not N. The log is append-only and is the record of
what the wiki was built from.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from core.prompts import loader as prompts
from core.vault.ingest import slugify
from core.vault.layers import Layer, VaultPaths
from core.vault.models import StrategyNote

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 4000

SYSTEM_PROMPT = "vault_compile_system"
USER_PROMPT = "vault_compile_user"

# How much of a source to send. Long enough for a substantial article, short
# enough that one enormous paste cannot dominate a compile run's cost.
_SOURCE_CHARS = 24_000

# ```quantos-rules``` blocks are stripped from compiled output — see the module
# docstring. Matches the parser's fence, not a general code fence.
_RULE_BLOCK_RE = re.compile(r"^```quantos-rules[ \t]*\r?\n.*?^```[ \t]*\r?\n?",
                            re.DOTALL | re.MULTILINE)

# The model returns pages delimited by this marker so several concepts can come
# out of one source in a single call.
_PAGE_SPLIT_RE = re.compile(r"^===PAGE:\s*(.+?)\s*===\s*$", re.MULTILINE)


class CompileError(RuntimeError):
    """The compile step could not run."""


@dataclass
class CompileResult:
    """What one compile run produced."""
    pages_written: list[Path] = field(default_factory=list)
    sources_read: list[str] = field(default_factory=list)
    sources_skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def summary(self) -> str:
        return (f"{len(self.pages_written)} page(s) written from "
                f"{len(self.sources_read)} source(s); "
                f"{len(self.sources_skipped)} already compiled, "
                f"{len(self.errors)} error(s)")


def compile_vault(
    vault: VaultPaths,
    raw_notes: Iterable[StrategyNote],
    *,
    existing_pages: Optional[Iterable[StrategyNote]] = None,
    client=None,
    force: bool = False,
    limit: Optional[int] = None,
) -> CompileResult:
    """Compile `raw/` sources into `wiki/` entity pages.

    `raw_notes` should be `index.by_layer(Layer.RAW)`. `existing_pages` gives
    the model the current wiki's page names so it links to real pages and
    updates rather than duplicates.
    """
    vault.ensure()
    result = CompileResult()

    if client is None:
        client = _default_client()
    if client is None:
        raise CompileError(
            "No Anthropic client available — set ANTHROPIC_API_KEY and install "
            "the anthropic SDK. Compiling is the one vault operation that needs "
            "a model; ingest, query and lint all work without one."
        )

    already = _compiled_sources(vault)
    page_names = sorted(n.name for n in (existing_pages or []))

    count = 0
    for note in raw_notes:
        if note.layer is not Layer.RAW:
            # Defensive: compiling a brain/ note would feed hand-written canon
            # back through a model and risk it returning as a wiki page.
            continue
        if not force and note.name in already:
            result.sources_skipped.append(note.name)
            continue
        if limit is not None and count >= limit:
            result.sources_skipped.append(note.name)
            continue

        try:
            pages = _compile_one(note, page_names, client)
        except Exception as e:
            logger.error("Compile: %s failed — %s", note.name, e)
            result.errors.append(f"{note.name}: {e}")
            continue

        for title, body in pages:
            try:
                path = _write_page(vault, title, body, source_name=note.name)
            except CompileError as e:
                result.errors.append(str(e))
                continue
            result.pages_written.append(path)
            page_names.append(path.stem)

        result.sources_read.append(note.name)
        count += 1
        _append_log(vault, note.name, [p.stem for p in result.pages_written[-len(pages):]])

    logger.info("Compile: %s", result.summary())
    return result


def _compile_one(note: StrategyNote, existing_pages: list[str],
                 client) -> list[tuple[str, str]]:
    """One model call → a list of (page title, markdown body)."""
    system = prompts.load(SYSTEM_PROMPT)
    user = prompts.render(
        USER_PROMPT,
        source_name=note.name,
        source_title=note.title,
        existing_pages="\n".join(f"- {p}" for p in existing_pages) or "(the wiki is empty)",
        source_text=note.body[:_SOURCE_CHARS],
    )
    response = client.messages.create(
        model=MODEL, max_tokens=MAX_TOKENS, system=system,
        messages=[{"role": "user", "content": user}],
    )
    text = "\n".join(
        block.text for block in response.content
        if getattr(block, "type", "") == "text"
    ).strip()
    return _split_pages(text)


def _split_pages(text: str) -> list[tuple[str, str]]:
    """Parse the `===PAGE: Title===` delimited response.

    A response with no marker at all is treated as a single untitled page
    rather than discarded — the content is still worth keeping, and lint will
    flag a page that ends up orphaned.
    """
    matches = list(_PAGE_SPLIT_RE.finditer(text))
    if not matches:
        return [("Untitled Concept", text)] if text else []

    pages: list[tuple[str, str]] = []
    for i, match in enumerate(matches):
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if body:
            pages.append((match.group(1).strip(), body))
    return pages


def _write_page(vault: VaultPaths, title: str, body: str, *, source_name: str) -> Path:
    """Write one entity page into `wiki/concepts/`, rules stripped."""
    cleaned, removed = _strip_rule_blocks(body)
    if removed:
        logger.warning(
            "Compile: stripped %d quantos-rules block(s) from the generated page "
            "%r. Compiled pages are context, never gates — a rule that should "
            "execute belongs in brain/, written by you.", removed, title)

    slug = slugify(title)
    target = _safe_target(vault, vault.wiki_concepts / f"{slug}.md")
    stamp = datetime.now(timezone.utc).date().isoformat()

    header = (
        "---\n"
        f"title: {title}\n"
        f"compiled: {stamp}\n"
        "tags:\n"
        "  - wiki/concept\n"
        "quantos:\n"
        "  layer: wiki\n"
        "  generated: true\n"
        f"  compiled_from: {source_name}\n"
        "---\n\n"
        f"# {title}\n\n"
        "> [!abstract] Compiled page\n"
        f"> Written by an agent from `[[{source_name}]]` on {stamp}. Context and\n"
        "> retrieval only — rules in this layer never execute. Edit freely; a\n"
        "> recompile may overwrite it.\n\n"
    )
    target.write_text(header + cleaned.strip() + "\n", encoding="utf-8")
    return target


def _safe_target(vault: VaultPaths, candidate: Path) -> Path:
    """Refuse to write anywhere but `wiki/`.

    Belt and braces against a model-supplied title containing path separators
    or `..`. The layer boundary is a safety property (core/vault/layers.py),
    so it is checked on the resolved path rather than trusted from the input.
    """
    resolved = candidate.resolve()
    wiki_root = vault.wiki.resolve()
    if not resolved.is_relative_to(wiki_root):
        raise CompileError(
            f"refusing to write {resolved} — the compile step may only write "
            f"inside {wiki_root}"
        )
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


def _strip_rule_blocks(body: str) -> tuple[str, int]:
    matches = len(_RULE_BLOCK_RE.findall(body))
    return _RULE_BLOCK_RE.sub("", body), matches


def _compiled_sources(vault: VaultPaths) -> set[str]:
    """Source note names already recorded in `wiki/log.md`."""
    if not vault.log_page.is_file():
        return set()
    names: set[str] = set()
    for line in vault.log_page.read_text(encoding="utf-8").splitlines():
        if "compiled" in line and "[[" in line:
            for target in re.findall(r"\[\[([^\]|#]+)", line):
                names.add(target.strip())
    return names


def _append_log(vault: VaultPaths, source_name: str, page_names: list[str]) -> None:
    """Append to `wiki/log.md` — the append-only record of what the wiki was
    built from, and what `_compiled_sources` reads to stay idempotent."""
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    pages = ", ".join(f"[[{p}]]" for p in page_names) or "(no pages)"
    entry = f"- {stamp} — compiled [[{source_name}]] -> {pages}\n"

    if not vault.log_page.is_file():
        vault.log_page.parent.mkdir(parents=True, exist_ok=True)
        vault.log_page.write_text(
            "---\ntags:\n  - wiki/log\nquantos:\n  layer: wiki\n---\n\n"
            "# Compile log\n\n"
            "Append-only. Every line records one source being compiled into wiki\n"
            "pages. `compile` reads this to skip sources it has already seen, so\n"
            "editing it by hand will cause re-compilation.\n\n",
            encoding="utf-8")

    with vault.log_page.open("a", encoding="utf-8") as handle:
        handle.write(entry)


def write_index(vault: VaultPaths, notes: Iterable[StrategyNote]) -> Path:
    """Regenerate `wiki/index.md` — the global table of contents.

    Deterministic, no model involved: it is a listing, and having a model
    write a listing invites it to invent entries. Grouped by layer so the
    executable/non-executable split is visible on the page a reader opens
    first.
    """
    by_layer: dict[Layer, list[StrategyNote]] = {}
    for note in notes:
        by_layer.setdefault(note.layer or Layer.LOOSE, []).append(note)

    lines = [
        "---", "tags:", "  - wiki/index", "quantos:", "  layer: wiki",
        "  generated: true", "---", "",
        "# Vault index", "",
        f"Regenerated {datetime.now(timezone.utc).date().isoformat()} by "
        "`python scripts/vault.py index`. Do not hand-edit.", "",
    ]

    for layer in (Layer.BRAIN, Layer.WIKI, Layer.RAW, Layer.LOOSE):
        group = sorted(by_layer.get(layer, []), key=lambda n: n.name)
        if not group:
            continue
        executable = "executable" if layer.is_executable else "not executable"
        lines += [f"## {layer.value}/ ({len(group)} — {executable})", "",
                  f"_{layer.description}_", ""]
        for note in group:
            rules = f" — {len(note.rules)} rules" if note.rules else ""
            lines.append(f"- [[{note.name}]] — {note.title}{rules}")
        lines.append("")

    vault.index_page.parent.mkdir(parents=True, exist_ok=True)
    vault.index_page.write_text("\n".join(lines), encoding="utf-8")
    return vault.index_page


def _default_client():
    if not os.getenv("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic
    except ImportError:
        return None
    return anthropic.Anthropic()
