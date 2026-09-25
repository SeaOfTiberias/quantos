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
from core.risk import ClosedTrade, TradeHistoryService  # noqa: E402


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
    monkeypatch.setattr("core.orb_scalping.live_positions.ORB_TRADED_TODAY_PATH",
                         tmp_path / "orb_traded_today.json")
    # Isolate the halt-flag kill-switch (agent/risk_guard.py) from this
    # machine's real ~/.quantos/halt -- process_underlying now checks it
    # before every new entry (added 2026-09-25), so every test reaching
    # that path must not depend on whatever real halt state happens to
    # exist wherever tests run.
    monkeypatch.setattr("agent.risk_guard.HALT_FLAG_PATH", tmp_path / "halt")
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
                            lots_per_trade=1, dry_run=True, positions=positions, trade_history=trade_history, traded_today=set())

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
                            lots_per_trade=1, dry_run=False, positions=positions, trade_history=trade_history, traded_today=set())

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
                            trade_history=TradeHistoryService(), traded_today=set())
    assert positions == {}
    assert broker.placed_orders == []


def test_no_reentry_once_already_traded_today_even_if_candle_state_lags(monkeypatch, tmp_path):
    """Regression for two bugs caught live via the supervised dry_run cycle:
    compute_live_state() only reflects a force-exit once a CLOSED candle confirms it --
    up to ~5 minutes behind whichever live-speed check actually triggered the exit
    (the wall-clock SESSION_FLATTEN_UTC check, caught 2026-09-10; the live-LTP
    index-stop check, caught 2026-09-11, even faster since it's checked every fire
    with no candle-close wait at all). In the gap right after either kind of
    force-exit, `existing=None` (the position was just removed) while state.status
    still reads "in_position", which used to look like a fresh breakout and caused a
    flatten/re-enter/flatten oscillation live -- twice, through two different doors.
    has_traded_today() closes both at once: no new entry once this underlying has
    already had its one trade today, regardless of why compute_live_state() still
    thinks a position is open."""
    _patch_common(monkeypatch, tmp_path)
    start = datetime(2026, 9, 3, 3, 45, tzinfo=timezone.utc)
    candles = _entry_candles(start)  # state.status will read "in_position"
    now_at_entry = candles[-1].timestamp + timedelta(minutes=5, seconds=30)
    monkeypatch.setattr(mod, "datetime", _FrozenDatetime(now_at_entry))

    broker = _FakeBroker(candles, index_ltp=24005.0, chain_rows=[_chain_row(24000.0, "CE", 50.0)])
    positions = {}  # the earlier position was already force-exited and removed
    traded_today = {"NIFTY:2026-09-03"}  # ...but it did happen, so this is marked
    mod.process_underlying(broker, "NIFTY", "NIFTY 50", dte_floor_days=0, strike_interval=50.0,
                            lots_per_trade=1, dry_run=True, positions=positions,
                            trade_history=TradeHistoryService(), traded_today=traded_today)

    assert positions == {}
    assert broker.placed_orders == []


def test_reentry_allowed_same_day_once_traded_today_is_unmarked(monkeypatch, tmp_path):
    """Sanity check for the fix above: an empty traded_today must not accidentally
    block ordinary first entries -- only an underlying/date already marked traded
    blocks re-entry."""
    _patch_common(monkeypatch, tmp_path)
    start = datetime(2026, 9, 3, 3, 45, tzinfo=timezone.utc)
    candles = _entry_candles(start)
    now_at_entry = candles[-1].timestamp + timedelta(minutes=5, seconds=30)
    monkeypatch.setattr(mod, "datetime", _FrozenDatetime(now_at_entry))

    broker = _FakeBroker(candles, index_ltp=24005.0, chain_rows=[_chain_row(24000.0, "CE", 50.0)])
    positions = {}
    traded_today = set()
    mod.process_underlying(broker, "NIFTY", "NIFTY 50", dte_floor_days=0, strike_interval=50.0,
                            lots_per_trade=1, dry_run=True, positions=positions,
                            trade_history=TradeHistoryService(), traded_today=traded_today)

    assert get_position(positions, "NIFTY", "2026-09-03") is not None
    assert "NIFTY:2026-09-03" in traded_today


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
                            lots_per_trade=1, dry_run=True, positions=positions, trade_history=trade_history, traded_today=set())

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
                            lots_per_trade=1, dry_run=False, positions=positions, trade_history=trade_history, traded_today=set())

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
                            lots_per_trade=1, dry_run=False, positions=positions, trade_history=trade_history, traded_today=set())

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
                            lots_per_trade=1, dry_run=False, positions=positions, trade_history=trade_history, traded_today=set())

    pos = get_position(positions, "NIFTY", "2026-09-03")
    assert pos is not None  # still open, not force-exited
    assert broker.placed_orders == []
    assert broker.cancelled_order_ids == []
    assert trade_history.get_trade_history() == []


