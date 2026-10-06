"""
IV-Gated Short Premium (docs/VRP_IV_GATED_METHODOLOGY.md) — Unit Tests
"""

from datetime import date

import pytest

from core.options.greeks import compute_greeks
from core.options.models import OptionType
from core.options.vrp import iv_gated as g
from core.options.vrp.bhavcopy import BhavcopyOptionRow

ENTRY, EXPIRY, DTE = date(2024, 1, 4), date(2024, 1, 11), 7
FWD, IV = 20000.0, 0.15


def _row(strike, opt_type, close, expiry=EXPIRY, trade_date=ENTRY):
    return BhavcopyOptionRow(
        trade_date=trade_date, underlying="NIFTY", expiry=expiry, strike=strike,
        option_type=opt_type, open=close, high=close, low=close, close=close,
        settle_price=close, open_interest=1000, volume=100, underlying_close=None,
    )


def _chain(fwd=FWD, iv=IV, lo=18000, hi=22000, step=50):
    """A Black-Scholes-priced chain, so every price inverts to `iv`."""
    rows = []
    for k in range(lo, hi + step, step):
        for t in (OptionType.CALL, OptionType.PUT):
            price = round(compute_greeks(fwd, k, DTE, iv, t).theoretical_price, 2)
            if price > 0.05:
                rows.append(_row(float(k), t, price))
    return rows


# ─── Costs ───────────────────────────────────────────────────────────────

class TestLegCost:
    def test_short_itm_leg_pays_no_exercise_stt(self):
        leg = g.Leg(OptionType.CALL, 20000, g.SHORT, 100.0, "delta")
        base = g.leg_cost_points(leg, date(2025, 1, 2), date(2025, 1, 9), settlement=20000)
        itm = g.leg_cost_points(leg, date(2025, 1, 2), date(2025, 1, 9), settlement=20500)
        assert itm == pytest.approx(base)

    def test_long_itm_leg_pays_exercise_stt_on_intrinsic(self):
        leg = g.Leg(OptionType.PUT, 19000, g.LONG, 10.0, "delta")
        otm = g.leg_cost_points(leg, date(2025, 1, 2), date(2025, 1, 9), settlement=19500)
        itm = g.leg_cost_points(leg, date(2025, 1, 2), date(2025, 1, 9), settlement=18800)
        assert itm - otm == pytest.approx(0.00125 * 200)

    @pytest.mark.parametrize("d, rate", [(date(2022, 6, 1), 0.0005), (date(2023, 4, 3), 0.000625),
                                         (date(2024, 10, 1), 0.001), (date(2026, 4, 1), 0.0015)])
    def test_sell_stt_schedule(self, d, rate):
        assert g._rate_asof(g._STT_SELL, d) == rate


# ─── Trades ──────────────────────────────────────────────────────────────

class TestStructureTrade:
    def test_iron_condor_loss_is_capped_by_the_wing(self):
        legs = (g.Leg(OptionType.CALL, 20400, g.SHORT, 40.0, "delta"),
                g.Leg(OptionType.PUT, 19600, g.SHORT, 40.0, "delta"),
                g.Leg(OptionType.CALL, 20700, g.LONG, 8.0, "delta"),
                g.Leg(OptionType.PUT, 19300, g.LONG, 8.0, "delta"))
        t = g.StructureTrade("iron_condor", ENTRY, EXPIRY, FWD, legs, 300.0, settlement=22000.0)
        assert t.entry_credit == pytest.approx(64.0)
        assert t.gross_pnl_points == pytest.approx(64.0 - 300.0)
        assert t.return_on_margin < 0 and t.return_on_margin > -1.0

    def test_unsettled_trade_has_no_return(self):
        legs = (g.Leg(OptionType.CALL, 20400, g.SHORT, 40.0, "delta"),)
        t = g.StructureTrade("strangle", ENTRY, EXPIRY, FWD, legs, 2400.0, settlement=None)
        assert t.return_on_margin is None


class TestSelection:
    def test_atm_iv_recovers_the_chain_iv(self):
        # synthetic_forward is K + C - P without discounting K, so it sits a
        # few points above the pricing spot; ATM is the strike nearest IT.
        atm = g.select_atm(_chain(), EXPIRY, DTE)
        assert atm.strike == round(atm.forward / 50) * 50
        assert atm.iv == pytest.approx(IV, abs=0.01)

    def test_atm_none_when_price_cannot_be_inverted(self):
        rows = [_row(20000.0, OptionType.CALL, 0.01), _row(20000.0, OptionType.PUT, 0.01),
                _row(20050.0, OptionType.CALL, 0.01), _row(20050.0, OptionType.PUT, 0.01)]
        assert g.select_atm(rows, EXPIRY, DTE) is None

    def test_wing_is_beyond_short_strike_near_005_delta(self):
        strike, row, method = g.select_wing(_chain(), EXPIRY, FWD, DTE, 20400.0, OptionType.CALL)
        assert strike > 20400.0 and method == "delta"
        delta = compute_greeks(FWD, strike, DTE, IV, OptionType.CALL).delta
        assert abs(delta - 0.05) <= g.WING_DELTA_TOLERANCE

    def test_wing_falls_back_to_2pct_beyond_when_no_delta_fits(self):
        rows = [_row(20500.0, OptionType.CALL, 30.0), _row(20800.0, OptionType.CALL, 0.01)]
        strike, _, method = g.select_wing(rows, EXPIRY, FWD, DTE, 20400.0, OptionType.CALL)
        assert method == "fallback_pct_otm"
        assert strike == 20800.0   # nearest to 20400 * 1.02 = 20808

    def test_wing_none_when_nothing_beyond(self):
        assert g.select_wing(_chain(hi=20400), EXPIRY, FWD, DTE, 20400.0, OptionType.CALL) is None


