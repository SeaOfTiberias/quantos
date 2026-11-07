"""L1 price store (core/market_map/l1_store.py), NSE daily files (core/market_map/nse_daily.py)
and the refresh job's checks (scripts/run_l1_refresh.py), on synthetic data only."""

import io
import zipfile
from datetime import date

import numpy as np
import pandas as pd
import pytest

from core.market_map import nse_daily as nd
from core.market_map.l1_store import Store
from core.techno_funda.symbols import SymbolChain
from scripts import run_l1_refresh as job

NO_RENAMES = SymbolChain([])


def _day(rows):
    return pd.DataFrame(rows, columns=["sym", "series", "o", "h", "l", "c", "vol", "val"])


def _fill(store, sym, closes, start="2026-01-01", series="EQ", vals=None):
    dates = pd.bdate_range(start, periods=len(closes))
    for i, (d, c) in enumerate(zip(dates, closes)):
        v = vals[i] if vals is not None else 1e7
        store.append_day(_day([(sym, series, c, c * 1.01, c * 0.99, c, 1000, v)]), d.date())
    return dates


def test_append_keeps_full_precision_and_a_rerun_does_not_duplicate(tmp_path):
    s = Store(tmp_path)
    d = date(2026, 11, 6)
    row = _day([("ABC", "EQ", 12345.65, 12400.05, 12300.0, 12345.65, 123456789, 152345678901.5)])
    s.append_day(row, d)
    s.append_day(row, d)                       # a crashed run repeated
    g = s.read_raw("ABC")
    assert len(g) == 1
    assert g["c"].iat[0] == 12345.65 and g["val"].iat[0] == 152345678901.5


def test_actions_are_merged_once_per_ex_date_and_factor(tmp_path):
    s = Store(tmp_path)
    a = dict(sym="ABC", ex="2026-06-12", factor=0.75, purpose="BONUS 1:3", source="nse_pr")
    assert len(s.add_actions([a, a])) == 1
    assert s.add_actions([dict(a, purpose="Bonus 1:3", source="nse_api")]) == []
    assert len(s.add_actions([dict(a, ex="2026-06-13")])) == 1
    assert len(s.actions()["ABC"]) == 2


def test_a_listed_split_is_back_adjusted_without_a_segment_break(tmp_path):
    s = Store(tmp_path)
    dates = _fill(s, "ABC", [1000.0] * 5 + [100.0] * 5)
    s.add_actions([dict(sym="ABC", ex=dates[5].date().isoformat(), factor=0.1, purpose="FV split 10 to 1",
                        source="nse_pr")])
    a, gaps = s.adjusted("ABC")
    assert np.allclose(a["c"], 100.0) and np.allclose(a["raw_c"][:5], 1000.0)
    assert np.allclose(a["vol"][:5], 10000)            # volume scales the other way
    assert (a["seg"] == 0).all() and gaps == []


def test_an_unexplained_drop_starts_a_new_segment_and_is_logged(tmp_path):
    s = Store(tmp_path)
    _fill(s, "ABC", [1000.0] * 5 + [500.0] * 5)
    a, gaps = s.adjusted("ABC")
    assert list(a["seg"]) == [0] * 5 + [1] * 5
    assert len(gaps) == 1 and gaps[0]["move"] == pytest.approx(-0.5) and not gaps[0]["confirmed"]
    assert a["c"].iat[0] == 1000.0                     # prices stay continuous: P&L sees the drop


def test_universe_ranks_eq_stocks_traded_today_by_60_session_median(tmp_path):
    s = Store(tmp_path)
    dates = _fill(s, "BIG", [10.0] * 60, vals=[5e8] * 60)
    _fill(s, "MID", [10.0] * 60, vals=[1e8] * 59 + [9e9])      # one huge day doesn't move a median
    _fill(s, "HUGE", [10.0] * 59, vals=[9e9] * 59)              # too short
    _fill(s, "BEX", [10.0] * 60, vals=[9e9] * 60, series="BE")  # not EQ
    _fill(s, "OLD", [10.0] * 61, start="2025-12-31", vals=[9e9] * 61)
    s.append_day(_day([("BIG", "EQ", 10, 10, 10, 10, 1, 5e8)]), date(2026, 3, 26))  # BIG trades one more day
    u = s.universe(dates[-1].date(), top_n=2)
    assert [r["sym"] for r in u] == ["OLD", "MID"]     # BIG and OLD traded after; only rows ending on d count
    assert u[1]["med_val"] == 1e8


def test_renames_move_rows_dated_before_the_change_only(tmp_path):
    s = Store(tmp_path)
    s.append_day(_day([("OLDCO", "EQ", 10, 10, 10, 10, 1, 1)]), date(2026, 2, 27))
    s.append_day(_day([("OLDCO", "EQ", 20, 20, 20, 20, 1, 1)]), date(2026, 3, 3))   # a reused symbol
    s.append_day(_day([("NEWCO", "EQ", 11, 11, 11, 11, 1, 1)]), date(2026, 3, 2))
    s.add_actions([dict(sym="OLDCO", ex="2026-02-20", factor=0.5, purpose="BONUS 1:1", source="nse_api")])
    chain = SymbolChain([("OLDCO", "NEWCO", date(2026, 3, 1))])
    moved = s.apply_renames(chain)
    assert moved == [("OLDCO", "NEWCO", 1)]
    assert list(s.read_raw("NEWCO")["c"]) == [10, 11]
    assert list(s.read_raw("OLDCO")["c"]) == [20]
    assert "OLDCO" not in s.actions() and s.actions()["NEWCO"][0]["factor"] == 0.5


