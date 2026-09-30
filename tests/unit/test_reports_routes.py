"""
Paper Strategy Reports Route — Unit Tests
───────────────────────────────────────────
GET /reports/paper-strategies builds cost-adjusted equity curves from the
ORB 18 and Darvas ATR-stop dry-run logs. Covers: net = gross - research cost
model, unpriced ORB exits are counted not guessed, curve/summary arithmetic,
empty logs, and that 18b's log is never read (its P&L is blinded until its
2026-11-17 gate).
"""

import json

import pytest
from httpx import AsyncClient, ASGITransport

import cloud.api.reports_routes as routes
from cloud.api.main import app


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("QUANTOS_HOME_DIR", str(tmp_path))
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "orb_scalping:\n  dry_run: true\n  starting_capital: 70000\n"
        "darvas_atr_stop:\n  dry_run: true\n  starting_capital: 250000\n"
    )
    monkeypatch.setenv("QUANTOS_AGENT_CONFIG", str(cfg))
    return tmp_path


def _orb(underlying, entry, exit_, qty, day="2026-09-23", exit_reason="trailing_stop"):
    return {"underlying": underlying, "direction": "PUT",
            "entry_timestamp": f"{day}T05:10:00+00:00", "entry_premium": entry,
            "exit_timestamp": f"{day}T06:30:00+00:00", "exit_reason": exit_reason,
            "quantity": qty, "exit_premium": exit_}