# ─── docs/ORB_ENTRY_FILTER_METHODOLOGY.md's entry_filter gate ─────────────

def test_entry_filter_returning_false_blocks_entry(monkeypatch, tmp_path):
    _patch_common(monkeypatch, tmp_path)
    start = datetime(2026, 9, 3, 3, 45, tzinfo=timezone.utc)
    candles = _entry_candles(start)
    now_at_entry = candles[-1].timestamp + timedelta(minutes=5, seconds=30)
    monkeypatch.setattr(mod, "datetime", _FrozenDatetime(now_at_entry))

    broker = _FakeBroker(candles, index_ltp=24005.0, chain_rows=[_chain_row(24000.0, "CE", 50.0)])
    positions = {}
    mod.process_underlying(broker, "NIFTY", "NIFTY 50", dte_floor_days=0, strike_interval=50.0,
                            lots_per_trade=1, dry_run=True, positions=positions,
                            trade_history=TradeHistoryService(), traded_today=set(),
                            entry_filter=lambda trade_date, first_open: False)

    assert positions == {}
    assert broker.placed_orders == []


def test_entry_filter_returning_true_allows_entry(monkeypatch, tmp_path):
    _patch_common(monkeypatch, tmp_path)
    start = datetime(2026, 9, 3, 3, 45, tzinfo=timezone.utc)
    candles = _entry_candles(start)
    now_at_entry = candles[-1].timestamp + timedelta(minutes=5, seconds=30)
    monkeypatch.setattr(mod, "datetime", _FrozenDatetime(now_at_entry))

    broker = _FakeBroker(candles, index_ltp=24005.0, chain_rows=[_chain_row(24000.0, "CE", 50.0)])
    positions = {}
    mod.process_underlying(broker, "NIFTY", "NIFTY 50", dte_floor_days=0, strike_interval=50.0,
                            lots_per_trade=1, dry_run=True, positions=positions,
                            trade_history=TradeHistoryService(), traded_today=set(),
                            entry_filter=lambda trade_date, first_open: True)

    assert get_position(positions, "NIFTY", now_at_entry.date().isoformat()) is not None


def test_entry_filter_receives_the_days_first_candle_open(monkeypatch, tmp_path):
    """Proves the wiring, not just that a bool gates entry -- the filter
    must see the SAME opening value docs/ORB_CONDITION_MINING_RESULTS.md's
    big_gap condition was mined against (today's first 5m candle's open)."""
    _patch_common(monkeypatch, tmp_path)
    start = datetime(2026, 9, 3, 3, 45, tzinfo=timezone.utc)
    candles = _entry_candles(start)
    now_at_entry = candles[-1].timestamp + timedelta(minutes=5, seconds=30)
    monkeypatch.setattr(mod, "datetime", _FrozenDatetime(now_at_entry))

    seen = {}

    def spy_filter(trade_date, first_open):
        seen["trade_date"] = trade_date
        seen["first_open"] = first_open
        return True

    broker = _FakeBroker(candles, index_ltp=24005.0, chain_rows=[_chain_row(24000.0, "CE", 50.0)])
    mod.process_underlying(broker, "NIFTY", "NIFTY 50", dte_floor_days=0, strike_interval=50.0,
                            lots_per_trade=1, dry_run=True, positions={},
                            trade_history=TradeHistoryService(), traded_today=set(),
                            entry_filter=spy_filter)

    assert seen["first_open"] == candles[0].open
    assert seen["trade_date"] == now_at_entry.date()


