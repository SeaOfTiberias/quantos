"""core/ops/evening_brief.py + scripts/evening_brief.py (E6). Synthetic symbols and levels only."""
import json

import pytest

from core.ops import evening_brief as eb


def card(price=100.0, above=(), below=(), inside=(), d_above=(), d_below=(), atr_w=5.0):
    z = lambda lo, hi, strong=True: dict(lo=lo, hi=hi, strong=strong, edge_atr=None, edge_pct=(lo - price) / price * 100)  # noqa: E731
    return dict(sym="SYN", price=price, atr_d=2.0, atr_w=atr_w, alignment="aligned up",
                structure={"W": dict(state="up", protected=dict(px=90), weak=dict(px=105)),
                           "D": dict(state="up", protected=dict(px=95), weak=dict(px=100))},
                zones=dict(above=[z(*a) for a in above], below=[z(*b) for b in below], inside=[z(*i) for i in inside]),
                zones_d=dict(above=[dict(kind="bear_fvg", lo=a, hi=b) for a, b in d_above],
                             below=[dict(kind="bull_fvg", lo=a, hi=b) for a, b in d_below]))


def htf(low, high, kind, tf="W", strong=True):
    return dict(low=low, high=high, mid=(low + high) / 2, strong=strong,
                bands=[dict(kind=kind, tf=tf, lo=low, hi=high)])


# ─── breadth ─────────────────────────────────────────────────────────────────

def test_breadth_counts_states_and_todays_sweeps():
    rows = [eb.breadth_row("A", {"W": dict(state="up", sweeps=[dict(side="low", level=9, extreme=8, date="2026-11-20")]),
                                 "D": dict(state="up", sweeps=[dict(side="low", level=10, extreme=9.5, date="2026-11-20"),
                                                               dict(side="high", level=12, extreme=12.5, date="2026-11-19")])}, "2026-11-20"),
            eb.breadth_row("B", {"W": dict(state="down"), "D": dict(state="down")}, "2026-11-20"),
            dict(sym="C", error="x")]
    b = eb.breadth(rows)
    assert b["n"] == 2 and b["errors"] == 1
    assert b["W"] == dict(up=1, down=1, none=0) and b["D"]["down"] == 1
    assert [(s["sym"], s["tf"]) for s in b["sweeps"]["low"]] == [("A", "D"), ("A", "W")]
    assert b["sweeps"]["high"] == []                                        # yesterday's sweep is not today's


# ─── trades ──────────────────────────────────────────────────────────────────

def test_trades_darvas_plan_and_map_plan_with_estimated_stop():
    c = dict(sym="SYN", side="CE", spot=100.0, src="Darvas", stop=92.0, target=120.0)
    v = dict(atr=2.0, sweep=dict(level=96.0, target=dict(level=108.0)))
    t = eb.trades(c, v)
    assert t[0] == dict(basis="Darvas plan", entry=100.0, stop=92.0, target=120.0, estimate=False)
    assert t[1]["entry"] == 96.0 and t[1]["stop"] == pytest.approx(96.0 - 0.35 * 2.0) and t[1]["estimate"]
    assert t[1]["target"] == 108.0


def test_trades_short_screener_call_without_stop():
    t = eb.trades(dict(sym="SYN", side="PE", spot=100.0, src="F&O"), dict(atr=2.0, sweep=dict(level=104.0)))
    assert t[0]["stop"] is None and t[1]["stop"] == pytest.approx(104.7)


# ─── vetoes ──────────────────────────────────────────────────────────────────

def codes(vs):
    return [v["code"] for v in vs]


def test_v1_stop_inside_strong_zone_only():
    c = card(below=[(90, 94)])
    assert codes(eb.vetoes(dict(entry=100, stop=92), "long", c, [], None)) == ["V1"]
    c_weak = card(below=[(90, 94, False)])
    assert eb.vetoes(dict(entry=100, stop=92), "long", c_weak, [], None) == []


def test_v2_rr_to_first_obstacle_uses_htf_and_d_zones():
    c = card(above=[(110, 112)], d_above=[(104, 105)])                     # D gap at 104 is first
    v = eb.vetoes(dict(entry=100, stop=95), "long", c, [], None)
    assert codes(v) == ["V2"] and v[0]["rr"] == 0.8
    assert eb.vetoes(dict(entry=100, stop=98), "long", c, [], None) == []  # 4 / 2 = 2R
    assert eb.vetoes(dict(entry=100, stop=None), "long", c, [], None) == []
    s = card(below=[(90, 92)])                                              # short: obstacle is 92 (zone high)
    assert codes(eb.vetoes(dict(entry=100, stop=110), "short", s, [], None)) == ["V2"]       # 8 / 10 = 0.8R
    assert eb.vetoes(dict(entry=100, stop=106), "short", s, [], None) == []                  # 8 / 6 = 1.33R


