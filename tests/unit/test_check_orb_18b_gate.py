"""
Tests for scripts/check_orb_18b_gate.py -- docs/ORB_ENTRY_FILTER_
METHODOLOGY.md's prospective PF/Sharpe gate (no peeking before N>=20 AND
40 recorded sessions, the 2026-11-19 amendment of ">=8 weeks") and the
Rs50,000 equity narrative (no peeking before 40 recorded sessions). No network/broker.
"""

import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.orb_scalping.dry_run_log import DryRunTrade  # noqa: E402
from scripts.check_orb_18b_gate import (  # noqa: E402
    BASE_CAPITAL,
    DEPLOYED_AT,
    MIN_SAMPLE_N,
    MIN_SESSIONS,
    closed_only,
    due_session,
    elapsed_weeks,
    format_equity_report,
    format_pf_sharpe_report,
    gate_status,
    net_pnl,
    recorded_sessions,
    to_backtest_trade,
)

# Synthetic NSE sessions: every weekday, Sep 2026 to Jun 2027 (no real calendar, no files).
WEEKDAYS = [date(2026, 9, 1) + timedelta(days=i) for i in range(300)
            if (date(2026, 9, 1) + timedelta(days=i)).weekday() < 5]
GATE_MET = date(2027, 2, 1)          # well past 40 recorded sessions after the outage
BEFORE = date(2026, 11, 20)          # 8 calendar weeks gone, but only ~14 recorded sessions


@pytest.fixture(autouse=True)
def _sessions(monkeypatch):
    import scripts.check_orb_18b_gate as gate
    monkeypatch.setattr(gate, "load_sessions", lambda path=None: WEEKDAYS)


def trade(underlying="NIFTY", entry_premium=100.0, exit_premium=110.0, quantity=65,
         entry="2026-09-22T04:10:00+00:00", exit_="2026-09-22T09:50:00+00:00",
         exit_reason="session_flatten", direction="CALL"):
    return DryRunTrade(underlying=underlying, direction=direction, entry_timestamp=entry,
                       entry_premium=entry_premium, exit_timestamp=exit_, exit_reason=exit_reason,
                       quantity=quantity, exit_premium=exit_premium)


# ─── elapsed_weeks / gate_status ────────────────────────────────────────────

def test_elapsed_weeks_from_deployment():
    assert elapsed_weeks(date(2026, 11, 17)) == 8.0


def test_gate_status_requires_both_n_and_time():
    assert gate_status(n=25, recorded=45)["both_met"] is True
    assert gate_status(n=25, recorded=15)["both_met"] is False   # enough trades, not enough sessions
    assert gate_status(n=5, recorded=45)["both_met"] is False    # enough sessions, not enough trades


def test_gate_status_boundary_is_inclusive():
    assert gate_status(n=MIN_SAMPLE_N, recorded=MIN_SESSIONS)["both_met"] is True


def test_recorded_sessions_skip_the_2026_10_08_to_11_17_outage():
    """The 2026-11-19 amendment: 8 calendar weeks passed on 11-17, but 18b ran on 11 of them."""
    real = [date(2026, 9, d) for d in (22, 23, 24, 25, 28, 29, 30)] +            [date(2026, 10, d) for d in (1, 5, 6, 7, 8, 9)] + [date(2026, 11, d) for d in (17, 18, 19)]
    assert recorded_sessions(date(2026, 11, 19), real) == 12          # 11 before the outage + 11-18
    assert recorded_sessions(date(2026, 11, 17), real) == 11
    assert due_session(real) is None                                  # far from the 40th


def test_the_gate_stays_shut_on_the_amendment_day_and_without_a_session_list():
    filtered = [trade() for _ in range(MIN_SAMPLE_N)]
    assert "WAITING" in format_pf_sharpe_report("NIFTY", filtered, [], today=date(2026, 11, 19))
    shut = format_pf_sharpe_report("NIFTY", filtered, [], today=GATE_MET, sessions=[])
    assert "recorded sessions=0" in shut and "Gate MET" not in shut  # unreadable store: never opens
    assert "Not due until" in format_equity_report({"NIFTY": filtered, "BANKNIFTY": []}, GATE_MET, sessions=[])


# ─── closed_only ─────────────────────────────────────────────────────────

def test_closed_only_excludes_unknown_exit_premium():
    trades = [trade(exit_premium=110.0), trade(exit_premium=None)]
    assert len(closed_only(trades)) == 1


# ─── net_pnl / to_backtest_trade: gross vs. net, no double-subtracting costs ─

