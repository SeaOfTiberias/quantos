"""core/market_map/read.py -- map_read over the L1 map (definitions v3); synthetic maps and bars only."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from core.market_map import read as mr


def zone(low, high, why, strong=True):
    return {"low": low, "high": high, "mid": round((low + high) / 2, 2), "strong": strong,
            "families": ["structure"], "tfs": ["W"], "n": 1, "why": why}


# HDFCBANK-like: strong 664-666 below the 678 short, a weak one at 672, strong 700-702 above.
MAP = {"symbol": "HDFC", "built_for": "2026-10-23", "close": 680.0, "atr": 10.0, "status": "untested",
       "zones": [zone(664, 666, "W demand base"), zone(672, 672, "W EQL", strong=False),
                 zone(700, 702, "W bear OB")]}


def test_location_only_read():
    rd = mr.read(MAP)
    assert rd["price"] == 680.0 and rd["status"] == "untested" and "trade" not in rd
    assert rd["below"]["range"] == "664–666" and rd["below"]["distance"] == 14 and rd["below"]["distance_atr"] == 1.4
    assert rd["above"]["range"] == "700–702" and rd["above"]["distance_pct"] == pytest.approx(2.94)
    assert rd["below"]["test"] == rd["above"]["test"] == "untested"
    assert rd["inside"] is None                                        # the weak zone at 672 is not strong
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


def test_lines_carry_the_zone_test_status():
    out = mr.lines(mr.read(MAP, {"side": "short", "entry": 678, "stop": 690, "target": 660}))
    assert "untested" in out[0] and "map v3" in out[0] and "664–666" in out[1] and out[-1].strip().startswith("! target 660")
    assert mr.lines({"symbol": "X", "error": "no map"}) == ["MAP  X: none (no map)"]


# ─── the map from the store, the index bars, and for futures ─────────────────

def _store(tmp_path, sym="ABC", n=900):
    from core.market_map.l1_store import Store
    st = Store(tmp_path / "store")
    c = 100 * np.exp(np.cumsum(np.random.default_rng(7).normal(0, 0.015, n)))
    for dt, x in zip(pd.bdate_range("2023-01-02", periods=n), c):
        st.append_day(pd.DataFrame([(sym, "EQ", x, x * 1.01, x * 0.99, x, 1, 1)],
                                   columns=["sym", "series", "o", "h", "l", "c", "vol", "val"]), dt.date())
    return st


def test_a_symbol_outside_the_store_has_no_map_and_never_a_fallback(tmp_path):
    rd = mr.map_read("TCS", l1_store=_store(tmp_path))
    assert rd == {"symbol": "TCS", "error": rd["error"]} and "not in the L1 store" in rd["error"]
    assert "error" in mr.current_map("TCS", l1_store=_store(tmp_path))


def test_failures_come_back_as_errors_never_raise():
    class Broken:
        root = "x"

        def adjusted(self, sym):
            raise RuntimeError("disk gone")
    assert mr.map_read("ABC", l1_store=Broken())["error"].startswith("RuntimeError")


def test_as_of_uses_only_earlier_bars(tmp_path):
    st = _store(tmp_path)
    rd = mr.map_read("ABC", as_of=date(2026, 6, 1), l1_store=st)
    assert rd["source"] == "l1" and rd["built_for"] < "2026-06-01" and rd["status"] == "untested"


def test_nifty_reads_from_the_index_bars_with_the_same_engine(tmp_path):
    from core.market_map.index_bars import COLS
    root = tmp_path / "idx"
    root.mkdir()
    c = 20000 * np.exp(np.cumsum(np.random.default_rng(3).normal(0, 0.01, 900)))
    days = pd.bdate_range("2023-01-02", periods=900)
    pd.DataFrame({"date": days.date, "o": c, "h": c * 1.01, "l": c * 0.99, "c": c, "vol": 1, "val": 1})[COLS]         .to_csv(root / "NIFTY.csv", index=False)
    rd = mr.map_read("nifty", as_of=date(2026, 6, 1), index_root=root)
    assert "error" not in rd, rd.get("error")
    assert rd["symbol"] == "NIFTY" and rd["source"] == "index" and rd["map"] == mr.MAP_NAME
    assert "no index bars" in mr.map_read("BANKNIFTY", index_root=root)["error"]


def test_shift_moves_zones_onto_futures_and_markers_name_v3():
    f = mr.shift(MAP, 5)
    assert f["zones"][0]["low"] == 669 and f["zones"][0]["mid"] == 670 and f["shifted_by"] == 5
    assert mr.shift(MAP, 0) is MAP and mr.shift({"error": "x"}, 5) == {"error": "x"}
    out = mr.markers(f, 690, 690, -1, 10, 660)
    assert "v3, untested" in out[0] and "futures = cash +5" in out[0] and "669–671 (W demand base)" in out[0]
    assert out[1].startswith("• First obstacle 669–671 at 1.9R") and "beyond" in out[1]
    assert mr.markers({"error": "not in the L1 store"}, 1, 1, 1, 1, None) == ["• Map: none (not in the L1 store)"]
