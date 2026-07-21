"""
core/options/regime_trigger.py — fires a new options suggestion on a
regime change (the user's explicit 2026-07-21 decision: event-driven,
like Darvas's breakout scan). Scoped to NIFTY only, deliberately, since
the regime engine classifies the market, not individual stocks.

Claude's pick is fetched via HTTP from the existing POST /strategy/
recommend rather than calling recommend_strategy() directly — corrected
same day after the direct-call version needed ANTHROPIC_API_KEY on every
machine running this trigger, when the cloud process already has both
the key and this exact endpoint idle.
"""

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

from core.options import regime_trigger as trig
from core.regime.models import Regime, RegimeResult


@pytest.fixture(autouse=True)
def _isolated_path(tmp_path, monkeypatch):
    monkeypatch.setattr(trig, "LAST_REGIME_PATH", tmp_path / "options_last_regime.json")


def _regime(regime=Regime.TRENDING_BULL, allowed=("bull_call_spread",)):
    return RegimeResult(
        regime=regime, confidence=80.0, allowed_strategies=list(allowed),
        size_multiplier=1.0, timestamp=None,
    )


def _recommend_response(**overrides):
    payload = {
        "underlying": "NIFTY", "strategy": "bull_call_spread",
        "legs": [
            {"action": "BUY", "option_type": "CE", "strike": 24800.0, "premium": 120.0, "quantity": 1},
            {"action": "SELL", "option_type": "CE", "strike": 25000.0, "premium": 40.0, "quantity": 1},
        ],
        "greeks": {"delta": 0.3, "gamma": 0.01, "theta": -2.0, "vega": 5.0},
        "max_profit": 12675.0, "max_loss": 5200.0, "probability_of_profit": 58.0,
        "rationale": "TRENDING_BULL with room to the upside",
        "regime_context": "TRENDING_BULL (confidence 80)", "confidence_score": 75.0,
        "whatsapp_preview": "",
    }
    payload.update(overrides)
    return payload


def _fake_post_recommend(response_json):
    def _post(url, json, headers, timeout):
        assert url == "http://cloud/strategy/recommend"
        return MagicMock(raise_for_status=lambda: None, json=lambda: response_json)
    return _post


class TestHasRegimeChanged:

    def test_no_prior_state_counts_as_changed(self):
        assert trig._load_last_regime() is None

    def test_marking_then_reloading_persists(self):
        trig._mark_regime_seen("TRENDING_BULL")
        assert trig._load_last_regime() == "TRENDING_BULL"