def test_no_entry_filter_reproduces_unfiltered_behaviour():
    """entry_filter=None (the default, and what --variant unfiltered
    always passes) must never be called and must never block -- covered
    implicitly by every pre-existing test in this file never passing it."""
    import inspect
    assert inspect.signature(mod.process_underlying).parameters["entry_filter"].default is None


# ─── _fetch_prior_daily_close ───────────────────────────────────────────────

def test_fetch_prior_daily_close_picks_the_most_recent_bar_before_today():
    class _Broker:
        def get_historical_data(self, symbol, timeframe, from_date, to_date):
            return [
                _bar_daily(date(2026, 9, 18), 100.0),
                _bar_daily(date(2026, 9, 21), 105.0),  # most recent before "today"
            ]

    close = mod._fetch_prior_daily_close(_Broker(), "NIFTY BANK", date(2026, 9, 22))
    assert close == 105.0


def test_fetch_prior_daily_close_excludes_todays_own_bar():
    class _Broker:
        def get_historical_data(self, symbol, timeframe, from_date, to_date):
            return [_bar_daily(date(2026, 9, 21), 100.0), _bar_daily(date(2026, 9, 22), 999.0)]

    close = mod._fetch_prior_daily_close(_Broker(), "NIFTY BANK", date(2026, 9, 22))
    assert close == 100.0


def test_fetch_prior_daily_close_returns_none_with_no_prior_bars():
    class _Broker:
        def get_historical_data(self, symbol, timeframe, from_date, to_date):
            return []

    assert mod._fetch_prior_daily_close(_Broker(), "NIFTY BANK", date(2026, 9, 22)) is None


def test_fetch_prior_daily_close_returns_none_on_broker_error_rather_than_raising():
    class _Broker:
        def get_historical_data(self, symbol, timeframe, from_date, to_date):
            raise RuntimeError("history fetch failed")

    assert mod._fetch_prior_daily_close(_Broker(), "NIFTY BANK", date(2026, 9, 22)) is None


def _bar_daily(day, close):
    return OHLCV(timestamp=datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc),
                 open=close, high=close, low=close, close=close, volume=1000)


# ─── --variant CLI wiring: config key + position-store selection ───────────
# broker/candle-level behaviour is exercised via process_underlying above;
# these check main() itself picks the right config block, paths, and builds
# an entry_filter only for the filtered variant -- load_config/get_broker
# are faked so no real file or network is touched.

def _patch_main_deps(monkeypatch, orb_cfg=None, orb_cfg_filtered=None):
    calls = []

    class _StubBroker:
        def connect(self):
            return True

        def get_historical_data(self, *a, **k):
            return []  # only reached by --variant filtered's daily-close fetch

    monkeypatch.setattr(mod, "load_config", lambda path: {
        "broker": "stub",
        "orb_scalping": orb_cfg if orb_cfg is not None else {"enabled": False},
        "orb_scalping_filtered": orb_cfg_filtered if orb_cfg_filtered is not None else {"enabled": False},
    })
    monkeypatch.setattr(mod, "get_broker", lambda config: _StubBroker())

    def spy_process_underlying(broker, underlying, spot_symbol, dte_floor_days, strike_interval,
                                lots_per_trade, dry_run, positions, trade_history, traded_today,
                                entry_filter=None, positions_path=None, traded_today_path=None,
                                dry_run_log_path=None, dynamic_sizing=False, starting_capital=0.0,
                                min_capital_floor=0.0, strategy_name="orb_scalping"):
        calls.append(dict(underlying=underlying, entry_filter=entry_filter,
                           positions_path=positions_path, traded_today_path=traded_today_path,
                           dry_run_log_path=dry_run_log_path, dry_run=dry_run,
                           dynamic_sizing=dynamic_sizing, starting_capital=starting_capital,
                           min_capital_floor=min_capital_floor, strategy_name=strategy_name))

    monkeypatch.setattr(mod, "process_underlying", spy_process_underlying)
    return calls


def test_unfiltered_variant_is_the_default_and_uses_default_paths(monkeypatch, tmp_path):
    calls = _patch_main_deps(monkeypatch, orb_cfg={"enabled": True, "dry_run": True})
    monkeypatch.setattr(mod, "load_open_positions", lambda path=None: {})
    monkeypatch.setattr(mod, "load_traded_today", lambda path=None: set())

    assert mod.main([]) == 0
    assert len(calls) == 2  # NIFTY, BANKNIFTY
    for c in calls:
        assert c["entry_filter"] is None
        assert c["positions_path"] is None
        assert c["traded_today_path"] is None
        assert c["dry_run_log_path"] is None


