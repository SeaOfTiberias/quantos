"""core/position_manager/rules.py -- Breeze futures rows, the plan, and its checks."""

from datetime import date

from core.position_manager.rules import (
    MAX_SESSIONS, FutPosition, Plan, check_close, check_intraday, make_plan, parse_future, update_trail,
)

D = date(2026, 10, 22)


def test_parse_breeze_futures_rows():
    row = {"stock_code": "TCS", "action": "Buy", "quantity": "225", "average_price": "2515",
           "product_type": "Futures", "expiry_date": "23-Nov-2026", "right": "Others", "strike_price": "0"}
    p = parse_future(row)
    assert p == FutPosition("TCS", date(2026, 11, 23), 225, 2515.0) and p.side == 1
    short = parse_future({**row, "action": "Sell", "average_price": None, "average_cost": "334"})
    assert short.qty == -225 and short.avg_price == 334.0 and short.side == -1
    assert parse_future({**row, "product_type": "Options"}) is None
    assert parse_future({**row, "quantity": "0"}) is None


def test_tested_plan_levels_long_and_short():
    p = make_plan(FutPosition("TCS", date(2026, 11, 23), 225, 2520.0), "TCS", 80.0, D)
    assert (p.stop, p.emergency, p.target, p.source) == (2460.0, 2380.0, 2580.0, "tested")
    s = make_plan(FutPosition("POWFIN", date(2026, 11, 23), -1300, 334.0), "PFC", 8.8, D)
    assert (s.stop, s.emergency, s.target) == (340.6, 349.4, 327.4)


def test_override_levels_and_no_atr():
    p = make_plan(FutPosition("TCS", date(2026, 11, 23), 225, 2515.0), "TCS", 80.0, D, {"stop": 2495, "target": 2614})
    assert (p.stop, p.target, p.emergency, p.source) == (2495.0, 2614.0, 2415.0, "override")
    q = make_plan(FutPosition("TCS", date(2026, 11, 23), 225, 2515.0), "TCS", None, D)
    assert q.emergency is None and q.target is None


def test_intraday_touches_alert_once():
    p = make_plan(FutPosition("TCS", date(2026, 11, 23), 225, 2520.0), "TCS", 80.0, D)
    assert check_intraday(p, 2500.0) == []                          # a dip above the emergency is noise
    assert [e.kind for e in check_intraday(p, 2581.0)] == ["TARGET"]
    assert check_intraday(p, 2590.0) == []                          # once
    s = make_plan(FutPosition("POWFIN", date(2026, 11, 23), -1300, 334.0), "PFC", 8.8, D)
    assert [e.kind for e in check_intraday(s, 350.0)] == ["EMERGENCY"]


def test_daily_close_check():
    p = make_plan(FutPosition("TCS", date(2026, 11, 23), 225, 2515.0), "TCS", 80.0, D, {"stop": 2495, "target": 2614})
    # 22 Oct: intraday low 2479 but the close 2506.9 is above the stop -> HOLD (the TCS lesson)
    assert check_intraday(p, 2479.0) == []
    ev = check_close(p, 2506.9, D, 1)
    assert ev.kind == "HOLD" and "session 1 of" in ev.detail and p.last_check == D.isoformat()
    assert check_close(p, 2490.0, D, 2).kind == "CLOSE"
    assert check_close(p, 2550.0, D, MAX_SESSIONS).kind == "TIME"
    assert check_close(p, 2550.0, date(2026, 11, 23), 3).kind == "TIME"   # expiry day


def test_state_round_trip():
    p = make_plan(FutPosition("TCS", date(2026, 11, 23), 225, 2520.0), "TCS", 80.0, D)
    p.sent.append("target")
    assert Plan.from_dict(p.to_dict()) == p


def test_profit_stop_ratchets_and_never_loosens():
    s = make_plan(FutPosition("POWFIN", date(2026, 11, 23), -1300, 334.0), "PFC", 8.8, D)   # short, 1R = 6.6
    assert update_trail(s, 331.0) is None and s.trail is None and s.best == 331.0          # +0.45R: nothing yet
    assert update_trail(s, 330.7) == 333.34                                                # +0.5R: entry +0.1R
    assert update_trail(s, 331.5) is None and s.best == 330.7                              # a bounce doesn't loosen it
    assert update_trail(s, 329.05) == 332.35                                               # +0.75R: entry +0.25R
    assert update_trail(s, 328.0) is None                                                  # no rung past 0.75R
    lng = make_plan(FutPosition("TCS", date(2026, 11, 23), 225, 2520.0), "TCS", 80.0, D)   # long, 1R = 60
    assert update_trail(lng, 2550.0) == 2526.0
    assert update_trail(make_plan(FutPosition("X", date(2026, 11, 23), 100, 10.0), "X", None, D), 12.0) is None


def test_profit_stop_touch_alerts_once():
    s = make_plan(FutPosition("POWFIN", date(2026, 11, 23), -1300, 334.0), "PFC", 8.8, D)
    update_trail(s, 330.0)
    assert check_intraday(s, 333.0) == []
    assert [e.kind for e in check_intraday(s, 333.4)] == ["TRAIL"]
    assert check_intraday(s, 333.6) == []


def test_old_state_without_trail_fields_loads():
    d = make_plan(FutPosition("TCS", date(2026, 11, 23), 225, 2520.0), "TCS", 80.0, D).to_dict()
    del d["best"], d["trail"]
    p = Plan.from_dict(d)
    assert p.best is None and p.trail is None
