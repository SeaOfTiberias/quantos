"""
Tests for scripts/check_orb_stopout_probe_gate.py -- the pre-registered
stopping-rule check (docs/ORB_STOPOUT_SPREAD_PROBE_METHODOLOGY.md).
Covers the two gates (N>=20, >=4 weeks elapsed) and, critically, that no
spread statistic is ever revealed before BOTH gates clear -- the whole
point of pre-registering this rule was to prevent a repeat of this
candidate's earlier stop-when-favorable pattern.
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.check_orb_stopout_probe_gate import (  # noqa: E402
    MIN_SAMPLE_N,
    MIN_WEEKS,
    PROBE_DEPLOYED_AT,
    elapsed_weeks,
    format_report,
    gate_status,
)


# ─── elapsed_weeks ───────────────────────────────────────────────────────

def test_elapsed_weeks_zero_on_deployment_day():
    assert elapsed_weeks(PROBE_DEPLOYED_AT) == 0.0


def test_elapsed_weeks_four_weeks_later():
    assert elapsed_weeks(date(2026, 10, 1)) == 4.0


# ─── gate_status ─────────────────────────────────────────────────────────

def test_neither_gate_met_at_deployment():
    status = gate_status(n=0, weeks=0.0)
    assert status == {"n": 0, "n_met": False, "elapsed_weeks": 0.0,
                       "time_met": False, "both_met": False}


def test_n_met_but_time_not_met_does_not_satisfy_gate():
    # A lucky burst of stop-outs in week 1 must NOT be treated as "done".
    status = gate_status(n=25, weeks=1.0)
    assert status["n_met"] is True
    assert status["time_met"] is False
    assert status["both_met"] is False


def test_time_met_but_n_not_met_does_not_satisfy_gate():
    # 4+ weeks elapsed but events proved rarer than expected.
    status = gate_status(n=5, weeks=5.0)
    assert status["n_met"] is False
    assert status["time_met"] is True
    assert status["both_met"] is False


def test_both_gates_met():
    status = gate_status(n=MIN_SAMPLE_N, weeks=MIN_WEEKS)
    assert status["both_met"] is True


def test_gate_boundary_is_inclusive():
    assert gate_status(n=20, weeks=4.0)["both_met"] is True
    assert gate_status(n=19, weeks=4.0)["both_met"] is False
    assert gate_status(n=20, weeks=3.9)["both_met"] is False


# ─── format_report: the "no peek" guarantee ─────────────────────────────

def _rows(*spread_pcts):
    return [{"spread_pct_of_mid": str(p), "trigger_reason": "stop"} for p in spread_pcts]


def test_report_reveals_no_spread_numbers_before_gate_met():
    status = gate_status(n=5, weeks=1.0)
    report = format_report("NIFTY", _rows(1.5, 2.0, 0.8), status)
    assert "WAITING" in report
    assert "mean" not in report
    assert "median" not in report
    for pct in ("1.5", "2.0", "0.8"):
        assert pct not in report


def test_report_reveals_spread_numbers_once_both_gates_met():
    status = gate_status(n=MIN_SAMPLE_N, weeks=MIN_WEEKS)
    report = format_report("NIFTY", _rows(1.0, 2.0, 3.0), status)
    assert "MET" in report
    assert "mean spread_pct_of_mid=2.000%" in report
    assert "median spread_pct_of_mid=2.000%" in report


def test_report_handles_gate_met_with_no_usable_rows():
    status = gate_status(n=MIN_SAMPLE_N, weeks=MIN_WEEKS)
    report = format_report("BANKNIFTY", [], status)
    assert "no rows have a usable spread_pct_of_mid" in report


def test_report_breaks_down_by_trigger_reason_only_after_gate_met():
    status = gate_status(n=MIN_SAMPLE_N, weeks=MIN_WEEKS)
    rows = [{"spread_pct_of_mid": "1.0", "trigger_reason": "stop"},
            {"spread_pct_of_mid": "3.0", "trigger_reason": "premium_stop"}]
    report = format_report("NIFTY", rows, status)
    assert "stop: n=1" in report
    assert "premium_stop: n=1" in report
