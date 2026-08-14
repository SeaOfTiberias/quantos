"""
QuantOS — Obsidian Vault: ingest (raw/)
────────────────────────────────────────
The first of Karpathy's three LLM-wiki operations. Takes a file you dropped
into `raw/_inbox/`, normalises it, stamps it with provenance, and files it
under `raw/<topic>/YYYY-MM-DD-slug.md`.

`raw/` is immutable after landing. Nothing in this package ever edits an
ingested source, and `vault lint` reports it if the checksum stops matching.
That is what makes a wiki page's citation worth anything: `[[source]]` points
at bytes that have not moved since the claim was written from them.

What "normalise" means
──────────────────────
Very little, deliberately. The body is preserved verbatim; only a frontmatter
header is added. Sources are evidence, and rewriting evidence on the way in
defeats the purpose. Concretely:

  • YAML frontmatter recording where it came from, when it landed, and a
    SHA-256 of the original bytes.
  • A `source/<topic>` tag so `raw/` is filterable in Obsidian's tag pane and
    in `VaultIndex.by_tag`.
  • Nothing else. No summarising, no reformatting, no truncation. The compile
    step is where interpretation happens, and it happens into `wiki/`.

Supported inputs are text-shaped: `.md`, `.txt`, and light HTML-to-text for
pages saved with Obsidian Web Clipper. A PDF is accepted only if its text has
already been extracted — this module does not carry a PDF dependency, and
silently ingesting an unreadable binary would poison the wiki with a source
nothing can quote.
"""

from __future__ import annotations

import hashlib
import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from core.vault.layers import VaultPaths

logger = logging.getLogger(__name__)

TEXT_SUFFIXES = {".md", ".markdown", ".txt", ".text"}
HTML_SUFFIXES = {".html", ".htm"}
INGESTIBLE_SUFFIXES = TEXT_SUFFIXES | HTML_SUFFIXES

_SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b.*?</\1>", re.DOTALL | re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_BLANKS_RE = re.compile(r"\n{3,}")
_SLUG_STRIP_RE = re.compile(r"[^a-z0-9]+")
# Apostrophes are DROPPED, not turned into separators, so "Minervini's" slugs
# to "minervinis". Otherwise a curly apostrophe (which unicode folding deletes)
# and a straight one (which would become a hyphen) produce two different pages
# for the same article.
_SLUG_DROP_RE = re.compile(r"['‘’ʼ]")
_FRONTMATTER_RE = re.compile(r"\A---\r?\n.*?\r?\n---\r?\n?", re.DOTALL)


class IngestError(ValueError):
    """The file could not be ingested."""


@dataclass(frozen=True)
class IngestResult:
    """One ingested source."""
    source_path: Path          # where it came from
    vault_path: Path           # where it landed under raw/
    topic: str
    slug: str
    checksum: str              # SHA-256 of the ORIGINAL bytes, not the written file
    bytes_in: int
    skipped: bool = False      # already present with an identical checksum
    reason: str = ""

    @property
    def note_name(self) -> str:
        return self.vault_path.stem


def slugify(text: str, *, max_length: int = 60) -> str:
    """Filesystem- and wiki-link-safe slug.

    Unicode is folded to ASCII first so a source titled "Minervini's 'Trend
    Template'" and one titled "Minervini's ‘Trend Template’" — different
    apostrophes, same article — do not become two separate pages.
    """
    dropped = _SLUG_DROP_RE.sub("", text)
    folded = unicodedata.normalize("NFKD", dropped).encode("ascii", "ignore").decode("ascii")
    slug = _SLUG_STRIP_RE.sub("-", folded.lower()).strip("-")
    if len(slug) > max_length:
        slug = slug[:max_length].rstrip("-")
    return slug or "untitled"


def checksum_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def extract_body(document: str) -> str:
    """The part of a note below its YAML frontmatter, stripped.

    THE single definition of "the body" for checksum purposes. Both `_render`
    (writing the hash) and core/vault/lint.py (re-checking it) call this. They
    previously each stripped the frontmatter their own way and disagreed by two
    blank lines, so every freshly-ingested source lint-ed as modified — a
    false alarm on the one check that is supposed to prove a source is intact.
    """
    return _FRONTMATTER_RE.sub("", document).strip()


def body_checksum(document: str) -> str:
    """SHA-256 of a note's body, frontmatter excluded."""
    return checksum_bytes(extract_body(document).encode("utf-8"))


