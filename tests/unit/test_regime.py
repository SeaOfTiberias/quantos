"""core/ideas/regime.py -- IV rank and velocity for structure choice; deltas on candidates."""

from datetime import date, timedelta

from core.ideas import regime
from core.ideas.structure import View, candidates
from core.mcp_tools import market as mt
from tests.unit.test_mcp_market_tools import TODAY, FakeMarket
from tests.unit.test_structure_selector import HVIEW, _get, _hdfc


def _series(n, lo=0.15, hi=0.35, end=date(2026, 10, 23)):
    return [(end - timedelta(days=n - i), lo + (hi - lo) * i / (n - 1)) for i in range(n)]


def test_b76_iv_round_trip_and_atm_average():
    F, K, T = 1000.0, 1000.0, 30 / 365
    for put in (False, True):
        price = regime.b76(F, K, T, 0.27, put)
        assert abs(regime.b76_iv(price, F, K, T, put) - 0.27) < 1e-4
    assert regime.b76_iv(0.0, F, K, T, False) is None             # below intrinsic
    iv = regime.atm_iv(F, K, regime.b76(F, K, T, 0.2, False), regime.b76(F, K, T, 0.3, True), T)
    assert abs(iv - 0.25) < 1e-4


def test_iv_rank_window_labels_and_minimum_history():
    s = _series(260)
    today = date(2026, 10, 26)
    hi = regime.iv_rank(0.40, s, today)
    assert hi["rank"] == 1.0 and hi["label"] == "high" and hi["n"] == 252
    lo = regime.iv_rank(0.16, s, today)
    assert lo["label"] == "low" and lo["rank"] <= 0.3
    assert regime.iv_rank(0.25, _series(150), today) is None        # under 200 sessions
    assert regime.iv_rank(0.25, s, s[0][0])  is None                  # nothing before today


def test_velocity_labels_and_hdfc_max_at():
    assert regime.velocity_label(regime.velocity_k(692.8, 665, 15.9, 10)) == "normal"    # 0.55
    assert regime.velocity_label(regime.velocity_k(692.8, 685, 15.9, 10)) == "drift"
    assert regime.velocity_label(regime.velocity_k(692.8, 600, 15.9, 10)) == "fast"     # the 670/600's max
    assert regime.velocity_k(100, 90, None, 10) is None


def test_warnings_are_advisory_and_specific():
    view = {"thesis": "move"}
    fast = regime.warnings(view, {"k": 1.4, "label": "fast"}, {}, None)
    assert len(fast) == 1 and "fast move" in fast[0]
    assert "drift-sized" in regime.warnings(view, {"k": 0.3, "label": "drift"}, {}, None)[0]
    hi = regime.warnings(view, {"k": 0.7, "label": "normal"}, {"rank": 0.8, "label": "high"},
                         {"structure": "bear put 690/660"})
    assert hi and "credit row" in hi[0]
    lo = regime.warnings({"thesis": "hold"}, None, {"rank": 0.1, "label": "low"},
                         {"structure": "bear call 710/730 (credit)"})
    assert lo and "collects little" in lo[0]
    assert regime.warnings(view, {"k": 0.7, "label": "normal"}, {"rank": 0.5, "label": "mid"},
                           {"structure": "bear put 690/660"}) == []


def test_history_save_load_trim_and_refresh_without_new_days(tmp_path):
    p = tmp_path / "iv.csv"
    regime.save(p, {"ABC": _series(400)})
    h = regime.load(p)
    assert len(h["ABC"]) == regime.KEEP_ROWS and h["ABC"][-1][0] == date(2026, 10, 22)
    (tmp_path / "bhav").mkdir()
    assert regime.refresh(p, tmp_path / "bhav") == 0
    assert regime.refresh(tmp_path / "missing.csv", tmp_path / "bhav") == 0
    assert regime.load(tmp_path / "missing.csv") == {}


def test_live_atm_iv_and_iv_context(tmp_path):
    ch = FakeMarket().chain("ABC", 10)
    now = regime.live_atm_iv(ch)
    assert now["strike"] == 1000.0 and 0.05 < now["iv"] < 1.0
    p = tmp_path / "iv.csv"
    assert "error" in regime.iv_context(ch, p)                        # no history
    regime.save(p, {"ABC": _series(260, end=TODAY - timedelta(days=1))})
    ctx = regime.iv_context(ch, p)
    assert {"iv", "rank", "label", "history_to"} <= set(ctx)


def test_candidate_deltas_are_position_signed():
    ranked = candidates(_hdfc(), View(**HVIEW))
    bp = _get(ranked, "bear put 690/660")
    assert bp.deltas[0] < -0.3 and bp.deltas[1] > 0 and -0.6 < sum(bp.deltas) < 0
    fut = next(c for c in ranked if "future" in c.name)
    assert fut.deltas == [-1.0]
    credit = next(c for c in ranked if "credit" in c.name)        # bear call: short call (-), long call (+)
    assert credit.deltas[0] < 0 < credit.deltas[1]


def test_pick_structure_carries_regime_and_max_at(tmp_path):
    p = tmp_path / "iv.csv"
    regime.save(p, {"ABC": _series(260, end=TODAY - timedelta(days=1))})
    ps = mt.pick_structure(FakeMarket(), "ABC", "bull", target=1060, stop=980, days=3, iv_history=p, bhav_dir=None)
    assert ps["regime"]["velocity"]["label"] in ("drift", "normal", "fast")
    assert "rank" in ps["regime"]["iv"] and isinstance(ps["warnings"], list)
    debit = next(r for r in ps["top"] + ps["best_by_family"] if r["structure"].startswith("bull call"))
    assert debit["max_at"]["price"] == float(debit["structure"].split("/")[1]) and debit["deltas"]
    none = mt.pick_structure(FakeMarket(), "ABC", "bull", target=1060, stop=980, days=3, iv_history=None)
    assert none["regime"]["iv"] == {"error": "no IV history"}