@pytest.mark.parametrize("purpose,factor", [
    ("FVSPLT FRM RS 10 TO RE 1", 0.1),
    ("FV SPLT FRM RS 5 TO RE 1", 0.2),
    ("FV SPLIT RS.10/- TO RS.2/-", 0.2),
    ("BONUS 1:3", 0.75),
    ("BONUS 1:1/FV SPLT FRM RS 10 TO RS 5", 0.25),
    ("INTEREST PAYMENT", None),
    ("DIVIDEND - RS 5 PER SHARE", None),
    ("BONUS DEBENTURE 1:1", None),
])
def test_pr_purposes_map_to_the_panel_factor_rule(purpose, factor):
    got = nd.purpose_factor(purpose)
    assert (got is None and factor is None) or got == pytest.approx(factor)


def _pr_zip(lines):
    head = "SERIES,SYMBOL,SECURITY,RECORD_DT,BC_STRT_DT,BC_END_DT,EX_DT,ND_STRT_DT,ND_END_DT,PURPOSE"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("bc06112026.csv", "\n".join([head] + lines))
        z.writestr("pd06112026.csv", "x")
    return buf.getvalue()


def test_pr_bundle_keeps_equity_splits_and_bonuses_once():
    body = _pr_zip([
        "EQ,ABC,Abc Ltd,2026-06-12,,,2026-06-12,,,BONUS 1:3",
        "BE,ABC,Abc Ltd,2026-06-12,,,2026-06-12,,,BONUS 1:3",
        "BL,ABC,Abc Ltd,2026-06-12,,,2026-06-12,,,BONUS 1:3",
        "EQ,OLDX,Xyz Ltd,2026-11-06,,,2026-11-06,,,FV SPLT FRM RS 5 TO RE 1",
        "N1,BOND1,Ncd,2026-11-09,,,2026-11-09,,,INTEREST PAYMENT",
    ])
    rows = nd.parse_pr_actions(body, SymbolChain([("OLDX", "NEWX", date(2026, 12, 1))]))
    assert [(r["sym"], r["ex"], r["factor"]) for r in rows] == [("ABC", "2026-06-12", 0.75),
                                                                ("NEWX", "2026-11-06", pytest.approx(0.2))]
    assert all(r["source"] == "nse_pr" for r in rows)


def test_pr_bundle_with_an_unknown_header_fails_loudly():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("bc01012026.csv", "A,B\n1,2")
    with pytest.raises(ValueError):
        nd.parse_pr_actions(buf.getvalue(), NO_RENAMES)


def test_bhavcopy_day_reads_the_new_format_under_canonical_symbols(tmp_path, monkeypatch):
    head = "TradDt,FinInstrmTp,TckrSymb,SctySrs,OpnPric,HghPric,LwPric,ClsPric,TtlTradgVol,TtlTrfVal"
    lines = ["2026-11-06,STK,OLDX,EQ,10,11,9,10.5,100,1050",
             "2026-11-06,STK,NIFTYBEES,EQ,1,1,1,1,1,1",
             "2026-11-06,STK,ABC,BE,5,5,5,5,1,5",
             "2026-11-06,FUT,ABC,EQ,5,5,5,5,1,5"]
    p = tmp_path / "cm.zip"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("x.csv", "\n".join([head] + lines))
    monkeypatch.setattr(nd, "fetch_to", lambda url, path: p)
    df = nd.bhavcopy_day(tmp_path, date(2026, 11, 6), SymbolChain([("OLDX", "NEWX", date(2026, 12, 1))]))
    assert sorted(df["sym"]) == ["ABC", "NEWX"]
    assert df.set_index("sym").loc["NEWX", "c"] == 10.5 and df.set_index("sym").loc["ABC", "series"] == "BE"


def test_catch_up_tries_every_weekday_after_the_last_session():
    assert job.weekdays_after(date(2026, 11, 5), date(2026, 11, 10)) == [
        date(2026, 11, 6), date(2026, 11, 9), date(2026, 11, 10)]
    assert job.weekdays_after(date(2026, 11, 6), date(2026, 11, 6)) == []


def test_fyers_ratio_check_flags_a_missed_split_at_its_date():
    dates = pd.bdate_range("2026-01-01", periods=40)
    ours = pd.DataFrame({"date": dates, "c": np.linspace(100, 120, 40)})
    flat = [(d.date(), c * 1.001) for d, c in zip(dates, ours["c"])]
    assert job.ratio_check(ours, flat) is None
    stepped = [(d.date(), c * (0.5 if i < 25 else 1.0)) for i, (d, c) in enumerate(zip(dates, ours["c"]))]
    res = job.ratio_check(ours, stepped)
    assert res["status"] == "mismatch" and res["step_date"] == dates[25].date().isoformat()
    assert job.ratio_check(ours.head(5), flat)["status"] == "too_few_dates"