def test_net_pnl_is_gross_minus_stressed_cost():
    t = trade(entry_premium=100.0, exit_premium=110.0, quantity=65)
    pnl = net_pnl(t)
    gross = (110.0 - 100.0) * 65
    assert pnl < gross   # cost was actually subtracted
    assert pnl > gross - 100   # but not by an absurd amount for this trade size


def test_to_backtest_trade_profit_stays_gross_costs_stay_separate():
    """Regression guard: BacktestMetrics computes net_profit = profit -
    costs internally. If `profit` here were already cost-adjusted, that
    would double-subtract the cost."""
    t = trade(entry_premium=100.0, exit_premium=110.0, quantity=65)
    bt = to_backtest_trade(t, trade_num=1)
    assert bt.profit == (110.0 - 100.0) * 65
    assert bt.costs > 0
    assert bt.net_profit == bt.profit - bt.costs
    assert abs(bt.net_profit - net_pnl(t)) < 1e-9   # same number, two paths


# ─── format_pf_sharpe_report: no peeking ────────────────────────────────────

def test_pf_sharpe_report_withholds_numbers_before_gate_met():
    trades = [trade() for _ in range(5)]   # well under MIN_SAMPLE_N
    text = format_pf_sharpe_report("NIFTY", trades, [], today=DEPLOYED_AT)
    assert "WAITING" in text
    assert "Gate MET" not in text
    assert "PASS" not in text and "FAIL" not in text


def test_pf_sharpe_report_reveals_numbers_once_gate_met():
    filtered = [trade(exit_premium=110.0 + i) for i in range(MIN_SAMPLE_N)]
    text = format_pf_sharpe_report("NIFTY", filtered, [], today=GATE_MET)
    assert "Gate MET" in text
    assert "PF" in text and "Sharpe" in text


def test_pf_sharpe_report_compares_against_unfiltered_same_window():
    filtered = [trade(exit_premium=110.0) for _ in range(MIN_SAMPLE_N)]
    unfiltered = [trade(exit_premium=105.0) for _ in range(30)]
    text = format_pf_sharpe_report("NIFTY", filtered, unfiltered, today=GATE_MET)
    assert "Unfiltered 18 over the SAME window" in text


def test_pf_sharpe_report_notes_no_unfiltered_comparison_available():
    filtered = [trade(exit_premium=110.0) for _ in range(MIN_SAMPLE_N)]
    text = format_pf_sharpe_report("NIFTY", filtered, [], today=GATE_MET)
    assert "zero comparable closed trades" in text


# ─── format_equity_report: no peeking before 40 recorded sessions ───────────

def test_equity_report_withholds_total_before_the_date():
    text = format_equity_report({"NIFTY": [trade()], "BANKNIFTY": []}, today=BEFORE)
    assert "Not due until" in text
    assert "Final equity" not in text


def test_equity_report_counts_trades_only_through_the_40th_recorded_session():
    due = due_session(WEEKDAYS)
    late = trade(exit_=f"{due + timedelta(days=7)}T09:50:00+00:00", exit_premium=500.0)
    text = format_equity_report({"NIFTY": [trade(), late], "BANKNIFTY": []}, today=GATE_MET)
    assert f"as of {due}" in text and "Trades counted: 1 " in text


def test_equity_report_reveals_total_on_the_date():
    trades = {"NIFTY": [trade(entry_premium=100.0, exit_premium=110.0, quantity=65)], "BANKNIFTY": []}
    text = format_equity_report(trades, today=GATE_MET)
    assert "Final equity" in text
    assert f"Rs{BASE_CAPITAL:,.0f}" in text.split("as of")[0]


def test_equity_report_excludes_unknown_exit_premium_trades():
    trades = {"NIFTY": [trade(exit_premium=None)], "BANKNIFTY": []}
    text = format_equity_report(trades, today=GATE_MET)
    assert "excluded 1" in text


def test_equity_report_pools_both_indices_into_one_account():
    trades = {
        "NIFTY": [trade(underlying="NIFTY", entry_premium=100.0, exit_premium=110.0, quantity=65)],
        "BANKNIFTY": [trade(underlying="BANKNIFTY", entry_premium=500.0, exit_premium=480.0, quantity=30)],
    }
    text = format_equity_report(trades, today=GATE_MET)
    nifty_pnl = net_pnl(trades["NIFTY"][0])
    banknifty_pnl = net_pnl(trades["BANKNIFTY"][0])
    expected_equity = BASE_CAPITAL + nifty_pnl + banknifty_pnl
    assert f"Rs{expected_equity:,.2f}" in text
    # Both legs' own contribution disclosed even though pooled into one account.
    assert "NIFTY contribution" in text and "BANKNIFTY contribution" in text


# ─── 2026-09-30 addendum: two views, INCONCLUSIVE on disagreement ──────────