def test_v3_long_into_weekly_supply_short_into_monthly_demand():
    sup = [htf(103, 106, "supply")]
    assert codes(eb.vetoes(dict(entry=100, stop=None), "long", card(atr_w=5), sup, None)) == ["V3"]
    assert eb.vetoes(dict(entry=100, stop=None), "long", card(atr_w=2), sup, None) == []        # 3 > 1 ATR(W)
    assert eb.vetoes(dict(entry=100, stop=None), "long", card(atr_w=5), [htf(103, 106, "supply", tf="D")], None) == []
    dem = [htf(97, 101, "bull_ob", tf="M")]                                 # the HDFCBANK case: price inside demand
    v = eb.vetoes(dict(entry=100, stop=None), "short", card(), dem, None)
    assert codes(v) == ["V3"] and "inside" in v[0]["text"]
    assert eb.vetoes(dict(entry=100, stop=None), "long", card(), dem, None) == []                 # demand helps a long


def test_v4_results_within_blackout():
    assert codes(eb.vetoes(dict(entry=100, stop=None), "long", card(), [], 5)) == ["V4"]
    assert eb.vetoes(dict(entry=100, stop=None), "long", card(), [], 6) == []


def test_text_renders_every_part():
    b = dict(session="2026-11-20", index={"NIFTY": card(), "BANKNIFTY": dict(error="no bars")},
             breadth=eb.breadth([eb.breadth_row("A", {"W": dict(state="up"), "D": dict(state="up", sweeps=[
                 dict(side="low", level=1, extreme=0.9, date="2026-11-20")])}, "2026-11-20")]),
             candidates=[dict(sym="SYN", side="CE", src="Darvas", spot=100.0, results="2026-11-25",
                              trades=[dict(basis="Darvas plan", entry=100, stop=92, target=120, estimate=False,
                                           vetoes=[dict(code="V1", text="stop 92 inside strong zone 90-94")])])],
             warnings=["call plans have not walked 2026-11-20 yet"])
    t = eb.text(b)
    for want in ("NIFTY 100: aligned up", "BANKNIFTY: no read", "W up 1", "swept lows today: 1: A",
                 "SYN CE [Darvas]", "⚠ V1 stop 92", "results 2026-11-25", "⚠ call plans", "ledger.py add"):
        assert want in t, want


# ─── script joins ────────────────────────────────────────────────────────────

def test_tonight_calls_joins_darvas_stop_and_warns_when_plans_are_stale(tmp_path):
    from scripts.evening_brief import tonight_calls
    v = dict(as_of="2026-11-20", atr=2.0, sweep=dict(level=96.0))
    state = {"2026-11-20|DARVAS|SYN": dict(call=dict(key="k1", date="2026-11-20", sym="SYN", side="CE", spot=100, src="Darvas"),
                                           versions=[v], through="2026-11-20"),
             "2026-11-20|PE|SYM": dict(call=dict(key="k2", date="2026-11-20", sym="SYM", side="PE", spot=50),
                                       versions=[v], through="2026-11-20"),
             "2026-11-19|CE|OLD": dict(call=dict(key="k3", date="2026-11-19", sym="OLD", side="CE", spot=10),
                                       versions=[v], through="2026-11-20")}
    sp, dp = tmp_path / "state.json", tmp_path / "darvas.json"
    sp.write_text(json.dumps(state))
    dp.write_text(json.dumps(dict(bars_as_of="2026-11-20", entries=[dict(symbol="SYN", initial_stop=92.0, target=120.0)])))
    calls, warn = tonight_calls("2026-11-20", sp, dp)
    assert sorted(c["sym"] for c in calls) == ["SYM", "SYN"] and warn == []
    syn = next(c for c in calls if c["sym"] == "SYN")
    assert syn["stop"] == 92.0 and syn["target"] == 120.0 and syn["version"] == v
    assert next(c for c in calls if c["sym"] == "SYM")["stop"] is None
    _, warn = tonight_calls("2026-11-23", sp, dp)
    assert warn and "2026-11-23" in warn[0]


@pytest.mark.asyncio
async def test_brief_route(tmp_path, monkeypatch):
    from httpx import ASGITransport, AsyncClient
    from cloud.api.main import app
    monkeypatch.setenv("QUANTOS_HOME_DIR", str(tmp_path))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        assert "error" in (await c.get("/reports/brief")).json()
        (tmp_path / "brief").mkdir()
        (tmp_path / "brief" / "brief_latest.json").write_text(json.dumps(dict(session="2026-11-20", candidates=[])))
        assert (await c.get("/reports/brief")).json()["session"] == "2026-11-20"


def test_v2_obstacle_must_lie_beyond_the_entry():
    """Smoke run 2026-11-21: an entry above the price got a negative R:R to a zone between them."""
    c = card(price=100.0, above=[(102, 104), (115, 118)])
    assert eb.first_obstacle(c, "long", 105.0) == 115
    assert eb.vetoes(dict(entry=105, stop=100), "long", c, [], None) == []      # 10 / 5 = 2R