def html_to_text(html: str) -> str:
    """Crude tag stripping for clipper output.

    Deliberately not a real HTML parser: this runs on pages a human chose to
    save, and losing some structure is an acceptable trade for having no
    dependency. If a source matters enough that its markup matters, save it as
    markdown instead.
    """
    without_code = _SCRIPT_STYLE_RE.sub("", html)
    text = _TAG_RE.sub("", without_code)
    for entity, char in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"),
                         ("&gt;", ">"), ("&quot;", '"'), ("&#39;", "'")):
        text = text.replace(entity, char)
    return _BLANKS_RE.sub("\n\n", text).strip()


def read_source(path: Path) -> str:
    """Extract text from a supported source file. Raises `IngestError`."""
    suffix = path.suffix.lower()
    if suffix not in INGESTIBLE_SUFFIXES:
        raise IngestError(
            f"{path.name}: {suffix or 'no extension'} is not ingestible. "
            f"Supported: {', '.join(sorted(INGESTIBLE_SUFFIXES))}. "
            f"For a PDF, extract the text first — a source nothing can quote "
            f"is worse than no source."
        )
    try:
        raw = path.read_bytes()
    except OSError as e:
        raise IngestError(f"could not read {path}: {e}") from e

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("utf-8", errors="replace")
        logger.warning("Ingest: %s is not valid UTF-8 — undecodable bytes replaced", path.name)

    # Normalise line endings to \n. Bytes are read directly (rather than via
    # text mode) so the checksum is of the true file, but that preserves CRLF —
    # and Path.write_text then translates every \n to \r\n, turning an existing
    # \r\n into \r\r\n, which reads back as TWO newlines. A Windows-authored
    # source would gain a blank line between every line on ingest, and its body
    # checksum would never match on the way back in.
    #
    # This is the one normalisation applied to a source. It changes the
    # encoding of line breaks, not the content: no reflowing, no reformatting.
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    return html_to_text(text) if suffix in HTML_SUFFIXES else text


def ingest_file(
    source: Path,
    vault: VaultPaths,
    *,
    topic: str = "misc",
    title: Optional[str] = None,
    origin: Optional[str] = None,
    on_date: Optional[date] = None,
    move: bool = False,
) -> IngestResult:
    """File one source into `raw/<topic>/YYYY-MM-DD-slug.md`.

    Re-ingesting a byte-identical source is a no-op — it returns
    `skipped=True` rather than writing a second dated copy. Dragging the same
    article in twice is a normal accident, and duplicate sources would double
    its apparent weight in both BM25 and any compile step reading `raw/`.

    A source with the SAME name but DIFFERENT bytes is a genuine second
    version and lands beside the first with a `-2` suffix; `raw/` is
    append-only, so the earlier one is never overwritten.
    """
    source = Path(source)
    if not source.is_file():
        raise IngestError(f"no such file: {source}")

    text = read_source(source)
    checksum = checksum_bytes(source.read_bytes())
    stamp = (on_date or datetime.now(timezone.utc).date()).isoformat()
    display_title = title or _derive_title(text, source)
    slug = slugify(display_title)

    topic_dir = vault.raw / slugify(topic, max_length=40)
    topic_dir.mkdir(parents=True, exist_ok=True)

    target = topic_dir / f"{stamp}-{slug}.md"
    existing = _find_by_checksum(topic_dir, checksum)
    if existing is not None:
        return IngestResult(
            source_path=source, vault_path=existing, topic=topic, slug=slug,
            checksum=checksum, bytes_in=len(text), skipped=True,
            reason=f"identical content already ingested as {existing.name}",
        )

    counter = 2
    while target.exists():
        target = topic_dir / f"{stamp}-{slug}-{counter}.md"
        counter += 1

    target.write_text(
        _render(text, title=display_title, topic=topic, origin=origin or str(source),
                stamp=stamp, checksum=checksum),
        encoding="utf-8",
    )

    if move:
        try:
            source.unlink()
        except OSError as e:
            logger.warning("Ingest: filed %s but could not remove the original (%s)",
                           source.name, e)

    logger.info("Ingest: %s -> %s (%d chars, sha256 %s)",
                source.name, target.relative_to(vault.root), len(text), checksum[:12])
    return IngestResult(source_path=source, vault_path=target, topic=topic, slug=slug,
                        checksum=checksum, bytes_in=len(text))


