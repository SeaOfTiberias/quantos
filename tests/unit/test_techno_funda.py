"""
Techno-funda candidate — unit tests for the pre-registered rules
(docs/TECHNO_FUNDA_PREREG_2026-11-01.md). Synthetic data, round numbers.
"""

from datetime import date, datetime

import numpy as np
import pandas as pd
import pytest

from core.fundamentals.xbrl_financials import PeriodFigures
from core.techno_funda import portfolio as pf
from core.techno_funda.fundamentals import (Filing, integrated_financial, old_feed_financial,
                                            state_from, states_for_symbol)
from core.techno_funda.prices import action_factor, adjust_symbol
from core.techno_funda.symbols import SymbolChain


# ─── Symbols ──────────────────────────────────────────────────────────────────

class TestSymbolChain:
    chain = SymbolChain([("OLD", "MID", date(2015, 1, 1)), ("MID", "NEW", date(2020, 1, 1)),
                         ("REUSE", "A", date(2012, 1, 1)), ("REUSE", "B", date(2018, 1, 1))])

    def test_follows_every_later_rename(self):
        assert self.chain.canonical("OLD", date(2014, 6, 1)) == "NEW"

    def test_row_after_a_rename_is_not_renamed_again(self):
        assert self.chain.canonical("MID", date(2021, 1, 1)) == "MID"

    def test_reused_symbol_maps_by_date(self):
        assert self.chain.canonical("REUSE", date(2011, 1, 1)) == "A"
        assert self.chain.canonical("REUSE", date(2015, 1, 1)) == "B"
        assert self.chain.canonical("REUSE", date(2019, 1, 1)) == "REUSE"


# ─── Classification ───────────────────────────────────────────────────────────

class TestClassification:
    def test_old_feed(self):
        assert old_feed_financial({"bank": "N", "indAs": "Ind-AS New"}) is False
        assert old_feed_financial({"bank": "B", "indAs": "Non-Ind-AS"}) is True
        assert old_feed_financial({"bank": "F", "indAs": "NBFC-IND"}) is True
        assert old_feed_financial({"bank": "N", "indAs": "Non-Ind-AS"}) is True
        assert old_feed_financial({"bank": "N", "indAs": "NBFC-IND"}) is True
        assert old_feed_financial({}) is None

    def test_integrated_feed_by_file_name(self):
        base = "https://nsearchives.nseindia.com/corporate/xbrl/"
        assert integrated_financial({"xbrl": base + "INTEGRATED_FILING_INDAS_1_2_WEB.xml"}) is False
        assert integrated_financial({"xbrl": base + "INTEGRATED_FILING_NBFC_INDAS_1_WEB.xml"}) is True
        assert integrated_financial({"xbrl": base + "INTEGRATED_FILING_LI_1_WEB.xml"}) is True
        assert integrated_financial({"xbrl": None}) is None


# ─── Point-in-time fundamentals ───────────────────────────────────────────────

def q(pat=100.0, revenue=1000.0, op=200.0, shares=1e6):
    # operating profit = revenue - (expenses - da - fc); with da = fc = 0 -> expenses = revenue - op
    return PeriodFigures(revenue=revenue, expenses=revenue - op, da=0.0, finance_costs=0.0,
                         pat=pat, paid_up=shares * 10, face_value=10.0)


def filing(pe, bc, pat=100.0, cons=True, fin=False, fig="default", **kw):
    return Filing("ABC", datetime(*bc), date(*pe), cons, fin, q(pat=pat, **kw) if fig == "default" else fig,
                  None, "old", f"{pe}{bc}")


QUARTERS = [(2023, 6, 30), (2023, 9, 30), (2023, 12, 31), (2024, 3, 31),
            (2024, 6, 30), (2024, 9, 30), (2024, 12, 31), (2025, 3, 31)]


def history(last_pat=130.0):
    fs = [filing(pe, (pe[0], pe[1] % 12 + 1, 10, 18, 0), pat=100.0) for pe in QUARTERS[:4]]
    fs += [filing(pe, (pe[0] + (pe[1] == 12), pe[1] % 12 + 1, 10, 18, 0), pat=110.0) for pe in QUARTERS[4:7]]
    fs.append(filing(QUARTERS[7], (2025, 4, 10, 18, 0), pat=last_pat))
    return fs