# ─── Gate ────────────────────────────────────────────────────────────────

class TestGate:
    def test_warm_up_then_open_on_a_high_value(self):
        ivs = [0.10 + 0.001 * i for i in range(40)] + [0.50, 0.01]
        states = g.gate_states(ivs)
        assert states[:40] == [None] * 40
        assert states[40] is True and states[41] is False

    def test_no_lookahead(self):
        """A cycle's gate must not change when later IVs change."""
        base = [0.12] * 45 + [0.20]
        assert g.gate_states(base)[45] == g.gate_states(base + [0.99, 0.01, 0.50])[45]

    def test_missing_iv_gives_no_state_and_is_not_history(self):
        states = g.gate_states([0.1] * 40 + [None, 0.2])
        assert states[40] is None and states[41] is True

    def test_lookback_is_last_52(self):
        # 52 recent values all above 0.30 means 0.30 is at the 0th percentile,
        # however many low values came before them.
        ivs = [0.05] * 100 + [0.40] * 52 + [0.30]
        assert g.gate_states(ivs)[-1] is False

    def test_segments(self):
        assert g.segment_of(date(2023, 7, 21)) == "A"
        assert g.segment_of(date(2023, 7, 24)) == "B"
        assert g.segment_of(date(2026, 7, 23)) == "C"


# ─── Stats & verdict ─────────────────────────────────────────────────────

def _trade(d, ret):
    """A one-leg trade whose return on a 1000-point margin is `ret` before
    costs (a fraction of a basis point here)."""
    pnl = ret * 1000
    premium = 100.0 + abs(pnl)
    leg = g.Leg(OptionType.CALL, 20000, g.SHORT, premium, "delta")
    return g.StructureTrade("strangle", d, d, FWD, (leg,), 1000.0, settlement=20000 + premium - pnl)


class TestStats:
    def test_closed_weeks_are_zero_filled(self):
        rows = [(date(2020, 1, 2), True, _trade(date(2020, 1, 2), 0.02)),
                (date(2020, 1, 9), False, _trade(date(2020, 1, 9), -0.05)),
                (date(2020, 1, 16), True, _trade(date(2020, 1, 16), 0.01))]
        gated = g.arm_stats(rows, gated=True)
        ungated = g.arm_stats(rows, gated=False)
        assert gated.eligible_cycles == 3 and gated.trades == 2 and gated.gate_runs == 2
        assert ungated.trades == 3 and ungated.gate_runs == 1
        assert gated.annual_return_pct == pytest.approx((0.02 + 0.01) / 3 * 52 * 100, rel=0.03)  # less ~1% costs

    def test_concentration_share(self):
        rows = [(date(2020, 1, 2), True, _trade(date(2020, 1, 2), 0.09)),
                (date(2020, 7, 2), True, _trade(date(2020, 7, 2), 0.01))]
        assert g.arm_stats(rows, gated=True).top_quarter_share == pytest.approx(0.9, abs=0.01)

    def test_open_gate_with_no_trade_counts_as_skipped(self):
        rows = [(date(2020, 1, 2), True, None)]
        s = g.arm_stats(rows, gated=True)
        assert s.trades == 0 and s.skipped_open == 1


def _stats(**kw):
    base = dict(eligible_cycles=100, trades=40, skipped_open=0, gate_runs=10, win_rate=0.7,
                profit_factor=1.5, sharpe=0.8, annual_return_pct=10.0, max_drawdown_pct=5.0,
                worst_trade_pct=-8.0, avg_pct_credit=20.0, top_quarter_share=0.3)
    base.update(kw)
    return g.ArmStats(**base)


class TestVerdict:
    def test_pass(self):
        assert g.verdict(_stats(), _stats(sharpe=0.3))[0] == "PASS"

    def test_gate_must_beat_ungated(self):
        assert g.verdict(_stats(), _stats(sharpe=0.9))[0] == "FAIL"

    def test_concentration_fails(self):
        assert g.verdict(_stats(top_quarter_share=0.6), _stats(sharpe=0.3))[0] == "FAIL"

    def test_small_sample_is_inconclusive(self):
        assert g.verdict(_stats(trades=29), _stats(sharpe=0.3))[0] == "INCONCLUSIVE"
