"""
core/fno_screener -- bhavcopy parsing, OI build-up, bar inversion, contract
selection, candidate ranking and the Telegram text. build_shortlist and
analyse_symbol are covered by their own tests and mocked here.
"""

import csv
import io
import zipfile
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

from core.brokers.base import OHLCV
from core.darvas.weekly_discovery import DiscoveryResult
from core.discovery.momentum_shortlist import ShortlistEntry
from core.fno_screener.bhavcopy import FnoDay, OptionQuote, parse_fno_day
from core.fno_screener.screener import (
    LONG_BUILDUP, LONG_UNWINDING, OI_FLAT, SHORT_BUILDUP, SHORT_COVERING,
    ScreenerConfig, bar_date, bid_ask_pct, build_candidates, classify_buildup, format_telegram,
    invert_bars, market_regime, oi_buildup, pick_contract, setup_rank,
)
from core.options.models import OptionType
from core.trade_watcher.rules import ExitRules

TODAY = date(2026, 10, 9)
OCT, NOV, DEC = date(2026, 10, 27), date(2026, 11, 23), date(2026, 12, 29)
CE, PE = OptionType.CALL, OptionType.PUT

_HEADER = ["FinInstrmTp", "TckrSymb", "XpryDt", "StrkPric", "OptnTp", "ClsPric",
           "UndrlygPric", "OpnIntrst", "TtlTradgVol", "NewBrdLotQty"]


def _zip(rows: list[dict]) -> bytes:
    text = io.StringIO()
    w = csv.DictWriter(text, fieldnames=_HEADER)
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k, "") for k in _HEADER})
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("fo.csv", text.getvalue())
    return buf.getvalue()


def _q(strike, expiry, typ=CE, close=10.0, oi_lots=500, volume=500, lot=1000, symbol="ABC"):
    return OptionQuote(symbol=symbol, expiry=expiry, strike=strike, option_type=typ, close=close,
                       oi_lots=oi_lots, volume=volume, lot_size=lot)


def _day(quotes, spot=100.0, futures=None, trade_date=TODAY, symbol="ABC"):
    return FnoDay(trade_date=trade_date, spot={symbol: spot},
                  futures_oi={symbol: futures or {OCT: 1000}}, options={symbol: quotes})


def _bars(closes, start=datetime(2026, 1, 1, tzinfo=timezone.utc)):
    return [OHLCV(timestamp=start + timedelta(days=i), open=c, high=c * 1.01, low=c * 0.99, close=c, volume=1)
            for i, c in enumerate(closes)]


class TestParse:

    def test_units_and_universe(self):
        raw = _zip([
            dict(FinInstrmTp="STF", TckrSymb="ABC", XpryDt="2026-10-27", OpnIntrst="500000", UndrlygPric="101.5"),
            dict(FinInstrmTp="STF", TckrSymb="ABC", XpryDt="2026-11-23", OpnIntrst="20000", UndrlygPric="101.5"),
            dict(FinInstrmTp="STO", TckrSymb="ABC", XpryDt="2026-10-27", StrkPric="100", OptnTp="CE",
                 ClsPric="4.5", OpnIntrst="250000", TtlTradgVol="37", NewBrdLotQty="500"),
            dict(FinInstrmTp="IDO", TckrSymb="NIFTY", XpryDt="2026-10-13", StrkPric="25000", OptnTp="CE"),
        ])
        day = parse_fno_day(raw, TODAY)
        assert day.symbols == ["ABC"]
        assert day.spot["ABC"] == 101.5
        assert day.futures_oi["ABC"] == {OCT: 500000, NOV: 20000}
        (q,) = day.options["ABC"]
        assert (q.strike, q.option_type, q.close, q.oi_lots, q.volume, q.lot_size) == (100.0, CE, 4.5, 500, 37, 500)


class TestOiBuildup:

    def test_classification(self):
        assert classify_buildup(+2, +10, 2) == LONG_BUILDUP
        assert classify_buildup(-2, +10, 2) == SHORT_BUILDUP
        assert classify_buildup(+2, -10, 2) == SHORT_COVERING
        assert classify_buildup(-2, -10, 2) == LONG_UNWINDING
        assert classify_buildup(+5, 1.5, 2) == OI_FLAT

    def test_expired_contract_does_not_read_as_unwinding(self):
        past = _day([], spot=100, futures={date(2026, 9, 29): 5000, OCT: 1000}, trade_date=date(2026, 9, 25))
        now = _day([], spot=104, futures={OCT: 1100, NOV: 100})
        b = oi_buildup(now, past, "ABC", 2)
        assert b.label == LONG_BUILDUP
        assert b.oi_chg_pct == 20.0          # 1200 vs 1000 (Sep's 5000 is excluded)
        assert b.price_chg_pct == 4.0

    def test_missing_history_is_none(self):
        assert oi_buildup(_day([]), None, "ABC", 2) is None


