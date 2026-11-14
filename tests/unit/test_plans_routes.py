"""cloud/api/plans_routes.py: the #/plans list and one-pager data (synthetic state and pages)."""
import json

import pytest
from fastapi import HTTPException

from cloud.api import plans_routes as pr


def _state(tmp_path):
    st = {
        "2026-11-13|CE|TESTA": dict(call=dict(key="2026-11-13|CE|TESTA", date="2026-11-13", sym="TESTA", side="CE", spot=100.0),
                                    versions=[dict(as_of="2026-11-13", sweep=dict(level=96.5, target=dict(level=104.0)))],
                                    tracks=[dict(kind="sweep", side="CE", state="triggered", entry=98.0, stop=94.3,
                                                 risk=3.7, target=104.0, events=[])], through="2026-11-16"),
        "2026-11-10|DARVAS|TESTB": dict(call=dict(key="2026-11-10|DARVAS|TESTB", date="2026-11-10", sym="TESTB", side="CE",
                                                  spot=50.0, src="Darvas"),
                                        versions=[dict(as_of="2026-11-10")], tracks=[dict(kind="sweep", side="CE",
                                        state="stopped", r=-1.0, pct=-2.0, events=[])], through="2026-11-16"),
    }
    (tmp_path / "state.json").write_text(json.dumps(st))
    (tmp_path / "pages").mkdir()
    (tmp_path / "pages" / "2026-11-13_CE_TESTA.json").write_text(json.dumps(dict(bars=[["2026-11-16", 99, 102, 98, 101.7]])))
    return tmp_path


def test_list_open_first_with_marks(tmp_path):
    d = pr.list_plans(_state(tmp_path))
    a, b = d["plans"]
    assert d["n_open"] == 1 and a["sym"] == "TESTA" and a["open"] and b["src"] == "Darvas"
    assert a["status"] == "triggered" and a["last_close"] == 101.7 and a["as_sent_pct"] == 1.7
    assert a["tracks"][0]["r"] == round(3.7 / 3.7, 2) and a["tracks"][0]["open"]          # marked at 101.7
    assert a["sweep"] == dict(level=96.5, target=104.0) and a["expires"] == "2026-11-27"
    assert b["status"] == "stopped" and b["tracks"][0]["r"] == -1.0 and b["last_close"] is None


def test_one_plan_and_key_checks(tmp_path):
    root = _state(tmp_path)
    d = pr.one_plan("2026-11-13|CE|TESTA", root)
    assert d["page"]["bars"][0][4] == 101.7 and d["plan"]["tracks"][0]["entry"] == 98.0
    assert pr.one_plan("2026-11-10|DARVAS|TESTB", root)["page"] is None
    for bad, code in (("../state", 400), ("2026-11-13|CE|NOPE", 404)):
        with pytest.raises(HTTPException) as e:
            pr.one_plan(bad, root)
        assert e.value.status_code == code


def test_status_rank():
    assert pr.status([dict(state="lapsed"), dict(state="swept")]) == "swept"
    assert pr.status([]) == "no plan"
