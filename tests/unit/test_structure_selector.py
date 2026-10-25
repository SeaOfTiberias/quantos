"""Structure selector (core/ideas/structure.py) on a synthetic Black-Scholes chain."""

from datetime import date

import pytest

from core.ideas.structure import Chain, Quote, View, best_by_family, bs_price, candidates, implied_vol

TODAY, OCT, NOV = date(2026, 10, 21), date(2026, 10, 27), date(2026, 11, 23)


def _chain(spot=1224.0, vol=0.25, spread_pct=1.0):
    ch = Chain("NESTLEIND", spot, 500, TODAY)
    for e in (OCT, NOV):
        t = (e - TODAY).days / 365
        for k in range(1150, 1301, 10):
            for r in ("CE", "PE"):
                m = bs_price(spot, k, t, vol, r)
                hs = max(0.05, m * spread_pct / 100)
                if m > 0.2:
                    ch.options[(e, float(k), r)] = Quote(round(m - hs, 2), round(m + hs, 2))
        ch.futures[e] = Quote(spot + 3.0, spot + 3.3)
    return ch


def test_bs_and_iv_round_trip():
    p = bs_price(1224, 1250, 33 / 365, 0.25, "PE")
    assert implied_vol(p, 1224, 1250, 33 / 365, "PE") == pytest.approx(0.25, abs=1e-3)
    c = bs_price(1224, 1250, 33 / 365, 0.25, "CE")
    assert c - p == pytest.approx(1224 - 1250 * 2.718281828 ** (-0.065 * 33 / 365), abs=0.01)  # put-call parity
    assert implied_vol(0.5, 1224, 1100, 33 / 365, "CE") is None                                # below intrinsic


def test_everything_fits_budget_and_is_ranked():
    view = View(-1, 1200, 1245, 5, risk_budget=12000)
    ranked = candidates(_chain(), view)
    assert ranked and all(c.worst_case * c.lots <= 12000 for c in ranked)
    keys = [(bool(c.flags), -c.score) for c in ranked]            # rule-passing first, then by score
    assert keys == sorted(keys)
    assert all(c.loss_stop <= 0 for c in ranked)


def test_overnight_gap_keeps_futures_out_of_a_small_budget():
    names = lambda v: {c.name for c in candidates(_chain(), v)}
    assert "short future" not in names(View(-1, 1200, 1245, 5, risk_budget=12000, overnight=True))
    assert "short future" in names(View(-1, 1200, 1245, 1, risk_budget=12000, overnight=False))


def test_penny_spreads_are_dropped():
    assert all(c.entry >= 1.0 or "/" in c.name for c in candidates(_chain(), View(-1, 1150, 1245, 5, risk_budget=50000)))


def test_expiry_inside_horizon_is_excluded():
    assert all(c.expiry == NOV for c in candidates(_chain(), View(-1, 1200, 1245, 5, risk_budget=50000)))
    assert any(c.expiry == OCT for c in candidates(_chain(), View(-1, 1200, 1245, 2, risk_budget=50000, overnight=False)))


def test_stall_penalises_long_premium():
    view = View(-1, 1200, 1245, 5, risk_budget=50000)
    single = next(c for c in candidates(_chain(), view) if c.name == "long 1200 PE" and c.expiry == NOV)
    assert single.loss_stop <= min(single.stall, 0)
    near = next(c for c in candidates(_chain(), View(-1, 1200, 1245, 2, risk_budget=50000, overnight=False))
                if c.name == "long 1190 PE" and c.expiry == OCT)
    assert near.stall < 0            # out of the money: half the move does not beat 3 days of decay


def test_wider_bid_ask_lowers_scores():
    view = View(-1, 1200, 1245, 5, risk_budget=12000)
    tight = best_by_family(candidates(_chain(spread_pct=0.5), view))[0]
    wide = {c.name: c for c in candidates(_chain(spread_pct=5.0), view)}
    if tight.name in wide:
        assert wide[tight.name].score < tight.score


def test_bull_view_uses_calls_and_put_credits():
    ranked = candidates(_chain(), View(+1, 1260, 1205, 5, risk_budget=12000))
    assert any(c.name.startswith("bull call") for c in ranked)
    assert any(c.name.startswith("bull put") for c in ranked)
    assert not any(c.name.startswith("bear") for c in ranked)


