#!/usr/bin/env python
"""
QuantOS — vault CLI
────────────────────
Karpathy's three LLM-wiki operations, plus the housekeeping they imply.

    # 1. drop files into obsidian_vault/QuantOS/raw/_inbox/, then:
    python scripts/vault.py ingest --topic minervini

    # 2. compile raw sources into interlinked wiki pages.
    #    Preferred: ask your coding agent to "compile the vault" -- it uses
    #    .claude/skills/vault-compile/SKILL.md and file tools, needs no API key,
    #    and can read the existing pages before linking to them.
    #    This command is the UNATTENDED fallback (needs ANTHROPIC_API_KEY):
    python scripts/vault.py compile --dry-run
    python scripts/vault.py compile

    # 3. ask the vault a question (BM25 + graph expansion, no model needed)
    python scripts/vault.py query "what makes a base tight enough to buy"

    # housekeeping
    python scripts/vault.py lint          # integrity, links, safety
    python scripts/vault.py index         # regenerate wiki/index.md
    python scripts/vault.py status        # what is where
    python scripts/vault.py graph VCP     # links in and out of a note

`ingest`, `query`, `lint`, `index`, `status` and `graph` need no API key and no
network. Only `compile` calls a model, and even that is better run through the
agent skill than through this command.

To audit a SYMBOL against the strategy rules in brain/, use
scripts/audit_symbol.py. This script manages the vault; that one uses it.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.vault.compile import (  # noqa: E402
    CompileError, compile_vault, write_index,
)
from core.vault.index import VaultIndex, VaultNotFoundError  # noqa: E402
from core.vault.ingest import IngestError, ingest_file, ingest_inbox  # noqa: E402
from core.vault.layers import Layer, VaultPaths  # noqa: E402
from core.vault.lint import Severity, lint_vault  # noqa: E402

logger = logging.getLogger("quantos.vault")

_AGENT_COMPILE_HINT = """\
Compiling is the one vault operation that needs a model, and there are two ways
to run it:

  1. In your coding agent (recommended).  Ask Claude Code to "compile the
     vault" -- it loads .claude/skills/vault-compile/SKILL.md and does the work
     with file tools. It reads every existing wiki page before linking a new
     concept to them, then runs `vault lint` and fixes what it finds. No API
     key, no separate bill.

  2. Unattended, via this command.  Needs ANTHROPIC_API_KEY and the anthropic
     SDK. Use this only for a scheduled compile where no agent is present -- it
     sees existing pages by NAME only, so its linking is weaker.

