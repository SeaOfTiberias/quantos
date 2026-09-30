"""Offline tests for scripts/backtest_orb_fix2.py -- the pre-registered
decision rule and a smoke run over synthetic candles (no Fyers)."""

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.brokers.base import OHLCV  # noqa: E402
from scripts.backtest_orb_fix2 import decide, run  # noqa: E402


def test_decision_rule_prefers_the_higher_pf_outside_the_tie_band():
    assert decide(pf_roll=1.30, pf_skip=1.10) == "roll"
    assert decide(pf_roll=1.10, pf_skip=1.30) == "skip"


def test_decision_rule_ties_go_to_skip():
    assert decide(pf_roll=1.22, pf_skip=1.20) == "skip"
    assert decide(pf_roll=1.20, pf_skip=1.22) == "skip"


def _day(day: date, base: float) -> list:
    start = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=3, minutes=45)
    out = []
    for i in range(75):
        p = base + (60 if i >= 3 else 0) + (i if i >= 4 else 0)
        out.append(OHLCV(timestamp=start + timedelta(minutes=5 * i), open=p, high=p + 2, low=p - 2,
                         close=p, volume=1))
    return out


def test_smoke_run_produces_every_section_and_a_decision():
    days = [date(2026, 9, 28), date(2026, 9, 29), date(2026, 9, 30)]   # 09-29 = BN expiry
    nifty = [c for d in days for c in _day(d, 24000.0)]
    bank = [c for d in days for c in _day(d, 54000.0)]
    vix = [OHLCV(timestamp=c.timestamp, open=13, high=13, low=13, close=13, volume=1) for c in bank]
    report = run({"nifty": nifty, "banknifty": bank, "vix": vix, "fetched_at": "test"})
    for heading in ("## NIFTY", "## BANKNIFTY", "expiry-day trades only", "Pre-registered BANKNIFTY decision"):
        assert heading in report
    assert "BN roll" in report and "BN skip" in report
    assert "-> **" in report
