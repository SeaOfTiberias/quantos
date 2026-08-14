"""
Option Chain Snapshot Builder — converts FyersBroker.get_option_chain()'s
raw dict into the OptionChainSnapshot recommender.py expects. NOT YET
LIVE-VERIFIED (see chain_builder.py's module docstring) — these tests
pin down the documented/assumed response shape so a future live-response
mismatch surfaces here first.
"""

import pytest
from datetime import date

from core.options.greeks import FALLBACK_IV
from core.options.chain_builder import (
    build_chain_snapshot, ChainBuildError,
    IV_RANK_PLACEHOLDER, IV_PERCENTILE_PLACEHOLDER,
)
from core.options.models import OptionType


def _row(strike, option_type, ltp, oi, volume=100):
    return {
        "strike_price": strike,
        "option_type": option_type,
        "ltp": ltp,
        "oi": oi,
        "volume": volume,
    }


def _sample_raw_chain():
    return {
        "callOi": 300,
        "putOi": 400,
        "optionsChain": [
            _row(21800, "CE", 250, oi=100),
            _row(21800, "PE", 180, oi=150),
            _row(22000, "CE", 120, oi=200),
            _row(22000, "PE", 260, oi=250),
        ],
    }


class TestBuildChainSnapshot:

    def test_builds_expected_number_of_legs(self):
        snap = build_chain_snapshot(
            underlying="NIFTY", expiry=date(2026, 7, 21), spot_price=22000,
            raw_chain=_sample_raw_chain(), days_to_expiry=14,
        )
        assert len(snap.legs) == 4

    def test_pcr_computed_from_oi(self):
        snap = build_chain_snapshot(
            underlying="NIFTY", expiry=date(2026, 7, 21), spot_price=22000,
            raw_chain=_sample_raw_chain(), days_to_expiry=14,
        )
        # total put OI 400 / total call OI 300
        assert snap.pcr == pytest.approx(400 / 300, abs=0.001)

    def test_max_pain_is_a_listed_strike(self):
        snap = build_chain_snapshot(
            underlying="NIFTY", expiry=date(2026, 7, 21), spot_price=22000,
            raw_chain=_sample_raw_chain(), days_to_expiry=14,
        )
        assert snap.max_pain in {21800, 22000}

    def test_iv_solved_per_leg_not_left_as_stub(self):
        snap = build_chain_snapshot(
            underlying="NIFTY", expiry=date(2026, 7, 21), spot_price=22000,
            raw_chain=_sample_raw_chain(), days_to_expiry=14,
        )
        for leg in snap.legs:
            assert leg.implied_vol > 0

    def test_iv_rank_and_percentile_default_to_documented_placeholder(self):
        snap = build_chain_snapshot(
            underlying="NIFTY", expiry=date(2026, 7, 21), spot_price=22000,
            raw_chain=_sample_raw_chain(), days_to_expiry=14,
        )
        assert snap.iv_rank == IV_RANK_PLACEHOLDER
        assert snap.iv_percentile == IV_PERCENTILE_PLACEHOLDER

    def test_camel_case_keys_also_parse(self):
        """Fyers' own docs are inconsistent about snake_case vs camelCase —
        a response using camelCase keys must not silently drop every row."""
        raw = {
            "optionsChain": [
                {"strikePrice": 22000, "optionType": "CE", "ltp": 120, "oi": 200},
                {"strikePrice": 22000, "optionType": "PE", "ltp": 260, "oi": 250},
            ]
        }
        snap = build_chain_snapshot(
            underlying="NIFTY", expiry=date(2026, 7, 21), spot_price=22000,
            raw_chain=raw, days_to_expiry=14,
        )
        assert len(snap.legs) == 2

    def test_non_option_rows_skipped(self):
        raw = _sample_raw_chain()
        raw["optionsChain"].append({
            "strike_price": -1, "option_type": "XX", "ltp": 0, "oi": 0,
        })
        snap = build_chain_snapshot(
            underlying="NIFTY", expiry=date(2026, 7, 21), spot_price=22000,
            raw_chain=raw, days_to_expiry=14,
        )
        assert len(snap.legs) == 4

    def test_empty_chain_raises(self):
        with pytest.raises(ChainBuildError):
            build_chain_snapshot(
                underlying="NIFTY", expiry=date(2026, 7, 21), spot_price=22000,
                raw_chain={"optionsChain": []}, days_to_expiry=14,
            )

    def test_missing_optionschain_key_raises(self):
        with pytest.raises(ChainBuildError):
            build_chain_snapshot(
                underlying="NIFTY", expiry=date(2026, 7, 21), spot_price=22000,
                raw_chain={}, days_to_expiry=14,
            )


class TestEstimatedIvIsFlagged:
    """A leg whose IV could not be solved carries FALLBACK_IV. The value is
    kept so nothing downstream breaks, but the flag records that it was
    invented — otherwise a fabricated 0.18 is indistinguishable from a solved
    one inside an OptionLeg, and gets sized off exactly the same."""

    def _chain(self, rows):
        return {"optionsChain": rows}

    def _row(self, strike, ltp, opt="CE"):
        return {"strike_price": strike, "option_type": opt, "ltp": ltp,
                "oi": 100, "volume": 10}

    def test_solvable_leg_is_not_flagged(self):
        snap = build_chain_snapshot(
            underlying="NIFTY", expiry=date(2026, 8, 28), spot_price=24300.0,
            raw_chain=self._chain([self._row(24300.0, 150.0)]), days_to_expiry=5,
        )
        assert snap.legs[0].implied_vol_estimated is False
        assert snap.legs[0].implied_vol != FALLBACK_IV

    def test_deep_itm_leg_at_intrinsic_is_flagged(self):
        """LTP at intrinsic leaves no time value to invert — routine on a real
        chain, so it must not be an error, only a flag."""
        snap = build_chain_snapshot(
            underlying="NIFTY", expiry=date(2026, 8, 28), spot_price=24300.0,
            raw_chain=self._chain([self._row(20000.0, 4300.0)]), days_to_expiry=5,
        )
        leg = snap.legs[0]
        assert leg.implied_vol_estimated is True
        assert leg.implied_vol == FALLBACK_IV

    def test_a_flagged_leg_does_not_abort_the_chain(self):
        snap = build_chain_snapshot(
            underlying="NIFTY", expiry=date(2026, 8, 28), spot_price=24300.0,
            raw_chain=self._chain([
                self._row(20000.0, 4300.0),      # unsolvable
                self._row(24300.0, 150.0),       # solvable
            ]),
            days_to_expiry=5,
        )
        assert len(snap.legs) == 2
        assert [l.implied_vol_estimated for l in snap.legs] == [True, False]

    def test_caller_can_filter_to_trustworthy_legs(self):
        """The whole point of the flag."""
        snap = build_chain_snapshot(
            underlying="NIFTY", expiry=date(2026, 8, 28), spot_price=24300.0,
            raw_chain=self._chain([
                self._row(20000.0, 4300.0), self._row(24300.0, 150.0),
            ]),
            days_to_expiry=5,
        )
        solved = [l for l in snap.legs if not l.implied_vol_estimated]
        assert [l.strike for l in solved] == [24300.0]
