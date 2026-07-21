"""
QuantOS — Option Chain Snapshot Builder
─────────────────────────────────────────
Converts the raw dict returned by FyersBroker.get_option_chain() into the
OptionChainSnapshot shape core/options/recommender.py expects.

NOT YET LIVE-VERIFIED. Built from Fyers' public API docs/community
threads (2026-07-21), not a real captured response — same category of
risk as core/regime/fetcher.py's index-symbol fix, which turned out
right but wasn't confirmed until a real agent run hit it. Fyers'
optionsChain rows are read via _field() below, which tries several
known key-name variants (snake_case and camelCase both show up in
different pieces of Fyers' own docs) rather than assuming one — but the
first real run against a live token should log a raw sample response and
this module corrected against it before being trusted for real orders.

Fyers' option chain supplies OI/LTP/bid/ask per strike — no Greeks, no
IV, no PCR, no max pain, and no spot price (confirmed absent from the
documented response fields). This module computes PCR and max pain from
OI, solves each leg's IV from its LTP (core/options/greeks.implied_volatility),
and requires the caller to supply spot_price separately (e.g. via
broker.get_ltp([underlying]) — already tested code, rather than trusting
an unconfirmed field in the chain response).

iv_rank/iv_percentile need a trailing history of daily IV readings that
doesn't exist yet on day one. Both default to a documented placeholder
(50.0, "neutral") until a history-accumulation job is built — the same
kind of degraded-input risk already accepted for the regime classifier,
not a new blocker.
"""

import logging
from datetime import date

from core.options.greeks import implied_volatility
from core.options.models import OptionChainSnapshot, OptionLeg, OptionType

logger = logging.getLogger(__name__)

# Fyers' documented field names are inconsistent across their own docs/
# community threads (snake_case in some, camelCase in others) — try both
# rather than assume one and silently misparse every row.
_STRIKE_KEYS = ("strike_price", "strikePrice")
_OPTION_TYPE_KEYS = ("option_type", "optionType")
_LTP_KEYS = ("ltp",)
_OI_KEYS = ("oi",)
_VOLUME_KEYS = ("volume", "vol")

IV_RANK_PLACEHOLDER = 50.0
IV_PERCENTILE_PLACEHOLDER = 50.0


class ChainBuildError(Exception):
    """Raised when the raw chain response can't be parsed into a snapshot."""
    pass


def _field(row: dict, keys: tuple[str, ...], required: bool = True):
    for k in keys:
        if k in row:
            return row[k]
    if required:
        raise ChainBuildError(
            f"None of {keys} found in option chain row: {list(row.keys())}"
        )
    return None


def build_chain_snapshot(
    underlying: str,
    expiry: date,
    spot_price: float,
    raw_chain: dict,
    days_to_expiry: int,
    iv_rank: float = IV_RANK_PLACEHOLDER,
    iv_percentile: float = IV_PERCENTILE_PLACEHOLDER,
) -> OptionChainSnapshot:
    """
    Args:
        underlying: e.g. "NIFTY", "SBIN"
        expiry: the expiry date this chain is for
        spot_price: current underlying price, fetched separately
            (broker.get_ltp) rather than trusted from the chain response
        raw_chain: the dict FyersBroker.get_option_chain() returns
            (response["data"] — has "optionsChain" list plus callOi/putOi)
        days_to_expiry: calendar days to expiry, for the IV solve
        iv_rank / iv_percentile: pass real values once a history job
            exists; otherwise leave at the documented placeholder
    """
    rows = raw_chain.get("optionsChain", [])
    if not rows:
        raise ChainBuildError(f"Empty optionsChain in raw response for {underlying}")

    legs: list[OptionLeg] = []
    total_call_oi = 0
    total_put_oi = 0

    for row in rows:
        opt_type_raw = _field(row, _OPTION_TYPE_KEYS, required=False)
        if opt_type_raw not in ("CE", "PE"):
            continue  # skip the underlying's own row / futures row if present

        strike = float(_field(row, _STRIKE_KEYS))
        ltp = float(_field(row, _LTP_KEYS))
        oi = int(_field(row, _OI_KEYS, required=False) or 0)
        volume = int(_field(row, _VOLUME_KEYS, required=False) or 0)
        option_type = OptionType.CALL if opt_type_raw == "CE" else OptionType.PUT

        if option_type == OptionType.CALL:
            total_call_oi += oi
        else:
            total_put_oi += oi

        iv = implied_volatility(
            market_price=ltp, spot=spot_price, strike=strike,
            days_to_expiry=days_to_expiry, option_type=option_type,
        )

        legs.append(OptionLeg(
            strike=strike, option_type=option_type, expiry=expiry,
            premium=ltp, open_interest=oi, volume=volume, implied_vol=iv,
        ))

    if not legs:
        raise ChainBuildError(f"No CE/PE legs parsed for {underlying} {expiry}")

    pcr = round(total_put_oi / total_call_oi, 3) if total_call_oi > 0 else 0.0
    max_pain = _compute_max_pain(legs)

    return OptionChainSnapshot(
        underlying=underlying,
        spot_price=spot_price,
        expiry=expiry,
        legs=legs,
        iv_rank=iv_rank,
        iv_percentile=iv_percentile,
        pcr=pcr,
        max_pain=max_pain,
    )


def _compute_max_pain(legs: list[OptionLeg]) -> float:
    """
    Standard max-pain algorithm: the strike at which option WRITERS' total
    payout obligation (and therefore buyers' aggregate profit) is smallest,
    if the underlying settled exactly there at expiry.
    """
    calls = [l for l in legs if l.is_call]
    puts = [l for l in legs if l.is_put]
    candidate_strikes = sorted(set(l.strike for l in legs))

    best_strike = candidate_strikes[0]
    best_payout = float("inf")

    for candidate in candidate_strikes:
        payout = 0.0
        for c in calls:
            if candidate > c.strike:
                payout += c.open_interest * (candidate - c.strike)
        for p in puts:
            if candidate < p.strike:
                payout += p.open_interest * (p.strike - candidate)
        if payout < best_payout:
            best_payout = payout
            best_strike = candidate

    return best_strike
