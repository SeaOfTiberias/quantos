"""
agent/main.py — options webhook orchestration glue, added 2026-07-25:
_run_options_webhook_check (poll+dispatch), _handle_options_webhook_open
(real chain analysis -> Telegram confirm), _handle_options_webhook_close
(immediate flatten, no confirm — trailing-stop precedent). Replaces the
killed regime trigger (see agent.main._run_options_trigger's docstring).
"""

from datetime import date, timedelta
from unittest.mock import MagicMock

import pytest

import agent.main as main
from core.brokers.base import Position, ProductType
from core.options.executor import FlattenResult
from core.options.fyers_symbol_master import ResolvedOption, SymbolMasterError
from core.options.models import OptionChainSnapshot, OptionLeg, OptionType
from core.options.positions import OptionsPosition


def _chain_snapshot() -> OptionChainSnapshot:
    expiry = date.today() + timedelta(days=7)
    return OptionChainSnapshot(
        underlying="NIFTY", spot_price=22000.0, expiry=expiry,
        legs=[
            OptionLeg(strike=22000.0, option_type=OptionType.CALL, expiry=expiry,
                      premium=150.0, open_interest=10000, volume=5000, implied_vol=0.15),
            OptionLeg(strike=22200.0, option_type=OptionType.CALL, expiry=expiry,
                      premium=80.0, open_interest=10000, volume=5000, implied_vol=0.15),
        ],
        iv_rank=55.0, iv_percentile=60.0, pcr=1.1, max_pain=22000.0,
    )


class TestRunOptionsWebhookCheck:

    def test_does_nothing_when_queue_empty(self, monkeypatch):
        monkeypatch.setattr(main.requests, "post",
                            lambda *a, **k: MagicMock(raise_for_status=lambda: None,
                                                       json=lambda: {"request": None}))
        called = {}
        monkeypatch.setattr(main, "_handle_options_webhook_open",
                            lambda *a, **k: called.setdefault("open", True))
        main._run_options_webhook_check(MagicMock(), "http://cloud", {}, {}, lots=1)
        assert "open" not in called

    def test_dispatches_open_action(self, monkeypatch):
        monkeypatch.setattr(main.requests, "post",
                            lambda *a, **k: MagicMock(raise_for_status=lambda: None,
                                                       json=lambda: {"request": {
                                                           "request_id": "OWH-1", "underlying": "NIFTY",
                                                           "template": "bull_call_spread", "action": "open",
                                                       }}))
        captured = {}
        monkeypatch.setattr(main, "_handle_options_webhook_open",
                            lambda broker, cloud_url, headers, positions, underlying, template,
                            lots, config=None:
                            captured.update(underlying=underlying, template=template, lots=lots))
        main._run_options_webhook_check(MagicMock(), "http://cloud", {}, {}, lots=2)
        assert captured == {"underlying": "NIFTY", "template": "bull_call_spread", "lots": 2}

    def test_dispatches_close_action(self, monkeypatch):
        monkeypatch.setattr(main.requests, "post",
                            lambda *a, **k: MagicMock(raise_for_status=lambda: None,
                                                       json=lambda: {"request": {
                                                           "request_id": "OWH-2", "underlying": "NIFTY",
                                                           "template": "bull_call_spread", "action": "close",
                                                       }}))
        captured = {}
        monkeypatch.setattr(main, "_handle_options_webhook_close",
                            lambda broker, cloud_url, headers, positions, underlying, template:
                            captured.update(underlying=underlying, template=template))
        main._run_options_webhook_check(MagicMock(), "http://cloud", {}, {}, lots=1)
        assert captured == {"underlying": "NIFTY", "template": "bull_call_spread"}

    def test_claim_failure_does_not_raise(self, monkeypatch):
        def _boom(*a, **k):
            raise RuntimeError("network error")
        monkeypatch.setattr(main.requests, "post", _boom)
        main._run_options_webhook_check(MagicMock(), "http://cloud", {}, {}, lots=1)


