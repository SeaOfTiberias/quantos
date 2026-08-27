"""Tests for the Morning Brief: the pure diff, the history store, and the
journald backfill parser."""

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.discovery.shortlist_brief import (  # noqa: E402
    FOCUS_BUCKETS, bucket_census, build_brief, compute_flags, diff_entry,
)


def entry(symbol, *, bucket="LEADER_TIGHT_BASE", momentum=90.0, rank=1,
          breakout="IN BOX", cross="BULL", cross_days=None, width=10.0,
          minervini=3, weinstein=2, trend_up=True):
    notes = []
    if minervini is not None:
        notes.append({"label": "Minervini", "rules_passed": minervini, "rules_total": 6})
    if weinstein is not None:
        notes.append({"label": "Weinstein", "rules_passed": weinstein, "rules_total": 5})
    return {
        "symbol": symbol, "bucket": bucket, "momentum_pct": momentum,
        "momentum_rank": rank, "breakout_state": breakout, "trend_up": trend_up,
        "ma_cross": cross, "ma_cross_days": cross_days, "box_width_pct": width,
        "rr_ratio": 4.0, "vault_notes": notes,
    }


def kinds(flags):
    return [(f["kind"], f["symbol"]) for f in flags]


# ── the diff itself ────────────────────────────────────────────────────────

def test_no_previous_session_yields_no_flags():
    """Day one has nothing to have changed from. 484 NEW_ENTRY rows would be
    technically true and useless."""
    assert compute_flags([entry("A"), entry("B")], []) == []


def test_missing_previous_entry_gives_null_deltas_not_zero():
    """"Did not move" and "no comparison available" must not render alike."""
    d = diff_entry(entry("A", momentum=90.0), None)
    assert d["is_new"] is True
    assert d["momentum_delta"] is None
    assert d["rank_delta"] is None


def test_rank_delta_is_positive_when_the_name_moves_up():
    """Rank improves as the number falls; every other delta is positive-is-
    better, so this one is negated to match."""
    d = diff_entry(entry("A", rank=10), entry("A", rank=40))
    assert d["rank_delta"] == 30
    assert diff_entry(entry("A", rank=40), entry("A", rank=10))["rank_delta"] == -30


# ── breakout ladder ────────────────────────────────────────────────────────

def test_fresh_breakout_is_flagged():
    flags = compute_flags([entry("A", breakout="FRESH")],
                          [entry("A", breakout="NEAR")])
    assert ("NEW_BREAKOUT", "A") in kinds(flags)


def test_moving_up_to_near_is_flagged_but_falling_to_near_is_not():
    """NEAR reached from inside the box is a name approaching its ceiling.
    NEAR reached by falling back from OUT is the opposite event and must not
    wear the same label."""
    up = compute_flags([entry("A", breakout="NEAR")], [entry("A", breakout="IN BOX")])
    assert ("TURNED_NEAR", "A") in kinds(up)

    down = compute_flags([entry("A", breakout="NEAR")], [entry("A", breakout="OUT")])
    assert ("TURNED_NEAR", "A") not in kinds(down)


def test_out_drifting_is_not_a_new_breakout():
    """Still above the ceiling from days ago is not today's event."""
    flags = compute_flags([entry("A", breakout="OUT")], [entry("A", breakout="OUT")])
    assert not any(f["kind"] == "NEW_BREAKOUT" for f in flags)


# ── buckets ────────────────────────────────────────────────────────────────

def test_promotion_and_demotion_out_of_the_leader_bucket():
    promoted = compute_flags([entry("A", bucket="LEADER_TIGHT_BASE")],
                             [entry("A", bucket="BUILDING_BASE")])
    assert ("NEW_LEADER", "A") in kinds(promoted)

    demoted = compute_flags([entry("A", bucket="WATCH")],
                            [entry("A", bucket="LEADER_TIGHT_BASE")])
    assert ("LOST_LEADER", "A") in kinds(demoted)