class TestCheckAndBuildSuggestion:

    def test_unchanged_regime_returns_none(self):
        trig._mark_regime_seen("TRENDING_BULL")
        broker = MagicMock()
        result = trig.check_and_build_suggestion(
            broker, _regime(Regime.TRENDING_BULL), {}, "http://cloud", {})
        assert result is None
        broker.get_ltp.assert_not_called()

    def test_regime_with_no_allowed_strategies_skips_and_marks_seen(self):
        broker = MagicMock()
        result = trig.check_and_build_suggestion(
            broker, _regime(Regime.UNCERTAIN, allowed=()), {}, "http://cloud", {})
        assert result is None
        assert trig._load_last_regime() == "UNCERTAIN"
        broker.get_ltp.assert_not_called()

    def test_open_position_for_underlying_skips_and_marks_seen(self):
        from core.options.positions import OptionsPosition
        broker = MagicMock()
        open_positions = {
            "NIFTY": OptionsPosition(
                signal_id="SIG-OPT-X", underlying="NIFTY", strategy="bull_call_spread",
                expiry=(date.today() + timedelta(days=5)).isoformat(),
            )
        }
        result = trig.check_and_build_suggestion(
            broker, _regime(Regime.TRENDING_BULL), open_positions, "http://cloud", {})
        assert result is None
        assert trig._load_last_regime() == "TRENDING_BULL"
        broker.get_ltp.assert_not_called()

    def test_expired_position_does_not_block_new_suggestion(self):
        from core.options.positions import OptionsPosition
        open_positions = {
            "NIFTY": OptionsPosition(
                signal_id="SIG-OPT-OLD", underlying="NIFTY", strategy="bull_call_spread",
                expiry=(date.today() - timedelta(days=1)).isoformat(),
            )
        }
        broker = MagicMock()
        broker.get_ltp.return_value = {"NIFTY 50": 24900.0}
        broker.get_option_chain.return_value = {
            "optionsChain": [
                {"strike_price": 24800, "option_type": "CE", "ltp": 120.0, "oi": 100},
                {"strike_price": 25000, "option_type": "CE", "ltp": 40.0, "oi": 100},
            ]
        }
        with patch("core.options.fyers_symbol_master.list_expiries",
                   return_value=[date.today() + timedelta(days=7)]), \
             patch("core.options.fyers_symbol_master.get_expiry_epoch",
                   return_value="1784628000"), \
             patch("core.options.fyers_symbol_master.resolve_option_symbol") as mock_resolve, \
             patch("core.options.regime_trigger.requests.post",
                   side_effect=_fake_post_recommend(_recommend_response())):
            mock_resolve.side_effect = lambda underlying, expiry, strike, opt_type: MagicMock(
                symbol=f"NSE:NIFTY-{strike}-{opt_type.value}", lot_size=65)
            result = trig.check_and_build_suggestion(
                broker, _regime(Regime.TRENDING_BULL), open_positions, "http://cloud", {})
        assert result is not None

    def test_transient_failure_does_not_mark_regime_seen(self):
        """A network error mid-build must not be treated as 'handled' —
        the next tick should retry, not silently wait for the next regime
        change."""
        broker = MagicMock()
        broker.get_ltp.side_effect = RuntimeError("network error")
        with pytest.raises(RuntimeError):
            trig.check_and_build_suggestion(
                broker, _regime(Regime.TRENDING_BULL), {}, "http://cloud", {})
        assert trig._load_last_regime() is None