class TestFundState:
    def test_growth_against_same_quarter_last_year(self):
        s = state_from(history(130.0), date(2025, 4, 11))
        assert s.quarter_end == date(2025, 3, 31)
        assert s.growth == pytest.approx(0.30)             # 130 vs 100

    def test_opm_ttm(self):
        assert state_from(history(), date(2025, 4, 11)).opm == pytest.approx(0.20)

    def test_growth_from_a_loss_is_undefined(self):
        fs = history()
        fs[3] = filing(QUARTERS[3], (2024, 4, 10, 18, 0), pat=-50.0)
        s = state_from(fs, date(2025, 4, 11))
        assert s.growth is None and s.growth_inputs is True

    def test_missing_quarter_breaks_opm(self):
        fs = [f for f in history() if f.period_end != date(2024, 12, 31)]
        s = state_from(fs, date(2025, 4, 11))
        assert s.opm is None and s.opm_inputs is False

    def test_missing_figures_are_not_filled(self):
        fs = history()
        fs[-1] = filing(QUARTERS[7], (2025, 4, 10, 18, 0), fig=None)
        s = state_from(fs, date(2025, 4, 11))
        assert s.growth is None and s.opm is None and s.shares is None

    def test_consolidated_preferred_and_types_not_mixed(self):
        fs = history()                                  # all consolidated
        fs.append(filing(QUARTERS[7], (2025, 4, 10, 17, 0), pat=999.0, cons=False))
        assert state_from(fs, date(2025, 4, 11)).growth == pytest.approx(0.30)
        # only a standalone filing for the latest quarter -> standalone chosen, no history -> None
        fs = history()[:-1] + [filing(QUARTERS[7], (2025, 4, 10, 18, 0), pat=130.0, cons=False)]
        s = state_from(fs, date(2025, 4, 11))
        assert s.consolidated is False and s.growth is None

    def test_revision_applies_from_its_own_broadcast(self):
        fs = history(130.0) + [filing(QUARTERS[7], (2025, 5, 2, 9, 0), pat=90.0)]
        states = states_for_symbol(fs)
        before = [s for s in states if s.effective == date(2025, 4, 11)][0]
        after = [s for s in states if s.effective == date(2025, 5, 3)][0]
        assert before.growth == pytest.approx(0.30) and after.growth == pytest.approx(-0.10)

    def test_usable_only_from_the_next_calendar_day(self):
        assert states_for_symbol(history())[-1].effective == date(2025, 4, 11)

    def test_latest_financial_filing_makes_ineligible(self):
        fs = history() + [filing((2025, 6, 30), (2025, 7, 20, 9, 0), fin=True, fig=None)]
        s = state_from(fs, date(2025, 7, 21))
        assert s.financial is True and s.growth is None

    def test_shares(self):
        assert state_from(history(), date(2025, 4, 11)).shares == 1e6


# ─── Prices ───────────────────────────────────────────────────────────────────

def bars(closes, start="2020-01-01", sym="ABC"):
    d = pd.bdate_range(start, periods=len(closes))
    c = np.array(closes, dtype=float)
    return pd.DataFrame(dict(sym=sym, series="EQ", date=d, o=c, h=c, l=c, c=c, vol=1000.0, val=1e7))


class TestActionFactor:
    def test_bonus_split_and_both(self):
        assert action_factor("Bonus 1:1") == 0.5
        assert action_factor("Face Value Split (Sub-Division) - From Rs 10/- Per Share To Re 1/- Per Share") == 0.1
        assert action_factor("Bonus 1:1 / Face Value Split From Rs 10/- Per Share To Rs 2/- Per Share") == pytest.approx(0.1)
        assert action_factor("Dividend - Rs 5 Per Share") is None
        assert action_factor("Bonus Debentures 1:1") is None


class TestAdjustSymbol:
    no_filings = staticmethod(lambda s, d: None)

    def test_listed_split_is_back_adjusted(self):
        g = bars([100, 100, 50, 50])
        adj, gaps = adjust_symbol(g, [(g["date"][2], 0.5)], self.no_filings, 0.0)
        assert list(adj["c"]) == [50, 50, 50, 50] and gaps == [] and adj["seg"].max() == 0

    def test_unconfirmed_gap_restarts_the_record(self):
        adj, gaps = adjust_symbol(bars([100, 100, 50, 55, 120]), [], self.no_filings, 0.0)
        assert list(adj["seg"]) == [0, 0, 1, 1, 1] and gaps[0]["confirmed"] is False
        # earlier highs bound the new segment: ATH unknown until 100 is reached
        assert list(adj["ath_known"]) == [True, True, False, False, True]
        assert list(adj["c"]) == [100, 100, 50, 55, 120]          # prices stay continuous

    def test_gap_confirmed_by_share_count_is_adjusted(self):
        adj, gaps = adjust_symbol(bars([100, 100, 50, 55]), [], lambda s, d: 0.5, 0.0)
        assert gaps[0]["confirmed"] and adj["seg"].max() == 0
        assert list(adj["c"]) == [50, 50, 50, 55]

    def test_share_ratio_must_match_within_4pct(self):
        _, gaps = adjust_symbol(bars([100, 100, 50]), [], lambda s, d: 0.6, 0.0)
        assert gaps[0]["confirmed"] is False

    def test_pre2010_raw_high_bounds_the_ath(self):
        adj, _ = adjust_symbol(bars([80, 90, 120]), [], self.no_filings, 100.0)
        assert list(adj["ath_known"]) == [False, False, True]

    def test_pre2010_bound_is_scaled_by_later_splits(self):
        g = bars([80, 90, 60])                                      # 1:1 bonus before day 3
        adj, _ = adjust_symbol(g, [(g["date"][2], 0.5)], self.no_filings, 100.0)
        # bound 100 x 0.5 = 50 on the adjusted scale; adjusted highs 40, 45, 60
        assert list(adj["ath_known"]) == [False, False, True]

    def test_no_history_means_true_ath(self):
        adj, _ = adjust_symbol(bars([10, 12, 11]), [], self.no_filings, 0.0)
        assert adj["ath_known"].all() and list(adj["ath"]) == [10, 12, 12]