def test_dropping_out_of_the_universe_is_distinct_from_sliding_down_it():
    """A name that vanished and a name that fell to WATCH are different
    events — one may be a delisting or a data gap."""
    flags = compute_flags([], [entry("A", bucket="LEADER_TIGHT_BASE")])
    assert ("DROPPED", "A") in kinds(flags)

    slid = compute_flags([entry("A", bucket="WATCH")],
                         [entry("A", bucket="LEADER_TIGHT_BASE")])
    assert not any(f["kind"] == "DROPPED" for f in slid)


# ── vault scores, per note ─────────────────────────────────────────────────

def test_vault_flags_are_per_note_never_summed():
    """The regression this guards: a name gaining a Minervini rule and losing
    a Weinstein rule on the same day nets to zero if the scores are summed,
    and the session would report that nothing happened. core/vault/
    shortlist_audit.py exposes a summed count but its own docstring says the
    notes are incommensurable and must never be added together."""
    flags = compute_flags(
        [entry("A", minervini=4, weinstein=1)],
        [entry("A", minervini=3, weinstein=2)],
    )
    got = {(f["kind"], f["note_label"]) for f in flags if "note_label" in f}
    assert ("VAULT_IMPROVED", "Minervini") in got
    assert ("VAULT_WEAKENED", "Weinstein") in got


def test_vault_moves_expose_both_notes_with_their_own_deltas():
    d = diff_entry(entry("A", minervini=5, weinstein=3),
                   entry("A", minervini=4, weinstein=3))
    by_label = {m["label"]: m for m in d["vault_moves"]}
    assert by_label["Minervini"]["delta"] == 1
    assert by_label["Weinstein"]["delta"] == 0
    assert d["vault_changed"] is True


def test_vault_delta_is_none_when_a_note_is_absent_previously():
    d = diff_entry(entry("A", minervini=5), entry("A", minervini=None, weinstein=2))
    minervini = [m for m in d["vault_moves"] if m["label"] == "Minervini"][0]
    assert minervini["delta"] is None


# ── ordering and shape ─────────────────────────────────────────────────────

def test_flags_are_ordered_most_important_first():
    """A breakout must never render below a lost rule."""
    flags = compute_flags(
        [entry("AAA", breakout="FRESH", minervini=2), entry("ZZZ", minervini=2)],
        [entry("AAA", breakout="NEAR", minervini=2), entry("ZZZ", minervini=3)],
    )
    assert flags[0]["kind"] == "NEW_BREAKOUT"
    assert flags[-1]["kind"] == "VAULT_WEAKENED"


def test_only_focus_buckets_appear_as_rows():
    today = [entry("A", bucket="LEADER_TIGHT_BASE"),
             entry("B", bucket="BUILDING_BASE"),
             entry("C", bucket="LEADER_EXTENDED"),
             entry("D", bucket="WATCH")]
    brief = build_brief(today, [])
    assert {r["symbol"] for r in brief["entries"]} == {"A", "B"}
    assert all(r["bucket"] in FOCUS_BUCKETS for r in brief["entries"])


def test_census_counts_every_bucket_including_non_focus_ones():
    today = [entry("A", bucket="LEADER_TIGHT_BASE"),
             entry("C", bucket="LEADER_EXTENDED")]
    prev = [entry("A", bucket="LEADER_TIGHT_BASE")]
    census = {c["bucket"]: c for c in bucket_census(today, prev)}
    assert census["LEADER_EXTENDED"]["count"] == 1
    assert census["LEADER_EXTENDED"]["delta"] == 1
    assert census["WATCH"]["count"] == 0


def test_build_brief_reports_absence_of_a_comparison():
    brief = build_brief([entry("A")], [], scan_date="2026-08-27")
    assert brief["has_comparison"] is False
    assert brief["flags"] == []
    assert brief["prev_scan_date"] is None