class TestHandleOptionsWebhookOpen:

    def test_skips_if_already_has_open_position(self, monkeypatch):
        positions = {"NIFTY": OptionsPosition(signal_id="X", underlying="NIFTY",
                                               strategy="bull_call_spread", expiry="2099-01-01")}
        posted = {}
        monkeypatch.setattr(main.requests, "post",
                            lambda *a, **k: posted.setdefault("called", True))
        main._handle_options_webhook_open(MagicMock(), "http://cloud", {}, positions,
                                          "NIFTY", "bull_call_spread", lots=1)
        assert "called" not in posted

    def test_skips_unknown_template(self, monkeypatch):
        posted = {}
        monkeypatch.setattr(main.requests, "post",
                            lambda *a, **k: posted.setdefault("called", True))
        main._handle_options_webhook_open(MagicMock(), "http://cloud", {}, {},
                                          "NIFTY", "not_a_real_template", lots=1)
        assert "called" not in posted

    def test_happy_path_sends_signal_for_confirmation(self, monkeypatch):
        broker = MagicMock()
        broker.get_ltp.return_value = {"NIFTY 50": 22000.0}
        broker.get_option_chain.return_value = {"fake": "raw chain"}

        monkeypatch.setattr(main.options_symbol_master, "list_expiries",
                            lambda underlying: [date.today() + timedelta(days=7)])
        monkeypatch.setattr(main.options_symbol_master, "get_expiry_epoch",
                            lambda underlying, expiry: 1234567890)
        monkeypatch.setattr(main.options_chain_builder, "build_chain_snapshot",
                            lambda **kwargs: _chain_snapshot())

        resolved = MagicMock(symbol="NSE:NIFTY2672122000CE", lot_size=65)
        monkeypatch.setattr(main.options_symbol_master, "resolve_option_symbol",
                            lambda *a, **k: resolved)

        calls = []

        def _fake_post(url, json=None, headers=None, timeout=None):
            calls.append((url, json))
            if url.endswith("/strategy/recommend"):
                return MagicMock(raise_for_status=lambda: None, json=lambda: {
                    "strategy": "bull_call_spread",
                    "legs": [{"action": "BUY", "option_type": "CE", "strike": 22000.0, "premium": 150.0}],
                    "max_profit": 5000.0, "max_loss": -2000.0, "probability_of_profit": 55.0,
                })
            if url.endswith("/options/signal"):
                return MagicMock(raise_for_status=lambda: None,
                                 json=lambda: {"signal_id": "SIG-OPT-TEST"})
            raise AssertionError(f"unexpected POST to {url}")

        monkeypatch.setattr(main.requests, "post", _fake_post)

        main._handle_options_webhook_open(broker, "http://cloud", {}, {},
                                          "NIFTY", "bull_call_spread", lots=1)

        urls = [c[0] for c in calls]
        assert urls == ["http://cloud/strategy/recommend", "http://cloud/options/signal"]
        signal_payload = calls[1][1]
        assert signal_payload["trigger_source"] == "tradingview_webhook"
        assert signal_payload["legs"][0]["symbol"] == "NSE:NIFTY2672122000CE"

    def test_recommend_failure_does_not_post_signal(self, monkeypatch):
        broker = MagicMock()
        broker.get_ltp.return_value = {"NIFTY 50": 22000.0}
        broker.get_option_chain.return_value = {}
        monkeypatch.setattr(main.options_symbol_master, "list_expiries",
                            lambda underlying: [date.today() + timedelta(days=7)])
        monkeypatch.setattr(main.options_symbol_master, "get_expiry_epoch",
                            lambda underlying, expiry: 1)
        monkeypatch.setattr(main.options_chain_builder, "build_chain_snapshot",
                            lambda **kwargs: _chain_snapshot())

        def _fake_post(url, json=None, headers=None, timeout=None):
            raise RuntimeError("recommend endpoint down")
        monkeypatch.setattr(main.requests, "post", _fake_post)

        # Must not raise.
        main._handle_options_webhook_open(broker, "http://cloud", {}, {},
                                          "NIFTY", "bull_call_spread", lots=1)