def _gate_met_today():
    return GATE_MET


def test_views_agree_gives_a_plain_verdict():
    # Post-fix rows only: both views are identical, so they cannot disagree.
    filtered = [trade(exit_premium=110.0 + i % 3, entry="2026-10-05T04:10:00+00:00",
                      exit_="2026-10-05T09:50:00+00:00") for i in range(MIN_SAMPLE_N)]
    text = format_pf_sharpe_report("NIFTY", filtered, [], today=_gate_met_today())
    assert "[as logged]" in text and "[stop enforced]" in text
    assert "VERDICT: 18b" in text and "INCONCLUSIVE" not in text


def test_views_that_flip_the_verdict_are_inconclusive_not_picked():
    """As logged, two pre-fix rows that rode past the unenforced stop to
    near zero sink PF below 1; with the stop enforced they are capped at
    -25% and PF clears. The verdict must refuse to choose."""
    winners = [trade(exit_premium=110.0 + (i % 3)) for i in range(18)]
    blowups = [trade(exit_premium=1.0) for _ in range(2)]
    text = format_pf_sharpe_report("NIFTY", winners + blowups, [], today=_gate_met_today())
    assert "VERDICT: INCONCLUSIVE" in text
    assert "18b PASS/FAIL" in text


def test_stop_enforcement_is_applied_to_the_unfiltered_baseline_too():
    """Symmetry: a pre-fix blowup in unfiltered 18 is capped as well, so the
    baseline is not made artificially weak for 18b to beat."""
    import scripts.check_orb_18b_gate as gate
    filtered = [trade(exit_premium=110.0 + (i % 3), entry="2026-10-05T04:10:00+00:00",
                      exit_="2026-10-05T09:50:00+00:00") for i in range(MIN_SAMPLE_N)]
    unfiltered = [trade(exit_premium=112.0) for _ in range(10)] + [trade(exit_premium=1.0)]
    logged = gate._view(filtered, unfiltered)
    enforced = gate._view(gate.enforce_premium_stop_all(filtered),
                          gate.enforce_premium_stop_all(unfiltered))
    assert enforced["um"].profit_factor > logged["um"].profit_factor


def test_banknifty_sensitivity_view_excludes_expiry_days_from_both_arms(monkeypatch):
    import scripts.check_orb_18b_gate as gate
    monkeypatch.setattr(gate, "BANKNIFTY_EXPIRY_POLICY", "pending")   # the pre-decision behaviour
    filtered = [trade(underlying="BANKNIFTY", exit_premium=110.0 + (i % 3)) for i in range(MIN_SAMPLE_N)]
    filtered.append(trade(underlying="BANKNIFTY", exit_premium=1.0,
                          entry="2026-09-29T04:10:00+00:00", exit_="2026-09-29T09:50:00+00:00"))
    text = format_pf_sharpe_report("BANKNIFTY", filtered, [], today=_gate_met_today())
    assert "BANKNIFTY expiry days excluded both arms" in text
    assert f"n={MIN_SAMPLE_N})" in text.split("sensitivity")[1]


def test_skip_policy_drops_expiry_days_from_the_primary_views(monkeypatch):
    import scripts.check_orb_18b_gate as gate
    monkeypatch.setattr(gate, "BANKNIFTY_EXPIRY_POLICY", "skip")
    filtered = [trade(underlying="BANKNIFTY", exit_premium=110.0 + (i % 3)) for i in range(MIN_SAMPLE_N)]
    filtered.append(trade(underlying="BANKNIFTY", exit_premium=1.0,
                          entry="2026-09-29T04:10:00+00:00", exit_="2026-09-29T09:50:00+00:00"))
    text = gate.format_pf_sharpe_report("BANKNIFTY", filtered, [], today=_gate_met_today())
    assert f"N={MIN_SAMPLE_N} " in text
    assert "sensitivity" not in text


def test_equity_report_shows_both_views():
    text = format_equity_report({"NIFTY": [trade(exit_premium=1.0)], "BANKNIFTY": []}, GATE_MET)
    assert "[as logged]" in text and "[stop enforced]" in text



def test_policy_is_skip_after_the_2026_09_30_fix2_decision():
    import scripts.check_orb_18b_gate as gate
    assert gate.BANKNIFTY_EXPIRY_POLICY == "skip"


def test_2026_11_23_token_outage_is_not_a_recorded_session():
    from scripts.check_orb_18b_gate import recorded_sessions
    s = [date(2026, 11, 20), date(2026, 11, 23), date(2026, 11, 25)]
    assert recorded_sessions(date(2026, 11, 26), s, start=date(2026, 11, 20)) == 2
