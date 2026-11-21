"""scripts/ledger.py (E5): add / score with a stub market. Synthetic data only."""
import json
from datetime import date, datetime, timedelta, timezone

import pytest

import scripts.ledger as lg
from core.ledger.schema import CallError

IST = timezone(timedelta(hours=5, minutes=30))


class StubMarket:
    def __init__(self, bars, ref_close=100.0, now_ref=100.0, map_plan=None, read=None):
        self.bars, self.ref_close, self.now_ref = bars, ref_close, now_ref
        self.map_plan, self.read = map_plan, read if read is not None else {"symbol": "SYN", "price": 100.0}

    def context(self, raw, now):
        return dict(as_of="2026-11-20", ref_date="2026-11-20", ref_close=self.ref_close, atr=2.0,
                    map_read=self.read, map_plan=self.map_plan)

    def bars_after(self, sym, as_of):
        return [b for b in self.bars if b["date"] > as_of]

    def close_on(self, sym, day):
        return self.now_ref


RAW = dict(symbol="SYN", side="long", who="claude", entry={"kind": "open"}, stop=95, target=110,
           salvage="cut at the stop", decision="taken", why="test")
NOW = datetime(2026, 11, 20, 20, 0, tzinfo=IST)


def test_add_appends_and_numbers(tmp_path):
    m = StubMarket([])
    a = lg.add(dict(RAW), m, NOW, tmp_path)
    b = lg.add(dict(RAW), m, NOW, tmp_path)
    assert a["id"].endswith("-1") and b["id"].endswith("-2")
    assert len((tmp_path / "calls.jsonl").read_text().splitlines()) == 2


def test_add_refuses_without_map_read(tmp_path):
    with pytest.raises(CallError):
        lg.add(dict(RAW), StubMarket([], read={"error": "not in store"}), NOW, tmp_path)
    assert not (tmp_path / "calls.jsonl").exists()


def test_add_refuses_duplicate_source_ref(tmp_path):
    m = StubMarket([])
    lg.add(dict(RAW, who="screener", source_ref="2026-11-20|CE|SYN"), m, NOW, tmp_path)
    with pytest.raises(CallError, match="already"):
        lg.add(dict(RAW, who="screener", source_ref="2026-11-20|CE|SYN"), m, NOW, tmp_path)


def test_score_all_writes_scores_and_rescales(tmp_path):
    bars = [dict(date="2026-11-23", o=50, h=51.5, l=49.5, c=51), dict(date="2026-11-24", o=51, h=55.5, l=50.5, c=55)]
    lg.add(dict(RAW), StubMarket([]), NOW, tmp_path)
    out = lg.score_all(StubMarket(bars, now_ref=50.0), tmp_path)           # a 1:2 split after the call
    s = next(iter(out["scores"].values()))
    assert s["call"]["state"] == "target" and s["r_call"] == 2.0
    assert json.loads((tmp_path / "scores.json").read_text())["summary"]["claude"]["n"] == 1
    assert "Discretionary: n 1" in lg.summary_text(out, lg.load_calls(tmp_path))


@pytest.mark.parametrize("now,last,want", [
    (datetime(2026, 11, 20, 8, 0, tzinfo=IST), date(2026, 11, 19), "2026-11-19"),    # before the open
    (datetime(2026, 11, 20, 11, 0, tzinfo=IST), date(2026, 11, 19), "2026-11-20"),   # during: today's bar seen
    (datetime(2026, 11, 20, 21, 0, tzinfo=IST), date(2026, 11, 20), "2026-11-20"),   # after the refresh
    (datetime(2026, 11, 22, 11, 0, tzinfo=IST), date(2026, 11, 20), "2026-11-20"),   # Sunday
])
def test_cutoff(now, last, want):
    assert lg.cutoff(now, last) == want