class TestHandleOptionsWebhookClose:

    def _position(self, strategy="bull_call_spread"):
        return OptionsPosition(
            signal_id="SIG-OPT-X", underlying="NIFTY", strategy=strategy,
            expiry="2099-01-01",
            legs=[{"action": "BUY", "option_type": "CE", "strike": 22000.0,
                   "symbol": "NSE:NIFTY2672122000CE", "quantity": 1, "lot_size": 65,
                   "order_id": "ORD1", "fill_price": 150.0}],
        )

    def test_skips_if_no_open_position(self, monkeypatch):
        called = {}
        monkeypatch.setattr(main.options_executor, "flatten_position",
                            lambda *a, **k: called.setdefault("flattened", True))
        main._handle_options_webhook_close(MagicMock(), "http://cloud", {}, {},
                                           "NIFTY", "bull_call_spread")
        assert "flattened" not in called

    def test_happy_path_flattens_and_reports(self, monkeypatch):
        positions = {"NIFTY": self._position()}
        flatten_results = [FlattenResult(
            leg={"action": "BUY", "option_type": "CE", "strike": 22000.0},
            flattened=True, order_id="ORD-FLAT-1")]
        monkeypatch.setattr(main.options_executor, "flatten_position",
                            lambda broker, legs: flatten_results)

        captured = {}
        def _fake_post(url, json=None, headers=None, timeout=None):
            captured["url"] = url
            captured["json"] = json
            return MagicMock(raise_for_status=lambda: None)
        monkeypatch.setattr(main.requests, "post", _fake_post)

        main._handle_options_webhook_close(MagicMock(), "http://cloud", {}, positions,
                                           "NIFTY", "bull_call_spread")

        assert "NIFTY" not in positions   # removed after close
        assert captured["url"] == "http://cloud/webhook/options/closed"
        assert captured["json"]["underlying"] == "NIFTY"

    def test_closes_anyway_on_template_mismatch(self, monkeypatch):
        """Still closes (at most one open position per underlying is
        tracked) — just logs a warning, doesn't refuse."""
        positions = {"NIFTY": self._position(strategy="iron_condor")}
        monkeypatch.setattr(main.options_executor, "flatten_position",
                            lambda broker, legs: [])
        monkeypatch.setattr(main.requests, "post",
                            lambda *a, **k: MagicMock(raise_for_status=lambda: None))
        main._handle_options_webhook_close(MagicMock(), "http://cloud", {}, positions,
                                           "NIFTY", "bull_call_spread")
        assert "NIFTY" not in positions

    def test_flatten_exception_leaves_position_tracked(self, monkeypatch):
        """A failed flatten call must NOT remove the position from tracking
        — the position may genuinely still be open at the broker."""
        positions = {"NIFTY": self._position()}

        def _boom(broker, legs):
            raise RuntimeError("broker unreachable")
        monkeypatch.setattr(main.options_executor, "flatten_position", _boom)

        main._handle_options_webhook_close(MagicMock(), "http://cloud", {}, positions,
                                           "NIFTY", "bull_call_spread")
        assert "NIFTY" in positions


