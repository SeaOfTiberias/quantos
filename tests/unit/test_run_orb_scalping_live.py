"""
Tests for scripts/run_orb_scalping_live.py (layer 2) -- broker-mocked,
no network, no Fyers, no real filesystem paths (ORB_OPEN_POSITIONS_PATH
and TRADE_HISTORY_PATH are monkeypatched to tmp_path in every test).
"""

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import scripts.run_orb_scalping_live as mod  # noqa: E402
from core.brokers.base import (  # noqa: E402
    OHLCV,
    OrderResult,
    OrderStatus,
    Position,
    ProductType,
)
from core.options.fyers_symbol_master import ResolvedOption  # noqa: E402
from core.options.models import OptionType  # noqa: E402
from core.orb_scalping.live_positions import get_position  # noqa: E402
from core.risk import TradeHistoryService  # noqa: E402


# ─── _exit_reason (pure) ─────────────────────────────────────────────────

def test_exit_reason_none_when_nothing_fired():
    assert mod._exit_reason(past_flatten=False, index_stop_hit=False,
                             candle_confirmed_stop=False, candle_exit_reason=None,
                             armed=True) is None


def test_exit_reason_index_stop_while_armed_is_trailing_stop():
    assert mod._exit_reason(past_flatten=False, index_stop_hit=True,
                             candle_confirmed_stop=False, candle_exit_reason=None,
                             armed=True) == "trailing_stop"


def test_exit_reason_index_stop_while_not_armed_is_plain_stop():
    assert mod._exit_reason(past_flatten=False, index_stop_hit=True,
                             candle_confirmed_stop=False, candle_exit_reason=None,
                             armed=False) == "stop"


def test_exit_reason_candle_fallback_used_when_ltp_missed_it():
    assert mod._exit_reason(past_flatten=False, index_stop_hit=False,
                             candle_confirmed_stop=True, candle_exit_reason="trailing_stop",
                             armed=True) == "trailing_stop"


def test_exit_reason_index_side_wins_over_candle_fallback_when_both_fire():
    assert mod._exit_reason(past_flatten=False, index_stop_hit=True,
                             candle_confirmed_stop=True, candle_exit_reason="stop",
                             armed=False) == "stop"


def test_exit_reason_session_flatten_when_nothing_else_fired():
    assert mod._exit_reason(past_flatten=True, index_stop_hit=False,
                             candle_confirmed_stop=False, candle_exit_reason=None,
                             armed=False) == "session_flatten"


# ─── Fixtures ────────────────────────────────────────────────────────────

def _bar(start, i, o, h, l, c):
    return OHLCV(timestamp=start + timedelta(minutes=5 * i), open=o, high=h, low=l, close=c, volume=1000)


def _entry_candles(start):
    """Opening range 23999-24001 (first 3 candles), breakout close above
    24001 on candle 3, entry executes at candle 4's open (24005) -- same
    shape as test_probe_orb_scalping_stopout_spreads.py's own fixture."""
    candles = [_bar(start, i, 24000, 24001, 23999, 24000) for i in range(3)]
    candles.append(_bar(start, 3, 24000, 24010, 23999, 24005))
    candles.append(_bar(start, 4, 24005, 24006, 24004, 24005))
    return candles


def _chain_row(strike, option_type, ltp=50.0):
    return {"strike_price": strike, "option_type": option_type,
            "bid": ltp - 0.5, "ask": ltp + 0.5, "ltp": ltp}