# ── history store (in-memory path) ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_history_roundtrip_and_previous_session_skips_gaps():
    """"Previous session" is the last one that EXISTS, never a calendar-
    derived yesterday — otherwise a weekend or a missed token refresh would
    report "no data" on exactly the mornings the diff matters most."""
    from cloud.api.shortlist_history import ShortlistHistory

    h = ShortlistHistory()
    assert h.backend == "memory"

    await h.record_snapshot("nifty500", [entry("A")], scan_date=date(2026, 8, 21))
    await h.record_snapshot("nifty500", [entry("A", momentum=95.0)],
                            scan_date=date(2026, 8, 24))

    assert await h.session_dates("nifty500") == ["2026-08-24", "2026-08-21"]
    # Friday -> Monday: three calendar days, one session apart.
    assert await h.previous_session_date("nifty500", "2026-08-24") == "2026-08-21"
    assert await h.previous_session_date("nifty500", "2026-08-21") is None

    rows = await h.fetch_session("nifty500", "2026-08-24")
    assert rows[0]["symbol"] == "A"
    assert rows[0]["momentum_pct"] == 95.0


@pytest.mark.asyncio
async def test_history_rerun_of_a_day_replaces_it_rather_than_appending():
    """A re-run is a correction of that day. An upsert would leave a symbol
    that dropped out of the universe behind as a phantom row."""
    from cloud.api.shortlist_history import ShortlistHistory

    h = ShortlistHistory()
    await h.record_snapshot("u", [entry("A"), entry("B")], scan_date=date(2026, 8, 24))
    await h.record_snapshot("u", [entry("A")], scan_date=date(2026, 8, 24))
    rows = await h.fetch_session("u", "2026-08-24")
    assert [r["symbol"] for r in rows] == ["A"]


@pytest.mark.asyncio
async def test_history_write_failure_never_propagates():
    """record_snapshot is called from inside the sync endpoint; a history
    problem must not lose an 11-minute scan."""
    from cloud.api.shortlist_history import ShortlistHistory

    h = ShortlistHistory()
    h._backend = "sqlite"          # claim persistence...
    h._engine = None               # ...with nothing behind it
    assert await h.record_snapshot("u", [entry("A")]) == 0


# ── journald backfill parser ───────────────────────────────────────────────

JOURNAL = """\
Aug 27 01:31:55 host python[1]: 2026-08-27 01:31:55,000 [INFO] quantos.discovery.momentum_shortlist: [nifty500] Fetching daily history for 500 symbols (agent/universe_nifty500.txt)...
Aug 27 01:42:28 host python[1]: 2026-08-27 01:42:28,857 [INFO] quantos.discovery.momentum_shortlist: LEADER_TIGHT_BASE (2):
Aug 27 01:42:28 host python[1]: 2026-08-27 01:42:28,857 [INFO] quantos.discovery.momentum_shortlist:   JSWSTEEL     momentum=100.0% trend=UP   breakout=OUT 3d     50/200=BULL      width=7.1% rr=3.32 vault=Minervini=5/6 Weinstein=4/5
Aug 27 01:42:28 host python[1]: 2026-08-27 01:42:28,857 [INFO] quantos.discovery.momentum_shortlist:   SHRIRAMFIN   momentum=96.9% trend=UP   breakout=NEAR       50/200=BULL      width=9.7% rr=4.42 vault=Minervini=5/6 Weinstein=3/5
Aug 27 01:42:28 host python[1]: 2026-08-27 01:42:28,858 [INFO] quantos.discovery.momentum_shortlist: WATCH (1):
Aug 27 01:42:28 host python[1]: 2026-08-27 01:42:28,858 [INFO] quantos.discovery.momentum_shortlist:   RPOWER       momentum=44.6% trend=down breakout=NO BASE    50/200=BEAR      width=— rr=— vault=Minervini=0/6 Weinstein=0/5
"""