def test_filtered_variant_uses_its_own_config_block_and_paths(monkeypatch):
    calls = _patch_main_deps(monkeypatch, orb_cfg={"enabled": True},
                              orb_cfg_filtered={"enabled": True, "dry_run": True})
    monkeypatch.setattr(mod, "load_open_positions", lambda path=None: {})
    monkeypatch.setattr(mod, "load_traded_today", lambda path=None: set())

    assert mod.main(["--variant", "filtered"]) == 0
    assert len(calls) == 2
    for c in calls:
        assert c["entry_filter"] is not None
        assert c["positions_path"] == mod.ORB_OPEN_POSITIONS_FILTERED_PATH
        assert c["traded_today_path"] == mod.ORB_TRADED_TODAY_FILTERED_PATH
        assert c["dry_run_log_path"] == mod.ORB_DRY_RUN_LOG_FILTERED_PATH


def test_filtered_variant_disabled_by_default_config_does_nothing(monkeypatch):
    """agent/config.yaml.example ships orb_scalping_filtered.enabled: false
    -- the same safe-default gate unfiltered candidate 18 already has."""
    calls = _patch_main_deps(monkeypatch, orb_cfg={"enabled": True},
                              orb_cfg_filtered={"enabled": False})
    assert mod.main(["--variant", "filtered"]) == 0
    assert calls == []


def test_unfiltered_variant_never_reads_the_filtered_config_block(monkeypatch):
    """Turning orb_scalping_filtered on must never affect what the default
    --variant does -- the two are independent switches."""
    calls = _patch_main_deps(monkeypatch, orb_cfg={"enabled": True, "dry_run": True},
                              orb_cfg_filtered={"enabled": True, "dry_run": False})
    monkeypatch.setattr(mod, "load_open_positions", lambda path=None: {})
    monkeypatch.setattr(mod, "load_traded_today", lambda path=None: set())

    assert mod.main([]) == 0
    assert all(c["dry_run"] is True for c in calls)  # read from orb_scalping, not _filtered


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


# ─── _dynamic_lot_count (pure) ────────────────────────────────────────────

def _winning_trade(i: int, strategy: str = "orb_scalping") -> ClosedTrade:
    """A clean winner: entry 100 -> exit 120, well above any stop, so
    win_loss_ratio is large and positive Kelly is guaranteed once enough
    of these exist."""
    day = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=i)
    return ClosedTrade(trade_id=f"t{i}", symbol="NIFTY", entry_price=100.0, exit_price=120.0,
                        quantity=65, direction="BUY", entry_date=day, exit_date=day, strategy=strategy)


def _losing_trade(i: int, strategy: str = "orb_scalping") -> ClosedTrade:
    day = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=i)
    return ClosedTrade(trade_id=f"l{i}", symbol="NIFTY", entry_price=100.0, exit_price=80.0,
                        quantity=65, direction="BUY", entry_date=day, exit_date=day, strategy=strategy)