def test_trade_idea_maps_to_ledger_call(tmp_path):
    from core.ledger.schema import from_idea
    from scripts.trade_ideas import to_ledger
    idea = dict(id="2026-11-20-SYN-enter_if", symbol="SYN", view="bull", action="enter_if", source="gemini",
                trigger={"kind": "close_above", "level": 101}, stop={"kind": "close_below", "level": 95},
                target=110, note="breakout")
    raw = from_idea(idea)
    assert raw["who"] == "model" and raw["entry"] == {"kind": "close_above", "price": 101, "window": 10}
    assert raw["stop"] == 95 and raw["decision"] == "taken" and raw["source_ref"] == "idea:2026-11-20-SYN-enter_if"
    assert from_idea(dict(idea, view="none")) is None
    m = StubMarket([])
    assert to_ledger(idea, lambda r: lg.add(r, m, NOW, tmp_path)).startswith("ledger: 2026-11-20-model-SYN")
    # a Claude idea with no salvage plan is refused by the ledger, the idea itself is untouched
    msg = to_ledger(dict(idea, id="x", source="claude"), lambda r: lg.add(r, m, NOW, tmp_path))
    assert "NOT written" in msg and "salvage" in msg


def test_call_plans_writes_tonights_calls_as_mechanical_rows(tmp_path):
    from scripts.call_plans import ledger_mechanical
    state = {"2026-11-20|CE|SYN": {"call": dict(key="2026-11-20|CE|SYN", sym="SYN", side="CE", date="2026-11-20", spot=100)},
             "2026-11-20|PE|SYM": {"call": dict(key="2026-11-20|PE|SYM", sym="SYM", side="PE", date="2026-11-20", spot=50, src="Darvas")},
             "2026-11-19|CE|OLD": {"call": dict(key="2026-11-19|CE|OLD", sym="OLD", side="CE", date="2026-11-19", spot=10)}}
    (tmp_path / "state.json").write_text(json.dumps(state))
    got = []
    out = ledger_mechanical(tmp_path, "2026-11-20", None, lambda raw: got.append(raw) or {"id": raw["source_ref"]})
    assert len(out) == 2 and {r["who"] for r in got} == {"screener", "darvas"}
    assert {r["side"] for r in got} == {"long", "short"} and all(r["stop"] is None for r in got)


@pytest.mark.asyncio
async def test_ledger_route_serves_calls_newest_first_without_map_read(tmp_path, monkeypatch):
    from httpx import ASGITransport, AsyncClient
    from cloud.api.main import app
    monkeypatch.setenv("QUANTOS_HOME_DIR", str(tmp_path))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        assert (await c.get("/ledger")).json()["calls"] == []
        m = StubMarket([dict(date="2026-11-23", o=100, h=111, l=99, c=110)],
                       map_plan=dict(sweep=dict(level=97.0, kinds=["D protected"], target=dict(level=106.0))))
        lg.add(dict(RAW), m, NOW)
        lg.add(dict(RAW, who="user"), m, NOW)
        lg.score_all(m)
        body = (await c.get("/ledger")).json()
    assert [x["who"] for x in body["calls"]] == ["user", "claude"]
    assert "map_read" not in body["calls"][0] and body["calls"][0]["map_plan"]["level"] == 97.0
    assert body["calls"][0]["score"]["call"]["state"] == "target" and body["summary"]["discretionary"]["n"] == 2


def test_trade_ideas_add_command_writes_the_ledger(monkeypatch, capsys):
    """Regression (2026-11-21): main's add printed the idea but never called to_ledger."""
    import scripts.trade_ideas as ti
    idea = dict(id="2026-11-21-SYN-avoid", symbol="SYN", view="bull", action="avoid", source="claude",
                stop={"kind": "close_below", "level": 95}, salvage="exit below 95", note="t",
                map_read={"symbol": "SYN", "price": 100.0})
    monkeypatch.setattr(ti, "add", lambda raw: idea)
    monkeypatch.setattr("core.market_map.read.lines", lambda rd: ["MAP"])
    seen = []
    monkeypatch.setattr(ti, "to_ledger", lambda i: seen.append(i["id"]) or "ledger: ok")
    assert ti.main(["add", "--json", "{}"]) == 0
    assert seen == ["2026-11-21-SYN-avoid"] and "ledger: ok" in capsys.readouterr().out
