"""
QuantOS — Regime-Change Options Trigger
────────────────────────────────────────
Fires a new options strategy suggestion when the market regime changes —
the user's explicit decision (2026-07-21): event-driven, like Darvas's
breakout scan, rather than a fixed schedule or manual-only trigger.

Scope decision, stated plainly rather than silently assumed: this only
ever triggers for NIFTY, even though the mechanical plumbing underneath
(symbol resolution, lot sizes, chain building) works for any F&O
underlying. core/regime/service.py classifies the MARKET (NIFTY trend/
VIX/breadth) — there is no per-stock regime. Applying that market-wide
signal to a single stock's options would be an extra, unvalidated
assumption stacked on top of S8-1's already-flagged finding that this
classifier doesn't reliably separate forward outcomes. Single-stock
support stays available in the underlying modules for a future per-stock
signal source, but is not wired into this automatic trigger.

Only the local agent ever holds a connected broker (ADR-01), so this is
the only place the chain fetch can run — mirrors core/regime/service.py's
own reasoning and core/rotation/executor.py's orchestration shape.

Claude's strategy pick itself is fetched via HTTP from the EXISTING
POST /strategy/recommend (cloud/api/strategy_routes.py) rather than
calling core/options/recommender.py's recommend_strategy() directly —
first written the direct-call way, then corrected same day: that would
have needed ANTHROPIC_API_KEY on every machine running this trigger
(this dev box, eventually the VM), a second place to manage that secret
when the cloud process already holds it and already has this exact
endpoint built and idle. Reusing it also means one less thing to keep in
sync (regime routing, prompt template, whatsapp formatting) between two
code paths that both wrap the same Claude call.
"""

import json
import logging
from datetime import date
from pathlib import Path
from typing import Optional

import requests

from core.options import chain_builder
from core.options import fyers_symbol_master as sm
from core.options.models import OptionType
from core.regime.models import RegimeResult

logger = logging.getLogger(__name__)

LAST_REGIME_PATH = Path.home() / ".quantos" / "options_last_regime.json"
TRIGGER_UNDERLYING = "NIFTY"
MIN_DAYS_TO_EXPIRY = 2   # avoid firing into an expiry-day contract with no time value left


def _load_last_regime() -> Optional[str]:
    if not LAST_REGIME_PATH.exists():
        return None
    try:
        return json.loads(LAST_REGIME_PATH.read_text()).get("regime")
    except (json.JSONDecodeError, OSError):
        return None


def _mark_regime_seen(regime_value: str) -> None:
    LAST_REGIME_PATH.parent.mkdir(parents=True, exist_ok=True)
    LAST_REGIME_PATH.write_text(json.dumps({"regime": regime_value}))


def _pick_expiry(underlying: str) -> date:
    expiries = sm.list_expiries(underlying)
    if not expiries:
        raise sm.SymbolMasterError(f"No expiries available for {underlying}")
    for expiry in expiries:
        if (expiry - date.today()).days >= MIN_DAYS_TO_EXPIRY:
            return expiry
    return expiries[-1]   # everything left is inside the buffer — take the furthest