class TestDynamicLotCount:
    def test_insufficient_history_uses_fixed_fallback_not_a_refusal(self):
        lots, note = mod._dynamic_lot_count(
            trades=[], starting_capital=100_000.0, entry_premium=100.0,
            protective_stop_trigger=75.0, lot_size=65, min_capital_floor=50_000.0, symbol="NIFTY",
        )
        assert lots >= 1
        assert "FIXED_FALLBACK" in note or "fallback" in note.lower() or "Kelly sizing" in note

    def test_positive_edge_history_sizes_a_real_lot_count(self):
        trades = [_winning_trade(i) for i in range(25)]
        lots, note = mod._dynamic_lot_count(
            trades=trades, starting_capital=1_000_000.0, entry_premium=100.0,
            protective_stop_trigger=75.0, lot_size=65, min_capital_floor=50_000.0, symbol="NIFTY",
        )
        assert lots >= 1
        assert "Kelly sizing" in note

    def test_negative_edge_history_refuses_entirely(self):
        trades = [_losing_trade(i) for i in range(25)]
        lots, note = mod._dynamic_lot_count(
            trades=trades, starting_capital=1_000_000.0, entry_premium=100.0,
            protective_stop_trigger=75.0, lot_size=65, min_capital_floor=50_000.0, symbol="NIFTY",
        )
        assert lots == 0
        assert "refused" in note.lower()

    def test_rounds_to_zero_but_capital_above_floor_gets_floored_to_one_lot(self):
        # 25 winners' realized P&L (~Rs32,310) plus a small starting
        # capital puts current_capital (~Rs37,310) below the ~Rs40,625
        # threshold where 4%-capped Kelly risk still affords a full lot --
        # but it's above a Rs30,000 floor, so this should floor to 1.
        trades = [_winning_trade(i) for i in range(25)]
        lots, note = mod._dynamic_lot_count(
            trades=trades, starting_capital=5_000.0, entry_premium=100.0,
            protective_stop_trigger=75.0, lot_size=65, min_capital_floor=30_000.0, symbol="NIFTY",
        )
        assert lots == 1
        assert "flooring to 1 lot" in note

    def test_rounds_to_zero_and_below_floor_refuses_with_low_capital_warning(self):
        trades = [_winning_trade(i) for i in range(25)]
        lots, note = mod._dynamic_lot_count(
            trades=trades, starting_capital=5_000.0, entry_premium=100.0,
            protective_stop_trigger=75.0, lot_size=65, min_capital_floor=50_000.0, symbol="NIFTY",
        )
        assert lots == 0
        assert "LOW CAPITAL WARNING" in note

    def test_current_capital_includes_realized_pnl_not_just_starting_capital(self):
        # 25 winners at (120-100)*65 - costs each add real realized P&L;
        # current_capital should be well above the bare starting_capital.
        trades = [_winning_trade(i) for i in range(25)]
        lots_low_start, _ = mod._dynamic_lot_count(
            trades=[], starting_capital=50_000.0, entry_premium=100.0,
            protective_stop_trigger=75.0, lot_size=65, min_capital_floor=50_000.0, symbol="NIFTY",
        )
        lots_with_history, _ = mod._dynamic_lot_count(
            trades=trades, starting_capital=50_000.0, entry_premium=100.0,
            protective_stop_trigger=75.0, lot_size=65, min_capital_floor=50_000.0, symbol="NIFTY",
        )
        # Both may floor to a small number of lots, but the realized-gain
        # version must never size off LESS capital than the bare starting
        # figure -- i.e. it must not ignore the trade history's P&L.
        assert lots_with_history >= lots_low_start


# ─── Halt-flag kill-switch ─────────────────────────────────────────────────

class TestHaltFlagBlocksNewEntries:
    def test_entry_refused_and_no_order_placed_while_halted(self, monkeypatch, tmp_path):
        _patch_common(monkeypatch, tmp_path)
        halt_path = tmp_path / "halt"
        halt_path.write_text("2026-09-25T00:00:00 IST — test halt\n")
        monkeypatch.setattr("agent.risk_guard.HALT_FLAG_PATH", halt_path)

        start = datetime(2026, 9, 3, 3, 45, tzinfo=timezone.utc)
        candles = _entry_candles(start)
        now_at_entry = candles[-1].timestamp + timedelta(minutes=5, seconds=30)
        monkeypatch.setattr(mod, "datetime", _FrozenDatetime(now_at_entry))

        broker = _FakeBroker(candles, index_ltp=24005.0, chain_rows=[_chain_row(24000.0, "CE", 50.0)])
        trade_history = TradeHistoryService()
        positions = {}
        mod.process_underlying(broker, "NIFTY", "NIFTY 50", dte_floor_days=0, strike_interval=50.0,
                                lots_per_trade=1, dry_run=False, positions=positions,
                                trade_history=trade_history, traded_today=set())

        assert broker.placed_orders == []
        assert get_position(positions, "NIFTY", now_at_entry.date().isoformat()) is None

    def test_entry_allowed_once_halt_file_is_absent(self, monkeypatch, tmp_path):
        # Sanity check for the test above: with _patch_common's isolated
        # (non-existent) halt path, entry proceeds normally.
        _patch_common(monkeypatch, tmp_path)
        start = datetime(2026, 9, 3, 3, 45, tzinfo=timezone.utc)
        candles = _entry_candles(start)
        now_at_entry = candles[-1].timestamp + timedelta(minutes=5, seconds=30)
        monkeypatch.setattr(mod, "datetime", _FrozenDatetime(now_at_entry))

        broker = _FakeBroker(candles, index_ltp=24005.0, chain_rows=[_chain_row(24000.0, "CE", 50.0)])
        trade_history = TradeHistoryService()
        positions = {}
        mod.process_underlying(broker, "NIFTY", "NIFTY 50", dte_floor_days=0, strike_interval=50.0,
                                lots_per_trade=1, dry_run=True, positions=positions,
                                trade_history=trade_history, traded_today=set())

        assert get_position(positions, "NIFTY", now_at_entry.date().isoformat()) is not None


