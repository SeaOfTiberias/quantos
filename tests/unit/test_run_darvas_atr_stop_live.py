"""
Tests for scripts/run_darvas_atr_stop_live.py -- broker-mocked, no
network, no Fyers, no real filesystem paths (every test that touches the
position store or the dry-run log monkeypatches
core.darvas_atr_stop.live_positions.DARVAS_ATR_STOP_OPEN_POSITIONS_PATH,
core.darvas_atr_stop.dry_run_log.DARVAS_ATR_STOP_DRY_RUN_LOG_PATH, and
agent.risk_guard.HALT_FLAG_PATH to tmp_path, same discipline as
tests/unit/test_run_orb_scalping_live.py's own _patch_common).
"""

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import scripts.run_darvas_atr_stop_live as mod  # noqa: E402
from core.brokers.base import (  # noqa: E402
    OHLCV,
    OrderResult,
    OrderStatus,
    Position,
    ProductType,
)
from core.darvas_atr_stop.dry_run_log import load_dry_run_trades  # noqa: E402
from core.darvas_atr_stop.live_positions import DarvasOpenPosition  # noqa: E402
from core.risk import ClosedTrade, TradeHistoryService  # noqa: E402

START = datetime(2024, 1, 1, tzinfo=timezone.utc)


# ─── Fixtures ────────────────────────────────────────────────────────────

def _bar(i: int, o: float, h: float, l: float, c: float, v: int = 100_000) -> OHLCV:
    return OHLCV(timestamp=START + timedelta(days=i), open=o, high=h, low=l, close=c, volume=v)


def _flat(n: int, price: float, start_i: int = 0) -> list:
    return [_bar(start_i + i, price, price + 0.5, price - 0.5, price) for i in range(n)]


def build_breakout_daily(box_low: float, box_high: float, breakout_close: float,
                          weeks_in_box: int = 10) -> list:
    """A flat warm-up run, a tight weekly range confirming a Darvas box at
    [box_low, box_high], then a high-volume breakout candle as the LAST
    bar -- same fixture shape as
    scripts/analyze_darvas_width_sensitivity.py's own build_breakout_series
    (proven to clear core/darvas/weekly_discovery.py's real box/breakout
    logic), truncated right at the breakout with no forward tail since
    this file only needs the FRESH BREAKOUT day itself, not a return
    window -- analyse_symbol's own box math is exercised exhaustively in
    tests/unit/test_weekly_discovery.py, not re-verified here."""
    candles = _flat(70, price=(box_low + box_high) / 2)
    day = len(candles)
    mid = (box_low + box_high) / 2
    for _w in range(weeks_in_box):
        for _d in range(5):
            candles.append(_bar(day, mid, box_high - 0.1, box_low + 0.1, mid, v=100_000))
            day += 1
    candles.append(_bar(day, box_high, breakout_close + 1, box_high - 0.1, breakout_close, v=500_000))
    return candles


def _position(symbol="TEST", **overrides) -> DarvasOpenPosition:
    defaults = dict(
        symbol=symbol, quantity=50, entry_price=140.0, entry_date="2024-01-02",
        box_width_pct=40.0, seen_ceiling=140.0, current_stop=130.0, current_target=180.0,
        entry_order_id="ORD-1", stop_order_id="SL-1",
    )
    defaults.update(overrides)
    return DarvasOpenPosition(**defaults)


