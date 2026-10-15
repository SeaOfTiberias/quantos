"""Unit tests for core/surge/spreads.py and options.py (docs/SURGE_SPREAD_STAGE2_METHODOLOGY.md)."""

import io
import zipfile
from datetime import date, timedelta

import pandas as pd
import pytest

from core.pairs.backtest import FuturesDay
from core.statarb.residuals import build_panel
from core.surge.events import SurgeEvent
from core.surge.options import parse_ce_rows
from core.surge.spreads import (
    bidask_cost, build_trades, run_stage2, statutory_cost, stt_sell_rate,
)


def _days(n, start=date(2024, 3, 1)):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


DAYS = _days(30)
EXPIRY_NEAR = DAYS[3]      # too close (< 5 trading days) -> skipped
EXPIRY = DAYS[20]


def _panel(s_entry=1000.0, s_exit=1060.0):
    prices = [s_entry] * 10 + [s_exit] * 20
    return build_panel({"AAA": [FuturesDay(d, p, 100, EXPIRY, adj_close=p) for d, p in zip(DAYS, prices)]})


def _row(d, k, close, contracts=10, settle=None, expiry=EXPIRY, lot=100):
    return dict(trade_date=d, symbol="AAA", expiry=expiry, strike=k, close=close,
                settle=close if settle is None else settle, contracts=contracts, lot=lot)


def _event(t=2):
    return SurgeEvent("AAA", t, DAYS[t], 0.06, {}, {}, {"results": False, "breakout52": False,
                                                       "big_z": True, "market_day": False, "extended": False})


def _rows(exit_overrides=None):
    rows = []
    entry, exit_ = DAYS[2], DAYS[10]   # hold 8 trading days
    strikes = [960, 980, 1000, 1020, 1040, 1060, 1080, 1100]
    for k in strikes:
        rows.append(_row(entry, k, max(1000 - k, 0) + 15))
        rows.append(_row(entry, k, 30, expiry=EXPIRY_NEAR))
        v = max(1060 - k, 0) + 8
        rows.append(_row(exit_, k, v, **(exit_overrides or {}).get(k, {})))
    return pd.DataFrame(rows)


def test_zero_debit_structures_are_skipped():
    # base rows price every OTM strike at 15, so any OTM pair has debit 0
    trades, skips = build_trades(_panel(), [_event()], _rows(), cutoff=date(2030, 1, 1))
    assert not any(x.structure == "L0W2" for x in trades)   # long 1000 @ 15, short 1040 @ 15
    assert skips["L0W2: debit outside (0, width)"] == 1


def test_debit_validity_and_values():
    rows = _rows()
    # make premiums decay with strike so debits are positive
    rows.loc[(rows.trade_date == DAYS[2]) & (rows.expiry == EXPIRY), "close"] = \
        rows.loc[(rows.trade_date == DAYS[2]) & (rows.expiry == EXPIRY), "strike"].map(
            lambda k: max(1000 - k, 0) + 40 - (k - 960) * 0.3)
    trades, skips = build_trades(_panel(), [_event()], rows, cutoff=date(2030, 1, 1))
    t = next(x for x in trades if x.structure == "L1W1")   # long 1020, short 1040
    assert t.debit == pytest.approx((40 - 60 * 0.3) - (40 - 80 * 0.3))
    assert t.gross == pytest.approx((48 - 28) - t.debit)
    assert t.exit_fallback == ""
    assert not any("expiry" in k for k in skips)   # near expiry ignored, not a skip


def test_untraded_leg_skips_structure_and_exit_fallbacks():
    rows = _rows(exit_overrides={1020: {"contracts": 0, "settle": 47.0}})
    rows.loc[(rows.trade_date == DAYS[2]) & (rows.expiry == EXPIRY), "close"] = \
        rows.loc[(rows.trade_date == DAYS[2]) & (rows.expiry == EXPIRY), "strike"].map(
            lambda k: max(1000 - k, 0) + 40 - (k - 960) * 0.3)
    rows = rows[~((rows.trade_date == DAYS[10]) & (rows.strike == 1040))]   # no exit row at all
    rows.loc[(rows.trade_date == DAYS[2]) & (rows.strike == 1100) & (rows.expiry == EXPIRY), "contracts"] = 0
    trades, skips = build_trades(_panel(), [_event()], rows, cutoff=date(2030, 1, 1))
    t = next(x for x in trades if x.structure == "L1W1")
    assert t.exit_fallback == "settle"                  # long leg valued at settle 47
    assert t.gross == pytest.approx((47 - 20) - t.debit)  # short leg 1040 -> intrinsic 1060-1040
    assert any("untraded" in k for k in skips)


def test_costs():
    assert stt_sell_rate(date(2023, 1, 1)) == 0.0005 and stt_sell_rate(date(2026, 5, 1)) == 0.0015
    assert bidask_cost((10, 2, 12, 1), 0.0) == 0
    assert bidask_cost((10, 2, 12, 1), 0.02) == pytest.approx(0.2 + 0.05 + 0.24 + 0.05)
    c = statutory_cost(10, 5, 12, 6, 100, date(2025, 1, 1), date(2025, 1, 9))
    assert 0.8 < c < 1.0   # dominated by ₹80 brokerage spread over 100 shares


def test_run_stage2_picks_on_mining_only():
    rows = _rows()
    rows.loc[(rows.trade_date == DAYS[2]) & (rows.expiry == EXPIRY), "close"] = \
        rows.loc[(rows.trade_date == DAYS[2]) & (rows.expiry == EXPIRY), "strike"].map(
            lambda k: max(1000 - k, 0) + 40 - (k - 960) * 0.3)
    res = run_stage2(_panel(), [_event()], rows, cutoff=date(2030, 1, 1))
    assert res.chosen is None and res.verdict == "FAIL"   # 1 trade < 100 mining minimum


def test_parse_legacy_ce_rows():
    csv_text = (
        "INSTRUMENT,SYMBOL,EXPIRY_DT,STRIKE_PR,OPTION_TYP,OPEN,HIGH,LOW,CLOSE,SETTLE_PR,"
        "CONTRACTS,VAL_INLAKH,OPEN_INT,CHG_IN_OI,TIMESTAMP,\n"
        "OPTSTK,ZOMATO,24-Jun-2021,100,CE,1,1,1,5.5,5.6,12,0,0,0,10-JUN-2021,\n"
        "OPTSTK,ZOMATO,24-Jun-2021,100,PE,1,1,1,2.0,2.0,3,0,0,0,10-JUN-2021,\n"
        "OPTSTK,INFY,24-Jun-2021,1500,CE,1,1,1,9.0,9.0,1,0,0,0,10-JUN-2021,\n"
        "FUTSTK,ZOMATO,24-Jun-2021,0,XX,1,1,1,120,120,1,0,0,0,10-JUN-2021,\n"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("fo.csv", csv_text)
    df = parse_ce_rows(buf.getvalue(), date(2021, 6, 10), {"ETERNAL"})
    assert len(df) == 1
    r = df.iloc[0]
    assert r.symbol == "ETERNAL" and r.strike == 100 and r.close == 5.5 and r.contracts == 12
    assert r.expiry == date(2021, 6, 24)