def ingest_inbox(vault: VaultPaths, *, topic: str = "misc",
                 move: bool = True) -> list[IngestResult]:
    """Ingest everything sitting in `raw/_inbox/`.

    This is the drop-zone workflow: drag files in, run `vault ingest`. Files
    are MOVED out of the inbox by default so a second run does not reprocess
    them — and even if one is left behind, the checksum check makes the repeat
    a no-op.

    A file that cannot be ingested is left in the inbox with the reason
    logged, so the inbox doubles as the error queue.
    """
    vault.ensure()
    results: list[IngestResult] = []
    for path in sorted(vault.inbox.iterdir()):
        if path.is_dir() or path.name.startswith("."):
            continue
        try:
            results.append(ingest_file(path, vault, topic=topic, move=move))
        except IngestError as e:
            logger.error("Ingest: leaving %s in the inbox — %s", path.name, e)
            results.append(IngestResult(
                source_path=path, vault_path=path, topic=topic, slug="",
                checksum="", bytes_in=0, skipped=True, reason=str(e),
            ))
    return results


def _derive_title(text: str, source: Path) -> str:
    """First markdown H1, else the first non-empty line, else the filename."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
        if stripped:
            return stripped[:100]
    return source.stem


def _drop_leading_h1(text: str, title: str) -> str:
    """Remove the source's own leading H1 when it is the title we lifted.

    `_render` writes `# {title}` as the note's heading. Without this, a source
    that begins with its own H1 — which most markdown does — renders the same
    heading twice, once from us and once from the file. Only the FIRST heading
    is removed, and only when it matches, so subheadings and any later `#` in
    the body survive untouched.
    """
    lines = text.splitlines()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("# ") and stripped[2:].strip() == title:
            return "\n".join(lines[i + 1:]).strip()
        return text.strip()
    return text.strip()


def _find_by_checksum(directory: Path, checksum: str) -> Optional[Path]:
    """Locate an already-ingested source with this checksum, by reading the
    `checksum:` line out of each file's frontmatter."""
    needle = f"checksum: {checksum}"
    for path in directory.glob("*.md"):
        try:
            head = path.read_text(encoding="utf-8")[:600]
        except OSError:
            continue
        if needle in head:
            return path
    return None


def _render(text: str, *, title: str, topic: str, origin: str,
            stamp: str, checksum: str) -> str:
    """Frontmatter header plus the body, verbatim.

    Two hashes, because they answer different questions. `checksum` is of the
    ORIGINAL source bytes and identifies the source — it is what makes
    re-ingesting the same article a no-op. `body_checksum` is of the rendered
    body and is what `vault lint` re-computes to detect that someone edited an
    immutable source after wiki pages had already cited it.

    `quantos.immutable: true` is documentation for a human reading the file in
    Obsidian, not access control — nothing here can prevent an edit. Lint is
    what actually notices.
    """
    body = (
        f"# {title}\n\n"
        "> [!info] Ingested source\n"
        f"> Filed {stamp} from `{origin}`. Do not edit — wiki pages cite this\n"
        "> file's contents, and `vault lint` re-hashes it to check.\n\n"
        f"{_drop_leading_h1(text, title)}\n"
    )

    def _document(body_hash: str) -> str:
        return (
            "---\n"
            f"title: {_yaml_scalar(title)}\n"
            f"ingested: {stamp}\n"
            f"origin: {_yaml_scalar(origin)}\n"
            f"checksum: {checksum}\n"
            f"body_checksum: {body_hash}\n"
            "tags:\n"
            f"  - source/{slugify(topic, max_length=40)}\n"
            "quantos:\n"
            "  layer: raw\n"
            "  immutable: true\n"
            "---\n\n"
            f"{body}"
        )

    # Hash the ASSEMBLED document through the same `extract_body` that lint
    # will use, rather than hashing `body` directly. The two differed by two
    # blank lines when each stripped the frontmatter its own way, which made
    # every freshly-ingested source lint as modified — a false alarm on the
    # one check meant to prove a source is intact.
    #
    # The placeholder pass is safe because `extract_body` discards the
    # frontmatter entirely, so swapping the hash line cannot change what is
    # hashed.
    return _document(body_checksum(_document("0" * 64)))


def _yaml_scalar(value: str) -> str:
    """Emit a value as a SINGLE-quoted YAML scalar.

    Single quotes, not double, because origins are frequently Windows paths:
    inside a double-quoted YAML scalar `D:\\Exodus_14_14\\...` is a string of
    escape sequences and `\\E` is not a legal one, so the whole frontmatter
    fails to parse and the note silently loses its tags. YAML's single-quoted
    style processes no escapes at all; the only special case is a literal
    single quote, written by doubling it.
    """
    cleaned = value.replace("\n", " ").strip()
    return "'" + cleaned.replace("'", "''") + "'"
