"""Release page: core/orders/totp.py, core/orders/tickets.py, cloud/api/release_routes.py.
A fake Breeze client and synthetic tickets; nothing reaches a broker."""
from datetime import date, datetime, timedelta

import pytest
from fastapi import HTTPException

from cloud.api import release_routes as rr
from core.orders import tickets as tk
from core.orders.checks import Intent
from core.orders.gateway import IST, Gateway
from core.orders.totp import Verifier, code_at, new_secret
from tests.unit.test_order_gateway import FakeBreeze

EXP = date(2026, 11, 23)
MON = datetime(2026, 10, 26, 10, 0, tzinfo=IST)


# ─── one-time codes ──────────────────────────────────────────────────────────

def test_totp_rfc6238_vector():
    # RFC 6238 appendix B, SHA-1, T = 59 s -> 94287082 (8 digits); the last 6 digits are 287082
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"          # base32 of "12345678901234567890"
    assert code_at(secret, 59 // 30) == "287082"


def _verifier(tmp_path, t=1_000_000.0):
    s = new_secret()
    p = tmp_path / "totp.json"
    p.write_text('{"secret": "%s"}' % s)
    clock = [t]
    return Verifier(p, clock=lambda: clock[0]), s, clock


def test_code_once_only_and_lockout(tmp_path):
    v, s, clock = _verifier(tmp_path)
    good = code_at(s, int(clock[0] // 30))
    assert v.check(good) is None
    assert "already used" in v.check(good)
    for _ in range(5):
        assert v.check("000000" if good != "000000" else "111111") is not None
    clock[0] += 30
    assert "locked" in v.check(code_at(s, int(clock[0] // 30)))


def test_no_secret_means_no_release(tmp_path):
    assert "not set up" in Verifier(tmp_path / "none.json").check("123456")


# ─── tickets ─────────────────────────────────────────────────────────────────

def leg(qty=1000, price=782.0, product="futures", action="buy", right="others", strike=0.0, purpose="entry"):
    return Intent(account="icici-spouse", product=product, code="INDHOT", expiry=EXP, action=action, qty=qty,
                  price=price, purpose=purpose, right=right, strike=strike)


def store(tmp_path, now=MON):
    return tk.Store(tmp_path / "tickets.json", clock=lambda: now)


def gw(tmp_path, live=False):
    g = Gateway(FakeBreeze(), live=live, journal=tmp_path / "orders.jsonl", kill_switch=tmp_path / "ORDERS_OFF",
                clock=lambda: MON, fo_master=tmp_path / "no_master.csv")
    g._lots["INDHOT"] = 1000
    return g


def test_max_loss_by_code():
    assert tk.max_loss([leg()], 770.0) == 12000.0                                       # futures with a stop
    assert tk.max_loss([leg()], None) is None                                           # no stop: unknown
    assert tk.max_loss([leg(product="options", right="call", strike=780, price=12.5)], None) == 12500.0
    spread = [leg(product="options", right="call", strike=780, price=12.5),
              leg(product="options", right="call", strike=800, price=5.0, action="sell")]
    assert tk.max_loss(spread, None) == 7500.0


def test_draft_refuses_exit_legs(tmp_path):
    with pytest.raises(ValueError):
        store(tmp_path).draft([leg(purpose="exit")], symbol="INDHOTEL", why="x", strategy="t", ref_price=782,
                              valid_until=MON + timedelta(hours=1))


def test_release_paper_journals_and_sends_nothing(tmp_path):
    st, g = store(tmp_path), gw(tmp_path, live=False)
    t = st.draft([leg()], symbol="INDHOTEL", why="sweep reclaim", strategy="call-plan", ref_price=782,
                 valid_until=MON + timedelta(hours=1), stop=770.0)
    out = st.release(t["id"], g, price=782.0)
    assert out["status"] == "released" and out["paper"] and out["results"][0]["order_id"] == "paper"
    assert g.client.calls == []                                                         # nothing reached Breeze
    assert (tmp_path / "orders.jsonl").read_text().count('"live": false') == 1
    with pytest.raises(ValueError):
        st.release(t["id"], g)                                                          # no double release


def test_stale_by_time_and_by_move(tmp_path):
    st, g = store(tmp_path), gw(tmp_path)
    t = st.draft([leg()], symbol="INDHOTEL", why="x", strategy="t", ref_price=782, valid_until=MON - timedelta(minutes=1))
    with pytest.raises(ValueError, match="expired"):
        st.release(t["id"], g)
    t = st.draft([leg()], symbol="INDHOTEL", why="x", strategy="t", ref_price=782, valid_until=MON + timedelta(hours=1))
    with pytest.raises(ValueError, match="moved"):
        st.release(t["id"], g, price=800.0)
    assert st.get(t["id"])["status"] == "expired"


def test_quantity_only_down_in_whole_lots(tmp_path):
    st, g = store(tmp_path), gw(tmp_path)
    t = st.draft([leg(qty=3000)], symbol="INDHOTEL", why="x", strategy="t", ref_price=782,
                 valid_until=MON + timedelta(hours=1))
    with pytest.raises(ValueError, match="lowered"):
        st.release(t["id"], g, qty_scale=1.5)
    out = st.release(t["id"], g, qty_scale=0.5)
    assert out["results"][0]["leg"]["qty"] == 1000                                     # 1500 -> one lot


def test_refused_leg_marks_ticket_refused(tmp_path):
    st, g = store(tmp_path), gw(tmp_path)
    (tmp_path / "ORDERS_OFF").write_text("on")
    t = st.draft([leg()], symbol="INDHOTEL", why="x", strategy="t", ref_price=782, valid_until=MON + timedelta(hours=1))
    out = st.release(t["id"], g)
    assert out["status"] == "refused" and out["results"][0]["reasons"]


# ─── routes ──────────────────────────────────────────────────────────────────

@pytest.fixture
def routes(tmp_path, monkeypatch):
    v, s, clock = _verifier(tmp_path)
    monkeypatch.setattr(rr, "store", store(tmp_path))
    monkeypatch.setattr(rr, "verifier", v)
    monkeypatch.setattr(rr, "KILL_SWITCH", tmp_path / "ORDERS_OFF")
    monkeypatch.setattr(rr, "JOURNAL", tmp_path / "orders.jsonl")
    made = []
    monkeypatch.setattr(rr, "make_gateway", lambda live: made.append(live) or gw(tmp_path, live=live))
    return dict(s=s, clock=clock, made=made, tmp=tmp_path)


def test_mode_is_paper_unless_both_flags(monkeypatch, tmp_path):
    monkeypatch.setattr(rr, "KILL_SWITCH", tmp_path / "ORDERS_OFF")
    assert rr.mode({"live": True}) == "paper"
    assert rr.mode({"release_page": "live"}) == "paper"
    assert rr.mode({"live": True, "release_page": "live"}) == "live"
    (tmp_path / "ORDERS_OFF").write_text("on")
    assert rr.mode({"live": True, "release_page": "live"}) == "off"


def test_route_release_needs_the_code(routes, monkeypatch):
    monkeypatch.setattr(rr, "orders_cfg", lambda: {"live": True})                     # page not switched live
    t = rr.store.draft([leg()], symbol="INDHOTEL", why="x", strategy="t", ref_price=782,
                       valid_until=MON + timedelta(hours=1))
    with pytest.raises(HTTPException) as e:
        rr.release(t["id"], rr.ReleaseBody(code="000000" if code_at(routes["s"], 33333) != "000000" else "111111"))
    assert e.value.status_code == 403 and routes["made"] == []                        # no gateway on a bad code
    out = rr.release(t["id"], rr.ReleaseBody(code=code_at(routes["s"], int(routes["clock"][0] // 30))))
    assert out["status"] == "released" and routes["made"] == [False]                  # paper gateway


def test_route_kill_on_blocks_release(routes):
    t = rr.store.draft([leg()], symbol="INDHOTEL", why="x", strategy="t", ref_price=782,
                       valid_until=MON + timedelta(hours=1))
    rr.kill_on()
    with pytest.raises(HTTPException) as e:
        rr.release(t["id"], rr.ReleaseBody(code="123456"))
    assert e.value.status_code == 409
    assert rr.list_tickets()["mode"] == "off"
