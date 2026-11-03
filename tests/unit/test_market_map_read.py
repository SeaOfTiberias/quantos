"""core/market_map/read.py -- map_read over the price map; synthetic maps and bars only."""

import json
import os
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import pytest

from core.market_map import read as mr
from core.price_map.levels import Level, Zone


def zone(low, high, *fams):
    lv = [Level(low, f, f"{f} {low:g}") for f in fams] + ([Level(high, fams[0], f"{fams[0]} {high:g}")] if high != low else [])
    return Zone(low, high, lv).to_dict()


# HDFCBANK-like: strong 664-666 below the 678 short, a weak pivot at 672, strong 700-702 above.
MAP = {"symbol": "HDFC", "built_for": "2026-10-23", "close": 680.0, "atr": 10.0,
       "zones": [zone(664, 666, "swing", "volume"), zone(672, 672, "pivot"), zone(700, 702, "swing", "pivot", "volume")]}


def test_location_only_read():
    rd = mr.read(MAP)
    assert rd["price"] == 680.0 and rd["status"] == "untested" and "trade" not in rd
    assert rd["below"]["range"] == "664–666" and rd["below"]["distance"] == 14 and rd["below"]["distance_atr"] == 1.4
    assert rd["above"]["range"] == "700–702" and rd["above"]["distance_pct"] == pytest.approx(2.94)
    assert rd["below"]["test"] == rd["above"]["test"] == "untested"
    assert rd["inside"] is None                                        # the single pivot at 672 is not strong
    assert mr.read(MAP, price=665)["inside"]["range"] == "664–666"


def test_short_into_a_strong_low_flags_the_target_beyond_it():
    """The 10-23 HDFCBANK case: short 678, stop 690, target 660 through the strong zone at 666."""
    t = mr.read(MAP, {"side": "short", "entry": 678, "stop": 690, "target": 660})["trade"]
    assert t["side"] == "short" and t["r"] == 12 and t["target_r"] == 1.5
    assert t["first_obstacle"]["range"] == "664–666" and t["first_obstacle"]["r"] == 1.0     # (678 - 666) / 12
    assert t["target_beyond_obstacle"] and t["stop_in_zone"] is None
    assert t["flags"] == ["target 660 is beyond the strong zone 664–666 at 1R"]


def test_stop_inside_a_zone_and_target_short_of_it():
    t = mr.read(MAP, {"side": "long", "entry": 680, "stop": 665, "target": 695})["trade"]
    assert t["stop_in_zone"]["range"] == "664–666"
    assert not t["target_beyond_obstacle"] and t["first_obstacle"]["edge"] == 700
    assert t["flags"] == ["stop 665 is inside the strong zone 664–666"]


def test_no_stop_means_no_r_and_no_obstacle():
    t = mr.read(MAP, {"side": 1, "entry": 680, "stop": None})["trade"]
    assert t["r"] is None and t["first_obstacle"] is None and t["flags"] == []
    assert any("no stop" in ln for ln in mr.lines(mr.read(MAP, {"side": 1, "entry": 680, "stop": None})))


def test_side_words():
    assert [mr.side_of(x) for x in ("long", "BUY", "bull", -1, "short", "sell", "bear", 1)] == [1, 1, 1, -1, -1, -1, -1, 1]
    with pytest.raises(ValueError):
        mr.side_of("flat")


def test_lines_label_untested():
    out = mr.lines(mr.read(MAP, {"side": "short", "entry": 678, "stop": 690, "target": 660}))
    assert "untested" in out[0] and "664–666" in out[1] and out[-1].strip().startswith("! target 660")
    assert mr.lines({"symbol": "X", "error": "no map"}) == ["MAP  X: none (no map)"]


# ─── loading, building on demand, as_of ──────────────────────────────────────

IST = timezone(timedelta(hours=5, minutes=30))


@dataclass
class Bar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


def bars(start: date, n: int):
    """A zig-zag: up 10 sessions, down 10, so there are swing highs and lows."""
    out, px = [], 100.0
    for i in range(n):
        px += 1.0 if (i // 10) % 2 == 0 else -1.0
        t = datetime.combine(start + timedelta(days=i), datetime.min.time(), tzinfo=IST)
        out.append(Bar(t, px, px + 0.8, px - 0.8, px, 1000))
    return out


class Market:
    def __init__(self, n=120):
        self.today = datetime.now(IST).date()
        self.bars = bars(self.today - timedelta(days=n), n)
        self.calls = 0

    def daily(self, symbol, days):
        self.calls += 1
        return self.bars


def test_builds_on_demand_saves_then_reads_the_file(tmp_path):
    m = Market()
    rd = mr.map_read("abc", market=m, maps_dir=tmp_path)
    assert rd["symbol"] == "ABC" and rd["source"] == "built" and m.calls == 1
    assert (tmp_path / "ABC.json").exists() and (tmp_path / "ABC.md").exists()
    rd2 = mr.map_read("ABC", market=m, maps_dir=tmp_path)
    assert rd2["source"] == "file" and m.calls == 1                   # fresh file: no second fetch


def test_a_stale_file_is_rebuilt(tmp_path):
    (tmp_path / "ABC.json").write_text(json.dumps({**MAP, "symbol": "ABC"}))
    old = time.time() - 8 * 86400
    os.utime(tmp_path / "ABC.json", (old, old))
    m = Market()
    assert mr.map_read("ABC", market=m, maps_dir=tmp_path)["source"] == "built" and m.calls == 1


def test_the_market_is_only_made_when_a_build_is_needed(tmp_path):
    (tmp_path / "ABC.json").write_text(json.dumps({**MAP, "symbol": "ABC"}))
    made = []
    rd = mr.map_read("ABC", market_factory=lambda: made.append(1), maps_dir=tmp_path)
    assert rd["source"] == "file" and made == []


def test_as_of_uses_only_earlier_bars_and_saves_nothing(tmp_path):
    m = Market()
    d = m.today - timedelta(days=30)
    rd = mr.map_read("ABC", as_of=d, market=m, maps_dir=tmp_path)
    assert rd["built_for"] == d.isoformat() and not (tmp_path / "ABC.json").exists()
    last = [b for b in m.bars if b.timestamp.date() < d][-1]
    assert rd["close"] == last.close                                  # nothing from day D or later


def test_failures_come_back_as_errors_never_raise(tmp_path):
    assert "error" in mr.map_read("ABC", maps_dir=tmp_path)            # no file, no market
    assert "error" in mr.map_read("ABC", market=Market(n=5), maps_dir=tmp_path)    # too few bars

    class Broken:
        def daily(self, symbol, days):
            raise RuntimeError("Fyers down")
    rd = mr.map_read("ABC", market=Broken(), maps_dir=tmp_path)
    assert rd["error"].startswith("RuntimeError")