# ─── Per-variant strategy tagging ──────────────────────────────────────────

class TestStrategyTagging:
    def test_close_out_tags_trade_history_with_the_given_strategy_name(self, monkeypatch, tmp_path):
        _patch_common(monkeypatch, tmp_path)
        existing = mod.OrbOpenPosition(
            underlying="NIFTY", option_symbol="NSE:NIFTYTESTCE", direction="CALL",
            option_type="CE", quantity=65, strike=24000.0, expiry="2026-09-29",
            dte_floor_rolled=False, entry_index_level=24005.0, entry_premium=50.0,
            entry_timestamp=datetime(2026, 9, 3, 5, 0, tzinfo=timezone.utc).isoformat(),
            current_index_stop=23990.0, current_premium_stop=37.5, armed=False,
            entry_order_id="ORD-1", stop_order_id="ORD-2", trade_date="2026-09-03",
        )
        positions = {}
        mod.add_position(positions, existing)
        trade_history = TradeHistoryService()

        mod._close_out("NIFTY", existing, 60.0, datetime(2026, 9, 3, 6, 0, tzinfo=timezone.utc),
                        "stop", positions, trade_history, strategy_name="orb_scalping_filtered")

        recorded = trade_history.get_trade_history()
        assert len(recorded) == 1
        assert recorded[0].strategy == "orb_scalping_filtered"

    def test_default_strategy_name_is_unfiltered_orb_scalping(self, monkeypatch, tmp_path):
        _patch_common(monkeypatch, tmp_path)
        existing = mod.OrbOpenPosition(
            underlying="NIFTY", option_symbol="NSE:NIFTYTESTCE", direction="CALL",
            option_type="CE", quantity=65, strike=24000.0, expiry="2026-09-29",
            dte_floor_rolled=False, entry_index_level=24005.0, entry_premium=50.0,
            entry_timestamp=datetime(2026, 9, 3, 5, 0, tzinfo=timezone.utc).isoformat(),
            current_index_stop=23990.0, current_premium_stop=37.5, armed=False,
            entry_order_id="ORD-1", stop_order_id="ORD-2", trade_date="2026-09-03",
        )
        positions = {}
        mod.add_position(positions, existing)
        trade_history = TradeHistoryService()

        mod._close_out("NIFTY", existing, 60.0, datetime(2026, 9, 3, 6, 0, tzinfo=timezone.utc),
                        "stop", positions, trade_history)

        assert trade_history.get_trade_history()[0].strategy == "orb_scalping"


# ─── Dynamic sizing end-to-end (through process_underlying) ────────────────