Everything else (ingest, query, lint, index, status, graph) needs no key."""


def _paths(args) -> VaultPaths:
    from core.vault.index import VAULT_DIR
    return VaultPaths(Path(args.vault) if args.vault else VAULT_DIR)


def _load(args) -> VaultIndex:
    return VaultIndex.load(Path(args.vault) if args.vault else None)


# ── commands ──────────────────────────────────────────────────────────────

def cmd_init(args) -> int:
    paths = _paths(args).ensure()
    print(f"Vault ready at {paths.root}")
    for layer in (Layer.BRAIN, Layer.RAW, Layer.WIKI):
        directory = paths.for_layer(layer)
        print(f"  {layer.value + '/':8} {layer.description}")
        print(f"           {directory}")
    print(f"\n  Drop files to ingest into: {paths.inbox}")
    return 0


def cmd_ingest(args) -> int:
    paths = _paths(args).ensure()

    if args.file:
        try:
            results = [ingest_file(Path(args.file), paths, topic=args.topic,
                                   title=args.title, move=args.move)]
        except IngestError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
    else:
        results = ingest_inbox(paths, topic=args.topic, move=args.move)

    if not results:
        print(f"Nothing to ingest. Drop files into {paths.inbox}")
        return 0

    filed = [r for r in results if not r.skipped]
    skipped = [r for r in results if r.skipped]

    for result in filed:
        rel = result.vault_path.relative_to(paths.root)
        print(f"  filed    {result.source_path.name}")
        print(f"           -> {rel}  ({result.bytes_in:,} chars, "
              f"sha256 {result.checksum[:12]})")
    for result in skipped:
        print(f"  skipped  {result.source_path.name}: {result.reason}")

    print(f"\n{len(filed)} filed, {len(skipped)} skipped.")
    if filed:
        print("Next: ask your coding agent to \"compile the vault\", or run "
              "`python scripts/vault.py compile` for an unattended pass.")
    return 0


def cmd_compile(args) -> int:
    index = _load(args)
    raw_notes = index.by_layer(Layer.RAW)
    if not raw_notes:
        print(f"No sources in {index.paths.raw}. Ingest something first.")
        return 0

    if args.dry_run:
        already = {n.name for n in index.by_layer(Layer.WIKI)}
        print(f"Would compile from {len(raw_notes)} raw source(s):")
        for note in raw_notes[: args.limit or len(raw_notes)]:
            print(f"  {note.name}  ({len(note.body):,} chars) — {note.title}")
        print(f"\nWiki currently holds {len(already)} page(s). "
              f"No model call made (--dry-run).")
        return 0

    try:
        result = compile_vault(
            index.paths, raw_notes,
            existing_pages=index.by_layer(Layer.WIKI),
            force=args.force, limit=args.limit,
        )
    except CompileError as e:
        # No API key is the expected case, not an error worth a stack trace:
        # the better path is the agent already sitting in the terminal, which
        # can read the existing pages before linking to them. See
        # .claude/skills/vault-compile/SKILL.md.
        print(f"error: {e}\n", file=sys.stderr)
        print(_AGENT_COMPILE_HINT, file=sys.stderr)
        return 2

    for path in result.pages_written:
        print(f"  wrote    {path.relative_to(index.paths.root)}")
    for name in result.sources_skipped:
        print(f"  skipped  {name} (already compiled — use --force to redo)")
    for error in result.errors:
        print(f"  ERROR    {error}", file=sys.stderr)

    print(f"\n{result.summary()}")
    if result.pages_written:
        write_index(index.paths, VaultIndex.load(index.vault_dir).notes)
        print(f"Regenerated {index.paths.index_page.name}")
    return 0 if result.ok else 1


def cmd_query(args) -> int:
    index = _load(args)
    hits = index.search(args.question, tags=args.tag or None, limit=args.limit)
    if not hits:
        print(f"No notes matched {args.question!r}")
        return 1

    print(f"\n{len(hits)} match(es) for {args.question!r}:\n")
    for hit in hits:
        layer = hit.note.layer.value if hit.note.layer else "?"
        print(f"  {hit.score:6.2f}  [{layer}] {hit.note.name}")
        print(f"          {hit.note.title}")
        print(f"          matched: {', '.join(hit.matched_terms)}")
        if args.hops:
            related = index.related(hit.note.name, hops=args.hops)
            if related:
                print(f"          links to: {', '.join(n.name for n in related[:6])}")
        if args.excerpt:
            for line in _excerpt(hit.note.body, hit.matched_terms).splitlines():
                print(f"          | {line}")
        print()
    return 0


def cmd_lint(args) -> int:
    report = lint_vault(_load(args))
    order = (Severity.ERROR, Severity.WARNING, Severity.INFO)
    for severity in order:
        group = [f for f in report.findings if f.severity is severity]
        if not group or (severity is Severity.INFO and not args.verbose):
            continue
        print()
        for finding in group:
            print(f"  {finding}")

    print(f"\n{report.summary()}")
    if not args.verbose and report.infos:
        print(f"({len(report.infos)} informational finding(s) hidden — use -v)")
    return 0 if report.ok else 1


def cmd_index(args) -> int:
    index = _load(args)
    path = write_index(index.paths, index.notes)
    print(f"Wrote {path} ({len(index.notes)} notes)")
    return 0


def cmd_status(args) -> int:
    index = _load(args)
    print(f"\nVault: {index.vault_dir}")
    print(f"{len(index.notes)} notes, {len(index.graph)} in the link graph\n")

    for layer in (Layer.BRAIN, Layer.RAW, Layer.WIKI, Layer.LOOSE):
        group = index.by_layer(layer)
        if not group and layer is Layer.LOOSE:
            continue
        flag = "executable" if layer.is_executable else "not executable"
        print(f"  {layer.value + '/':8} {len(group):4} notes   ({flag})")
        for note in sorted(group, key=lambda n: n.name)[: args.limit]:
            rules = f"  {len(note.rules)} rules" if note.rules else ""
            marker = " !" if note.has_unexecutable_rules else ""
            print(f"             {note.name}{rules}{marker}")
        if len(group) > args.limit:
            print(f"             … and {len(group) - args.limit} more")
        print()

    auditable = index.auditable_notes
    print(f"  {len(auditable)} note(s) can gate a trade: "
          f"{', '.join(n.strategy_id for n in auditable) or '(none)'}")

    unresolved = index.graph.unresolved_links()
    if unresolved:
        print(f"  {len(unresolved)} unresolved link(s) — pages worth writing")
    return 0


def cmd_graph(args) -> int:
    index = _load(args)
    if not index.has(args.note):
        print(f"error: no note named {args.note!r}", file=sys.stderr)
        return 2
    note = index.get(args.note)

    print(f"\n{note.name}  [{note.layer.value if note.layer else '?'}]")
    print(f"  {note.title}\n")
    outgoing = index.graph.links_from(note.name)
    incoming = index.graph.links_to(note.name)
    print(f"  links out ({len(outgoing)}): {', '.join(outgoing) or '(none)'}")
    print(f"  links in  ({len(incoming)}): {', '.join(incoming) or '(none)'}")
    if args.hops > 1:
        reachable = index.graph.expand([note.name], hops=args.hops)
        print(f"\n  within {args.hops} hops ({len(reachable)}): {', '.join(reachable)}")
    return 0


def _excerpt(body: str, terms, width: int = 240) -> str:
    """The first passage containing a matched term."""
    lowered = body.lower()
    for term in terms:
        position = lowered.find(term)
        if position == -1:
            continue
        start = max(0, position - width // 3)
        return "…" + " ".join(body[start:start + width].split()) + "…"
    return " ".join(body[:width].split()) + "…"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Manage the QuantOS Obsidian vault (Karpathy LLM-wiki pattern).")
    parser.add_argument("--vault", help="Vault directory (default: $QUANTOS_VAULT_DIR "
                                        "or obsidian_vault/QuantOS)")
    parser.add_argument("-v", "--verbose", action="store_true")

    # -v is accepted both before and after the subcommand. `vault lint -v` is
    # the form anyone actually types, and argparse only honours a global flag
    # in the leading position unless every subparser inherits it.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("-v", "--verbose", action="store_true")

    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", parents=[common], help="Create the brain/ raw/ wiki/ layout")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("ingest", parents=[common], help="File sources from raw/_inbox into raw/")
    p.add_argument("file", nargs="?", help="A single file (default: everything in the inbox)")
    p.add_argument("--topic", default="misc", help="Subfolder under raw/ (default: misc)")
    p.add_argument("--title", help="Override the derived title")
    p.add_argument("--no-move", dest="move", action="store_false",
                   help="Leave originals in the inbox after filing")
    p.set_defaults(func=cmd_ingest, move=True)

    p = sub.add_parser("compile", parents=[common],
                       help="Unattended compile of raw/ -> wiki/ (needs ANTHROPIC_API_KEY; "
                            "prefer asking your coding agent to compile the vault)")
    p.add_argument("--force", action="store_true", help="Recompile already-compiled sources")
    p.add_argument("--limit", type=int, help="Compile at most N sources this run")
    p.add_argument("--dry-run", action="store_true", help="Show what would compile, call nothing")
    p.set_defaults(func=cmd_compile)

    p = sub.add_parser("query", parents=[common], help="Search the vault (BM25 + graph expansion)")
    p.add_argument("question")
    p.add_argument("--tag", action="append", default=[], help="Restrict to a tag. Repeatable.")
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--hops", type=int, default=1, help="Graph expansion depth (0 to disable)")
    p.add_argument("--excerpt", action="store_true", help="Show a matching passage")
    p.set_defaults(func=cmd_query)

    p = sub.add_parser("lint", parents=[common], help="Check integrity, links and layer safety")
    p.set_defaults(func=cmd_lint)

    p = sub.add_parser("index", parents=[common], help="Regenerate wiki/index.md")
    p.set_defaults(func=cmd_index)

    p = sub.add_parser("status", parents=[common], help="What is in the vault, by layer")
    p.add_argument("--limit", type=int, default=8, help="Notes listed per layer")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("graph", parents=[common], help="Show a note's links in and out")
    p.add_argument("note")
    p.add_argument("--hops", type=int, default=1)
    p.set_defaults(func=cmd_graph)


    # Windows consoles default to cp1252, which cannot encode the box-drawing
    # characters, em dashes and ellipses that appear in perfectly ordinary
    # notes. Without this, printing an excerpt from a note containing an ASCII
    # chart raises UnicodeEncodeError and takes the whole command down.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):      # already wrapped, or a pipe
            pass

    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    try:
        return args.func(args)
    except VaultNotFoundError as e:
        print(f"error: {e}\n\nRun `python scripts/vault.py init` to create it.",
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
