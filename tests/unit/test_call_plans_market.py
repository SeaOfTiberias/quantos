"""scripts/call_plans.py: the NIFTY guard and the per-week entry cap (2026-11-16; synthetic data)."""
import pandas as pd

from scripts.call_plans import MAX_ENTRIES_PER_WEEK, IndexState, week_entries


def _idx(closes, start="2026-10-20"):
    d = pd.bdate_range(start, periods=len(closes))
    return pd.DataFrame(dict(date=d, o=closes, h=[c + 50 for c in closes], l=[c - 50 for c in closes], c=closes,
                             vol=0, val=0))


def test_guard_cancels_on_a_close_through_the_last_low_not_a_sweep():
    ix = IndexState(_idx([22500, 22300, 22150, 22400]))
    s = dict(D="down", low=22179.9, high=23489.0)
    assert ix.guard(s, "2026-10-21") == {}                                  # 22300: above the low
    assert "CE" in ix.guard(s, "2026-10-22")                                # closed 22150 < 22179.9
    assert ix.guard(s, "2026-10-23") == {}                                  # a sweep that closes back above
    assert "PE" in ix.guard(dict(D="up", low=22000.0, high=22350.0), "2026-10-23")
    assert ix.guard(None, "2026-10-22") == {} and IndexState(pd.DataFrame()).guard(s, "2026-10-22") == {}


def test_week_entries_counts_main_entries_per_side_per_iso_week():
    t = lambda kind, side, d: dict(kind=kind, side=side, entry_date=d)      # noqa: E731
    state = dict(a=dict(tracks=[t("sweep", "CE", "2026-10-26"), t("confirm", "CE", "2026-10-26")]),
                 b=dict(tracks=[t("re-sweep", "CE", "2026-10-28"), t("sweep", "PE", "2026-10-28")]),
                 c=dict(tracks=[t("sweep", "CE", "2026-10-23")]))           # the week before
    assert week_entries(state, "CE", "2026-10-30") == 2                     # starters don't count
    assert week_entries(state, "PE", "2026-10-27") == 1
    assert MAX_ENTRIES_PER_WEEK == 3