def test_backfill_parses_a_session_out_of_journal_text():
    from scripts.backfill_shortlist_history import parse_journal

    sessions = parse_journal(JOURNAL.splitlines())
    # 01:42 UTC is 07:12 IST the same day.
    entries = sessions[("2026-08-27", "nifty500")]
    assert len(entries) == 3

    by_symbol = {e["symbol"]: e for e in entries}
    jsw = by_symbol["JSWSTEEL"]
    assert jsw["bucket"] == "LEADER_TIGHT_BASE"
    assert jsw["breakout_state"] == "OUT" and jsw["days_above_ceil"] == 3
    assert jsw["ma_cross"] == "BULL" and jsw["ma_cross_days"] is None
    assert jsw["trend_up"] is True
    assert jsw["vault_notes"] == [
        {"label": "Minervini", "rules_passed": 5, "rules_total": 6},
        {"label": "Weinstein", "rules_passed": 4, "rules_total": 5},
    ]

    # Two-word states survive the padded-column split.
    assert by_symbol["RPOWER"]["breakout_state"] == "NO BASE"
    assert by_symbol["RPOWER"]["trend_up"] is False
    # An em dash means "no base", which must be None and never 0.0 — a zero
    # box width would read as an infinitely tight base.
    assert by_symbol["RPOWER"]["box_width_pct"] is None
    assert by_symbol["RPOWER"]["rr_ratio"] is None


def test_backfill_derives_rank_by_momentum_descending():
    from scripts.backfill_shortlist_history import parse_journal

    entries = parse_journal(JOURNAL.splitlines())[("2026-08-27", "nifty500")]
    ranked = sorted(entries, key=lambda e: e["momentum_rank"])
    assert [e["symbol"] for e in ranked] == ["JSWSTEEL", "SHRIRAMFIN", "RPOWER"]


def test_backfill_leaves_unrecoverable_fields_null_rather_than_guessing():
    """close/stage/vault_verdict are not in the log line. They are absent,
    not zero — and the rows are stamped so a reader knows why."""
    from scripts.backfill_shortlist_history import parse_journal

    e = parse_journal(JOURNAL.splitlines())[("2026-08-27", "nifty500")][0]
    assert e["close"] is None
    assert e["stage"] is None
    assert e["vault_verdict"] is None


def test_backfill_does_not_carry_a_bucket_across_a_universe_boundary():
    """The first rows of a new universe must not inherit the previous
    universe's last bucket header."""
    from scripts.backfill_shortlist_history import parse_journal

    text = JOURNAL + (
        "Aug 27 01:43:00 host python[1]: 2026-08-27 01:43:00,000 [INFO] "
        "quantos.discovery.momentum_shortlist: [alpha50] Fetching daily history for 50 symbols (x)...\n"
        "Aug 27 01:43:01 host python[1]: 2026-08-27 01:43:01,000 [INFO] "
        "quantos.discovery.momentum_shortlist:   ORPHAN       momentum=50.0% trend=UP   "
        "breakout=NEAR       50/200=BULL      width=9.0% rr=4.00 vault=Minervini=1/6 Weinstein=1/5\n"
    )
    sessions = parse_journal(text.splitlines())
    assert ("2026-08-27", "alpha50") not in sessions


def test_backfill_second_run_of_a_day_replaces_the_first_board():
    """The service can fire twice in one day (both triggers, or a forced
    re-run). 2026-08-17 did exactly that and the journal holds two complete
    nifty500 boards under one date. Appending them would produce a session
    with every symbol twice and ranks numbered past the size of the universe,
    so the later board supersedes the earlier one."""
    from scripts.backfill_shortlist_history import parse_journal

    second = JOURNAL.replace("01:31:55", "03:31:55").replace(
        "01:42:28", "03:42:28").replace("JSWSTEEL", "TATASTEEL")
    sessions = parse_journal((JOURNAL + second).splitlines())

    entries = sessions[("2026-08-27", "nifty500")]
    assert len(entries) == 3, "both boards were merged instead of superseded"
    assert "JSWSTEEL" not in [e["symbol"] for e in entries]
    assert [e["momentum_rank"] for e in entries] == [1, 2, 3]
