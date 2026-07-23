"""
VRP Phase 2 — Entry-Cycle + Strike Reconstruction — Unit Tests
"""

from datetime import date

import pytest

from core.options.greeks import compute_greeks
from core.options.models import OptionType
from core.options.vrp.bhavcopy import BhavcopyOptionRow
from core.options.vrp.strikes import (
    DELTA_TOLERANCE,
    TARGET_DELTA,
    build_entry_cycles,
    select_strangle,
    synthetic_forward,
)


def _row(strike, opt_type, close, expiry=date(2024, 1, 11), trade_date=date(2024, 1, 4)):
    return BhavcopyOptionRow(
        trade_date=trade_date, underlying="NIFTY", expiry=expiry, strike=strike,
        option_type=opt_type, open=close, high=close, low=close, close=close,
        settle_price=close, open_interest=1000, volume=100, underlying_close=None,
    )


# ─── synthetic_forward (put-call parity) ────────────────────────────────────

class TestSyntheticForward:
    def test_estimates_forward_from_parity(self):
        # C - P = F - K at every strike here, with F = 20000 exactly.
        rows = [
            _row(19800, OptionType.CALL, 300.0), _row(19800, OptionType.PUT, 100.0),   # F=19800+200=20000
            _row(20000, OptionType.CALL, 150.0), _row(20000, OptionType.PUT, 150.0),   # F=20000+0=20000
            _row(20200, OptionType.CALL, 60.0),  _row(20200, OptionType.PUT, 260.0),   # F=20200-200=20000
        ]
        assert synthetic_forward(rows) == pytest.approx(20000.0, abs=0.01)

    def test_none_when_fewer_than_two_priced_pairs(self):
        rows = [_row(20000, OptionType.CALL, 150.0)]  # no matching put
        assert synthetic_forward(rows) is None

    def test_ignores_zero_priced_legs(self):
        rows = [
            _row(19800, OptionType.CALL, 300.0), _row(19800, OptionType.PUT, 0.0),  # zero -> excluded
            _row(20000, OptionType.CALL, 150.0), _row(20000, OptionType.PUT, 150.0),
            _row(20200, OptionType.CALL, 60.0),  _row(20200, OptionType.PUT, 260.0),
        ]
        assert synthetic_forward(rows) == pytest.approx(20000.0, abs=0.01)


# ─── build_entry_cycles (immediate-roll rule) ────────────────────────────────

class TestBuildEntryCycles:
    def test_immediate_roll_sequence(self):
        # Two back-to-back weekly cycles: expiry Thu, next entry Fri.
        expiries_by_date = {
            date(2024, 1, 1): {date(2024, 1, 4)},
            date(2024, 1, 2): {date(2024, 1, 4)},
            date(2024, 1, 3): {date(2024, 1, 4)},
            date(2024, 1, 4): {date(2024, 1, 4), date(2024, 1, 11)},  # expiry day itself lists next week too
            date(2024, 1, 5): {date(2024, 1, 11)},
            date(2024, 1, 8): {date(2024, 1, 11)},
        }
        cycles = build_entry_cycles(expiries_by_date)
        assert [(c.entry_date, c.expiry_date, c.dte) for c in cycles] == [
            (date(2024, 1, 1), date(2024, 1, 4), 3),
            (date(2024, 1, 5), date(2024, 1, 11), 6),
        ]

    def test_skips_trading_days_with_no_forward_expiry_listed(self):
        # 1/4 has ONLY its own (same-day, non-forward) expiry -- must be
        # skipped as an entry date since there's nothing unexpired to sell.
        expiries_by_date = {
            date(2024, 1, 1): {date(2024, 1, 4)},
            date(2024, 1, 4): {date(2024, 1, 4)},
            date(2024, 1, 5): {date(2024, 1, 11)},
        }
        cycles = build_entry_cycles(expiries_by_date)
        entry_dates = [c.entry_date for c in cycles]
        assert date(2024, 1, 4) not in entry_dates

    def test_empty_input(self):
        assert build_entry_cycles({}) == []


# ─── select_strangle / strike selection ──────────────────────────────────────

SPOT = 20000.0
DTE = 6
IV = 0.15
EXPIRY = date(2024, 1, 11)
ENTRY = date(2024, 1, 4)


def _bs_row(strike, opt_type, spot=SPOT, dte=DTE, iv=IV):
    price = compute_greeks(spot, strike, dte, iv, opt_type).theoretical_price
    return _row(strike, opt_type, price, expiry=EXPIRY, trade_date=ENTRY)


class TestSelectStrangle:
    def test_selects_strike_near_target_delta_from_real_bs_prices(self):
        # A dense strike ladder, BOTH legs priced at every strike (as a real
        # bhavcopy would have) with real Black-Scholes theoretical prices at
        # a known IV -- both feeds the put-call-parity forward estimate and
        # lets the delta search land close to TARGET_DELTA via "delta", not
        # the fallback.
        strikes = [SPOT + k * 50 for k in range(-29, 30)]
        rows = (
            [_bs_row(k, OptionType.CALL) for k in strikes]
            + [_bs_row(k, OptionType.PUT) for k in strikes]
        )
        sel = select_strangle(rows, ENTRY, EXPIRY, DTE)
        assert sel is not None
        assert sel.call.method == "delta"
        assert abs(sel.call.delta - TARGET_DELTA) <= DELTA_TOLERANCE
        assert sel.put.method == "delta"
        assert abs(sel.put.delta - (-TARGET_DELTA)) <= DELTA_TOLERANCE
        assert sel.spot_estimate == pytest.approx(SPOT, rel=0.01)

    def test_falls_back_to_pct_otm_when_no_strike_near_target_delta(self):
        # A sparse ladder that straddles TARGET_DELTA without ever landing
        # near it (verified against real compute_greeks output: 20200 CE is
        # delta 0.33 / 20800 CE is delta 0.02; 19500 PE is delta -0.08 /
        # 19900 PE is delta -0.37 -- all four outside the [-0.30,-0.10] /
        # [0.10, 0.30] tolerance bands) -- the closest match on each side
        # should still exceed DELTA_TOLERANCE and trigger the fixed-%-OTM
        # fallback. Both legs priced at every strike (as a real bhavcopy
        # would have) so the put-call-parity forward estimate can resolve.
        ladder = [19500, 19900, SPOT, 20200, 20800]
        rows = (
            [_bs_row(k, OptionType.CALL) for k in ladder]
            + [_bs_row(k, OptionType.PUT) for k in ladder]
        )
        sel = select_strangle(rows, ENTRY, EXPIRY, DTE)
        assert sel is not None
        assert sel.call.method == "fallback_pct_otm"
        # Fallback target is spot*1.02 = 20400 -- 20200 is the nearer of the two.
        assert sel.call.strike == 20200
        assert sel.put.method == "fallback_pct_otm"
        # Fallback target is spot*0.98 = 19600 -- 19500 is the nearer of the two.
        assert sel.put.strike == 19500

    def test_none_when_expiry_not_present(self):
        rows = [_bs_row(SPOT + 100, OptionType.CALL, dte=13)]
        # rows carry EXPIRY (2024-01-11) but we ask for a different expiry
        sel = select_strangle(rows, ENTRY, date(2024, 1, 18), 13)
        assert sel is None

    def test_none_when_no_otm_strikes_at_all(self):
        # Only ITM strikes on both sides -- no valid OTM candidate for either leg.
        rows = [_bs_row(SPOT - 500, OptionType.CALL), _bs_row(SPOT + 500, OptionType.PUT)]
        sel = select_strangle(rows, ENTRY, EXPIRY, DTE)
        assert sel is None