class TestBuildSuggestion:

    def _mock_chain(self, broker):
        broker.get_ltp.return_value = {"NIFTY 50": 24900.0}
        broker.get_option_chain.return_value = {
            "optionsChain": [
                {"strike_price": 24800, "option_type": "CE", "ltp": 120.0, "oi": 100},
                {"strike_price": 25000, "option_type": "CE", "ltp": 40.0, "oi": 100},
            ]
        }

    def test_resolves_real_symbols_for_every_leg(self):
        broker = MagicMock()
        self._mock_chain(broker)
        with patch("core.options.fyers_symbol_master.list_expiries",
                   return_value=[date.today() + timedelta(days=7)]), \
             patch("core.options.fyers_symbol_master.get_expiry_epoch",
                   return_value="1784628000"), \
             patch("core.options.fyers_symbol_master.resolve_option_symbol") as mock_resolve, \
             patch("core.options.regime_trigger.requests.post",
                   side_effect=_fake_post_recommend(_recommend_response())):
            mock_resolve.side_effect = lambda underlying, expiry, strike, opt_type: MagicMock(
                symbol=f"NSE:NIFTY-{strike:.0f}-{opt_type.value}", lot_size=65)
            suggestion = trig.build_suggestion(broker, "http://cloud", {}, lots=1)

        assert suggestion["underlying"] == "NIFTY"
        assert suggestion["strategy"] == "bull_call_spread"
        assert len(suggestion["legs"]) == 2
        assert suggestion["legs"][0]["symbol"] == "NSE:NIFTY-24800-CE"
        assert suggestion["legs"][0]["lot_size"] == 65
        assert suggestion["legs"][0]["quantity"] == 1

    def test_posts_chain_snapshot_to_strategy_recommend(self):
        broker = MagicMock()
        self._mock_chain(broker)
        captured = {}

        def _post(url, json, headers, timeout):
            captured["url"] = url
            captured["json"] = json
            return MagicMock(raise_for_status=lambda: None,
                             json=lambda: _recommend_response())

        with patch("core.options.fyers_symbol_master.list_expiries",
                   return_value=[date.today() + timedelta(days=7)]), \
             patch("core.options.fyers_symbol_master.get_expiry_epoch",
                   return_value="1784628000"), \
             patch("core.options.fyers_symbol_master.resolve_option_symbol",
                   return_value=MagicMock(symbol="NSE:X", lot_size=65)), \
             patch("core.options.regime_trigger.requests.post", side_effect=_post):
            trig.build_suggestion(broker, "http://cloud", {"X-Cloud-Secret": "s"}, lots=1)

        assert captured["url"] == "http://cloud/strategy/recommend"
        assert captured["json"]["underlying"] == "NIFTY"
        assert captured["json"]["pcr"] is not None
        assert len(captured["json"]["legs"]) == 2

    def test_monetary_fields_scaled_by_lots(self):
        broker = MagicMock()
        self._mock_chain(broker)
        with patch("core.options.fyers_symbol_master.list_expiries",
                   return_value=[date.today() + timedelta(days=7)]), \
             patch("core.options.fyers_symbol_master.get_expiry_epoch",
                   return_value="1784628000"), \
             patch("core.options.fyers_symbol_master.resolve_option_symbol",
                   return_value=MagicMock(symbol="NSE:X", lot_size=65)), \
             patch("core.options.regime_trigger.requests.post",
                   side_effect=_fake_post_recommend(_recommend_response())):
            suggestion = trig.build_suggestion(broker, "http://cloud", {}, lots=3)

        assert suggestion["max_profit"] == pytest.approx(12675.0 * 3)
        assert suggestion["max_loss"] == pytest.approx(5200.0 * 3)
        assert suggestion["probability_of_profit"] == 58.0  # a % — never scaled

    def test_undefined_max_loss_converted_back_from_none(self):
        """/strategy/recommend serializes -inf as JSON null — must be
        restored, not left as None (which would break downstream
        max_loss == float('-inf') formatting checks)."""
        broker = MagicMock()
        self._mock_chain(broker)
        with patch("core.options.fyers_symbol_master.list_expiries",
                   return_value=[date.today() + timedelta(days=7)]), \
             patch("core.options.fyers_symbol_master.get_expiry_epoch",
                   return_value="1784628000"), \
             patch("core.options.fyers_symbol_master.resolve_option_symbol",
                   return_value=MagicMock(symbol="NSE:X", lot_size=65)), \
             patch("core.options.regime_trigger.requests.post",
                   side_effect=_fake_post_recommend(_recommend_response(max_loss=None))):
            suggestion = trig.build_suggestion(broker, "http://cloud", {})

        assert suggestion["max_loss"] == float("-inf")

    def test_no_expiries_available_raises(self):
        broker = MagicMock()
        with patch("core.options.fyers_symbol_master.list_expiries", return_value=[]):
            with pytest.raises(Exception):
                trig.build_suggestion(broker, "http://cloud", {})

    def test_prefers_expiry_at_least_min_days_out(self):
        near = date.today() + timedelta(days=1)
        far = date.today() + timedelta(days=9)
        broker = MagicMock()
        self._mock_chain(broker)
        with patch("core.options.fyers_symbol_master.list_expiries",
                   return_value=[near, far]), \
             patch("core.options.fyers_symbol_master.get_expiry_epoch",
                   return_value="1784628000"), \
             patch("core.options.fyers_symbol_master.resolve_option_symbol",
                   return_value=MagicMock(symbol="NSE:X", lot_size=65)), \
             patch("core.options.regime_trigger.requests.post",
                   side_effect=_fake_post_recommend(_recommend_response())):
            suggestion = trig.build_suggestion(broker, "http://cloud", {})

        assert suggestion["expiry"] == far.isoformat()
