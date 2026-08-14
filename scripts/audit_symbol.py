#!/usr/bin/env python
"""
QuantOS — audit a symbol against the Obsidian vault's strategy notes
─────────────────────────────────────────────────────────────────────
The interactive face of core/vault. Fetches daily bars from the configured
broker and evaluates them against one or more strategy notes, printing every
rule with its live numbers substituted.

    # audit against every note that has a rule block
    python scripts/audit_symbol.py TVSMOTOR

    # against specific notes (filename stem or quantos.id both work)
    python scripts/audit_symbol.py TVSMOTOR --note minervini_vcp --note weinstein_stage2

    # ask the vault a question instead of auditing (the RAG half)
    python scripts/audit_symbol.py --search "volume dry up before a pivot"

    # list what the vault knows
    python scripts/audit_symbol.py --list

    # add Claude's plain-English reading of an already-decided verdict
    python scripts/audit_symbol.py TVSMOTOR --narrate

`--rs-rating` supplies the cross-sectional strength percentile that
Minervini's and Weinstein's notes both ask for. Without it those rules are
unevaluable and the audit reports INSUFFICIENT_DATA — deliberately, since it
cannot be derived from one symbol's own bars. `--universe` computes one
properly by ranking a whole universe file first, which is slower but real.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml  # noqa: E402

from core.brokers.base import OHLCV  # noqa: E402
from core.vault.auditor import StrategyAuditor  # noqa: E402
from core.vault.gates import rs_rating_from_rank  # noqa: E402
from core.vault.index import VaultIndex, VaultNotFoundError  # noqa: E402
from core.vault.models import AuditReport, Verdict  # noqa: E402
from core.vault.narrator import narrate  # noqa: E402

logger = logging.getLogger("quantos.vault.audit")

# Enough history to warm up the longest window any note uses (SMA 200 needs
# 200, the 52-week high needs 252) with room to spare for holidays and the
# [n]-bar lag terms.
_HISTORY_DAYS = 600

_MARK = {
    True: "PASS",
    False: "FAIL",
    None: "  ? ",
}


def _load_broker():
    """Build the configured broker adapter, mirroring how the agent does it.

    Via `get_broker`, not a local broker map. The first cut of this function
    hand-rolled the dispatch and passed `config["credentials"]` to the
    adapter, but every adapter takes the WHOLE config and reads
    `self.config["credentials"]` itself — so it died with `KeyError:
    'credentials'` against a perfectly valid config. Deferring to the one
    factory also keeps this script from drifting out of step with
    core/brokers/__init__.py's supported list.
    """
    config_path = Path(__file__).resolve().parents[1] / "agent" / "config.yaml"
    if not config_path.is_file():
        raise SystemExit(f"No broker config at {config_path} — cannot fetch price data.")
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    from core.brokers import BrokerError, get_broker

    try:
        broker = get_broker(config)
        connected = broker.connect()
    except BrokerError as e:
        raise SystemExit(
            f"Broker connect failed: {e}\nIf this is Fyers, the daily token has "
            f"most likely expired — refresh it and retry."
        ) from e

    if not connected:
        raise SystemExit(
            "Broker connect failed. If this is Fyers, the daily token has most "
            "likely expired — refresh it and retry."
        )
    return broker


def _fetch_daily(broker, symbol: str) -> list[OHLCV]:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=_HISTORY_DAYS)
    return broker.get_historical_data(symbol, "1D", start, end)


def _print_report(report: AuditReport, *, verbose: bool) -> None:
    banner = {
        Verdict.PASS: "PASS",
        Verdict.FAIL: "FAIL",
        Verdict.INSUFFICIENT_DATA: "INSUFFICIENT DATA",
        Verdict.UNAVAILABLE: "UNAVAILABLE",
    }[report.verdict]

    print()
    print(f"  {report.note_name}  ->  {banner}")
    print(f"  {'-' * (len(report.note_name) + len(banner) + 8)}")

    for result in report.results:
        mark = _MARK[result.passed]
        print(f"    [{mark}] {result.detail}")
        if verbose and result.rule.comment:
            print(f"           note: {result.rule.comment}")

    if not report.results:
        print(f"    {report.reason}")

    if report.narration:
        print()
        for line in report.narration.splitlines():
            print(f"    | {line}")


def _cmd_list(index: VaultIndex) -> int:
    print(f"Vault: {index.vault_dir}")
    print(f"{len(index.notes)} notes, {len(index.auditable_notes)} with rule blocks\n")
    for note in sorted(index.notes, key=lambda n: n.name):
        flag = f"{len(note.rules)} rules" if note.is_auditable else "context only"
        print(f"  {note.name}")
        print(f"      id:    {note.strategy_id}")
        print(f"      tags:  {', '.join(note.tags) or '(none)'}")
        print(f"      rules: {flag}")
    return 0


def _cmd_search(index: VaultIndex, query: str, tags: list[str], limit: int) -> int:
    hits = index.search(query, tags=tags or None, limit=limit)
    if not hits:
        print(f"No notes matched {query!r}"
              + (f" within tags {', '.join(tags)}" if tags else ""))
        return 1
    print(f"{len(hits)} note(s) matched {query!r}:\n")
    for hit in hits:
        print(f"  {hit.score:6.2f}  {hit.note.name}")
        print(f"          matched: {', '.join(hit.matched_terms)}")
        print(f"          {hit.note.title}")
    return 0


async def _rs_rating_from_universe(broker, symbol: str, universe_file: Path) -> float | None:
    """Rank a whole universe by 52-week-high proximity and return `symbol`'s
    percentile. Slow (one history fetch per name) but it is the real number
    rather than a hand-typed guess."""
    from core.rotation.ranker import build_symbol_series, rank_universe

    symbols = [s.strip() for s in universe_file.read_text(encoding="utf-8").splitlines()
               if s.strip() and not s.startswith("#")]
    if symbol not in symbols:
        symbols.append(symbol)

    print(f"Ranking {len(symbols)} symbols to compute a real RS percentile — "
          f"this takes a few minutes ...")
    series = {}
    for i, name in enumerate(symbols, 1):
        try:
            bars = _fetch_daily(broker, name)
            if bars:
                series[name] = build_symbol_series(bars)
        except Exception as e:
            logger.debug("skipping %s: %s", name, e)
        if i % 50 == 0:
            print(f"  ... {i}/{len(symbols)}")

    ranked = rank_universe(series, datetime.now(timezone.utc), len(series))
    if symbol not in ranked:
        return None
    return rs_rating_from_rank(ranked.index(symbol) + 1, len(ranked))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit a symbol against the Obsidian vault's strategy notes.")
    parser.add_argument("symbol", nargs="?", help="NSE symbol, e.g. TVSMOTOR")
    parser.add_argument("--note", action="append", default=[], metavar="NAME",
                        help="Note filename stem or quantos.id. Repeatable. "
                             "Default: every note with a rule block.")
    parser.add_argument("--rs-rating", type=float, default=None, metavar="PCT",
                        help="Cross-sectional strength percentile 0-100.")
    parser.add_argument("--universe", type=Path, default=None, metavar="FILE",
                        help="Compute --rs-rating properly by ranking this universe file.")
    parser.add_argument("--narrate", action="store_true",
                        help="Add Claude's reading of the already-decided verdict.")
    parser.add_argument("--search", metavar="QUERY",
                        help="BM25-search the vault instead of auditing.")
    parser.add_argument("--tag", action="append", default=[], metavar="TAG",
                        help="Restrict --search to a frontmatter tag. Repeatable.")
    parser.add_argument("--limit", type=int, default=5, help="Max --search results.")
    parser.add_argument("--list", action="store_true", help="List the vault's notes and exit.")
    parser.add_argument("--vault", type=Path, default=None,
                        help="Vault directory (default: $QUANTOS_VAULT_DIR or obsidian_vault/QuantOS).")
    parser.add_argument("-v", "--verbose", action="store_true")

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
        index = VaultIndex.load(args.vault)
    except VaultNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    if args.list:
        return _cmd_list(index)
    if args.search:
        return _cmd_search(index, args.search, args.tag, args.limit)
    if not args.symbol:
        parser.error("a symbol is required unless --list or --search is used")

    auditor = StrategyAuditor(index)
    note_names = args.note or auditor.auditable_note_names()
    if not note_names:
        print(f"error: no notes in {index.vault_dir} carry a ```quantos-rules``` block.",
              file=sys.stderr)
        return 2

    broker = _load_broker()
    symbol = args.symbol.upper()
    daily = _fetch_daily(broker, symbol)
    if not daily:
        print(f"error: no price history returned for {symbol}.", file=sys.stderr)
        return 2

    rs_rating = args.rs_rating
    if rs_rating is None and args.universe:
        rs_rating = asyncio.run(_rs_rating_from_universe(broker, symbol, args.universe))

    print()
    print(f"{symbol} — {len(daily)} daily bars, last close {daily[-1].close:,.2f} "
          f"({daily[-1].timestamp:%Y-%m-%d})")
    if rs_rating is None:
        print("  rs_rating: not supplied — rules referencing it will be unevaluable "
              "(pass --rs-rating or --universe)")
    else:
        print(f"  rs_rating: {rs_rating:.1f}")

    worst_ok = True
    for name in note_names:
        report = auditor.audit(symbol, daily, name, rs_rating=rs_rating)
        if args.narrate:
            note = index.get(name) if index.has(name) else None
            report = narrate(report, note)
        _print_report(report, verbose=args.verbose)
        worst_ok = worst_ok and report.verdict.is_clear_to_proceed

    print()
    print(f"  => {symbol} {'CLEARS' if worst_ok else 'DOES NOT CLEAR'} "
          f"{len(note_names)} audit(s)")
    print()
    return 0 if worst_ok else 1


if __name__ == "__main__":
    sys.exit(main())
