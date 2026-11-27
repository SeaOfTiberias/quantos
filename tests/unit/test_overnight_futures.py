"""E3 overnight measurement + index futures bhavcopy parser -- synthetic data only."""

from datetime import date, timedelta

import pytest

from core.fno import bhavcopy_futures as bf
from scripts import measure_overnight_futures as mo

LEGACY = (
    "INSTRUMENT,SYMBOL,EXPIRY_DT,STRIKE_PR,OPTION_TYP,OPEN,HIGH,LOW,CLOSE,SETTLE_PR,CONTRACTS,VAL_INLAKH,OPEN_INT,CHG_IN_OI,TIMESTAMP,\n"
    "FUTIDX,NIFTY,28-Feb-2019,0,XX,10920,10945.9,10870.1,10909.6,10909.6,105474,1,21781800,0,11-FEB-2019,\n"
    "FUTIDX,NIFTY,28-Mar-2019,0,XX,10950,10970,10900,10940,10940,900,1,30000,0,11-FEB-2019,\n"
    "FUTIDX,FINNIFTY,28-Feb-2019,0,XX,1,1,1,1,1,1,1,1,0,11-FEB-2019,\n"
    "OPTIDX,NIFTY,28-Feb-2019,11000,CE,50,60,40,55,55,10,1,100,0,11-FEB-2019,\n"
    "FUTSTK,TCS,28-Feb-2019,0,XX,2000,2010,1990,2005,2005,10,1,100,0,11-FEB-2019,\n")

NEW = (
    "TradDt,BizDt,Sgmt,Src,FinInstrmTp,FinInstrmId,ISIN,TckrSymb,SctySrs,XpryDt,FininstrmActlXpryDt,StrkPric,OptnTp,"
    "FinInstrmNm,OpnPric,HghPric,LwPric,ClsPric,LastPric,PrvsClsgPric,UndrlygPric,SttlmPric,OpnIntrst,ChngInOpnIntrst,"
    "TtlTradgVol,TtlTrfVal,TtlNbOfTxsExctd,SsnId,NewBrdLotQty,Rmks,Rsvd1,Rsvd2,Rsvd3,Rsvd4\n"
    "2026-11-12,2026-11-12,FO,NSE,IDF,1,,BANKNIFTY,,2026-11-23,2026-11-23,,,X,60710.00,61436.60,60578.00,61337.60,61290.00,"
    "60637.80,61518.50,61337.60,2196990,0,28994,1,1,F1,30,,,,,\n"
    "2026-11-12,2026-11-12,FO,NSE,IDO,2,,NIFTY,,2026-11-17,2026-11-17,25000,CE,X,1,1,1,1,1,1,1,1,1,0,1,1,1,F1,65,,,,,\n")


def test_parse_legacy_keeps_index_futures_only():
    rows = bf.parse_csv(LEGACY, date(2019, 2, 11))
    assert [(r.symbol, r.expiry) for r in rows] == [("NIFTY", date(2019, 2, 28)), ("NIFTY", date(2019, 3, 28))]
    r = rows[0]
    assert (r.open, r.close, r.volume, r.oi, r.last, r.lot_size) == (10920, 10909.6, 105474, 21781800, None, None)


def test_parse_new_format_by_header_with_last_and_lot():
    rows = bf.parse_csv(NEW, date(2026, 11, 12))
    assert len(rows) == 1
    r = rows[0]
    assert r.symbol == "BANKNIFTY" and r.expiry == date(2026, 11, 23)
    assert (r.open, r.close, r.last, r.lot_size) == (60710.0, 61337.6, 61290.0, 30)


def test_contract_after_skips_the_expiring_one():
    rows = bf.parse_csv(LEGACY, date(2019, 2, 28))
    assert bf.contract_after(rows, "NIFTY", date(2019, 2, 27)).expiry == date(2019, 2, 28)
    assert bf.contract_after(rows, "NIFTY", date(2019, 2, 28)).expiry == date(2019, 3, 28)   # expiry day: next month
    assert bf.contract_after(rows, "BANKNIFTY", date(2019, 2, 27)) is None


def _row(d, exp, o, c, sym="NIFTY"):
    return bf.FutRow(d, sym, exp, o, o, c, c, None, 1, 1, None)


def test_nights_same_contract_and_no_bridging():
    d1, d2, d3, d5 = date(2019, 3, 25), date(2019, 3, 26), date(2019, 3, 27), date(2019, 3, 29)
    e1, e2 = date(2019, 3, 28), date(2019, 4, 25)
    data = {
        d1: [_row(d1, e1, 100, 101), _row(d1, e2, 200, 202)],
        d2: [_row(d2, e1, 102, 103), _row(d2, e2, 204, 205)],
        d3: [_row(d3, e1, 104, 105), _row(d3, e2, 206, 207)],
        d5: [_row(d5, e2, 210, 211)],                                   # 03-28 file missing
    }
    nxt = lambda d: d + timedelta(days=1)                              # every weekday a session here
    ns = mo.nights(data, "NIFTY", nxt)
    assert [(n.d, n.nxt) for n in ns] == [(d1, d2), (d2, d3)]           # d3 -> d5 skips a session: not bridged
    assert ns[0].expiry == e1 and ns[0].overnight == pytest.approx(102 / 101 - 1)
    assert ns[0].intraday == pytest.approx(101 / 100 - 1)


def test_round_trip_cost_2026_is_mostly_stt():
    c = mo.round_trip_bps(25000.0, 65, date(2026, 4, 1), 0.0)
    assert 5.0 < c < 6.5                                                 # 5 bps STT + ~0.5 bps charges
    assert mo.round_trip_bps(25000.0, 65, date(2023, 1, 2), 0.0) < 2.5  # 0.0125% STT then
    assert mo.round_trip_bps(25000.0, 65, date(2026, 4, 1), 3.0) == pytest.approx(c + 3.0)


def test_verdict_alive_dead_and_halves():
    def mk(d, bps):
        return mo.Night("NIFTY", d, d + timedelta(days=1), d, 100.0, 100.0, 100.0 * (1 + bps / 1e4), None, None)
    days = [date(2019, 3, 1) + timedelta(days=i) for i in range(0, 2900, 2)]
    zero = lambda n: 0.0
    alive = [mk(d, 10 + (5 if i % 2 else -5)) for i, d in enumerate(days)]
    assert mo.verdict(alive, zero)["alive"]
    flip = [mk(d, (10 if d < mo.HALF_SPLIT else -2) + (5 if i % 2 else -5)) for i, d in enumerate(days)]
    v = mo.verdict(flip, zero)
    assert v["full"]["net"] > 0 and not v["alive"] and v["h2"]["net"] < 0
    assert not mo.verdict(alive, lambda n: 20.0)["alive"]              # costs above the premium


def test_nights_skip_special_weekend_sessions():
    fri, sat, mon = date(2024, 3, 1), date(2024, 3, 2), date(2024, 3, 4)
    e = date(2024, 3, 28)
    data = {fri: [_row(fri, e, 100, 101)], sat: [_row(sat, e, 101, 102)], mon: [_row(mon, e, 103, 104)]}
    nxt = {fri: sat, sat: mon}.get
    assert mo.nights(data, "NIFTY", nxt) == []                          # Fri->Sat and Sat->Mon both excluded