class TestInvert:

    def test_high_becomes_low_and_ends_at_real_close(self):
        bars = _bars([100, 120, 80, 90])
        inv = invert_bars(bars)
        assert abs(inv[-1].close - 90) < 1e-9
        assert max(range(4), key=lambda i: inv[i].close) == 2       # real low -> inverted high
        assert all(b.high >= b.low for b in inv)

    def test_bar_date_reads_ist(self):
        midnight_ist = OHLCV(timestamp=datetime(2026, 10, 8, 18, 30, tzinfo=timezone.utc),
                             open=1, high=1, low=1, close=1, volume=1)
        assert bar_date(midnight_ist) == date(2026, 10, 9)


class TestPickContract:
    cfg = ScreenerConfig()

    def test_prefers_next_month_when_liquid(self):
        day = _day([_q(95, OCT, close=7), _q(95, NOV, close=9), _q(95, DEC, close=12)])
        k, why = pick_contract(day, "ABC", CE, self.cfg)
        assert k.quote.expiry == NOV and k.note == "" and why == ""
        assert k.lot_cost == 9000 and k.dte == 42      # from Mon 12 Oct, the next session

    def test_falls_back_to_current_month_with_note(self):
        day = _day([_q(95, OCT, close=7), _q(95, NOV, close=9, oi_lots=0, volume=0)])
        k, _ = pick_contract(day, "ABC", CE, self.cfg)
        assert k.quote.expiry == OCT
        assert k.note == "Nov not liquid"

    def test_current_month_too_close_to_expiry_is_never_used(self):
        late = date(2026, 10, 19)                                    # buy Tue 20th: 7 days to Oct expiry
        day = _day([_q(95, OCT, close=7), _q(95, NOV, close=9, oi_lots=0, volume=0)], trade_date=late)
        k, why = pick_contract(day, "ABC", CE, self.cfg)
        assert k is None and why == "illiquid"

    def test_nearest_itm_strike_for_each_side(self):
        quotes = [_q(s, NOV, typ=t, close=8) for s in (90, 95, 100, 105, 110) for t in (CE, PE)]
        day = _day(quotes, spot=101)
        assert pick_contract(day, "ABC", CE, self.cfg)[0].quote.strike == 100
        assert pick_contract(day, "ABC", PE, self.cfg)[0].quote.strike == 105

    def test_lot_cost_cap_is_off_by_default_and_works_when_set(self):
        day = _day([_q(95, NOV, close=30), _q(95, OCT, close=30)])      # 30 x 1000 = 30k
        assert pick_contract(day, "ABC", CE, self.cfg)[0].lot_cost == 30000
        k, why = pick_contract(day, "ABC", CE, ScreenerConfig(max_lot_cost=25000))
        assert k is None and "25,000" in why

    def test_greeks_present_for_a_sane_price(self):
        day = _day([_q(95, NOV, close=8)])
        k, _ = pick_contract(day, "ABC", CE, self.cfg)
        assert 0.5 < k.delta <= 0.8
        assert 0 < k.theta_pct < 5


def _entry(symbol, state="FRESH", days=1, tier="LEADER", trend=True, pct=95.0):
    return ShortlistEntry(symbol=symbol, close=100, momentum_pct=pct, momentum_rank=1, momentum_tier=tier,
                          bucket="LEADER_TIGHT_BASE", base_status="", trend_up=trend,
                          breakout_state=state, days_above_ceil=days, box_width_pct=10.0)


class TestSetupRank:

    def test_order_and_exclusions(self):
        assert setup_rank(_entry("A", "FRESH"), 5) == 0
        assert setup_rank(_entry("A", "OUT", 5), 5) == 1
        assert setup_rank(_entry("A", "NEAR", None), 5) == 2           # watchlist
        assert setup_rank(_entry("A", "OUT", 6), 5) is None             # stale breakout
        assert setup_rank(_entry("A", "IN BOX", None), 1) is None
        assert setup_rank(_entry("A", trend=False), 1) is None
        assert setup_rank(_entry("A", tier="LAGGARD"), 1) is None
        assert ScreenerConfig().max_out_sessions == 5


class TestGatesAndLabels:

    def test_bid_ask_pct(self):
        assert bid_ask_pct((9.5, 10.5)) == 10.0
        assert bid_ask_pct((0.0, 10.5)) is None and bid_ask_pct(None) is None and bid_ask_pct((11, 10)) is None

    def test_market_regime(self):
        up = market_regime(_bars([100.0 + i for i in range(30)]))
        assert up.above and up.close == 129.0 and up.ema < up.close
        assert not market_regime(_bars([130.0 - i for i in range(30)])).above
        assert market_regime(_bars([100.0] * 5)) is None