class _FakeBroker:
    def __init__(self, candles, index_ltp, chain_rows, positions=None, order_history=None):
        self._candles = candles
        self.index_ltp = index_ltp
        self._chain_rows = chain_rows
        self._positions = positions or []
        self._order_history = order_history or []
        self.placed_orders = []
        self.cancelled_order_ids = []
        self._next_id = 1

    def get_historical_data(self, symbol, timeframe, from_date, to_date):
        return [c for c in self._candles if c.timestamp <= to_date]

    def get_ltp(self, symbols):
        return {s: self.index_ltp for s in symbols}

    def get_option_chain(self, underlying, expiry_epoch):
        return {"optionsChain": self._chain_rows}

    def place_order(self, order):
        order_id = f"ORD-{self._next_id}"
        self._next_id += 1
        self.placed_orders.append(order)
        return OrderResult(
            order_id=order_id, status=OrderStatus.EXECUTED, symbol=order.symbol,
            direction=order.direction, quantity=order.quantity, filled_quantity=order.quantity,
            average_price=50.0, timestamp=datetime.now(timezone.utc),
        )

    def cancel_order(self, order_id):
        self.cancelled_order_ids.append(order_id)
        return True

    def modify_stop_loss(self, order_id, new_trigger_price):
        raise AssertionError("run_orb_scalping_live should never call modify_stop_loss "
                              "-- the premium stop is fixed and the index stop has no backing order")

    def get_positions(self):
        return self._positions

    def get_order_history(self):
        return self._order_history


def _patch_common(monkeypatch, tmp_path):
    monkeypatch.setattr("core.orb_scalping.live_positions.ORB_OPEN_POSITIONS_PATH",
                         tmp_path / "orb_open_positions.json")
    monkeypatch.setattr(mod.sm, "list_expiries", lambda underlying: [date(2026, 9, 29)])
    monkeypatch.setattr(mod.sm, "get_expiry_epoch", lambda *a, **k: "123")
    monkeypatch.setattr(
        mod.sm, "resolve_option_symbol",
        lambda underlying, expiry, strike, option_type, **k: ResolvedOption(
            symbol=f"NSE:{underlying}TESTCE", lot_size=65, expiry=expiry,
            strike=strike, option_type=option_type, underlying=underlying,
        ),
    )


# ─── Entry ───────────────────────────────────────────────────────────────

def test_enters_new_position_dry_run_places_no_orders(monkeypatch, tmp_path):
    _patch_common(monkeypatch, tmp_path)
    start = datetime(2026, 9, 3, 3, 45, tzinfo=timezone.utc)
    candles = _entry_candles(start)
    now_at_entry = candles[-1].timestamp + timedelta(minutes=5, seconds=30)
    monkeypatch.setattr(mod, "datetime", _FrozenDatetime(now_at_entry))

    broker = _FakeBroker(candles, index_ltp=24005.0, chain_rows=[_chain_row(24000.0, "CE", 50.0)])
    trade_history = TradeHistoryService()
    positions = {}
    mod.process_underlying(broker, "NIFTY", "NIFTY 50", dte_floor_days=0, strike_interval=50.0,
                            lots_per_trade=1, dry_run=True, positions=positions, trade_history=trade_history)

    assert broker.placed_orders == []
    pos = get_position(positions, "NIFTY", now_at_entry.date().isoformat())
    assert pos is not None
    assert pos.direction == "CALL"
    assert pos.entry_premium == 50.0
    assert pos.entry_order_id == ""
    assert pos.stop_order_id == ""


def test_enters_new_position_live_places_entry_and_stop_orders(monkeypatch, tmp_path):
    _patch_common(monkeypatch, tmp_path)
    start = datetime(2026, 9, 3, 3, 45, tzinfo=timezone.utc)
    candles = _entry_candles(start)
    now_at_entry = candles[-1].timestamp + timedelta(minutes=5, seconds=30)
    monkeypatch.setattr(mod, "datetime", _FrozenDatetime(now_at_entry))

    broker = _FakeBroker(candles, index_ltp=24005.0, chain_rows=[_chain_row(24000.0, "CE", 50.0)])
    trade_history = TradeHistoryService()
    positions = {}
    mod.process_underlying(broker, "NIFTY", "NIFTY 50", dte_floor_days=0, strike_interval=50.0,
                            lots_per_trade=1, dry_run=False, positions=positions, trade_history=trade_history)

    assert len(broker.placed_orders) == 2
    pos = get_position(positions, "NIFTY", now_at_entry.date().isoformat())
    assert pos.entry_order_id != ""
    assert pos.stop_order_id != ""
    assert pos.current_premium_stop == round(50.0 * (1 - mod.PREMIUM_STOP_PCT), 4)