# ─── Costs and portfolio ──────────────────────────────────────────────────────

class TestCosts:
    def test_buy_leg(self):
        base = 0.0010 + 0.0000307 + 0.000001
        assert pf.leg_cost(100_000, buy=True) == pytest.approx(100_000 * (base + 0.0010 + 0.00015 + 0.18 * base))

    def test_sell_leg_has_no_stamp(self):
        assert pf.leg_cost(100_000, True) - pf.leg_cost(100_000, False) == pytest.approx(15.0)


def run(open_, close, entry, exit_=None, rank=None, has_bar=None, last_bar=None, slots=2, nav0=1000.0):
    open_, close = np.array(open_, float), np.array(close, float)
    n, m = close.shape
    return pf.simulate(open_, close, np.ones((n, m)), np.ones((n, m), bool) if has_bar is None else np.array(has_bar),
                       np.array(entry, bool), np.ones((n, m)) if rank is None else np.array(rank, float),
                       np.zeros((n, m), bool) if exit_ is None else np.array(exit_, bool),
                       np.full(m, n - 1) if last_bar is None else np.array(last_bar),
                       [f"S{i}" for i in range(m)], nav0=nav0, slots=slots)


class TestSimulate:
    def test_buys_next_open_whole_shares_with_slippage_and_costs(self):
        r = run([[10], [10], [10]], [[10], [10], [10]], [[1], [0], [0]])
        # day 1: alloc 1000/2 = 500; fill 10.01 -> 49 shares
        turnover = 49 * 10.01
        assert r.nav[1] == pytest.approx(1000 - turnover - pf.leg_cost(turnover, True) + 49 * 10)
        assert r.trades == []

    def test_hard_stop_on_close_sells_next_open(self):
        r = run([[10], [10], [9], [9]], [[10], [10], [9.3], [9]], [[1], [0], [0], [0]])
        t = r.trades[0]
        assert (t.reason, t.entry_day, t.exit_day) == ("hard_stop", 1, 3)
        assert t.exit_fill == pytest.approx(9 * 0.999)

    def test_signal_exit_deferred_until_the_stock_trades(self):
        r = run([[10]] * 4, [[10]] * 4, [[1], [0], [0], [0]], exit_=[[0], [1], [0], [0]],
                has_bar=[[1], [1], [0], [1]])
        assert r.trades[0].exit_day == 3

    def test_best_rank_first_then_alphabetical_and_slot_cap(self):
        r = run([[10, 10, 10]] * 3, [[10, 10, 10]] * 3, [[1, 1, 1], [0, 0, 0], [0, 0, 0]],
                rank=[[0.9, 0.95, 0.95]] * 3)
        held = {t.sym for t in r.trades}
        assert held == set()                                   # nothing sold
        assert r.invested[1] > 0
        # S1 and S2 tie on rank and beat S0; only 2 slots
        r2 = run([[10, 10, 10]] * 3, [[10, 10, 10]] * 3, [[1, 1, 1], [0, 0, 0], [0, 0, 0]],
                 rank=[[0.9, 0.95, 0.95]] * 3, exit_=[[0, 0, 0], [1, 1, 1], [0, 0, 0]])
        assert sorted(t.sym for t in r2.trades) == [1, 2]

    def test_delisted_position_sold_at_last_close(self):
        r = run([[10]] * 4, [[10], [10], [8], [8]], [[1], [0], [0], [0]], last_bar=[2],
                has_bar=[[1], [1], [1], [0]])
        t = r.trades[0]
        assert (t.reason, t.exit_day) == ("delisted", 2) and t.exit_fill == pytest.approx(8 * 0.999)

    def test_held_stock_not_bought_twice(self):
        r = run([[10]] * 4, [[10]] * 4, [[1], [1], [1], [0]])
        assert r.invested[3] == pytest.approx(49 * 10)


class TestMetrics:
    def test_max_drawdown(self):
        assert pf.max_drawdown(np.array([100, 120, 90, 130, 117])) == pytest.approx(0.25)

    def test_cagr(self):
        assert pf.cagr(np.array([100.0, 121.0]), 2) == pytest.approx(0.10)

    def test_block_bootstrap_ci_brackets_the_mean(self):
        x = np.r_[np.full(50, 0.01), np.full(50, -0.005)]
        lo, hi = pf.block_bootstrap_ci(x, np.repeat(np.arange(20), 5), n=2000)
        assert lo < x.mean() < hi
