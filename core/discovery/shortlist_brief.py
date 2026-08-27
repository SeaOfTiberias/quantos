"""
QuantOS — Momentum Shortlist Morning Brief
───────────────────────────────────────────
Turns two consecutive shortlist scans into "what changed overnight".

Why this exists at all: the scan ranks ~484 names into four buckets and the
cockpit renders them, but a ranked table shows only a position, never a
move. A name that went from IN BOX to NEAR on a tight base, or that gained
two Minervini rules, looks identical to one that sat still. Those
transitions are the whole point of watching a shortlist daily, and until
2026-08-27 nothing in QuantOS retained yesterday's board to compare against
(cloud/api/shortlist_history.py now does).

Everything here is a pure function of two entry lists. No I/O, no clock, no
LLM — a flag either follows from the two snapshots or it isn't emitted. The
generated prose in cloud/analyst/shortlist_note.py reads THIS output; it
never sees the raw board, so it cannot introduce a claim the numbers don't
support. That ordering is deliberate and is the whole reason the flags are
computed first.

FOCUS_BUCKETS is the tight-base pair on purpose. LEADER_EXTENDED is a real
leader bucket but by construction has no tight base to break out of — it is
already extended — so per-name transition tracking there mostly generates
noise. Its size is still reported in the census, so a drift of names from
tight into extended stays visible.
"""

from typing import Optional

# The two buckets the brief tracks name-by-name.
FOCUS_BUCKETS = ("LEADER_TIGHT_BASE", "BUILDING_BASE")

# Every bucket, in the scan's own priority order — used for the census and
# for deciding whether a bucket move was a promotion or a demotion.
ALL_BUCKETS = ("LEADER_TIGHT_BASE", "LEADER_EXTENDED", "BUILDING_BASE", "WATCH")

_BUCKET_RANK = {b: i for i, b in enumerate(ALL_BUCKETS)}

# Distance along the road to a breakout. Ordered so a rise is constructive.
# FRESH outranks OUT deliberately: OUT means "cleared the ceiling N sessions
# ago and has been drifting since", FRESH means "cleared it today, on the
# volume test" — the second is the event, the first is its aftermath.
_BREAKOUT_LADDER = {
    "NO BASE": 0,
    "IN BOX": 1,
    "NEAR": 2,
    "OUT": 3,
    "FRESH": 4,
}

# Flag kinds, most important first. The cockpit renders in this order and the
# generated note is told to respect it, so that "a name broke out today"
# can never be buried under "a name lost one Weinstein rule".
FLAG_ORDER = (
    "NEW_BREAKOUT",
    "NEW_LEADER",
    "TURNED_NEAR",
    "NEW_BULL_CROSS",
    "LOST_LEADER",
    "VAULT_IMPROVED",
    "VAULT_WEAKENED",
    "NEW_ENTRY",
    "DROPPED",
)

_FLAG_RANK = {f: i for i, f in enumerate(FLAG_ORDER)}


def _by_symbol(entries: list[dict]) -> dict[str, dict]:
    return {e["symbol"]: e for e in entries if e.get("symbol")}


def _ladder(state: Optional[str]) -> Optional[int]:
    if state is None:
        return None
    return _BREAKOUT_LADDER.get(state)


def _delta(today: Optional[float], prev: Optional[float]) -> Optional[float]:
    if today is None or prev is None:
        return None
    return round(today - prev, 2)


def _vault_by_label(entry: dict) -> dict[str, dict]:
    """Per-note vault scores keyed by note label.

    Per note, never summed. core/vault/shortlist_audit.py does expose a
    summed `vault_rules_passed`, but its own docstring says the bundled
    notes are incommensurable and "must never be summed", and the cockpit's
    existing tables already refuse to render the aggregate for that reason.
    A Minervini rule and a Weinstein rule are not interchangeable units, so
    "vault score went from 6 to 7" says nothing a reader can act on, whereas
    "Minervini 4/6 -> 5/6" does."""
    out = {}
    for n in entry.get("vault_notes") or []:
        label = n.get("label")
        if label:
            out[label] = n
    return out