def _fetch_recommendation(cloud_url: str, headers: dict, snapshot) -> dict:
    """POSTs the chain snapshot to the existing /strategy/recommend
    endpoint and returns its JSON response. That endpoint reads the
    regime itself (get_synced_regime()) rather than trusting a value we
    pass — it's the same regime this trigger already synced this tick
    (_run_regime_sync runs immediately before this in agent/main.py), so
    there's no meaningful race, just one regime read instead of two."""
    payload = {
        "underlying":    snapshot.underlying,
        "spot_price":    snapshot.spot_price,
        "expiry":        snapshot.expiry.isoformat(),
        "legs": [
            {
                "strike": leg.strike, "option_type": leg.option_type.value,
                "premium": leg.premium, "open_interest": leg.open_interest,
                "volume": leg.volume, "implied_vol": leg.implied_vol,
            }
            for leg in snapshot.legs
        ],
        "iv_rank":       snapshot.iv_rank,
        "iv_percentile": snapshot.iv_percentile,
        "pcr":           snapshot.pcr,
        "max_pain":      snapshot.max_pain,
    }
    resp = requests.post(f"{cloud_url}/strategy/recommend", json=payload,
                         headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


def build_suggestion(broker, cloud_url: str, headers: dict, lots: int = 1,
                      underlying: str = TRIGGER_UNDERLYING) -> dict:
    """
    Fetches the chain, gets Claude's recommendation via the cloud's
    /strategy/recommend, and resolves every leg's real Fyers symbol + lot
    size (core/options/fyers_symbol_master.py). Returns the payload ready
    to POST to cloud's POST /options/signal. Raises on a hard failure —
    caller (agent/main.py) logs and swallows, matching every other
    best-effort agent tick (_run_regime_sync, _run_rotation_rebalance).
    """
    expiry = _pick_expiry(underlying)
    days_to_expiry = max(1, (expiry - date.today()).days)

    spot_symbol = "NIFTY 50" if underlying == "NIFTY" else underlying
    spot_prices = broker.get_ltp([spot_symbol])
    spot = spot_prices.get(spot_symbol) or spot_prices.get(underlying)
    if not spot:
        raise ValueError(f"Could not fetch spot price for {underlying}")

    expiry_epoch = sm.get_expiry_epoch(underlying, expiry)
    raw_chain = broker.get_option_chain(underlying, expiry_epoch)
    snapshot = chain_builder.build_chain_snapshot(
        underlying=underlying, expiry=expiry, spot_price=spot,
        raw_chain=raw_chain, days_to_expiry=days_to_expiry,
    )

    rec = _fetch_recommendation(cloud_url, headers, snapshot)

    legs = []
    for leg in rec["legs"]:
        opt_type = OptionType.CALL if leg["option_type"] == "CE" else OptionType.PUT
        resolved = sm.resolve_option_symbol(underlying, expiry, leg["strike"], opt_type)
        legs.append({
            "action":      leg["action"],
            "option_type": leg["option_type"],
            "strike":      leg["strike"],
            "premium":     leg["premium"],
            "quantity":    lots,
            "symbol":      resolved.symbol,
            "lot_size":    resolved.lot_size,
        })

    # /strategy/recommend's response is at its own internal qty=1 scale
    # (strategy_builder's default) and represents max_loss=-inf as `None`
    # over JSON — undo both before this goes into the Telegram prompt.
    max_loss = rec["max_loss"] if rec["max_loss"] is not None else float("-inf")
    net_premium = sum(
        (leg["premium"] if leg["action"] == "SELL" else -leg["premium"])
        for leg in rec["legs"]
    )

    def _scaled(value: float) -> float:
        return value * lots if value not in (float("inf"), float("-inf")) else value

    return {
        "underlying":             underlying,
        "expiry":                 expiry.isoformat(),
        "strategy":               rec["strategy"],
        "legs":                   legs,
        "rationale":              rec["rationale"],
        "regime_context":         rec["regime_context"],
        "max_profit":             _scaled(rec["max_profit"]),
        "max_loss":               _scaled(max_loss),
        "net_premium":            _scaled(net_premium),
        "probability_of_profit":  rec["probability_of_profit"],
    }


def check_and_build_suggestion(
    broker, regime_result: RegimeResult, options_positions: dict,
    cloud_url: str, headers: dict, lots: int = 1, underlying: str = TRIGGER_UNDERLYING,
) -> Optional[dict]:
    """
    Top-level entry point for agent/main.py. Returns a suggestion payload
    if a new one should be generated, else None. Marks the regime as seen
    in every branch that decides NOT to build a suggestion for a reason
    that won't change until the regime itself changes again (already-open
    position, no allowed strategies) — but deliberately does NOT mark it
    before a real attempt, so a transient failure (network error) gets
    retried on the next tick rather than silently skipped until the next
    regime change.
    """
    if _load_last_regime() == regime_result.regime.value:
        return None

    if not regime_result.allowed_strategies:
        logger.info("Regime %s allows no options strategies — skipping suggestion",
                    regime_result.regime.value)
        _mark_regime_seen(regime_result.regime.value)
        return None

    from core.options.positions import has_open_position
    if has_open_position(options_positions, underlying):
        logger.info("Regime changed to %s but %s already has an open options "
                    "position — skipping until it expires",
                    regime_result.regime.value, underlying)
        _mark_regime_seen(regime_result.regime.value)
        return None

    suggestion = build_suggestion(broker, cloud_url, headers, lots=lots, underlying=underlying)
    _mark_regime_seen(regime_result.regime.value)
    return suggestion