def test_no_entry_before_breakout_confirmed(monkeypatch, tmp_path):
    _patch_common(monkeypatch, tmp_path)
    start = datetime(2026, 9, 3, 3, 45, tzinfo=timezone.utc)
    candles = [_bar(start, i, 24000, 24001, 23999, 24000) for i in range(3)]  # range only, no breakout
    now_utc = candles[-1].timestamp + timedelta(minutes=5, seconds=30)
    monkeypatch.setattr(mod, "datetime", _FrozenDatetime(now_utc))

    broker = _FakeBroker(candles, index_ltp=24000.0, chain_rows=[])
    positions = {}
    mod.process_underlying(broker, "NIFTY", "NIFTY 50", dte_floor_days=0, strike_interval=50.0,
                            lots_per_trade=1, dry_run=True, positions=positions,
                            trade_history=TradeHistoryService())
    assert positions == {}
    assert broker.placed_orders == []


# ─── Managing an existing position ──────────────────────────────────────

def _existing_call_position(trade_date_iso="2026-09-03"):
    from core.orb_scalping.live_positions import OrbOpenPosition
    return OrbOpenPosition(
        underlying="NIFTY", option_symbol="NSE:NIFTYTESTCE", direction="CALL",
        option_type="CE", quantity=65, strike=24000.0, expiry="2026-09-29",
        dte_floor_rolled=False, entry_index_level=24005.0, entry_premium=50.0,
        entry_timestamp=datetime(2026, 9, 3, 4, 0, tzinfo=timezone.utc).isoformat(),
        current_index_stop=23999.0, current_premium_stop=37.5, armed=False,
        entry_order_id="ORD-1", stop_order_id="SL-1", trade_date=trade_date_iso,
    )


def test_dry_run_index_stop_exit_removes_position_without_recording_trade(monkeypatch, tmp_path):
    _patch_common(monkeypatch, tmp_path)
    start = datetime(2026, 9, 3, 3, 45, tzinfo=timezone.utc)
    candles = _entry_candles(start)  # still "in_position" per live_state, no candle-confirmed stop
    now_utc = candles[-1].timestamp + timedelta(minutes=6)
    monkeypatch.setattr(mod, "datetime", _FrozenDatetime(now_utc))

    # Index LTP has crossed below the CALL's stop (23999) -- an active,
    # script-side detected exit (no backing broker order for this leg).
    broker = _FakeBroker(candles, index_ltp=23990.0, chain_rows=[])
    positions = {"NIFTY:2026-09-03": _existing_call_position()}
    trade_history = TradeHistoryService()

    mod.process_underlying(broker, "NIFTY", "NIFTY 50", dte_floor_days=0, strike_interval=50.0,
                            lots_per_trade=1, dry_run=True, positions=positions, trade_history=trade_history)

    assert get_position(positions, "NIFTY", "2026-09-03") is None
    assert trade_history.get_trade_history() == []
    assert broker.placed_orders == []  # dry_run flatten places no real order either


def test_live_index_stop_exit_flattens_and_records_trade(monkeypatch, tmp_path):
    _patch_common(monkeypatch, tmp_path)
    start = datetime(2026, 9, 3, 3, 45, tzinfo=timezone.utc)
    candles = _entry_candles(start)
    now_utc = candles[-1].timestamp + timedelta(minutes=6)
    monkeypatch.setattr(mod, "datetime", _FrozenDatetime(now_utc))

    # Position still shows open on the broker (reconcile sees it still_open),
    # but the index has crossed the stop -- this script must force-exit it.
    broker = _FakeBroker(
        candles, index_ltp=23990.0, chain_rows=[],
        positions=[Position(symbol="NSE:NIFTYTESTCE", quantity=65, average_price=50.0,
                             current_price=45.0, pnl=-325.0, pnl_percent=-10.0,
                             product_type=ProductType.INTRADAY)],
    )
    positions = {"NIFTY:2026-09-03": _existing_call_position()}
    trade_history = TradeHistoryService()

    mod.process_underlying(broker, "NIFTY", "NIFTY 50", dte_floor_days=0, strike_interval=50.0,
                            lots_per_trade=1, dry_run=False, positions=positions, trade_history=trade_history)

    assert get_position(positions, "NIFTY", "2026-09-03") is None
    assert broker.cancelled_order_ids == ["SL-1"]
    assert len(broker.placed_orders) == 1  # the closing MARKET SELL
    history = trade_history.get_trade_history()
    assert len(history) == 1
    assert history[0].symbol == "NSE:NIFTYTESTCE"


