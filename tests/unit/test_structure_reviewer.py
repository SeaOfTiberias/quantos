"""core/ideas/reviewer.py + core/ideas/dual.py -- a fake Claude picks among code-scored candidates."""

from types import SimpleNamespace

import pytest

from core.ideas import dual, reviewer
from core.ideas.log import make_idea
from core.mcp_tools import market as mt
from tests.unit.test_mcp_market_tools import FakeMarket


@pytest.fixture(autouse=True)
def _call_log_in_tmp(tmp_path, monkeypatch):
    """log_call must not write fake rows into the real ~/.quantos/llm_calls.jsonl."""
    monkeypatch.setenv("QUANTOS_HOME_DIR", str(tmp_path))


def ps():
    return mt.pick_structure(FakeMarket(), "ABC", "bull", target=1060, stop=980, days=3, iv_history=None)


class FakeClaude:
    """client.beta.messages.create -> one text block with `answer`; records what it was sent."""

    def __init__(self, answer=None, error=None, stop_reason="end_turn"):
        self.answer, self.error, self.stop = answer, error, stop_reason
        self.sent = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    def create(self, **kw):
        self.sent.append(kw)
        if self.error:
            raise self.error
        return SimpleNamespace(stop_reason=self.stop, usage=None, _request_id="r1",
                               content=[SimpleNamespace(type="text", text=self.answer)])


def answer(pick, why="slow mover, short at the target"):
    return (f"Some reasoning first.\n```json\n{{\"pick\": \"{pick}\", \"fits_view\": true, \"why\": \"{why}\", "
            f"\"risks\": \"a gap down\", \"event_before_expiry\": \"none found\", \"accepted_flags\": []}}\n```")


def test_shortlist_ids_and_context_has_no_household_fields():
    p = ps()
    ctx = reviewer.build_context(p, {"atr14": 1.2}, {"nifty_chg_pct": 0.1}, "2026-10-26T10:00")
    ids = [c["id"] for c in ctx["candidates"]]
    assert ids and len(ids) == len(set(ids)) and len(ids) <= reviewer.MAX_CANDIDATES
    assert all("flags" in c and "if_flat" in c for c in ctx["candidates"])
    text = str(ctx).lower()
    assert not any(k in text for k in ("account", "pnl", "quantity", "icici"))


def test_valid_pick_differ_and_agree():
    p = ps()
    cands = reviewer.shortlist(p)
    other = cands[1]["id"]
    r, ctx = reviewer.review(FakeMarket(), FakeClaude(answer(other)), p, "SYSTEM")
    assert r.verdict == "differ" and r.pick["id"] == other and r.final["id"] == other
    assert r.why and r.risks == "a gap down" and "Some reasoning" in r.reasoning
    r2, _ = reviewer.review(FakeMarket(), FakeClaude(answer(cands[0]["id"])), p, "SYSTEM")
    assert r2.verdict == "agree" and r2.final["id"] == cands[0]["id"]


def test_invented_pick_is_discarded_and_tool_top_stands():
    r, _ = reviewer.review(FakeMarket(), FakeClaude(answer("bull call 990/1300 2099-01-01")), ps(), "SYSTEM")
    assert r.verdict == "invalid" and r.pick is None and r.final == r.tool_top


def test_none_is_respected_and_errors_fall_back():
    r, _ = reviewer.review(FakeMarket(), FakeClaude(answer("none", why="results tomorrow")), ps(), "SYSTEM")
    assert r.verdict == "none" and r.final is None
    e, _ = reviewer.review(FakeMarket(), FakeClaude(error=RuntimeError("503")), ps(), "SYSTEM")
    assert e.verdict == "error" and e.final == e.tool_top and "503" in e.error
    x, _ = reviewer.review(FakeMarket(), FakeClaude("no json here at all"), ps(), "SYSTEM")
    assert x.verdict == "invalid" and x.final == x.tool_top
    ref, _ = reviewer.review(FakeMarket(), FakeClaude(answer("none"), stop_reason="refusal"), ps(), "SYSTEM")
    assert ref.verdict == "error"


def test_request_shape():
    c = FakeClaude(answer("none"))
    reviewer.review(FakeMarket(), c, ps(), "SYSTEM")
    kw = c.sent[0]
    assert kw["system"] == "SYSTEM" and kw["output_config"] == {"effort": "high"}
    assert kw["tools"][0]["type"] == "web_search_20260209" and kw["fallbacks"] == "default"
    assert "tool_choice" not in kw and "thinking" not in kw


