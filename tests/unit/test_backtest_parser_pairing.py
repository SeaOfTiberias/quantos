"""TradingView exports list a trade's Exit row before its Entry row: pair by trade number (2026-11-27 fix)."""

import pytest

from core.backtest.parser import _parse_trades

HDR = ("Trade number,Type,Date and time,Signal,Price INR,Size (qty),Size (value),Net PnL INR,Return %,"
       "Favorable excursion INR,Favorable excursion %,Adverse excursion INR,Adverse excursion %,"
       "Cumulative PnL INR,Cumulative PnL %,Duration (bars)\n")
EXIT_FIRST = HDR + (
    "1,Exit long,2023-07-04 12:45,Exit,28.5,3508,99978,0,0.00,1,1,1,1,0,0.00,9\n"
    "1,Entry long,2023-07-04 10:30,Long,28.5,3508,99978,0,0.00,1,1,1,1,0,0.00,9\n"
    "2,Exit long,2023-07-07 09:45,Exit,28.55,3401,99819.35,-2720.8,-2.73,1,1,1,1,-2720.8,-2.72,28\n"
    "2,Entry long,2023-07-06 09:30,Long,29.35,3401,99819.35,-2720.8,-2.73,1,1,1,1,-2720.8,-2.72,28\n"
    "3,Exit long,,Open,30,100,3000,0,0,1,1,1,1,0,0,1\n"
    "3,Entry long,2023-07-10 09:30,Long,30,100,3000,0,0,1,1,1,1,0,0,1\n")


def test_exit_first_rows_pair_by_trade_number():
    t = _parse_trades(EXIT_FIRST)
    assert [x.trade_num for x in t] == [1, 2]                      # trade 3 has no parseable exit: skipped
    a, b = t
    assert (a.entry_price, a.exit_price, a.profit_pct) == (28.5, 28.5, 0.0)
    assert (b.entry_price, b.exit_price, b.profit_pct, b.qty) == (29.35, 28.55, -2.73, 3401)
    assert b.entry_date.day == 6 and b.exit_date.day == 7


def test_entry_first_and_no_number_column_still_work():
    entry_first = HDR + (
        "1,Entry long,2023-07-04 10:30,Long,28.5,3508,99978,0,0.00,1,1,1,1,0,0.00,9\n"
        "1,Exit long,2023-07-04 12:45,Exit,29.0,3508,99978,1754,1.75,1,1,1,1,0,0.00,9\n")
    assert [(x.entry_price, x.exit_price) for x in _parse_trades(entry_first)] == [(28.5, 29.0)]
    no_num = "Type,Date/Time,Price,Contracts,Profit,Profit %\nEntry Long,2023-07-04,10,1,0,0\nExit Long,2023-07-05,11,1,1,10\n"
    assert [(x.entry_price, x.exit_price, x.profit_pct) for x in _parse_trades(no_num)] == [(10.0, 11.0, 10.0)]
