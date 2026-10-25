"""core/ideas/events.py + the results-gap scenario (R7) in the structure selector."""

import json
from datetime import date, datetime, timedelta

from core.ideas import events
from core.ideas.structure import View, candidates
from core.mcp_tools import market as mt
from tests.unit.test_mcp_market_tools import TODAY, FakeMarket
from tests.unit.test_structure_selector import HVIEW, _get, _hdfc

ROWS = [
    {"bm_symbol": "ADANIENT", "bm_date": "28-Oct-2026", "bm_purpose": "Financial Results", "bm_desc": "Q2"},
    {"bm_symbol": "ADANIENT", "bm_date": "28-Oct-2026", "bm_purpose": "Board Meeting Intimation",
     "bm_desc": "To consider and approve the financial results for the period ended September 30, 2026"},
    {"bm_symbol": "LICI", "bm_date": "05-Nov-2026", "bm_purpose": "Financial Results"},
    {"bm_symbol": "XYZ", "bm_date": "02-Nov-2026", "bm_purpose": "Fund Raising", "bm_desc": "rights issue"},
    {"bm_symbol": "BAD", "bm_date": "sometime", "bm_purpose": "Financial Results"},
]


def test_parse_rows_keeps_results_only_deduped():
    assert events.parse_rows(ROWS) == {"ADANIENT": ["2026-10-28"], "LICI": ["2026-11-05"]}
    assert events.parse_rows({"not": "a list"}) == {}


def test_refresh_uses_fresh_cache_refetches_stale_and_survives_failure(tmp_path):
    p = tmp_path / "events.json"
    now = datetime(2026, 10, 25, 18, 0)
    calls = []

    def fetcher(d):
        calls.append(d)
        return {"LICI": ["2026-11-05"]}
    first = events.refresh(p, now, fetcher)
    assert first["results"] == {"LICI": ["2026-11-05"]} and calls == [date(2026, 10, 25)]
    events.refresh(p, now + timedelta(hours=2), fetcher)
    assert len(calls) == 1                                          # fresh: no refetch
    events.refresh(p, now + timedelta(hours=13), fetcher)
    assert len(calls) == 2                                          # stale: refetched

    def broken(d):
        raise RuntimeError("403")
    kept = events.refresh(p, now + timedelta(days=2), broken)
    assert kept["results"] == {"LICI": ["2026-11-05"]} and "refresh failed" in kept["error"]


def test_event_context_inside_and_after_horizon():
    cal = {"fetched": "2026-10-25T18:00:00", "results": {"LICI": ["2026-10-01", "2026-11-05"]}}
    fri = date(2026, 10, 23)
    assert events.trading_days_until(fri, date(2026, 11, 5)) == 9
    inside = events.event_context(cal, "lici", fri, 10)
    assert inside["results_date"] == "2026-11-05" and inside["inside_horizon"] and inside["sessions_away"] == 9
    assert not events.event_context(cal, "LICI", fri, 5)["inside_horizon"]
    assert events.event_context(cal, "HDFCBANK", fri, 10)["results_date"] is None
    assert events.event_context({}, "LICI", fri, 10)["error"] == "no results calendar"


def test_event_scenario_prices_a_gap_against_the_view_and_flags_r7():
    plain = candidates(_hdfc(), View(**HVIEW))
    assert all(c.event is None for c in plain) and not any(f.startswith("R7") for c in plain for f in c.flags)
    ev = candidates(_hdfc(), View(**HVIEW, event_date=date(2026, 10, 29), event_iv_shift=-0.05))
    fut = next(c for c in ev if "future" in c.name)
    assert fut.event < fut.flat and fut.event < 0                    # a 1.5 ATR gap up hurts a short
    bp = _get(ev, "bear put 690/660")
    assert bp.event is not None and bp.event < 0 and bp.loss_stop <= bp.event
    r7 = [c for c in ev if any(f.startswith("R7") for f in c.flags)]
    assert r7 and all(abs(c.event - c.loss_stop) < 1e-6 for c in r7)
    structural = [any(not f.startswith("R7") for f in c.flags) for c in ev]
    assert structural == sorted(structural)                         # R1-R6 breakers always rank after
    late = candidates(_hdfc(), View(**HVIEW, event_date=date(2026, 11, 20)))   # after the horizon
    assert all(c.event is None for c in late)


def test_pick_structure_attaches_event_and_warns(tmp_path):
    d = TODAY + timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    p = tmp_path / "events.json"
    p.write_text(json.dumps({"fetched": datetime.now().isoformat(timespec="seconds"),
                             "results": {"ABC": [d.isoformat()]}}))
    ps = mt.pick_structure(FakeMarket(), "ABC", "bull", target=1060, stop=980, days=3, iv_history=None, events_path=p)
    assert ps["event"]["inside_horizon"] and ps["event"]["results_date"] == d.isoformat()
    assert any("results on" in w for w in ps["warnings"])
    assert any(r.get("if_event") is not None for r in ps["top"])
    none = mt.pick_structure(FakeMarket(), "ABC", "bull", target=1060, stop=980, days=3, iv_history=None,
                             events_path=None)
    assert none["event"]["results_date"] is None and all(r.get("if_event") is None for r in none["top"])