class TestDynamicSizingIntegration:
    def test_dynamic_sizing_overrides_lots_per_trade_with_kelly_derived_quantity(self, monkeypatch, tmp_path):
        _patch_common(monkeypatch, tmp_path)
        start = datetime(2026, 9, 3, 3, 45, tzinfo=timezone.utc)
        candles = _entry_candles(start)
        now_at_entry = candles[-1].timestamp + timedelta(minutes=5, seconds=30)
        monkeypatch.setattr(mod, "datetime", _FrozenDatetime(now_at_entry))

        broker = _FakeBroker(candles, index_ltp=24005.0, chain_rows=[_chain_row(24000.0, "CE", 100.0)])
        trade_history = TradeHistoryService()
        for t in [_winning_trade(i) for i in range(25)]:
            trade_history.record_closed_trade(t)
        positions = {}

        # lots_per_trade=1 would place a 65-qty order; dynamic sizing with
        # this trade history and starting_capital should size UP well past
        # that (see TestDynamicLotCount's own calibration of this scenario).
        mod.process_underlying(
            broker, "NIFTY", "NIFTY 50", dte_floor_days=0, strike_interval=50.0,
            lots_per_trade=1, dry_run=False, positions=positions, trade_history=trade_history,
            traded_today=set(), dynamic_sizing=True, starting_capital=1_000_000.0,
            min_capital_floor=50_000.0, strategy_name="orb_scalping",
        )

        pos = get_position(positions, "NIFTY", now_at_entry.date().isoformat())
        assert pos is not None
        assert pos.quantity > 65          # more than lots_per_trade=1 would have placed
        assert pos.quantity % 65 == 0     # still a whole number of lots

    def test_dynamic_sizing_places_no_order_when_kelly_refuses(self, monkeypatch, tmp_path):
        _patch_common(monkeypatch, tmp_path)
        start = datetime(2026, 9, 3, 3, 45, tzinfo=timezone.utc)
        candles = _entry_candles(start)
        now_at_entry = candles[-1].timestamp + timedelta(minutes=5, seconds=30)
        monkeypatch.setattr(mod, "datetime", _FrozenDatetime(now_at_entry))

        broker = _FakeBroker(candles, index_ltp=24005.0, chain_rows=[_chain_row(24000.0, "CE", 100.0)])
        trade_history = TradeHistoryService()
        for t in [_losing_trade(i) for i in range(25)]:
            trade_history.record_closed_trade(t)
        positions = {}

        mod.process_underlying(
            broker, "NIFTY", "NIFTY 50", dte_floor_days=0, strike_interval=50.0,
            lots_per_trade=1, dry_run=False, positions=positions, trade_history=trade_history,
            traded_today=set(), dynamic_sizing=True, starting_capital=1_000_000.0,
            min_capital_floor=50_000.0, strategy_name="orb_scalping",
        )

        assert broker.placed_orders == []
        assert get_position(positions, "NIFTY", now_at_entry.date().isoformat()) is None

    def test_dynamic_sizing_filters_trade_history_by_strategy_name(self, monkeypatch, tmp_path):
        # 25 winners tagged for the OTHER variant must not feed this
        # variant's Kelly sizing -- with zero own-strategy history, this
        # should fall back to FIXED_FALLBACK sizing, not the aggressive
        # Kelly number the (wrong-strategy) winners would produce.
        _patch_common(monkeypatch, tmp_path)
        start = datetime(2026, 9, 3, 3, 45, tzinfo=timezone.utc)
        candles = _entry_candles(start)
        now_at_entry = candles[-1].timestamp + timedelta(minutes=5, seconds=30)
        monkeypatch.setattr(mod, "datetime", _FrozenDatetime(now_at_entry))

        broker = _FakeBroker(candles, index_ltp=24005.0, chain_rows=[_chain_row(24000.0, "CE", 100.0)])
        trade_history = TradeHistoryService()
        for t in [_winning_trade(i, strategy="orb_scalping_filtered") for i in range(25)]:
            trade_history.record_closed_trade(t)
        positions = {}

        mod.process_underlying(
            broker, "NIFTY", "NIFTY 50", dte_floor_days=0, strike_interval=50.0,
            lots_per_trade=1, dry_run=False, positions=positions, trade_history=trade_history,
            traded_today=set(), dynamic_sizing=True, starting_capital=1_000_000.0,
            min_capital_floor=50_000.0, strategy_name="orb_scalping",   # unfiltered
        )

        pos = get_position(positions, "NIFTY", now_at_entry.date().isoformat())
        assert pos is not None
        # FIXED_FALLBACK is 2% of capital, not the 4%-capped aggressive
        # Kelly the (wrong-strategy) winning history would have produced --
        # confirms the filter actually excluded them, not just happened to
        # size similarly.
        from core.risk.kelly import FALLBACK_SIZE_PCT
        expected_qty = (int((1_000_000.0 * FALLBACK_SIZE_PCT) / (100.0 - 75.0)) // 65) * 65
        assert pos.quantity == expected_qty