def test_live_reconcile_finds_premium_stop_fill_records_trade_as_premium_stop(monkeypatch, tmp_path):
    _patch_common(monkeypatch, tmp_path)
    start = datetime(2026, 9, 3, 3, 45, tzinfo=timezone.utc)
    candles = _entry_candles(start)
    now_utc = candles[-1].timestamp + timedelta(minutes=6)
    monkeypatch.setattr(mod, "datetime", _FrozenDatetime(now_utc))

    # Broker shows the position closed (quantity 0), and its own resting
    # SL_M order (stop_order_id) is the fill on record -- this is the real
    # 25%-of-premium stop firing on its own, noticed via reconcile, not an
    # active script-side exit.
    broker = _FakeBroker(
        candles, index_ltp=24005.0, chain_rows=[],  # index hasn't hit its stop
        positions=[],
        order_history=[OrderResult(
            order_id="SL-1", status=OrderStatus.EXECUTED, symbol="NSE:NIFTYTESTCE",
            direction=None, quantity=65, filled_quantity=65, average_price=37.5,
            timestamp=now_utc,
        )],
    )
    positions = {"NIFTY:2026-09-03": _existing_call_position()}
    trade_history = TradeHistoryService()

    mod.process_underlying(broker, "NIFTY", "NIFTY 50", dte_floor_days=0, strike_interval=50.0,
                            lots_per_trade=1, dry_run=False, positions=positions, trade_history=trade_history)

    assert get_position(positions, "NIFTY", "2026-09-03") is None
    history = trade_history.get_trade_history()
    assert len(history) == 1
    assert history[0].exit_price == 37.5
    assert broker.placed_orders == []  # no forced flatten needed -- the broker already closed it


def test_still_open_refreshes_persisted_trailing_stop(monkeypatch, tmp_path):
    _patch_common(monkeypatch, tmp_path)
    start = datetime(2026, 9, 3, 3, 45, tzinfo=timezone.utc)
    # Extend past the entry candle with a favorable move that arms and
    # trails the stop upward, per compute_live_state()'s own rules.
    candles = _entry_candles(start)
    candles.append(_bar(start, 5, 24005, 24020, 24004, 24018))  # favorable close -> arms
    now_utc = candles[-1].timestamp + timedelta(seconds=30)
    monkeypatch.setattr(mod, "datetime", _FrozenDatetime(now_utc))

    broker = _FakeBroker(
        candles, index_ltp=24018.0, chain_rows=[],
        positions=[Position(symbol="NSE:NIFTYTESTCE", quantity=65, average_price=50.0,
                             current_price=60.0, pnl=650.0, pnl_percent=20.0,
                             product_type=ProductType.INTRADAY)],
    )
    positions = {"NIFTY:2026-09-03": _existing_call_position()}
    trade_history = TradeHistoryService()

    mod.process_underlying(broker, "NIFTY", "NIFTY 50", dte_floor_days=0, strike_interval=50.0,
                            lots_per_trade=1, dry_run=False, positions=positions, trade_history=trade_history)

    pos = get_position(positions, "NIFTY", "2026-09-03")
    assert pos is not None  # still open, not force-exited
    assert broker.placed_orders == []
    assert broker.cancelled_order_ids == []
    assert trade_history.get_trade_history() == []


class _FrozenDatetime:
    """Stands in for the `datetime` class inside run_orb_scalping_live so
    datetime.now(timezone.utc) returns a fixed instant while combine/
    fromisoformat still work (delegated to the real class) -- same
    approach as test_probe_orb_scalping_stopout_spreads.py's own helper."""

    def __init__(self, frozen):
        self._frozen = frozen

    def now(self, tz=None):
        return self._frozen

    def combine(self, *a, **k):
        return datetime.combine(*a, **k)

    def fromisoformat(self, *a, **k):
        return datetime.fromisoformat(*a, **k)
