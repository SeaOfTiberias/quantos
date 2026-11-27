"""E1 results-day straddle: events, timing, stock-option reader, trade build, verdict -- synthetic only."""

from datetime import date, datetime, timedelta

import pytest

from core.fno import bhavcopy_futures as bf
from core.fno import bhavcopy_options as bo
from core.fno import results_events as rev
from scripts import measure_results_straddle as mr


def test_first_broadcast_per_symbol_and_period():
    f = [
        {"symbol": "ABC", "toDate": "30-Jun-2021", "broadCastDate": "31-Jul-2021 17:33:50"},
        {"symbol": "ABC", "toDate": "30-Jun-2021", "broadCastDate": "31-Jul-2021 16:10:00"},   # earlier basis
        {"symbol": "ABC", "toDate": "30-Sep-2021", "broadCastDate": "02-Nov-2021 09:00"},
        {"symbol": "", "toDate": "30-Jun-2021", "broadCastDate": "31-Jul-2021 10:00:00"},
        {"symbol": "XYZ", "toDate": "bad", "broadCastDate": "31-Jul-2021 10:00:00"},
    ]
    ev = rev.events_from_filings(f)
    assert [(e.symbol, e.period_end, e.broadcast) for e in ev] == [
        ("ABC", date(2021, 6, 30), datetime(2021, 7, 31, 16, 10)),
        ("ABC", date(2021, 9, 30), datetime(2021, 11, 2, 9, 0))]


def test_pre_and_reaction_sessions():
    s = [date(2021, 8, 2), date(2021, 8, 3), date(2021, 8, 4), date(2021, 8, 6)]     # 08-05 a holiday
    assert rev.pre_and_reaction(datetime(2021, 8, 3, 17, 0), s) == (date(2021, 8, 3), date(2021, 8, 4))   # after close
    assert rev.pre_and_reaction(datetime(2021, 8, 3, 12, 0), s) == (date(2021, 8, 2), date(2021, 8, 3))   # during hours
    assert rev.pre_and_reaction(datetime(2021, 8, 3, 8, 0), s) == (date(2021, 8, 2), date(2021, 8, 3))    # before open
    assert rev.pre_and_reaction(datetime(2021, 8, 5, 18, 0), s) == (date(2021, 8, 4), date(2021, 8, 6))   # holiday
    assert rev.pre_and_reaction(datetime(2021, 8, 6, 18, 0), s) is None                                    # no R in range


LEGACY = (
    "INSTRUMENT,SYMBOL,EXPIRY_DT,STRIKE_PR,OPTION_TYP,OPEN,HIGH,LOW,CLOSE,SETTLE_PR,CONTRACTS,VAL_INLAKH,OPEN_INT,CHG_IN_OI,TIMESTAMP,\n"
    "OPTSTK,TCS,30-Sep-2021,3000,CE,0,0,0,830.75,812,0,0,0,0,31-AUG-2021,\n"
    "OPTSTK,TCS,30-Sep-2021,3000,PE,10,12,9,11,11,40,0,500,0,31-AUG-2021,\n"
    "OPTSTK,TCS,30-Sep-2021,3100,CE,60,70,50,65,65,90,0,800,0,31-AUG-2021,\n"
    "OPTSTK,TCS,30-Sep-2021,3100,PE,40,45,35,42,42,80,0,700,0,31-AUG-2021,\n"
    "OPTSTK,INFY,30-Sep-2021,1700,CE,10,10,10,10,10,5,0,5,0,31-AUG-2021,\n"
    "FUTSTK,TCS,30-Sep-2021,0,XX,3080,3100,3070,3090,3090,1000,0,9000,0,31-AUG-2021,\n"
    "OPTIDX,NIFTY,30-Sep-2021,17000,CE,1,1,1,1,1,1,0,1,0,31-AUG-2021,\n")


def test_stock_option_reader_and_atm_needs_both_legs_traded():
    rows = bo.parse_csv(LEGACY, date(2021, 8, 31), {"TCS"})
    assert {(r.strike, r.opt) for r in rows} == {(3000, "CE"), (3000, "PE"), (3100, "CE"), (3100, "PE")}
    # 3000 is nearer 3040 but its call didn't trade: 3100 is the straddle
    k, c, p = bo.atm_straddle(rows, "TCS", date(2021, 9, 30), 3040.0)
    assert k == 3100 and c.close == 65 and p.close == 42
    assert len(bo.parse_csv(LEGACY, date(2021, 8, 31))) == 5                      # all stocks
    fut = bf.parse_csv(LEGACY, date(2021, 8, 31), {"TCS"}, kind="stock")
    assert [(f.symbol, f.close) for f in fut] == [("TCS", 3090.0)]