def _write_jsonl(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


async def _get():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        return await c.get("/reports/paper-strategies")


@pytest.mark.asyncio
async def test_empty_logs():
    body = (await _get()).json()
    for key in ("orb", "darvas"):
        assert body[key]["summary"]["trades"] == 0
        assert body[key]["curve"] == []
        assert body[key]["trades"] == []
    assert body["orb"]["summary"]["starting_capital"] == 70000
    assert body["darvas"]["summary"]["starting_capital"] == 250000


@pytest.mark.asyncio
async def test_orb_net_curve_and_unpriced(_isolated):
    _write_jsonl(_isolated / "orb_dry_run_trades.jsonl", [
        _orb("NIFTY", 100.0, 120.0, 65, day="2026-09-23"),
        _orb("BANKNIFTY", 300.0, 290.0, 30, day="2026-09-24"),
        _orb("NIFTY", 110.0, None, 65, day="2026-09-25", exit_reason="session_flatten"),
    ])
    # 18b's log is present but must never be read
    _write_jsonl(_isolated / "orb_dry_run_trades_filtered.jsonl", [_orb("NIFTY", 1.0, 999.0, 65)])

    orb = (await _get()).json()["orb"]
    assert orb["unpriced"] == 1
    s = orb["summary"]
    assert s["trades"] == 2
    assert s["gross_pnl"] == pytest.approx(20 * 65 - 10 * 30)
    assert s["costs"] > 0
    assert s["net_pnl"] == pytest.approx(s["gross_pnl"] - s["costs"], abs=0.02)
    assert s["equity"] == pytest.approx(70000 + s["net_pnl"], abs=0.02)

    curve = orb["curve"]
    assert curve[0]["equity"] == 70000
    assert len(curve) == 3
    assert curve[-1]["equity"] == pytest.approx(s["equity"], abs=0.02)
    assert orb["trades"][0]["underlying"] == "BANKNIFTY"   # newest first
    assert "999" not in json.dumps(orb)


@pytest.mark.asyncio
async def test_darvas_net_and_drawdown(_isolated):
    rows = [
        {"symbol": "AAA", "entry_timestamp": "2026-10-01", "entry_price": 100.0,
         "exit_timestamp": "2026-10-10T04:15:00+00:00", "exit_reason": "stop",
         "quantity": 100, "box_width_pct": 40.0, "seen_ceiling": 98.0,
         "boundary_price": 95.0, "exit_ltp": None},
        {"symbol": "BBB", "entry_timestamp": "2026-10-02", "entry_price": 200.0,
         "exit_timestamp": "2026-10-20T04:15:00+00:00", "exit_reason": "target",
         "quantity": 50, "box_width_pct": 45.0, "seen_ceiling": 190.0,
         "boundary_price": 260.0, "exit_ltp": 261.0},
    ]
    _write_jsonl(_isolated / "darvas_atr_stop_dry_run_trades.jsonl", rows)
    d = (await _get()).json()["darvas"]
    s = d["summary"]
    assert s["trades"] == 2 and s["wins"] == 1
    assert s["gross_pnl"] == pytest.approx(-500 + 3000)
    assert s["max_drawdown"] == pytest.approx(-d["trades"][1]["net_pnl"], abs=0.02)
    assert s["profit_factor"] > 1


def test_one_broken_report_does_not_blank_the_other(monkeypatch):
    def boom():
        raise RuntimeError("x")
    boom.__name__ = "orb_report"
    assert routes._safe(boom) == {"error": "RuntimeError: x"}


@pytest.mark.asyncio
async def test_orb_flags_exits_that_fell_through_the_unenforced_premium_stop(_isolated):
    """2026-09-29: paper held a BANKNIFTY put from 220.35 to 2.95 because
    dry_run never enforced the 25% premium stop. Such rows are flagged,
    not rewritten; a real premium_stop exit or a small loss is not."""
    _write_jsonl(_isolated / "orb_dry_run_trades.jsonl", [
        _orb("BANKNIFTY", 220.35, 2.95, 30, day="2026-09-29", exit_reason="session_flatten"),
        _orb("NIFTY", 100.0, 75.0, 65, day="2026-09-30", exit_reason="premium_stop"),
        _orb("NIFTY", 100.0, 80.0, 65, day="2026-09-30", exit_reason="stop"),
    ])
    orb = (await _get()).json()["orb"]
    assert orb["premium_stop_missed"] == 1
    flagged = [t for t in orb["trades"] if t["premium_stop_missed"]]
    assert [(t["underlying"], t["exit_price"]) for t in flagged] == [("BANKNIFTY", 2.95)]


@pytest.mark.asyncio
async def test_orb_stop_enforced_summary_caps_pre_fix_blowups_only(_isolated):
    """2026-09-30 addendum rule 4: the go-live figure re-marks a pre-fix row
    that fell past the unenforced stop at its trigger; the as-logged summary
    is left alone."""
    _write_jsonl(_isolated / "orb_dry_run_trades.jsonl", [
        _orb("BANKNIFTY", 220.35, 2.95, 30, day="2026-09-29", exit_reason="session_flatten"),
        _orb("NIFTY", 100.0, 120.0, 65, day="2026-09-30"),
    ])
    orb = (await _get()).json()["orb"]
    logged, enforced = orb["summary"], orb["summary_stop_enforced"]
    assert logged["gross_pnl"] == pytest.approx((2.95 - 220.35) * 30 + 20 * 65, abs=0.01)
    assert enforced["gross_pnl"] == pytest.approx((165.2625 - 220.35) * 30 + 20 * 65, abs=0.01)
    assert enforced["trades"] == logged["trades"] == 2


# ─── 1-lot LIVE pilot card ──────────────────────────────────────────────

def _ev(event, underlying="NIFTY", ts="2026-10-01T04:05:30+00:00", **kw):
    base = {"event": event, "underlying": underlying, "option_symbol": f"NSE:{underlying}TESTPE",
            "direction": "PUT", "timestamp": ts, "quantity": 65}
    base.update(kw)
    return base


@pytest.mark.asyncio
async def test_pilot_empty_when_no_live_events():
    pilot = (await _get()).json()["pilot"]
    assert pilot["summary"]["trades"] == 0
    assert pilot["enabled"] is False
    assert pilot["anomalies"] == [] and pilot["open_positions"] == []


@pytest.mark.asyncio
async def test_pilot_pairs_fills_nets_statutory_costs_and_measures_shortfall_vs_paper(_isolated):
    from core.orb_scalping.costs import clean_trade_cost
    _write_jsonl(_isolated / "orb_scalping_pilot_live_trades.jsonl", [
        _ev("entry", quoted_premium=52.0, fill_price=52.5, order_id="E1", stop_order_id="S1"),
        _ev("exit", ts="2026-10-01T09:50:30+00:00", fill_price=60.0, reason="session_flatten"),
    ])
    _write_jsonl(_isolated / "orb_dry_run_trades.jsonl", [
        {"underlying": "NIFTY", "direction": "PUT", "entry_timestamp": "2026-10-01T04:05:10+00:00",
         "entry_premium": 52.0, "exit_timestamp": "2026-10-01T09:50:10+00:00",
         "exit_reason": "session_flatten", "quantity": 130, "exit_premium": 61.0},
    ])
    pilot = (await _get()).json()["pilot"]
    t = pilot["trades"][0]
    costs = clean_trade_cost(52.5, 60.0, 65, __import__("datetime").date(2026, 10, 1)).total
    assert t["gross_pnl"] == pytest.approx((60.0 - 52.5) * 65)
    assert t["costs"] == pytest.approx(costs, abs=0.01)
    assert t["shortfall_vs_paper"] == pytest.approx((0.5 + 1.0) * 65)   # paid 0.5 more, got 1.0 less
    assert pilot["avg_shortfall_vs_paper"] == pytest.approx(97.5)
    assert pilot["exit_reasons"] == {"session_flatten": 1}
    assert pilot["anomalies"] == []


@pytest.mark.asyncio
async def test_pilot_surfaces_live_only_defect_signals(_isolated):
    _write_jsonl(_isolated / "orb_scalping_pilot_live_trades.jsonl", [
        _ev("entry", fill_price=50.0, stop_order_id=None, note="stop was not accepted -- flattened"),
        _ev("exit", ts="2026-10-01T04:06:30+00:00", fill_price=49.0, reason="manual"),
        _ev("exit", underlying="BANKNIFTY", fill_price=300.0, reason="stop"),       # no entry
        _ev("entry", underlying="BANKNIFTY", ts="2026-10-02T04:05:30+00:00",
            fill_price=280.0, stop_order_id="S9"),                                 # still open
    ])
    pilot = (await _get()).json()["pilot"]
    text = " | ".join(pilot["anomalies"])
    assert "no protective stop was left resting" in text
    assert "exit reason 'manual'" in text
    assert "with no matching entry" in text
    assert [p["underlying"] for p in pilot["open_positions"]] == ["BANKNIFTY"]
    assert pilot["open_positions"][0]["stop_resting"] is True


@pytest.mark.asyncio
async def test_pilot_card_reports_the_breaker_state_and_limits(_isolated):
    (_isolated / "halt_pilot").write_text("2026-10-01T05:00:00 UTC -- test reason\n")
    pilot = (await _get()).json()["pilot"]
    assert "test reason" in pilot["halted"]
    assert pilot["limits"] == {"budget_rs": 15000.0, "shortfall_limit_rs": 1500.0}
