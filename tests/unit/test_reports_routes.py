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
