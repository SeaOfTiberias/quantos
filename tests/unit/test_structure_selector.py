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
    assert [c.score for c in ranked] == sorted((c.score for c in ranked), reverse=True)
    assert all(c.loss_stop <= 0 for c in ranked)


def test_overnight_gap_keeps_futures_out_of_a_small_budget():
    names = lambda v: {c.name for c in candidates(_chain(), v)}
    assert "short future" not in names(View(-1, 1200, 1245, 5, risk_budget=12000, overnight=True))
    assert "short future" in names(View(-1, 1200, 1245, 1, risk_budget=12000, overnight=False))


def test_stall_penalises_long_premium():
    view = View(-1, 1200, 1245, 5, risk_budget=50000)
    single = next(c for c in candidates(_chain(), view) if c.name == "long 1200 PE" and c.expiry == OCT)
    assert single.stall < 0 and single.loss_stop <= single.stall


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