def _o(d, s, e, k, t, c, v=10):
    return bo.OptRow(d, s, e, k, t, c, c, v, 1, None)


def _f(d, s, e, c):
    return bf.FutRow(d, s, e, c, c, c, c, None, 1, 1, None)


def test_build_trade_and_reasons():
    p, r, e = date(2021, 7, 30), date(2021, 8, 2), date(2021, 8, 26)
    day = {p: ([_f(p, "ABC", e, 1005)], [_o(p, "ABC", e, 1000, "CE", 30), _o(p, "ABC", e, 1000, "PE", 25),
                                         _o(p, "ABC", e, 1100, "CE", 5), _o(p, "ABC", e, 1100, "PE", 90)]),
           r: ([_f(r, "ABC", e, 1040)], [_o(r, "ABC", e, 1000, "CE", 45), _o(r, "ABC", e, 1000, "PE", 6)])}
    t, why = mr.build_trade("ABC", p, r, day)
    assert why == "ok" and t.strike == 1000 and t.s_p == 55 and t.s_r == 51
    assert t.gross_bps == pytest.approx(4 / 1005 * 1e4) and t.realized_move == pytest.approx(35 / 1005)
    day[r] = (day[r][0], [_o(r, "ABC", e, 1000, "CE", 45), _o(r, "ABC", e, 1000, "PE", 6, v=0)])
    assert mr.build_trade("ABC", p, r, day) == (None, "straddle not traded at R")
    assert mr.build_trade("XYZ", p, r, day)[1] == "not in F&O"
    day2 = {p: ([_f(p, "ABC", r, 1005)], []), r: ([], [])}                  # future expires at R: excluded
    assert mr.build_trade("ABC", p, r, day2)[1] == "not in F&O"


def test_cost_2026_and_spread():
    t = mr.Trade("ABC", date(2026, 5, 4), date(2026, 5, 5), date(2026, 5, 26), 1000.0, 1000.0, 1000, 50.0, 40.0)
    c0 = mr.cost_bps(t, 0.0)
    assert 0.9 < c0 < 1.5                                   # ~0.15% STT on 50 + small charges, on spot 1000
    assert mr.cost_bps(t, 0.01) == pytest.approx(c0 + 0.01 * 90 / 1000 * 1e4)


def test_plan_controls_avoid_other_events():
    sessions = [date(2021, 1, 4) + timedelta(days=i) for i in range(200) if (date(2021, 1, 4) + timedelta(days=i)).weekday() < 5]
    e1 = rev.Event("ABC", date(2021, 3, 31), datetime.combine(sessions[40], datetime.min.time()).replace(hour=18))
    e2 = rev.Event("ABC", date(2021, 6, 30), datetime.combine(sessions[48], datetime.min.time()).replace(hour=18))
    rows, need = mr.plan([e1, e2], sessions)
    (_, pr1, c1), (_, pr2, c2) = rows
    assert pr1 == (sessions[40], sessions[41]) and c1 == (sessions[30], sessions[31])
    assert c2 is None                                        # 10 back = session 38, within 5 of e1


def test_verdict_alive_and_control():
    def tr(d, sp, sr):
        return mr.Trade("A", d, d + timedelta(days=1), d + timedelta(days=20), 1000.0, 1000.0, 1000, sp, sr)
    days = [date(2019, 3, 1) + timedelta(days=3 * i) for i in range(900)]
    ev = [tr(d, 60.0, 40.0 + (i % 7)) for i, d in enumerate(days)]
    ctl = [tr(d, 30.0, 29.0 + (i % 3) * 0.5) for i, d in enumerate(days)]
    v = mr.verdict(ev, list(zip(ev, ctl)), 0.0)
    assert v["alive"] and all(v["checks"].values())
    flat = [tr(d, 50.0, 50.0 + (1 if i % 2 else -1)) for i, d in enumerate(days)]
    assert not mr.verdict(flat, list(zip(flat, flat)), 0.0)["alive"]


def test_integrated_filing_schema_merges_with_the_old_one():
    f = [{"symbol": "ABC", "toDate": "31-Mar-2025", "broadCastDate": "02-May-2025 18:00:00"},
         {"symbol": "ABC", "qe_Date": "31-MAR-2025", "broadcast_Date": "02-May-2025 17:10:05"},   # same period, earlier
         {"symbol": "ABC", "qe_Date": "30-JUN-2025", "broadcast_Date": "29-Aug-2025 18:04:23"}]
    ev = rev.events_from_filings(f)
    assert [(e.period_end, e.broadcast) for e in ev] == [
        (date(2025, 3, 31), datetime(2025, 5, 2, 17, 10, 5)), (date(2025, 6, 30), datetime(2025, 8, 29, 18, 4, 23))]
