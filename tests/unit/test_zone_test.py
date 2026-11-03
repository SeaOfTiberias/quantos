"""core/market_map/zone_test.py -- the zone test's event, outcome and placebo rules; synthetic bars."""

from dataclasses import dataclass

from core.market_map.zone_test import (BROKEN, REJECTED, RESISTANCE, SUPPORT, TIMEOUT, Band, Seen, day_events, entry,
                                       htf_label, outcome, placebo, side)


@dataclass
class B:
    high: float
    low: float


ATR = 10.0
Z = Band(95.0, 100.0)                 # a zone under a previous close of 110: tested as support


def test_side_needs_the_close_clearly_outside():
    assert side(Z, 110, ATR) == SUPPORT and side(Z, 90, ATR) == RESISTANCE
    assert side(Z, 100.5, ATR) is None and side(Z, 94.5, ATR) is None        # within 0.1 ATR


def test_entry_is_the_first_overlapping_bar():
    assert entry([B(108, 104), B(104, 101), B(102, 99), B(99, 96)], Z) == 2
    assert entry([B(108, 104), B(105, 101)], Z) is None


def test_support_rejected_needs_half_an_atr_back_above_the_near_edge():
    bars = [B(103, 99), B(104, 98), B(105, 101)]                               # 105 = 100 + 0.5 ATR
    assert outcome(bars, Z, SUPPORT, ATR, True) == REJECTED


def test_support_broken_half_an_atr_under_the_far_edge():
    assert outcome([B(101, 97), B(98, 90)], Z, SUPPORT, ATR, True) == BROKEN    # 90 = 95 - 0.5 ATR


def test_the_entry_bar_can_break_but_not_reject():
    assert outcome([B(106, 99)], Z, SUPPORT, ATR, True) == TIMEOUT              # its 106 may have come first
    assert outcome([B(106, 89)], Z, SUPPORT, ATR, True) == BROKEN


def test_both_in_one_later_bar_is_broken():
    assert outcome([B(101, 99), B(106, 89)], Z, SUPPORT, ATR, True) == BROKEN


def test_resistance_mirrors_support():
    assert outcome([B(96, 94), B(93, 90)], Z, RESISTANCE, ATR, True) == REJECTED     # 90 = 95 - 0.5 ATR
    assert outcome([B(96, 94), B(105, 97)], Z, RESISTANCE, ATR, True) == BROKEN      # 105 = 100 + 0.5 ATR
    assert outcome([B(96, 94), B(99, 93)], Z, RESISTANCE, ATR, False) == TIMEOUT


def test_placebo_mirrors_through_the_close_and_keeps_clear_of_zones():
    zones = [{"low": 95.0, "high": 100.0}]
    assert placebo(Z, 110, zones, ATR) == Band(120.0, 125.0)
    assert placebo(Z, 110, zones + [{"low": 127.0, "high": 128.0}], ATR) is None      # 127 - 3 <= 125
    assert placebo(Z, 110, zones + [{"low": 128.5, "high": 130.0}], ATR) == Band(120.0, 125.0)


def test_seen_skips_an_overlapping_band_for_five_sessions_within_its_kind():
    s = Seen()
    s.add("strong", 10, Z)
    assert s.recent("strong", 15, Band(99, 101)) and not s.recent("strong", 16, Z)
    assert not s.recent("weak", 12, Z) and not s.recent("strong", 12, Band(101, 102))


def test_htf_labels():
    assert [htf_label(2, SUPPORT), htf_label(2, RESISTANCE), htf_label(4, RESISTANCE), htf_label(4, SUPPORT)] == \
        ["with", "against", "with", "against"]
    assert htf_label(1, SUPPORT) == htf_label(3, RESISTANCE) == "none" and htf_label(None, SUPPORT) == "unclassified"


def test_day_events_scores_strong_weak_and_placebo():
    zones = [{"low": 95.0, "high": 100.0, "strong": True, "families": ["swing", "volume"]},
             {"low": 103.0, "high": 104.0, "strong": False, "families": ["pivot"]}]
    today = [B(111, 108), B(109, 103.5), B(104, 99), B(118, 112), B(121, 117)]   # dips into both, then up to the placebo 120-125
    later = [B(131, 119)]                                                       # breaks the placebo (>= 125 + 5)
    evs = day_events(0, zones, 110.0, ATR, today, today + later, True, Seen())
    got = {e["kind"]: (e["side"], e["outcome"]) for e in evs}
    assert got == {"strong": (SUPPORT, REJECTED), "weak": (SUPPORT, REJECTED), "placebo": (RESISTANCE, BROKEN)}
    assert next(e for e in evs if e["kind"] == "strong")["families"] == "swing+volume"