class _FakeBroker:
    def __init__(self, daily_by_symbol=None, ltp=None, positions=None, order_history=None,
                 fill_price=100.0):
        self._daily_by_symbol = daily_by_symbol or {}
        self._ltp = ltp or {}
        self._positions = positions or []
        self._order_history = order_history or []
        self.fill_price = fill_price
        self.placed_orders = []
        self.cancelled_order_ids = []
        self.modified = None
        self._next_id = 1

    def get_historical_data(self, symbol, timeframe, from_date, to_date):
        candles = self._daily_by_symbol.get(symbol, [])
        return [c for c in candles if c.timestamp <= to_date]

    def get_ltp(self, symbols):
        return {s: self._ltp[s] for s in symbols if s in self._ltp}

    def place_order(self, order):
        order_id = f"ORD-{self._next_id}"
        self._next_id += 1
        self.placed_orders.append(order)
        return OrderResult(
            order_id=order_id, status=OrderStatus.EXECUTED, symbol=order.symbol,
            direction=order.direction, quantity=order.quantity, filled_quantity=order.quantity,
            average_price=self.fill_price, timestamp=datetime.now(timezone.utc),
        )

    def cancel_order(self, order_id):
        self.cancelled_order_ids.append(order_id)
        return True

    def modify_stop_loss(self, order_id, new_trigger_price):
        self.modified = (order_id, new_trigger_price)
        return True

    def get_positions(self):
        return self._positions

    def get_order_history(self):
        return self._order_history


def _patch_common(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "core.darvas_atr_stop.live_positions.DARVAS_ATR_STOP_OPEN_POSITIONS_PATH",
        tmp_path / "darvas_atr_stop_open_positions.json",
    )
    monkeypatch.setattr(
        "core.darvas_atr_stop.dry_run_log.DARVAS_ATR_STOP_DRY_RUN_LOG_PATH",
        tmp_path / "darvas_atr_stop_dry_run_trades.jsonl",
    )
    monkeypatch.setattr("agent.risk_guard.HALT_FLAG_PATH", tmp_path / "halt")


# ─── _position_size (pure) ─────────────────────────────────────────────────

