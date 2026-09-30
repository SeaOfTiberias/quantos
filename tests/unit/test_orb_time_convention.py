"""Offline tests for the ORB time-convention calibration + backtest runner
(2026-09-30, post-Fable). No broker, no data files."""

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.brokers.base import OHLCV  # noqa: E402
from core.orb_scalping.premium import TimeWeights, effective_days_to_expiry  # noqa: E402
import scripts.calibrate_orb_time_convention as cal  # noqa: E402
import scripts.backtest_orb_time_convention as btc  # noqa: E402


def _synthetic(truth, k_n, k_b):
    """Quotes priced by the model itself under known parameters: the fit must find them."""
    rows = []
    start = date(2026, 8, 3)
    for day in range(40):
        d = start + timedelta(days=day)
        if d.weekday() >= 5:
            continue
        for hh, mm in ((4, 5), (6, 30), (9, 45)):
            ts = datetime(d.year, d.month, d.day, hh, mm, tzinfo=timezone.utc)
            for und, dte, k in (("NIFTY", 4 + day % 5, k_n), ("BANKNIFTY", 18 + day % 8, k_b)):
                expiry = d + timedelta(days=dte)
                units = [effective_days_to_expiry(expiry, ts, u) for u in cal.UNIT]
                days = np.dot(units, [truth.session, truth.weeknight, truth.weekend])
                spot = 24000.0 + 30 * (day % 7)
                mid = float(cal.bs_price(np.array([spot]), np.array([24000.0]), np.array([days]),
                                         np.array([0.13 * k]), np.array([True]))[0])
                rows.append(dict(ts=ts, underlying=und, is_call=True, spot=spot, strike=24000.0,
                                 mid=mid, vix=0.13, units=units, dte=dte))
    return cal._arrays(rows)


def test_fit_recovers_known_weights_and_vix_scales():
    truth = TimeWeights(0.8, 0.3, 0.6)
    a = _synthetic(truth, k_n=1.05, k_b=1.25)
    grid = [(s, w, e) for s in (0.3, 0.55, 0.8, 1.05) for w in (0.1, 0.3, 0.5) for e in (0.4, 0.6, 1.2, 2.7)]
    p = cal.fit(a, grid)
    assert (p["session"], p["weeknight"], p["weekend"]) == (0.8, 0.3, 0.6)
    assert abs(p["k_nifty"] - 1.05) < 0.011 and abs(p["k_banknifty"] - 1.25) < 0.011
    assert cal.error(a, p) < 1e-6


def test_load_frozen_reads_the_json_block_and_validation_flag():
    doc = ("x\nFitted beats calendar on the holdout: **YES** (pre-registered validation condition).\n"
           "## Frozen convention (full-sample fit) — used by the backtest\n\n```json\n"
           '{"session": 0.8, "weeknight": 0.3, "weekend": 0.6, "k_nifty": 1.0, "k_banknifty": 1.2, "mse": 0.01}\n'
           "```\n")
    frozen, validated = btc.load_frozen(doc)
    assert frozen["session"] == 0.8 and frozen["k_banknifty"] == 1.2 and validated is True
    assert btc.load_frozen(doc.replace("**YES**", "**NO**"))[1] is False


def _day(day, base):
    start = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=3, minutes=45)
    return [OHLCV(timestamp=start + timedelta(minutes=5 * i), open=base + (60 if i >= 3 else 0) + (i if i >= 4 else 0),
                  high=base + 62 + i, low=base - 2, close=base + (60 if i >= 3 else 0) + (i if i >= 4 else 0), volume=1)
            for i in range(75)]


def test_backtest_runner_smoke_reports_a_verdict():
    days = [date(2026, 9, 28), date(2026, 9, 29), date(2026, 9, 30)]
    nifty = [c for d in days for c in _day(d, 24000.0)]
    bank = [c for d in days for c in _day(d, 54000.0)]
    vix = [OHLCV(timestamp=c.timestamp, open=13, high=13, low=13, close=13, volume=1) for c in bank]
    frozen = {"session": 0.8, "weeknight": 0.3, "weekend": 0.6, "k_nifty": 1.0, "k_banknifty": 1.2}
    report = btc.run({"nifty": nifty, "banknifty": bank, "vix": vix}, frozen, validated=True)
    assert "## NIFTY" in report and "## BANKNIFTY" in report
    assert "candidate 18 **" in report
    assert "No single verdict" in btc.run({"nifty": nifty, "banknifty": bank, "vix": vix}, frozen, validated=False)
