"""L1 structure (core/market_map/structure.py): definitions v1 §0, §1, §2, §7, on synthetic bars."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from core.market_map import read as mr
from core.market_map import structure as s
from core.market_map.l1_store import Store


def _bars(hlc):
    dates = pd.bdate_range("2026-01-05", periods=len(hlc))
    df = pd.DataFrame(hlc, columns=["h", "l", "c"])
    df["o"] = df["c"]
    df["vol"] = 1
    df["date"] = dates
    df["period"] = dates.strftime("%Y-%m-%d")
    return df


# bar: high, low, close (traced by hand; k = 1, ATR = 1)
TRACE = [(10, 9, 9.5), (12, 10, 11), (11, 8, 9), (11, 9, 10),
         (13, 10, 12.5),                 # 4: close above the swing high 12 -> BOS up from none
         (14, 12, 13.5), (13, 11, 12), (12, 9, 10), (13, 10, 11),
         (15, 11, 14.5),                 # 9: close above the swing high 14 -> BOS up
         (14, 8, 8.5)]                   # 10: close below the protected low 9 -> CHoCH down


def test_bos_then_choch_with_protected_and_weak_levels():
    b = _bars(TRACE)
    st = s.run(b, 1, np.ones(len(b)))
    assert [(e["type"], e["direction"], e["i"], e["level"]) for e in st.events] == [
        ("BOS", "up", 4, 12), ("BOS", "up", 9, 14), ("CHoCH", "down", 10, 9)]
    assert st.state == "down"
    assert (st.protected.price, st.protected.i) == (15, 9)       # highest high from the protected low's bar
    assert (st.weak.price, st.weak.i) == (8, 10)
    sm = s.summary(b, st, "D")
    assert sm["age_bars"] == 0 and sm["last_event"]["level"] == 9


def test_protected_low_after_a_bos_is_the_low_since_the_broken_high():
    b = _bars(TRACE[:10])
    st = s.run(b, 1, np.ones(len(b)))
    assert st.state == "up" and (st.protected.price, st.protected.i) == (9, 7)
    assert (st.weak.price, st.weak.i) == (15, 9)


def test_a_wick_through_the_swing_high_is_not_a_break():
    rows = TRACE[:4] + [(13, 10, 11.9), (11.5, 10.5, 11)]
    st = s.run(_bars(rows), 1, np.ones(len(rows)))
    assert st.events == [] and st.state == "none"


def test_swings_need_strictly_higher_highs_and_are_confirmed_k_bars_later():
    h = np.array([1, 2, 2, 1.0])
    assert s.candidates(h, -h, 1) == {}
    h = np.array([0, 1, 3, 2, 1.0])
    assert s.candidates(h, h + 10, 2) == {4: [("H", 2, 3.0)]}     # bar 2's high, usable from bar 4


def test_zigzag_keeps_the_more_extreme_and_drops_swings_under_one_atr():
    z = s.ZigZag()
    z.offer("H", 0, 10, 1, 1.0)
    assert z.offer("L", 1, 9.5, 2, 1.0) is None              # only 0.5 ATR below the high
    assert z.offer("H", 2, 11, 3, 1.0) is not None           # two highs in a row: the higher stays
    assert z.offer("H", 3, 10.8, 4, 1.0) is None
    z.offer("L", 4, 8, 5, 1.0)
    z.offer("H", 5, 10.5, 6, 1.0)
    z.offer("L", 6, 9, 7, 1.0)
    assert [(w.kind, w.price, w.label) for w in z.kept] == [
        ("H", 11, ""), ("L", 8, ""), ("H", 10.5, "LH"), ("L", 9, "HL")]


def test_events_never_change_when_later_bars_arrive():
    rng = np.random.default_rng(20261107)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, 600)))
    h, l = c * (1 + rng.uniform(0, 0.02, 600)), c * (1 - rng.uniform(0, 0.02, 600))
    b = _bars(list(zip(h, l, c)))
    full = s.run(b, 3).events
    assert len(full) > 5
    for n in (150, 300, 451):
        part = s.run(b.iloc[:n].reset_index(drop=True), 3).events
        assert part == [e for e in full if e["i"] < n]


def test_iso_weeks_months_and_only_completed_periods():
    days = pd.bdate_range("2025-12-29", "2026-01-09")
    d = pd.DataFrame({"date": days, "o": range(10), "h": np.arange(10) + 1.0, "l": np.arange(10) - 1.0,
                      "c": np.arange(10) + 0.5, "vol": 1})
    w = s.resample(d, "W")
    assert list(w["period"]) == ["2026-W01", "2026-W02"]          # 29 Dec 2025 is in ISO week 1 of 2026
    assert (w["o"].iat[0], w["h"].iat[0], w["l"].iat[0], w["c"].iat[0], w["vol"].iat[0]) == (0, 5.0, -1.0, 4.5, 5)
    m = s.resample(d, "M")
    assert list(m["period"]) == ["2025-12", "2026-01"] and m["c"].iat[0] == 2.5
    as_of = date(2026, 1, 7)
    assert list(s.completed(d, "W", as_of)["period"]) == ["2026-W01"]
    assert list(s.completed(d, "M", as_of)["period"]) == ["2025-12"]
    assert s.completed(d, "D", as_of)["date"].max() == pd.Timestamp("2026-01-06")


@pytest.mark.parametrize("states,aligned,conflicts", [
    (dict(M="up", W="up", D="up"), "up", []),
    (dict(M="down", W="down", D="down"), "down", []),
    (dict(M="up", W="up", D="down"), None, ["D"]),
    (dict(M="none", W="down", D="down"), None, ["M"]),
    (dict(M="up", W="down", D="none"), None, ["M", "W", "D"]),
])
def test_alignment(states, aligned, conflicts):
    a = s.alignment(states)
    assert a["aligned"] == aligned and a["conflicts"] == conflicts


def test_l1_read_uses_only_the_latest_segment():
    days = pd.bdate_range("2024-01-01", periods=300)
    d = pd.DataFrame({"date": days, "o": 100.0, "h": 101.0, "l": 99.0, "c": 100.0, "vol": 1,
                      "seg": [0] * 100 + [1] * 200})
    rd = s.l1_read(d, date(2025, 6, 1))
    assert rd["segment_break"] and rd["history_from"] == days[100].date().isoformat()
    assert rd["status"] == "untested" and set(rd["tf"]) == {"M", "W", "D"}


def test_map_read_carries_the_l1_read_from_the_store(tmp_path):
    st = Store(tmp_path)
    rng = np.random.default_rng(7)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.015, 900)))
    for dt, x in zip(pd.bdate_range("2023-01-02", periods=900), c):
        st.append_day(pd.DataFrame([("ABC", "EQ", x, x * 1.01, x * 0.99, x, 1, 1)],
                                   columns=["sym", "series", "o", "h", "l", "c", "vol", "val"]), dt.date())
    l1 = mr.l1_for("ABC", date(2026, 6, 1), st)
    assert l1["status"] == "untested" and l1["tf"]["W"]["bars"] > 100
    assert mr.l1_for("XYZ", date(2026, 6, 1), st)["error"].startswith("XYZ is not in")
    txt = s.lines(l1)
    assert txt[0].startswith("L1   structure (untested") and len(txt) >= 9
    for part in ("zones (untested)", "HTF strong zones (untested", "hot zones (Ochoa", "pivots (untested",
                 "pivot levels below", "profiles (untested", "long profile"):
        assert any(part in ln for ln in txt), part
    assert s.lines({"error": "no store"}) == ["L1   none (no store)"]


def test_join_checks_flag_a_close_mismatch_and_a_recent_split():
    rd = dict(close=101.0, l1=dict(price=100.0, last_date="2026-11-06",
                                   actions_l2_window=[dict(ex="2026-06-01", purpose="BONUS 1:1")]))
    j = mr.join_checks(rd)
    assert not j["close_check"]["ok"] and len(j["flags"]) == 2 and "BONUS 1:1 ex 2026-06-01" in j["flags"][1]
    rd["close"] = 100.3
    assert mr.join_checks(rd)["close_check"]["ok"]
    assert mr.join_checks(dict(close=1, l1=dict(error="x")))["flags"] == []