def test_research_mode_filters_nothing():
    v = View(-1, 1200, 1245, 5, risk_budget=None)
    ranked = candidates(_chain(), v)
    assert "short future" in {c.name for c in ranked} and all(c.lots == 1 for c in ranked)
    assert len(ranked) > len(candidates(_chain(), View(-1, 1200, 1245, 5, risk_budget=12000)))


# ── strike rules R1-R6 and the flat scenario (2026-10-25, the HDFC Bank 670/600 review) ──

def _hdfc(spot=692.8, vol=0.26):
    """A synthetic HDFC Bank-like chain: 10-point strikes, 1.5% bid-ask, 29 days to expiry."""
    ch = Chain("HDFCBANK", spot, 650, date(2026, 10, 25))
    t = (NOV - ch.today).days / 365
    for k in range(560, 791, 10):
        for r in ("CE", "PE"):
            m = bs_price(spot, k, t, vol, r)
            hs = max(0.05, m * 0.0075)
            if m > 0.3:
                ch.options[(NOV, float(k), r)] = Quote(round(m - hs, 2), round(m + hs, 2))
    ch.futures[NOV] = Quote(spot + 3.0, spot + 3.2)
    return ch


HVIEW = dict(direction=-1, target=665, stop=705, horizon_days=10, risk_budget=None, atr=15.9)


def _get(ranked, name):
    return next(c for c in ranked if c.name == name)


def test_the_670_600_breaks_r1_r2_r3_and_690_660_passes():
    ranked = candidates(_hdfc(), View(**HVIEW))
    old = _get(ranked, "bear put 670/600")
    tags = {f[:2] for f in old.flags}
    assert {"R1", "R2", "R3"} <= tags                       # 1.4 ATR OTM, 65 beyond target, ~13% financed
    good = _get(ranked, "bear put 690/660")                 # ~43% financed, short just past the target
    assert good.flags == []
    assert any(f.startswith("R3") for f in _get(ranked, "bear put 690/650").flags)   # ~34%: just under
    assert ranked.index(good) < ranked.index(old)
    assert ranked[0].flags == []                            # the top pick passes every rule


def test_r2_short_strike_too_close_caps_the_trade():
    c = _get(candidates(_hdfc(), View(**HVIEW)), "bear put 690/680")
    assert any(f.startswith("R2") and "caps" in f for f in c.flags)


def test_r6_reach_and_no_atr_skips_atr_rules():
    ranked = candidates(_hdfc(), View(**HVIEW))
    far = _get(ranked, "bear put 670/600")                  # 600 is 5.8 ATR out; reach is 3.0
    assert any(f.startswith("R6") and "600" in f for f in far.flags)
    no_atr = _get(candidates(_hdfc(), View(**{**HVIEW, "atr": None})), "bear put 670/600")
    assert not any(f[:2] in ("R1", "R6") for f in no_atr.flags)
    assert any(f.startswith("R3") for f in no_atr.flags)    # financing needs no ATR


def test_single_option_unfinanced_and_credit_short_inside_stop():
    ranked = candidates(_hdfc(), View(**HVIEW))
    assert any(f.startswith("R3") for f in _get(ranked, "long 690 PE").flags)
    inside = _get(ranked, "bear call 700/720 (credit)")
    assert any(f.startswith("R2") and "inside the stop" in f for f in inside.flags)
    beyond = _get(ranked, "bear call 710/730 (credit)")
    assert not any(f.startswith("R2") for f in beyond.flags)


def test_r5_thesis_matches_family():
    move = candidates(_hdfc(), View(**HVIEW))
    assert all(any(f.startswith("R5") for f in c.flags) for c in move if c.fits == "hold")
    hold = candidates(_hdfc(), View(**{**HVIEW, "thesis": "hold"}))
    assert all(any(f.startswith("R5") for f in c.flags) for c in hold if c.fits == "move" and "future" not in c.name)
    assert hold[0].fits == "hold" and hold[0].flags == []


def test_flat_scenario_counts_time_decay():
    ranked = candidates(_hdfc(), View(**HVIEW))
    otm = _get(ranked, "bear put 670/600")
    assert otm.flat < 0 and otm.loss_stop <= otm.flat           # no move: the OTM put just decays
    credit = _get(ranked, "bear call 710/730 (credit)")
    assert credit.flat > 0                                      # time decay is the credit spread's friend

