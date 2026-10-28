"""core/price_map/levels.py -- pivots, swings, volume profile, zones; synthetic bars only."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from pytest import approx

from core.price_map.levels import (
    Level, camarilla, classical, first_obstacle, naked_pocs, periods, pivot_levels, profile,
    sessions, shelves, swing_levels, value_area, volume_levels, zones,
)


@dataclass
class Bar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


def day(d: date, h, l, c, v=1000):
    return Bar(datetime(d.year, d.month, d.day, 4, 0, tzinfo=timezone.utc), c, h, l, c, v)


def five(d: date, minute, h, l, v):
    t = datetime(d.year, d.month, d.day, 3, 45, tzinfo=timezone.utc) + timedelta(minutes=minute)
    return Bar(t, l, h, l, h, v)


def test_classical_and_camarilla():
    assert classical(110, 90, 100) == approx({"P": 100, "S1": 90, "S2": 80, "S3": 70, "R1": 110, "R2": 120, "R3": 130})
    assert camarilla(110, 90, 100) == approx({"L3": 94.5, "L4": 89, "H3": 105.5, "H4": 111})


def test_periods_use_completed_bars_only():
    bars = [day(date(2026, 9, 30), 120, 80, 100),                      # September
            day(date(2026, 10, 19), 111, 101, 105), day(date(2026, 10, 23), 115, 99, 110),   # week of 19 Oct
            day(date(2026, 10, 27), 108, 104, 106), day(date(2026, 10, 28), 200, 1, 2)]       # today: ignored
    p = periods(bars, date(2026, 10, 28))
    assert p == {"daily": (108, 104, 106), "weekly": (115, 99, 110), "monthly": (120, 80, 100)}
    labels = {lv.label for lv in pivot_levels(bars, date(2026, 10, 28))}
    assert {"weekly S2", "monthly P", "daily Camarilla L4"} <= labels


def test_swing_lows_and_highs():
    d0 = date(2026, 1, 1)
    lows = [10, 9, 8, 7, 6, 5, 6, 7, 8, 9, 10, 11, 12]
    bars = [day(d0 + timedelta(days=i), x + 2, x, x + 1) for i, x in enumerate(lows)]
    got = swing_levels(bars, k=3)
    assert [(lv.price, lv.label.split()[1]) for lv in got] == [(5, "low")]


def test_profile_value_area_and_shelf():
    d = date(2026, 10, 27)
    bars = [five(d, 0, 110, 100, 100)] + [five(d, 5 * i, 104.9, 102, 900) for i in range(1, 4)]
    h = profile(bars, 1.0)
    poc, val, vah = value_area(h)
    assert 102 <= poc <= 104 and val >= 100 and vah <= 110
    assert shelves(h, 1.0) == [(102.0, 105.0)]


def test_naked_poc_only_when_never_revisited():
    d1, d2, d3 = date(2026, 10, 26), date(2026, 10, 27), date(2026, 10, 28)
    bars = ([five(d1, 0, 201, 200, 500)]                  # POC ~200.5, later sessions stay above -> naked
            + [five(d2, 0, 211, 210, 500)]                # POC ~210.5, revisited on d3 -> not naked
            + [five(d3, 0, 212, 209, 500)])
    got = naked_pocs(sessions(bars), 1.0)
    assert [d for d, _ in got] == [d1]


def test_volume_levels_report_recent_sessions():
    d = date(2026, 10, 27)
    lv, info = volume_levels([five(d, 5 * i, 101, 100, 100) for i in range(6)], 1.0)
    assert info["poc"] == 100.5 and info["recent"][0]["date"] == "2026-10-27"
    assert any(x.label == "composite POC" for x in lv)


def test_zones_strong_only_when_families_agree_and_first_obstacle():
    lv = [Level(3172, "pivot", "weekly S2"), Level(3171.4, "swing", "swing low 2026-10-27"),
          Level(3182, "swing", "swing low 2025-12-11"),
          Level(3214, "pivot", "daily S1"),                                  # alone -> weak
          Level(3468, "pivot", "weekly P"), Level(3475, "volume", "shelf 3450-3525 (edge)"),
          Level(3605, "pivot", "weekly R1"), Level(3612, "volume", "shelf 3555-3635 (edge)")]   # score 3: not enough
    zs = zones(lv, width=35)
    strong = [z for z in zs if z.strong]
    assert [(z.low, z.high) for z in strong] == [(3171.4, 3214)]
    zs = zones(lv + [Level(3480, "swing", "swing high 2026-06-15")], width=35)
    assert [(z.low, z.high, z.score) for z in zs if z.strong][1] == (3468, 3480, 5.0)
    ob = first_obstacle(zs, entry=3254, side=-1, r=80)                      # a short from 3254
    assert ob["edge"] == 3214 and ob["r"] == approx(0.5)
    assert first_obstacle(zs, entry=3254, side=1, r=80)["edge"] == 3468    # a long meets the shelf
    assert first_obstacle(zs, entry=3254, side=1, r=0) is None


def test_build_map_and_render():
    from core.price_map.build import build_map, nearest, render, step_for
    assert step_for(117) == 5 and step_for(14.08) == 0.5
    d0 = date(2026, 8, 3)
    daily = []
    for i in range(60):
        d = d0 + timedelta(days=i)
        x = 100 + (i % 10)                                        # a 100-110 range market
        daily.append(day(d, x + 2, x - 2, x))
    intraday = [five(d0 + timedelta(days=i), 5 * k, 105, 100, 1000) for i in range(50, 60) for k in range(4)]
    m = build_map("TEST", daily, intraday, d0 + timedelta(days=60))
    assert m["atr"] > 0 and m["volume"]["poc"] is not None and set(m["pivots"]) == {"daily", "weekly", "monthly"}
    assert any(z["strong"] for z in m["zones"])
    near = nearest(m, m["close"])
    assert near["below"] is None or near["below"]["high"] < m["close"]
    md = render(m)
    assert md.startswith("---") and "# TEST price map" in md and "## Zones" in md


def test_markers_name_the_first_obstacle_and_warn_when_the_target_is_beyond():
    from core.price_map.build import markers, zone_at
    z = lambda lo, hi, strong=True: {"low": lo, "high": hi, "mid": (lo + hi) / 2, "strong": strong, "score": 5,
                                      "families": ["swing", "pivot"],
                                      "levels": [{"price": lo, "family": "swing", "label": f"swing low {lo}"},
                                                 {"price": hi, "family": "pivot", "label": "weekly S2"}]}
    m = {"built_for": "2026-10-28", "zones": [z(960, 975), z(995, 998, strong=False), z(1100, 1110)]}
    lines = markers(m, price=1000, entry=1000, side=-1, r=50, target=940)              # a short, target past the floor
    assert "below 960–975" in lines[0] and "above 1100–1110" in lines[0]
    assert lines[1] == "• First obstacle 960–975 at 0.5R -- the target is beyond it ⚠️"
    assert "beyond" not in markers(m, 1000, 1000, -1, 50, 980)[1]
    assert zone_at(m, 965)["low"] == 960 and zone_at(m, 996) is None                  # weak zones don't alert
    assert markers({}, 1, 1, 1, 1, None) == ["• Map: none built -- run scripts/price_map.py"]