def test_structure_of_debit_and_credit_names():
    assert dual.structure_of({"structure": "bear put 690/660", "expiry": "2026-11-23"}, 650) == \
        {"kind": "bear_put", "expiry": "2026-11-23", "long_strike": 690.0, "short_strike": 660.0, "lot": 650}
    assert dual.structure_of({"structure": "bear call 710/730 (credit)", "expiry": "2026-11-23"}, 650) == \
        {"kind": "bear_call", "expiry": "2026-11-23", "long_strike": 730.0, "short_strike": 710.0, "lot": 650}
    assert dual.structure_of({"structure": "long 700 PE", "expiry": "2026-11-23"}, 650) is None


def _ideas(verdict_answer):
    p = ps()
    r, _ = reviewer.review(FakeMarket(), FakeClaude(verdict_answer), p, "SYSTEM")
    return r, [make_idea(x) for x in dual.ideas_for_review(r, p, "claude-opus-5-5", "pair1")]


def test_dual_logging_by_verdict():
    p = ps()
    cands = reviewer.shortlist(p)
    r, ideas = _ideas(answer(cands[1]["id"]))
    assert [i["source"] for i in ideas] == ["review-llm", "review-tool"]
    assert ideas[0]["review"]["pair"] == ideas[1]["review"]["pair"] == "pair1"
    assert ideas[0]["review"]["llm_pick"] == cands[1]["id"] and ideas[0]["review"]["tool_top"] == cands[0]["id"]
    assert all(i["stop"] == {"kind": "close_below", "level": 980.0} and i["action"] == "enter_now" for i in ideas)
    _, agree = _ideas(answer(cands[0]["id"]))
    assert [i["source"] for i in agree] == ["review-agree"]
    _, none = _ideas(answer("none"))
    assert [(i["source"], i["action"]) for i in none] == [("review-tool", "enter_now"), ("review-llm", "avoid")]
    _, bad = _ideas("garbage")
    assert [i["source"] for i in bad] == ["review-tool"]


def test_scoreboard_by_source():
    evals = [({"source": "review-llm"}, {"pnl": 500.0, "pnl_pct": 10.0}),
             ({"source": "review-llm"}, {"pnl": -200.0, "pnl_pct": -4.0}),
             ({"source": "review-tool"}, {"pnl": 100.0, "pnl_pct": 2.0}),
             ({"source": "review-agree"}, {}),
             ({"source": "claude"}, {"pnl": 999.0})]
    sb = dual.scoreboard_by_source(evals)
    assert set(sb) == {"review-llm", "review-tool", "review-agree"}
    assert sb["review-llm"] == {"ideas": 2, "scored": 2, "wins": 1, "pnl": 300.0, "mean_pnl_pct": 3.0}
    assert sb["review-agree"]["scored"] == 0 and sb["review-agree"]["mean_pnl_pct"] is None


def test_view_score_is_parsed_and_logged_but_changes_nothing():
    p = ps()
    top = reviewer.shortlist(p)[0]["id"]
    text = answer(top).replace('"accepted_flags": []}', '"accepted_flags": [], "view_score": 0.3, '
                                                        '"view_reason": "the 52w low is right under spot"}')
    r, ctx = reviewer.review(FakeMarket(), FakeClaude(text), p, "SYSTEM")
    assert r.view_score == 0.3 and "52w low" in r.view_reason
    assert r.verdict == "agree" and r.final["id"] == top                 # a low score doesn't move the pick
    assert "regime" in ctx and "warnings" in ctx
    (idea,) = [make_idea(x) for x in dual.ideas_for_review(r, p, "m", "pair")]
    assert idea["review"]["view_score"] == 0.3 and idea["action"] == "enter_now"
    bad, _ = reviewer.review(FakeMarket(), FakeClaude(answer(top).replace('"accepted_flags": []}',
                                                                        '"accepted_flags": [], "view_score": 7}')),
                             p, "SYSTEM")
    assert bad.view_score is None


def test_search_outcomes_recorded():
    ok = SimpleNamespace(type="web_search_tool_result", content=[1, 2, 3])
    bad = SimpleNamespace(type="web_search_tool_result", content=SimpleNamespace(error_code="max_uses_exceeded"))
    assert reviewer.search_outcomes([ok, bad, SimpleNamespace(type="text", text="x")]) == \
        ["ok:3", "error:max_uses_exceeded"]