def diff_entry(today: dict, prev: Optional[dict]) -> dict:
    """One name's overnight change. `prev` None means it wasn't ranked in the
    previous session — every delta is then None rather than 0, because "no
    comparison available" and "did not move" are different facts and a
    cockpit that renders them identically is lying."""
    out = dict(today)
    out["is_new"] = prev is None
    out["momentum_delta"] = _delta(today.get("momentum_pct"),
                                   (prev or {}).get("momentum_pct"))
    # Rank improves as it falls, so negate: a positive rank_delta always
    # means "moved up the board", matching every other delta's sign.
    rank_today, rank_prev = today.get("momentum_rank"), (prev or {}).get("momentum_rank")
    out["rank_delta"] = (rank_prev - rank_today
                         if rank_today is not None and rank_prev is not None
                         else None)
    out["prev_bucket"] = (prev or {}).get("bucket")
    out["prev_breakout_state"] = (prev or {}).get("breakout_state")
    # Per-note vault movement: [{label, rules_passed, rules_total, delta}].
    now_notes, was_notes = _vault_by_label(today), _vault_by_label(prev or {})
    moves = []
    for label, n in now_notes.items():
        before_n = was_notes.get(label)
        passed, prev_passed = n.get("rules_passed"), (before_n or {}).get("rules_passed")
        moves.append({
            "label": label,
            "rules_passed": passed,
            "rules_total": n.get("rules_total"),
            "prev_rules_passed": prev_passed,
            "delta": (passed - prev_passed
                      if isinstance(passed, int) and isinstance(prev_passed, int)
                      else None),
        })
    out["vault_moves"] = sorted(moves, key=lambda m: m["label"])
    out["vault_changed"] = any(m["delta"] not in (None, 0) for m in moves)
    return out


def _flag(kind: str, symbol: str, detail: str, **extra) -> dict:
    return {"kind": kind, "symbol": symbol, "detail": detail, **extra}


