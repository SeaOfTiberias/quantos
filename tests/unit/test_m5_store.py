"""5-minute store (core/market_map/m5_store.py) and the fetch job's chunks, on synthetic bars."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pandas as pd

from core.market_map.m5_store import M5Store, bars_frame
from scripts import fetch_m5 as job


def _bar(ts, px, vol=100):
    return SimpleNamespace(timestamp=ts, open=px, high=px + 1, low=px - 1, close=px, volume=vol)


def test_rows_split_by_ist_year_merge_on_rerun_and_adjust_by_date(tmp_path):
    m = M5Store(tmp_path)
    t = datetime(2025, 12, 31, 9, 55, tzinfo=timezone.utc)          # 15:25 IST, 31 Dec
    rows = bars_frame([_bar(t, 100.0), _bar(t + timedelta(hours=18), 50.0)])  # 1 Jan 2026, 09:25 IST
    m.write("ABC", rows)
    m.write("ABC", bars_frame([_bar(t, 101.0)]))                      # a rerun replaces the same bar
    assert sorted(p.name for p in (tmp_path / "m5" / "ABC").iterdir()) == ["2025.csv.gz", "2026.csv.gz"]
    raw = m.read_raw("ABC")
    assert list(raw["c"]) == [101.0, 50.0]
    daily = pd.DataFrame({"date": pd.to_datetime(["2025-12-31", "2026-01-01"])})
    m.set_state("ABC", basis="2025-12-30")
    acts = [dict(ex="2025-12-15", factor=0.1),           # before the basis: Fyers already adjusted it
            dict(ex="2026-01-01", factor=0.5)]           # after: applies to bars before 1 Jan
    adj = m.adjusted("ABC", daily, acts)
    assert list(adj["c"]) == [50.5, 50.0] and list(adj["vol"]) == [200.0, 100.0]


def test_state_is_kept_per_symbol(tmp_path):
    m = M5Store(tmp_path)
    m.set_state("ABC", last_ts=1, backfilled=True)
    m.set_state("ABC", last_ts=2)
    assert m.state() == {"ABC": {"last_ts": 2, "backfilled": True}}


def test_chunks_cover_the_span_without_overlap():
    s, e = datetime(2017, 12, 1, tzinfo=timezone.utc), datetime(2018, 12, 1, tzinfo=timezone.utc)
    c = job.chunks(s, e)
    assert c[0][0] == s and c[-1][1] == e and len(c) == 4
    assert all(b[0] > a[1] for a, b in zip(c, c[1:]))
    assert all((b - a).days <= 99 for a, b in c)


def test_fetch_raises_when_any_request_fails():
    class B:
        n = 0
        def get_historical_data(self, *a):
            B.n += 1
            if B.n == 2:
                raise RuntimeError("boom")
            return []
    s = datetime(2017, 12, 1, tzinfo=timezone.utc)
    try:
        job.fetch(B(), "ABC", s, s + timedelta(days=300), sleep=lambda x: None)
        assert False
    except RuntimeError:
        pass


def test_a_no_data_window_before_the_listing_is_empty_not_a_failure():
    class B:
        def get_historical_data(self, sym, tf, s, e):
            if s.year < 2018:
                raise RuntimeError("History fetch failed: {'candles': [], 'message': '', 's': 'no_data'}")
            return [_bar(e, 10.0)]
    s = datetime(2017, 12, 1, tzinfo=timezone.utc)
    rows = job.fetch(B(), "NEWCO", s, s + timedelta(days=200), sleep=lambda x: None)
    assert len(rows) == 2


def test_bad_bars_are_dropped_on_read_and_counted(tmp_path):
    m = M5Store(tmp_path)
    t = datetime(2019, 12, 6, 4, 0, tzinfo=timezone.utc)
    good = bars_frame([_bar(t, 100.0), _bar(t + timedelta(minutes=10), 102.0)])
    bad = pd.DataFrame([[int((t + timedelta(minutes=5)).timestamp()), 101.0, 99.0, 103.0, 101.0, 10],   # h < l
                        [int((t + timedelta(minutes=15)).timestamp()), 0.0, 1.0, 0.0, 0.5, 10]],       # price 0
                       columns=good.columns)
    m.write("NEO", pd.concat([good, bad]))
    raw = m.read_raw("NEO")
    assert list(raw["c"]) == [100.0, 102.0]
    assert (raw["h"] >= raw["l"]).all()
    assert m.bad_rows("NEO") == 2
