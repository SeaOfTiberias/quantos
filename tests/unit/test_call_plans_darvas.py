"""scripts/call_plans.py: Darvas breakouts as a second source of calls (synthetic plan file)."""
import json

from core.market_map import call_plan as cp
from scripts.call_plans import load_darvas


def test_load_darvas_reads_tonights_entries(tmp_path):
    p = tmp_path / "plan.json"
    p.write_text(json.dumps(dict(through="2026-11-16", bars_as_of="2026-11-16", entries=[
        dict(symbol="TESTA", last_close=101.5, initial_stop=90.0, box_ceiling=100.0),
        dict(symbol="TESTB")])))                                       # no close: skipped
    assert load_darvas(p) == [dict(key="2026-11-16|DARVAS|TESTA", date="2026-11-16", sym="TESTA", side="CE",
                                   spot=101.5, src="Darvas")]
    assert load_darvas(tmp_path / "missing.json") == []
    (tmp_path / "bad.json").write_text("{")
    assert load_darvas(tmp_path / "bad.json") == []


def test_darvas_tag_on_lines():
    v = dict(sweep=dict(level=96.5, kinds=["x"], atr_away=1.75, target=dict(level=104.0, kind="D weak")))
    assert cp.plan_lines("TESTA", "CE", 100.0, v, "2026-11-30", "Darvas")[0].startswith("🗺 TESTA CE [Darvas] (called 100)")
    assert cp.plan_lines("TESTA", "CE", 100.0, v, "2026-11-30")[0].startswith("🗺 TESTA CE (called 100)")
    assert cp.event_line("TESTA", "CE", "sweep", dict(date="2026-11-17", what="swept"), "Darvas") \
        == "   TESTA CE Darvas [sweep] 11-17: swept"
