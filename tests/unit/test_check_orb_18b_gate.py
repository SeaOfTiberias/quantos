"""
Tests for scripts/check_orb_18b_gate.py -- docs/ORB_ENTRY_FILTER_
METHODOLOGY.md's prospective PF/Sharpe gate (no peeking before N>=20 AND
>=8 weeks) and the Rs50,000 equity narrative (no peeking before
2026-11-17). No network/broker.
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.orb_scalping.dry_run_log import DryRunTrade  # noqa: E402
from scripts.check_orb_18b_gate import (  # noqa: E402
    BASE_CAPITAL,
    DEPLOYED_AT,
    EQUITY_DATE,
    MIN_SAMPLE_N,
    MIN_WEEKS,
    closed_only,
    elapsed_weeks,
    format_equity_report,
    format_pf_sharpe_report,
    gate_status,
    net_pnl,
    to_backtest_trade,
)


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
    assert gate_status(n=25, weeks=9.0)["both_met"] is True
    assert gate_status(n=25, weeks=3.0)["both_met"] is False   # enough trades, not enough time
    assert gate_status(n=5, weeks=9.0)["both_met"] is False    # enough time, not enough trades


def test_gate_status_boundary_is_inclusive():
    assert gate_status(n=MIN_SAMPLE_N, weeks=MIN_WEEKS)["both_met"] is True


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
    today = date(DEPLOYED_AT.year, DEPLOYED_AT.month, DEPLOYED_AT.day)
    from datetime import timedelta
    today = DEPLOYED_AT + timedelta(weeks=int(MIN_WEEKS) + 1)
    text = format_pf_sharpe_report("NIFTY", filtered, [], today=today)
    assert "Gate MET" in text
    assert "PF" in text and "Sharpe" in text


def test_pf_sharpe_report_compares_against_unfiltered_same_window():
    from datetime import timedelta
    today = DEPLOYED_AT + timedelta(weeks=int(MIN_WEEKS) + 1)
    filtered = [trade(exit_premium=110.0) for _ in range(MIN_SAMPLE_N)]
    unfiltered = [trade(exit_premium=105.0) for _ in range(30)]
    text = format_pf_sharpe_report("NIFTY", filtered, unfiltered, today=today)
    assert "Unfiltered 18 over the SAME window" in text


def test_pf_sharpe_report_notes_no_unfiltered_comparison_available():
    from datetime import timedelta
    today = DEPLOYED_AT + timedelta(weeks=int(MIN_WEEKS) + 1)
    filtered = [trade(exit_premium=110.0) for _ in range(MIN_SAMPLE_N)]
    text = format_pf_sharpe_report("NIFTY", filtered, [], today=today)
    assert "zero comparable closed trades" in text


# ─── format_equity_report: no peeking before 2026-11-17 ─────────────────────

def test_equity_report_withholds_total_before_the_date():
    from datetime import timedelta
    text = format_equity_report({"NIFTY": [trade()], "BANKNIFTY": []}, today=EQUITY_DATE - timedelta(days=1))
    assert "Not due until" in text
    assert "Final equity" not in text


def test_equity_report_reveals_total_on_the_date():
    trades = {"NIFTY": [trade(entry_premium=100.0, exit_premium=110.0, quantity=65)], "BANKNIFTY": []}
    text = format_equity_report(trades, today=EQUITY_DATE)
    assert "Final equity" in text
    assert f"Rs{BASE_CAPITAL:,.0f}" in text.split("as of")[0]


def test_equity_report_excludes_unknown_exit_premium_trades():
    trades = {"NIFTY": [trade(exit_premium=None)], "BANKNIFTY": []}
    text = format_equity_report(trades, today=EQUITY_DATE)
    assert "excluded 1" in text


def test_equity_report_pools_both_indices_into_one_account():
    trades = {
        "NIFTY": [trade(underlying="NIFTY", entry_premium=100.0, exit_premium=110.0, quantity=65)],
        "BANKNIFTY": [trade(underlying="BANKNIFTY", entry_premium=500.0, exit_premium=480.0, quantity=30)],
    }
    text = format_equity_report(trades, today=EQUITY_DATE)
    nifty_pnl = net_pnl(trades["NIFTY"][0])
    banknifty_pnl = net_pnl(trades["BANKNIFTY"][0])
    expected_equity = BASE_CAPITAL + nifty_pnl + banknifty_pnl
    assert f"Rs{expected_equity:,.2f}" in text
    # Both legs' own contribution disclosed even though pooled into one account.
    assert "NIFTY contribution" in text and "BANKNIFTY contribution" in text
