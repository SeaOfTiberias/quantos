"""
QuantOS — Shortlist Morning Note (generated commentary)
────────────────────────────────────────────────────────
One short Claude-written paragraph per universe per day, sitting UNDER the
computed flags from core/discovery/shortlist_brief.py in the cockpit's
Morning Brief tab.

The ordering is the whole design. The flags are deterministic and are the
signal; this note is commentary and is explicitly labelled as such in the
UI. Claude is handed the computed brief and nothing else — never the raw
board — so it has no raw numbers to misread and cannot introduce a claim the
flags don't already support. If this module fails, times out, or has no API
key, the tab still renders everything that matters.

Deliberately NOT an advisor. QuantOS had a regime→options-strategy Claude
advisor; it was structurally removed on 2026-07-25 after review found the
pathway unsound, and prompts/shortlist_note_system.md forbids recommending
an action in as many words. This is a description of a board, and the
shortlist has no execution path for it to influence.

Cost shape: one call per universe per morning, a few thousand input tokens
against a small output cap. Cached per (universe, scan_date) so a cockpit
left open all day, or ten refreshes in a row, cost exactly one call.
"""

import json
import logging
import os
import time
from typing import Optional

import anthropic

from cloud.api.metrics import record_claude
from core import prompts

logger = logging.getLogger(__name__)

_claude = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""),
                                   timeout=30.0)

# The rest of this repo pins claude-sonnet-4-6 (cloud/analyst/chat.py,
# pre_trade.py, core/backtest/analyst.py). This module defaults to Opus 5
# instead: it runs a handful of times a day rather than per-request, the
# judgement is the entire deliverable, and the spend difference at this call
# volume is a rounding error against the VM. Override with SHORTLIST_NOTE_MODEL
# to bring it in line with the others if that inconsistency ever bites.
MODEL = os.getenv("SHORTLIST_NOTE_MODEL", "claude-opus-5")

MAX_TOKENS = 400

# (universe, scan_date) -> note. The scan writes once a day, so a hit here is
# the overwhelmingly common case and a miss means a genuinely new board.
_note_cache: dict[tuple[str, str], str] = {}


class NoteUnavailable(Exception):
    """The note could not be generated. Never fatal — the caller renders the
    computed flags without it."""


def _trim_for_prompt(brief: dict) -> dict:
    """Send the flags and census whole, but only the focus rows that actually
    moved plus a bounded head of the rest.

    A quiet Nifty 500 morning still has ~60 tight-base rows, most of them
    unchanged, and paying to send "unchanged" sixty times teaches the model
    nothing. Rows are already sorted best-bucket-then-best-rank, so the head
    is the top of the board, not an arbitrary slice."""
    entries = brief.get("entries", [])
    moved = [e for e in entries
             if e.get("is_new")
             or (e.get("momentum_delta") not in (None, 0))
             or e.get("bucket") != e.get("prev_bucket")
             or e.get("breakout_state") != e.get("prev_breakout_state")
             or e.get("vault_changed")]
    head = [e for e in entries[:15] if e not in moved]
    keep = (moved + head)[:40]
    return {**brief, "entries": keep,
            "entries_note": (f"{len(keep)} of {len(entries)} focus rows shown "
                             f"(all that changed, plus the top of the board)")}


async def generate_note(universe: str, brief: dict) -> str:
    """Return the generated commentary for `brief`. Raises NoteUnavailable on
    any failure — including a missing API key — so the caller can render the
    tab without it rather than surfacing a 500."""
    scan_date = brief.get("scan_date") or "unknown"
    cache_key = (universe, scan_date)
    if cache_key in _note_cache:
        return _note_cache[cache_key]

    if not os.getenv("ANTHROPIC_API_KEY"):
        raise NoteUnavailable("ANTHROPIC_API_KEY is not set")

    system = prompts.load("shortlist_note_system")
    user = prompts.render(
        "shortlist_note_user",
        universe=universe,
        scan_date=scan_date,
        prev_scan_date=brief.get("prev_scan_date") or "no previous session",
        brief_json=json.dumps(_trim_for_prompt(brief), indent=2, default=str),
    )

    started = time.perf_counter()
    response = None
    try:
        response = await _claude.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
    except anthropic.APIStatusError as e:
        raise NoteUnavailable(f"Claude API error {e.status_code}") from e
    except anthropic.APIConnectionError as e:
        raise NoteUnavailable("Claude API unreachable") from e
    finally:
        usage = getattr(response, "usage", None) if response is not None else None
        record_claude(
            (time.perf_counter() - started) * 1000.0,
            input_tokens=getattr(usage, "input_tokens", 0) if usage else 0,
            output_tokens=getattr(usage, "output_tokens", 0) if usage else 0,
        )

    # A safety decline is a legitimate outcome, not a crash: fall through to
    # "no note today" rather than rendering an empty box with no explanation.
    if getattr(response, "stop_reason", None) == "refusal":
        raise NoteUnavailable("Claude declined to generate this note")

    blocks = [b.text for b in response.content
              if getattr(b, "type", None) == "text"]
    note = "\n".join(blocks).strip()
    if not note:
        raise NoteUnavailable("Claude returned no text")

    _note_cache[cache_key] = note
    return note


def cached_note(universe: str, scan_date: Optional[str]) -> Optional[str]:
    """The note for this universe/date if one has already been generated this
    process, else None. Lets a caller render instantly without deciding
    whether to spend on a call."""
    if not scan_date:
        return None
    return _note_cache.get((universe, scan_date))