class TestPositionSize:
    def test_sizes_a_fraction_of_current_equity(self):
        qty, note = mod._position_size([], {}, starting_capital=1_000_000.0, equity_fraction=0.09,
                                        entry_price=100.0, symbol="TEST")
        assert qty == int(0.09 * 1_000_000.0 // 100.0)
        assert "sized" in note

    def test_refuses_when_spendable_below_entry_price(self):
        qty, note = mod._position_size([], {}, starting_capital=500.0, equity_fraction=0.09,
                                        entry_price=1000.0, symbol="TEST")
        assert qty == 0
        assert "insufficient cash" in note

    def test_capital_already_committed_to_open_positions_reduces_spendable_cash(self):
        """The concurrency gap docs/DARVAS_ATR_STOP_EQUITY_CURVE_RESULTS.md
        flagged for single-trade Kelly (mean 12.2, max 29 concurrent
        Bucket B positions): a new signal must never be sized off TOTAL
        equity while other positions already hold real cash."""
        existing = _position(symbol="OTHER", quantity=100, entry_price=900.0)
        positions = {"OTHER": existing}
        # equity=1,000,000; invested=90,000; available=910,000; 9% of equity=90,000 (< available)
        qty, _ = mod._position_size([], positions, starting_capital=1_000_000.0,
                                     equity_fraction=0.09, entry_price=100.0, symbol="TEST")
        assert qty == int(90_000.0 // 100.0)

    def test_own_strategy_realized_pnl_increases_sizeable_equity(self):
        trade = ClosedTrade(
            trade_id="t1", symbol="X", entry_price=100.0, exit_price=200.0, quantity=500,
            direction="BUY", entry_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            exit_date=datetime(2024, 1, 2, tzinfo=timezone.utc), strategy=mod.STRATEGY_NAME,
        )
        qty_with, _ = mod._position_size([trade], {}, starting_capital=100_000.0,
                                          equity_fraction=0.09, entry_price=100.0, symbol="TEST")
        qty_without, _ = mod._position_size([], {}, starting_capital=100_000.0,
                                             equity_fraction=0.09, entry_price=100.0, symbol="TEST")
        assert qty_with > qty_without

    def test_other_strategy_trades_never_feed_this_strategys_sizing(self):
        trade = ClosedTrade(
            trade_id="t1", symbol="X", entry_price=100.0, exit_price=1000.0, quantity=100,
            direction="BUY", entry_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            exit_date=datetime(2024, 1, 2, tzinfo=timezone.utc), strategy="orb_scalping",
        )
        qty, _ = mod._position_size([trade], {}, starting_capital=100_000.0, equity_fraction=0.09,
                                     entry_price=100.0, symbol="TEST")
        assert qty == int(0.09 * 100_000.0 // 100.0)

    def test_below_capital_floor_refuses_entirely(self):
        qty, note = mod._position_size([], {}, starting_capital=10_000.0, equity_fraction=0.09,
                                        entry_price=100.0, symbol="TEST", min_capital_floor=50_000.0)
        assert qty == 0
        assert "below floor" in note

    def test_heavy_realized_losses_never_produce_a_negative_quantity(self):
        trade = ClosedTrade(
            trade_id="t1", symbol="X", entry_price=100.0, exit_price=0.0, quantity=1000,
            direction="BUY", entry_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            exit_date=datetime(2024, 1, 2, tzinfo=timezone.utc), strategy=mod.STRATEGY_NAME,
        )
        qty, note = mod._position_size([trade], {}, starting_capital=1000.0, equity_fraction=0.09,
                                        entry_price=100.0, symbol="TEST")
        assert qty == 0
        assert note   # refused with a reason, whichever guard caught it first


# ─── _fetch_daily_through_yesterday ─────────────────────────────────────────

def test_fetch_daily_through_yesterday_excludes_todays_own_bar():
    daily = [_bar(0, 100, 101, 99, 100), _bar(1, 101, 102, 100, 101)]
    broker = _FakeBroker(daily_by_symbol={"TEST": daily})
    today = daily[-1].timestamp.date()   # exclude the bar dated "today"
    result = mod._fetch_daily_through_yesterday(broker, "TEST", today)
    assert len(result) == 1
    assert result[0].timestamp.date() < today


def test_fetch_daily_through_yesterday_returns_sorted_bars():
    daily = [_bar(1, 101, 102, 100, 101), _bar(0, 100, 101, 99, 100)]   # out of order
    broker = _FakeBroker(daily_by_symbol={"TEST": daily})
    today = date(2024, 1, 3)
    result = mod._fetch_daily_through_yesterday(broker, "TEST", today)
    assert [c.timestamp for c in result] == sorted(c.timestamp for c in daily)


# ─── _detect_and_enter ──────────────────────────────────────────────────────

class TestDetectAndEnter:
    def test_enters_bucket_b_breakout_dry_run(self, monkeypatch, tmp_path):
        _patch_common(monkeypatch, tmp_path)
        daily = build_breakout_daily(box_low=100.0, box_high=140.0, breakout_close=145.0)
        broker = _FakeBroker(daily_by_symbol={"TEST": daily}, ltp={"TEST": 145.0})
        positions = {}
        mod._detect_and_enter(broker, "TEST", daily, positions, TradeHistoryService(), dry_run=True,
                               equity_fraction=0.09, starting_capital=1_000_000.0,
                               min_capital_floor=0.0, today_iso="2024-05-01")

        assert "TEST" in positions
        pos = positions["TEST"]
        assert 35.0 < pos.box_width_pct <= 50.0
        assert pos.quantity > 0
        assert broker.placed_orders == []   # dry_run places no real orders

    def test_enters_live_places_market_and_protective_stop_orders(self, monkeypatch, tmp_path):
        _patch_common(monkeypatch, tmp_path)
        daily = build_breakout_daily(box_low=100.0, box_high=140.0, breakout_close=145.0)
        broker = _FakeBroker(daily_by_symbol={"TEST": daily}, ltp={"TEST": 145.0})
        positions = {}
        mod._detect_and_enter(broker, "TEST", daily, positions, TradeHistoryService(), dry_run=False,
                               equity_fraction=0.09, starting_capital=1_000_000.0,
                               min_capital_floor=0.0, today_iso="2024-05-01")

        assert len(broker.placed_orders) == 2
        entry_order, stop_order = broker.placed_orders
        # CNC (delivery), never INTRADAY -- a multi-week hold would be
        # auto-squared-off same day under INTRADAY and silently destroy
        # the strategy.
        assert entry_order.product_type == ProductType.CNC
        assert stop_order.product_type == ProductType.CNC
        pos = positions["TEST"]
        assert pos.entry_order_id != "" and pos.stop_order_id != ""

    def test_skips_entry_outside_bucket_b_width(self, monkeypatch, tmp_path):
        _patch_common(monkeypatch, tmp_path)
        daily = build_breakout_daily(box_low=100.0, box_high=125.0, breakout_close=130.0)  # ~25% wide
        broker = _FakeBroker(daily_by_symbol={"TEST": daily}, ltp={"TEST": 130.0})
        positions = {}
        mod._detect_and_enter(broker, "TEST", daily, positions, TradeHistoryService(), dry_run=True,
                               equity_fraction=0.09, starting_capital=1_000_000.0,
                               min_capital_floor=0.0, today_iso="2024-05-01")
        assert positions == {}

    def test_skips_entry_with_insufficient_history(self, monkeypatch, tmp_path):
        _patch_common(monkeypatch, tmp_path)
        daily = _flat(10, price=100.0)
        positions = {}
        mod._detect_and_enter(_FakeBroker(), "TEST", daily, positions, TradeHistoryService(),
                               dry_run=True, equity_fraction=0.09, starting_capital=1_000_000.0,
                               min_capital_floor=0.0, today_iso="2024-05-01")
        assert positions == {}

    def test_skips_stale_signal_when_price_already_at_or_below_stop(self, monkeypatch, tmp_path):
        _patch_common(monkeypatch, tmp_path)
        daily = build_breakout_daily(box_low=100.0, box_high=140.0, breakout_close=145.0)
        result = mod.analyse_symbol("TEST", daily, cfg=mod.WIDE_CFG)
        stop = mod._stop_from_atr(daily, len(daily) - 1, result.box_ceiling)
        broker = _FakeBroker(daily_by_symbol={"TEST": daily}, ltp={"TEST": stop - 1.0})
        positions = {}
        mod._detect_and_enter(broker, "TEST", daily, positions, TradeHistoryService(), dry_run=True,
                               equity_fraction=0.09, starting_capital=1_000_000.0,
                               min_capital_floor=0.0, today_iso="2024-05-01")
        assert positions == {}

    def test_skips_entry_when_sizing_refuses(self, monkeypatch, tmp_path):
        _patch_common(monkeypatch, tmp_path)
        daily = build_breakout_daily(box_low=100.0, box_high=140.0, breakout_close=145.0)
        broker = _FakeBroker(daily_by_symbol={"TEST": daily}, ltp={"TEST": 145.0})
        positions = {}
        mod._detect_and_enter(broker, "TEST", daily, positions, TradeHistoryService(), dry_run=True,
                               equity_fraction=0.09, starting_capital=1.0,   # far too little capital
                               min_capital_floor=0.0, today_iso="2024-05-01")
        assert positions == {}
        assert broker.placed_orders == []


# ─── _manage_existing_position ──────────────────────────────────────────────

class TestManageExistingPosition:
    def test_dry_run_stop_hit_removes_position_without_recording_trade(self, monkeypatch, tmp_path):
        _patch_common(monkeypatch, tmp_path)
        existing = _position()
        positions = {"TEST": existing}
        daily = [_bar(0, 135, 136, 125, 128)]   # low=125 <= stop=130
        broker = _FakeBroker(ltp={"TEST": 129.0})
        trade_history = TradeHistoryService()

        mod._manage_existing_position(broker, "TEST", daily, existing, dry_run=True,
                                       positions=positions, trade_history=trade_history)

        assert "TEST" not in positions
        assert trade_history.get_trade_history() == []
        assert broker.placed_orders == []

        # The round trip must still leave a queryable record for a future
        # real equity curve -- PF/Sharpe alone is not what this log is for.
        logged = load_dry_run_trades()
        assert len(logged) == 1
        assert logged[0].symbol == "TEST"
        assert logged[0].exit_reason == "stop"
        assert logged[0].boundary_price == 130.0
        assert logged[0].entry_price == existing.entry_price
        assert logged[0].quantity == existing.quantity
        assert logged[0].box_width_pct == existing.box_width_pct
        assert logged[0].exit_ltp == 129.0

    def test_dry_run_target_hit_removes_position_without_recording_trade(self, monkeypatch, tmp_path):
        _patch_common(monkeypatch, tmp_path)
        existing = _position()
        positions = {"TEST": existing}
        daily = [_bar(0, 175, 185, 174, 182)]   # high=185 >= target=180
        broker = _FakeBroker()
        trade_history = TradeHistoryService()

        mod._manage_existing_position(broker, "TEST", daily, existing, dry_run=True,
                                       positions=positions, trade_history=trade_history)

        logged = load_dry_run_trades()
        assert len(logged) == 1
        assert logged[0].exit_reason == "target"
        assert logged[0].boundary_price == 180.0
        assert logged[0].exit_ltp is None   # no LTP configured on this broker -- never guessed

    def test_dry_run_log_survives_a_failed_ltp_fetch(self, monkeypatch, tmp_path):
        _patch_common(monkeypatch, tmp_path)
        existing = _position()
        positions = {"TEST": existing}
        daily = [_bar(0, 135, 136, 125, 128)]

        class _BrokenLtpBroker(_FakeBroker):
            def get_ltp(self, symbols):
                raise RuntimeError("quote feed down")

        broker = _BrokenLtpBroker()
        mod._manage_existing_position(broker, "TEST", daily, existing, dry_run=True,
                                       positions=positions, trade_history=TradeHistoryService())

        assert "TEST" not in positions
        logged = load_dry_run_trades()
        assert len(logged) == 1
        assert logged[0].exit_ltp is None

    def test_dry_run_log_path_is_respected_when_explicitly_given(self, monkeypatch, tmp_path):
        _patch_common(monkeypatch, tmp_path)
        custom_path = tmp_path / "custom_dry_run.jsonl"
        existing = _position()
        positions = {"TEST": existing}
        daily = [_bar(0, 135, 136, 125, 128)]

        mod._manage_existing_position(_FakeBroker(), "TEST", daily, existing, dry_run=True,
                                       positions=positions, trade_history=TradeHistoryService(),
                                       dry_run_log_path=custom_path)

        assert custom_path.exists()
        assert load_dry_run_trades() == []          # nothing at the default (monkeypatched) path
        assert len(load_dry_run_trades(path=custom_path)) == 1
        assert "TEST" not in positions

    def test_live_target_hit_flattens_and_records_trade(self, monkeypatch, tmp_path):
        _patch_common(monkeypatch, tmp_path)
        existing = _position()
        positions = {"TEST": existing}
        daily = [_bar(0, 175, 185, 174, 182)]   # high=185 >= target=180
        broker = _FakeBroker(positions=[Position(symbol="TEST", quantity=50, average_price=140.0,
                                                  current_price=182.0, pnl=2100.0, pnl_percent=30.0,
                                                  product_type=ProductType.CNC)])
        trade_history = TradeHistoryService()

        mod._manage_existing_position(broker, "TEST", daily, existing, dry_run=False,
                                       positions=positions, trade_history=trade_history)

        assert "TEST" not in positions
        assert broker.cancelled_order_ids == ["SL-1"]
        assert len(broker.placed_orders) == 1   # the closing MARKET SELL
        history = trade_history.get_trade_history()
        assert len(history) == 1
        assert history[0].strategy == mod.STRATEGY_NAME

    def test_live_reconcile_finds_stop_fill_before_any_bar_check(self, monkeypatch, tmp_path):
        _patch_common(monkeypatch, tmp_path)
        existing = _position()
        positions = {"TEST": existing}
        # This bar alone would trigger neither stop (130) nor target (180).
        daily = [_bar(0, 150, 155, 145, 152)]
        broker = _FakeBroker(
            positions=[],   # broker shows the position already closed
            order_history=[OrderResult(
                order_id="SL-1", status=OrderStatus.EXECUTED, symbol="TEST", direction=None,
                quantity=50, filled_quantity=50, average_price=129.5, timestamp=datetime.now(timezone.utc),
            )],
        )
        trade_history = TradeHistoryService()

        mod._manage_existing_position(broker, "TEST", daily, existing, dry_run=False,
                                       positions=positions, trade_history=trade_history)

        assert "TEST" not in positions
        history = trade_history.get_trade_history()
        assert len(history) == 1
        assert history[0].exit_price == 129.5
        assert broker.placed_orders == []   # no forced flatten -- the broker already closed it

    def test_still_open_with_no_new_closed_bar_is_a_no_op(self, monkeypatch, tmp_path):
        _patch_common(monkeypatch, tmp_path)
        existing = _position()
        positions = {"TEST": existing}
        broker = _FakeBroker(positions=[Position(symbol="TEST", quantity=50, average_price=140.0,
                                                  current_price=140.0, pnl=0.0, pnl_percent=0.0,
                                                  product_type=ProductType.CNC)])
        trade_history = TradeHistoryService()

        mod._manage_existing_position(broker, "TEST", [], existing, dry_run=False,
                                       positions=positions, trade_history=trade_history)

        assert "TEST" in positions
        assert broker.placed_orders == []
        assert broker.cancelled_order_ids == []

    def test_trails_stop_and_target_when_a_new_higher_box_confirms(self, monkeypatch, tmp_path):
        _patch_common(monkeypatch, tmp_path)
        existing = _position()
        positions = {"TEST": existing}
        daily = [_bar(0, 150, 160, 149, 158)]   # doesn't hit stop(130) or target(180)

        fake_result = SimpleNamespace(box_ceiling=170.0, mm_target=210.0)
        monkeypatch.setattr(mod, "analyse_symbol", lambda symbol, daily_arg, cfg=None: fake_result)
        monkeypatch.setattr(mod, "_stop_from_atr", lambda daily_arg, idx, ceiling: 150.0)

        broker = _FakeBroker(positions=[Position(symbol="TEST", quantity=50, average_price=140.0,
                                                  current_price=158.0, pnl=900.0, pnl_percent=13.0,
                                                  product_type=ProductType.CNC)])
        trade_history = TradeHistoryService()

        mod._manage_existing_position(broker, "TEST", daily, existing, dry_run=False,
                                       positions=positions, trade_history=trade_history)

        updated = positions["TEST"]
        assert updated.current_stop == 150.0
        assert updated.current_target == 210.0
        assert updated.seen_ceiling == 170.0
        assert broker.modified == ("SL-1", 150.0)

    def test_no_trail_when_the_recomputed_stop_is_not_higher(self, monkeypatch, tmp_path):
        _patch_common(monkeypatch, tmp_path)
        existing = _position()
        positions = {"TEST": existing}
        daily = [_bar(0, 150, 160, 149, 158)]

        fake_result = SimpleNamespace(box_ceiling=170.0, mm_target=175.0)
        monkeypatch.setattr(mod, "analyse_symbol", lambda symbol, daily_arg, cfg=None: fake_result)
        monkeypatch.setattr(mod, "_stop_from_atr", lambda daily_arg, idx, ceiling: 125.0)  # below current 130

        broker = _FakeBroker(positions=[Position(symbol="TEST", quantity=50, average_price=140.0,
                                                  current_price=158.0, pnl=900.0, pnl_percent=13.0,
                                                  product_type=ProductType.CNC)])
        trade_history = TradeHistoryService()

        mod._manage_existing_position(broker, "TEST", daily, existing, dry_run=False,
                                       positions=positions, trade_history=trade_history)

        updated = positions["TEST"]
        assert updated.current_stop == 130.0    # unchanged
        assert updated.current_target == 180.0  # unchanged
        assert broker.modified is None

    def test_stop_never_trails_down_even_if_a_lower_box_is_seen(self, monkeypatch, tmp_path):
        """`result.box_ceiling <= existing.seen_ceiling` short-circuits
        before _stop_from_atr is even consulted -- a lower/equal ceiling
        must never touch the trail."""
        _patch_common(monkeypatch, tmp_path)
        existing = _position()
        positions = {"TEST": existing}
        daily = [_bar(0, 135, 138, 132, 136)]   # doesn't hit stop(130) or target(180)

        fake_result = SimpleNamespace(box_ceiling=135.0, mm_target=160.0)   # <= seen_ceiling (140)
        monkeypatch.setattr(mod, "analyse_symbol", lambda symbol, daily_arg, cfg=None: fake_result)

        broker = _FakeBroker(positions=[Position(symbol="TEST", quantity=50, average_price=140.0,
                                                  current_price=136.0, pnl=-200.0, pnl_percent=-3.0,
                                                  product_type=ProductType.CNC)])
        trade_history = TradeHistoryService()

        mod._manage_existing_position(broker, "TEST", daily, existing, dry_run=False,
                                       positions=positions, trade_history=trade_history)

        assert positions["TEST"].current_stop == 130.0
        assert broker.modified is None


# ─── Halt-flag kill-switch ───────────────────────────────────────────────────

class TestHaltFlagBlocksNewEntriesOnly:
    def test_new_entry_refused_while_halted(self, monkeypatch, tmp_path):
        _patch_common(monkeypatch, tmp_path)
        (tmp_path / "halt").write_text("2026-09-25T00:00:00 IST -- test halt\n")

        daily = build_breakout_daily(box_low=100.0, box_high=140.0, breakout_close=145.0)
        broker = _FakeBroker(daily_by_symbol={"TEST": daily}, ltp={"TEST": 145.0})
        positions = {}
        today = daily[-1].timestamp.date() + timedelta(days=1)

        mod.process_symbol(broker, "TEST", positions, TradeHistoryService(), dry_run=True,
                            equity_fraction=0.09, starting_capital=1_000_000.0,
                            min_capital_floor=0.0, today=today)

        assert positions == {}
        assert broker.placed_orders == []

    def test_existing_position_still_managed_while_halted(self, monkeypatch, tmp_path):
        _patch_common(monkeypatch, tmp_path)
        (tmp_path / "halt").write_text("2026-09-25T00:00:00 IST -- test halt\n")

        existing = _position(entry_date="2024-01-01")
        positions = {"TEST": existing}
        daily = [_bar(0, 135, 136, 125, 128)]   # low=125 <= stop=130
        broker = _FakeBroker(daily_by_symbol={"TEST": daily})
        today = date(2024, 1, 2)

        mod.process_symbol(broker, "TEST", positions, TradeHistoryService(), dry_run=True,
                            equity_fraction=0.09, starting_capital=1_000_000.0,
                            min_capital_floor=0.0, today=today)

        # Proves exit management is never gated by the halt flag: the stop
        # fired and the position was closed, not merely "left alone".
        assert positions == {}

    def test_entry_allowed_once_halt_file_is_absent(self, monkeypatch, tmp_path):
        _patch_common(monkeypatch, tmp_path)
        daily = build_breakout_daily(box_low=100.0, box_high=140.0, breakout_close=145.0)
        broker = _FakeBroker(daily_by_symbol={"TEST": daily}, ltp={"TEST": 145.0})
        positions = {}
        today = daily[-1].timestamp.date() + timedelta(days=1)

        mod.process_symbol(broker, "TEST", positions, TradeHistoryService(), dry_run=True,
                            equity_fraction=0.09, starting_capital=1_000_000.0,
                            min_capital_floor=0.0, today=today)

        assert "TEST" in positions


# ─── main(): config wiring ───────────────────────────────────────────────────

def _patch_main_deps(monkeypatch, cfg=None, universe=None):
    calls = []

    class _StubBroker:
        def connect(self):
            return True

    monkeypatch.setattr(mod, "load_config", lambda path: {
        "broker": "stub", "darvas_atr_stop": cfg if cfg is not None else {"enabled": False},
    })
    monkeypatch.setattr(mod, "get_broker", lambda config: _StubBroker())
    monkeypatch.setattr(mod, "_load_universe", lambda universe_file: universe or [])

    def spy_process_symbol(broker, symbol, positions, trade_history, dry_run, equity_fraction,
                            starting_capital, min_capital_floor, today, positions_path=None):
        calls.append(dict(symbol=symbol, dry_run=dry_run, equity_fraction=equity_fraction,
                           starting_capital=starting_capital, min_capital_floor=min_capital_floor))

    monkeypatch.setattr(mod, "process_symbol", spy_process_symbol)
    monkeypatch.setattr(mod, "load_open_positions", lambda: {})
    monkeypatch.setattr(mod.time, "sleep", lambda s: None)   # keep the test suite fast
    return calls


class TestMainConfigWiring:
    def test_disabled_by_default_does_nothing(self, monkeypatch):
        calls = _patch_main_deps(monkeypatch, cfg={"enabled": False}, universe=["A", "B"])
        assert mod.main([]) == 0
        assert calls == []

    def test_enabled_scans_every_universe_symbol(self, monkeypatch):
        calls = _patch_main_deps(monkeypatch, cfg={"enabled": True, "dry_run": True},
                                  universe=["A", "B", "C"])
        assert mod.main([]) == 0
        assert {c["symbol"] for c in calls} == {"A", "B", "C"}
        assert all(c["dry_run"] is True for c in calls)

    def test_dry_run_defaults_true_even_if_omitted(self, monkeypatch):
        calls = _patch_main_deps(monkeypatch, cfg={"enabled": True}, universe=["A"])
        assert mod.main([]) == 0
        assert calls[0]["dry_run"] is True

    def test_equity_fraction_defaults_to_the_validated_nine_percent(self, monkeypatch):
        calls = _patch_main_deps(monkeypatch, cfg={"enabled": True}, universe=["A"])
        assert mod.main([]) == 0
        assert calls[0]["equity_fraction"] == 0.09

    def test_config_can_override_equity_fraction(self, monkeypatch):
        calls = _patch_main_deps(monkeypatch, cfg={"enabled": True, "equity_fraction": 0.05},
                                  universe=["A"])
        assert mod.main([]) == 0
        assert calls[0]["equity_fraction"] == 0.05

    def test_empty_universe_is_a_no_op(self, monkeypatch):
        calls = _patch_main_deps(monkeypatch, cfg={"enabled": True}, universe=[])
        assert mod.main([]) == 0
        assert calls == []

    def test_open_positions_outside_the_universe_are_still_scanned(self, monkeypatch):
        """A delisting or index reshuffle must never orphan a position
        real capital is already committed to."""
        calls = _patch_main_deps(monkeypatch, cfg={"enabled": True}, universe=["A"])
        monkeypatch.setattr(mod, "load_open_positions", lambda: {
            "DROPPED": _position(symbol="DROPPED"),
        })
        assert mod.main([]) == 0
        assert {c["symbol"] for c in calls} == {"A", "DROPPED"}

    def test_a_single_symbol_failure_does_not_abort_the_rest(self, monkeypatch):
        calls = _patch_main_deps(monkeypatch, cfg={"enabled": True}, universe=["A", "B"])

        def flaky(broker, symbol, positions, trade_history, dry_run, equity_fraction,
                  starting_capital, min_capital_floor, today, positions_path=None):
            calls.append(symbol)
            if symbol == "A":
                raise RuntimeError("broker hiccup")

        monkeypatch.setattr(mod, "process_symbol", flaky)
        assert mod.main([]) == 0
        assert calls == ["A", "B"]