class TestAutoRegisterManualOptionsPositions:
    """agent._auto_register_manual_options_positions — closes the gap where
    a position placed by hand (e.g. via TradingView's Fyers trading panel,
    bypassing QuantOS's own /webhook/options 'open' flow) has no entry in
    the options_positions store, so a trailing-stop 'close' webhook fired
    for it later would otherwise find nothing to flatten."""

    def _position(self, symbol, qty, avg=100.0):
        return Position(symbol=symbol, quantity=qty, average_price=avg,
                         current_price=avg, pnl=0.0, pnl_percent=0.0,
                         product_type=ProductType.INTRADAY)

    def _resolved(self, underlying="TVSMOTOR", strike=4350.0,
                  option_type=OptionType.CALL, lot_size=1000):
        return ResolvedOption(
            symbol=f"NSE:{underlying}25AUG{int(strike)}{option_type.value}",
            lot_size=lot_size, expiry=date(2026, 8, 25), strike=strike,
            option_type=option_type, underlying=underlying,
        )

    def test_registers_new_manual_option_position(self, monkeypatch):
        broker = MagicMock()
        broker.get_positions.return_value = [self._position("TVSMOTOR25AUG4350CE", 1000, avg=52.5)]
        monkeypatch.setattr(main.options_symbol_master, "resolve_symbol_to_option",
                            lambda symbol, **k: self._resolved())

        positions = {}
        main._auto_register_manual_options_positions(broker, positions)

        assert "TVSMOTOR" in positions
        pos = positions["TVSMOTOR"]
        assert pos.strategy == "manual_single_leg"
        assert pos.legs == [{
            "action": "BUY", "option_type": "CE", "strike": 4350.0, "premium": 52.5,
            "quantity": 1, "symbol": "NSE:TVSMOTOR25AUG4350CE", "lot_size": 1000,
        }]

    def test_short_position_registers_as_sell(self, monkeypatch):
        broker = MagicMock()
        broker.get_positions.return_value = [self._position("TVSMOTOR25AUG4350CE", -1000)]
        monkeypatch.setattr(main.options_symbol_master, "resolve_symbol_to_option",
                            lambda symbol, **k: self._resolved())

        positions = {}
        main._auto_register_manual_options_positions(broker, positions)
        assert positions["TVSMOTOR"].legs[0]["action"] == "SELL"

    def test_skips_zero_quantity_position(self, monkeypatch):
        broker = MagicMock()
        broker.get_positions.return_value = [self._position("TVSMOTOR25AUG4350CE", 0)]
        called = {}
        monkeypatch.setattr(main.options_symbol_master, "resolve_symbol_to_option",
                            lambda symbol, **k: called.setdefault("called", True))

        positions = {}
        main._auto_register_manual_options_positions(broker, positions)
        assert positions == {}
        assert "called" not in called   # never even attempted to resolve a flat line

    def test_skips_non_option_position(self, monkeypatch):
        """An equity position's symbol won't resolve against the option
        symbol master — must be skipped, not raise."""
        broker = MagicMock()
        broker.get_positions.return_value = [self._position("RELIANCE", 10)]

        def _raise(symbol, **k):
            raise SymbolMasterError(f"{symbol} not an option")
        monkeypatch.setattr(main.options_symbol_master, "resolve_symbol_to_option", _raise)

        positions = {}
        main._auto_register_manual_options_positions(broker, positions)
        assert positions == {}

    def test_skips_underlying_already_tracked(self, monkeypatch):
        existing = OptionsPosition(signal_id="SIG-1", underlying="TVSMOTOR",
                                   strategy="manual_single_leg", expiry="2026-08-25",
                                   legs=[{"symbol": "NSE:TVSMOTOR25AUG4300CE"}])
        broker = MagicMock()
        broker.get_positions.return_value = [self._position("TVSMOTOR25AUG4350CE", 1000)]
        monkeypatch.setattr(main.options_symbol_master, "resolve_symbol_to_option",
                            lambda symbol, **k: self._resolved())

        positions = {"TVSMOTOR": existing}
        main._auto_register_manual_options_positions(broker, positions)
        # Untouched — not overwritten with the newly-seen position.
        assert positions["TVSMOTOR"] is existing

    def test_skips_lot_size_mismatch_without_raising(self, monkeypatch):
        broker = MagicMock()
        # 999 doesn't divide evenly by lot_size=1000.
        broker.get_positions.return_value = [self._position("TVSMOTOR25AUG4350CE", 999)]
        monkeypatch.setattr(main.options_symbol_master, "resolve_symbol_to_option",
                            lambda symbol, **k: self._resolved())

        positions = {}
        main._auto_register_manual_options_positions(broker, positions)
        assert positions == {}

    def test_broker_fetch_failure_does_not_raise(self, monkeypatch):
        broker = MagicMock()
        broker.get_positions.side_effect = RuntimeError("broker unreachable")
        positions = {}
        main._auto_register_manual_options_positions(broker, positions)   # must not raise
        assert positions == {}

    def test_multiple_lots_computed_correctly(self, monkeypatch):
        broker = MagicMock()
        # 3 lots of 1000 = 3000 net quantity.
        broker.get_positions.return_value = [self._position("TVSMOTOR25AUG4350CE", 3000)]
        monkeypatch.setattr(main.options_symbol_master, "resolve_symbol_to_option",
                            lambda symbol, **k: self._resolved())

        positions = {}
        main._auto_register_manual_options_positions(broker, positions)
        assert positions["TVSMOTOR"].legs[0]["quantity"] == 3