def compute_flags(today: list[dict], prev: list[dict]) -> list[dict]:
    """Deterministic transitions between two sessions, most important first.

    An empty `prev` yields no flags at all — not a page of NEW_ENTRY noise.
    The first session ever recorded has nothing to have changed from, and
    saying "484 new entries" on day one would be technically true and
    completely useless."""
    if not prev:
        return []

    t_map, p_map = _by_symbol(today), _by_symbol(prev)
    flags: list[dict] = []

    for symbol, entry in t_map.items():
        before = p_map.get(symbol)
        bucket = entry.get("bucket")
        in_focus = bucket in FOCUS_BUCKETS

        if before is None:
            if in_focus:
                flags.append(_flag(
                    "NEW_ENTRY", symbol,
                    f"entered {bucket} — not ranked in the previous session",
                    bucket=bucket))
            continue

        # ── breakout ladder ──────────────────────────────────────────────
        now_state, was_state = entry.get("breakout_state"), before.get("breakout_state")
        now_rung, was_rung = _ladder(now_state), _ladder(was_state)
        if now_state != was_state and now_rung is not None and was_rung is not None:
            if now_state == "FRESH":
                flags.append(_flag(
                    "NEW_BREAKOUT", symbol,
                    f"broke out today (was {was_state})",
                    breakout_state=now_state, prev_breakout_state=was_state,
                    box_width_pct=entry.get("box_width_pct")))
            elif now_state == "NEAR" and now_rung > was_rung:
                flags.append(_flag(
                    "TURNED_NEAR", symbol,
                    f"moved up to NEAR from {was_state}",
                    breakout_state=now_state, prev_breakout_state=was_state,
                    box_width_pct=entry.get("box_width_pct")))

        # ── bucket promotion / demotion ──────────────────────────────────
        was_bucket = before.get("bucket")
        if bucket != was_bucket and bucket in _BUCKET_RANK and was_bucket in _BUCKET_RANK:
            if bucket == "LEADER_TIGHT_BASE":
                flags.append(_flag(
                    "NEW_LEADER", symbol,
                    f"promoted to LEADER_TIGHT_BASE from {was_bucket}",
                    bucket=bucket, prev_bucket=was_bucket))
            elif was_bucket == "LEADER_TIGHT_BASE":
                flags.append(_flag(
                    "LOST_LEADER", symbol,
                    f"fell out of LEADER_TIGHT_BASE into {bucket}",
                    bucket=bucket, prev_bucket=was_bucket))

        if not in_focus:
            continue

        # ── moving-average cross ─────────────────────────────────────────
        now_cross, was_cross = entry.get("ma_cross"), before.get("ma_cross")
        if now_cross == "BULL" and was_cross not in (None, "BULL"):
            flags.append(_flag(
                "NEW_BULL_CROSS", symbol,
                f"50/200 turned BULL (was {was_cross})",
                ma_cross=now_cross, prev_ma_cross=was_cross))

        # ── vault rules, one flag PER NOTE ───────────────────────────────
        # One flag per note rather than one per name: a name can gain a
        # Minervini rule and lose a Weinstein rule in the same session, and
        # collapsing that into a single number would net them to zero and
        # report nothing happened.
        now_notes, was_notes = _vault_by_label(entry), _vault_by_label(before)
        for label, n in sorted(now_notes.items()):
            before_n = was_notes.get(label)
            if not before_n:
                continue
            passed, prev_passed = n.get("rules_passed"), before_n.get("rules_passed")
            if not (isinstance(passed, int) and isinstance(prev_passed, int)):
                continue
            if passed == prev_passed:
                continue
            total = n.get("rules_total")
            suffix = f"/{total}" if total else ""
            kind = "VAULT_IMPROVED" if passed > prev_passed else "VAULT_WEAKENED"
            flags.append(_flag(
                kind, symbol,
                f"{label} {prev_passed}{suffix} -> {passed}{suffix}",
                note_label=label, rules_passed=passed,
                prev_rules_passed=prev_passed, rules_total=total))

    # Dropouts: was in a focus bucket, now ranked nowhere at all. A name that
    # merely moved to WATCH is covered by LOST_LEADER / bucket census, not
    # here — disappearing from the universe is a different event from sliding
    # down it, and conflating them hides delistings and data gaps.
    for symbol, before in p_map.items():
        if symbol in t_map:
            continue
        if before.get("bucket") in FOCUS_BUCKETS:
            flags.append(_flag(
                "DROPPED", symbol,
                f"no longer ranked (was {before.get('bucket')})",
                prev_bucket=before.get("bucket")))

    flags.sort(key=lambda f: (_FLAG_RANK.get(f["kind"], len(FLAG_ORDER)),
                              f["symbol"]))
    return flags


def bucket_census(today: list[dict], prev: list[dict]) -> list[dict]:
    """Per-bucket population, today vs the previous session."""
    def counts(entries):
        c = {b: 0 for b in ALL_BUCKETS}
        for e in entries:
            b = e.get("bucket")
            if b in c:
                c[b] += 1
        return c

    now, was = counts(today), counts(prev) if prev else None
    return [{
        "bucket": b,
        "count": now[b],
        "prev_count": was[b] if was else None,
        "delta": (now[b] - was[b]) if was else None,
    } for b in ALL_BUCKETS]


def build_brief(today: list[dict], prev: list[dict],
                scan_date: Optional[str] = None,
                prev_scan_date: Optional[str] = None) -> dict:
    """The whole computed brief: focus-bucket rows with per-name deltas, the
    ranked flags, and the bucket census. Pure — same inputs, same output."""
    p_map = _by_symbol(prev)
    focus = [e for e in today if e.get("bucket") in FOCUS_BUCKETS]
    focus.sort(key=lambda e: (_BUCKET_RANK.get(e.get("bucket"), 99),
                              e.get("momentum_rank") if e.get("momentum_rank")
                              is not None else 10**6))
    rows = [diff_entry(e, p_map.get(e["symbol"])) for e in focus]
    flags = compute_flags(today, prev)
    return {
        "scan_date": scan_date,
        "prev_scan_date": prev_scan_date,
        "has_comparison": bool(prev),
        "entries": rows,
        "flags": flags,
        "census": bucket_census(today, prev),
        "counts": {
            "ranked": len(today),
            "focus": len(rows),
            "flags": len(flags),
        },
    }