class TestBuildCandidates:

    def _universe(self):
        quotes = {s: [_q(95, NOV, close=8, symbol=s), _q(105, NOV, typ=PE, close=8, symbol=s)]
                  for s in ("UP1", "UP2", "DN1", "THIN")}
        quotes["THIN"] = [_q(95, NOV, close=8, oi_lots=0, volume=0, symbol="THIN")]
        start = datetime.combine(TODAY, datetime.min.time(), tzinfo=timezone.utc) - timedelta(days=299)
        bars = {s: _bars([100.0] * 300, start=start) for s in quotes}
        day = FnoDay(trade_date=TODAY, spot={s: 100.0 for s in quotes},
                     futures_oi={s: {NOV: 1000} for s in quotes}, options=quotes)
        return bars, day

    def test_routing_ranking_and_skips(self):
        bars, day = self._universe()
        calls = [_entry("UP1", "NEAR", None), _entry("UP2", "FRESH"), _entry("THIN", "FRESH")]
        puts = [_entry("DN1", "OUT", 1), _entry("DN2", "OUT", 7)]
        seen = []

        def fake_shortlist(bars_map, as_of):
            seen.append(bars_map)
            return calls if len(seen) == 1 else puts

        base = DiscoveryResult(symbol="X", status="WATCHING", box_ceiling=98.0)
        with patch("core.fno_screener.screener.build_shortlist", side_effect=fake_shortlist), \
             patch("core.fno_screener.screener.analyse_symbol", return_value=base):
            r = build_candidates(bars, day, None, ScreenerConfig())

        assert [c.symbol for c in r.calls] == ["UP2"]                # NEAR is not a buy
        assert [c.symbol for c in r.watch] == ["UP1"] and r.watch[0].contract is None
        assert [c.symbol for c in r.puts] == ["DN1"]                 # DN2 is 7 sessions out: dropped
        assert r.puts[0].contract.quote.option_type == PE
        assert r.puts[0].box_level == round(100.0 ** 2 / 98.0, 2)   # inverted ceiling -> real floor
        assert [c.symbol for c in r.skipped] == ["THIN"]
        assert seen[1]["UP1"][-1].close == bars["UP1"][-1].close and seen[1] is not bars   # puts got inverted bars

        text = format_telegram(r, ExitRules(initial_stop_pct=10, breakeven_at_pct=8, breakeven_lock_pct=5,
                                            trail_after_pct=12, trail_pct=8), ScreenerConfig())
        assert "UP2" in text and "DN1" in text and "THIN CE" in text
        assert "stop 7.20" in text and "lock at 8.64 → 8.40" in text and "trail from 8.96" in text
        assert "UP1 CE 100.00: close above 98.00" in text           # watchlist line, no contract

    def test_excluded_oi_hook_and_wide_single_not_offered(self, monkeypatch):
        from core.fno_screener import screener as scr
        monkeypatch.setitem(scr._EXCLUDED_OI, CE, {SHORT_COVERING})
        bars, day = self._universe()
        past = FnoDay(trade_date=TODAY - timedelta(days=7), spot={s: 95.0 for s in day.spot},
                      futures_oi={s: {NOV: 2000} for s in day.spot}, options={})   # price up, OI halved
        base = DiscoveryResult(symbol="X", status="WATCHING", box_ceiling=98.0)
        with patch("core.fno_screener.screener.build_shortlist", side_effect=[[_entry("UP2", "FRESH")], []]),              patch("core.fno_screener.screener.analyse_symbol", return_value=base):
            r = build_candidates(bars, day, past, ScreenerConfig())
        assert r.calls == [] and [c.symbol for c in r.dropped] == ["UP2"]
        assert "Dropped on OI build-up" in format_telegram(r, ExitRules(), ScreenerConfig())

        with patch("core.fno_screener.screener.build_shortlist", side_effect=[[_entry("UP2", "FRESH")], []]),              patch("core.fno_screener.screener.analyse_symbol", return_value=base):
            r = build_candidates(bars, day, None, ScreenerConfig())
        import dataclasses
        c = r.calls[0]
        r.calls = [dataclasses.replace(c, contract=dataclasses.replace(c.contract, bid_ask_pct=12.0))]
        text = format_telegram(r, ExitRules(), ScreenerConfig())
        assert "bid-ask 12% > 5%, don't buy it outright" in text and "watcher:" not in text

    def test_stale_symbols_ignored(self):
        bars, day = self._universe()
        bars = {s: b[:-1] for s, b in bars.items()}                 # last bar is the day before
        with patch("core.fno_screener.screener.build_shortlist", return_value=[]):
            assert build_candidates(bars, day, None, ScreenerConfig()).scanned == 0
