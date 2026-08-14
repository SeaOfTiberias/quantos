"""
QuantOS — Black-Scholes Greeks Calculator
─────────────────────────────────────────────
US-05b: Computes option Greeks (delta, gamma, theta, vega) using the
Black-Scholes model. Fyers' optionchain API supplies OI/LTP/bid/ask per
strike but no Greeks and no IV (confirmed against Fyers' own API docs/
community threads 2026-07-21) — this module is the only source of both,
via forward Greeks computation and (see implied_volatility()) inversion
from a leg's traded price.

Standard Black-Scholes assumptions apply (European-style, no dividends
adjustment built in — acceptable approximation for NSE index/stock options
over short to medium expiries).
"""

import math
from dataclasses import dataclass

from core.options.models import OptionType

# Risk-free rate — approximate using current Indian 91-day T-bill yield.
# Update periodically; small changes have minimal Greeks impact.
DEFAULT_RISK_FREE_RATE = 0.065   # 6.5%


def _norm_cdf(x: float) -> float:
    """Standard normal cumulative distribution function."""
    return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0


def _norm_pdf(x: float) -> float:
    """Standard normal probability density function."""
    return math.exp(-x * x / 2.0) / math.sqrt(2.0 * math.pi)


@dataclass
class GreeksResult:
    delta: float
    gamma: float
    theta: float    # per calendar day
    vega:  float    # per 1% change in IV
    theoretical_price: float


def compute_greeks(
    spot:           float,
    strike:         float,
    days_to_expiry: int,
    implied_vol:    float,          # decimal, e.g. 0.18
    option_type:    OptionType,
    risk_free_rate: float = DEFAULT_RISK_FREE_RATE,
) -> GreeksResult:
    """
    Compute Black-Scholes Greeks for a single option.

    Args:
        spot: current underlying price
        strike: option strike price
        days_to_expiry: calendar days until expiry (must be > 0)
        implied_vol: implied volatility as a decimal (0.18 = 18%)
        option_type: CALL or PUT
        risk_free_rate: annualized risk-free rate as a decimal

    Returns:
        GreeksResult with delta, gamma, theta, vega, theoretical_price
    """
    if days_to_expiry <= 0:
        # At/past expiry — use intrinsic value only, Greeks collapse
        if option_type == OptionType.CALL:
            intrinsic = max(0.0, spot - strike)
            delta = 1.0 if spot > strike else 0.0
        else:
            intrinsic = max(0.0, strike - spot)
            delta = -1.0 if spot < strike else 0.0
        return GreeksResult(delta=delta, gamma=0.0, theta=0.0, vega=0.0,
                            theoretical_price=intrinsic)

    if implied_vol <= 0:
        implied_vol = 0.01  # floor to avoid division by zero

    T = days_to_expiry / 365.0
    sqrt_T = math.sqrt(T)

    d1 = (
        math.log(spot / strike) + (risk_free_rate + 0.5 * implied_vol ** 2) * T
    ) / (implied_vol * sqrt_T)
    d2 = d1 - implied_vol * sqrt_T

    if option_type == OptionType.CALL:
        delta = _norm_cdf(d1)
        theoretical_price = (
            spot * _norm_cdf(d1)
            - strike * math.exp(-risk_free_rate * T) * _norm_cdf(d2)
        )
        theta_annual = (
            -(spot * _norm_pdf(d1) * implied_vol) / (2 * sqrt_T)
            - risk_free_rate * strike * math.exp(-risk_free_rate * T) * _norm_cdf(d2)
        )
    else:  # PUT
        delta = _norm_cdf(d1) - 1.0
        theoretical_price = (
            strike * math.exp(-risk_free_rate * T) * _norm_cdf(-d2)
            - spot * _norm_cdf(-d1)
        )
        theta_annual = (
            -(spot * _norm_pdf(d1) * implied_vol) / (2 * sqrt_T)
            + risk_free_rate * strike * math.exp(-risk_free_rate * T) * _norm_cdf(-d2)
        )

    gamma = _norm_pdf(d1) / (spot * implied_vol * sqrt_T)
    vega  = spot * _norm_pdf(d1) * sqrt_T / 100   # per 1% IV change
    theta_daily = theta_annual / 365.0             # convert to per-day decay

    return GreeksResult(
        delta=round(delta, 4),
        gamma=round(gamma, 6),
        theta=round(theta_daily, 4),
        vega=round(vega, 4),
        theoretical_price=round(max(0.0, theoretical_price), 2),
    )


FALLBACK_IV = 0.18   # the NIFTY-ish default returned when inversion is impossible

VOL_FLOOR, VOL_CEILING = 0.01, 5.0


class ImpliedVolatilityError(ValueError):
    """The market price cannot be inverted to an implied volatility.

    Raised only when `implied_volatility(..., strict=True)`. The non-strict
    default returns FALLBACK_IV instead, preserving the behaviour every
    existing caller was written against.
    """


def implied_volatility(
    market_price:   float,
    spot:           float,
    strike:         float,
    days_to_expiry: int,
    option_type:    OptionType,
    risk_free_rate: float = DEFAULT_RISK_FREE_RATE,
    tolerance:      float = 0.001,
    max_iterations: int = 100,
    strict:         bool = False,
) -> float:
    """
    Invert Black-Scholes to solve for implied volatility given a traded
    option price — needed because Fyers' option chain doesn't supply IV
    directly. Uses bisection rather than Newton's method: vega collapses
    near expiry/deep ITM-OTM, which makes Newton's derivative step
    unstable exactly where this will be called most (near-dated NIFTY
    weeklies).

    Returns a decimal (e.g. 0.18 = 18%), floored/capped to [0.01, 5.0].

    `strict` controls what happens when the price is NOT invertible:

      • False (default) — return FALLBACK_IV (0.18). Behaviour is unchanged
        from before this parameter existed, so every existing caller is
        unaffected.
      • True — raise `ImpliedVolatilityError` naming the reason.

    Prefer `strict=True` in anything that feeds a trading decision. A
    fabricated 0.18 is indistinguishable from a solved 0.18 once it is in a
    dataclass, and it will be averaged, ranked and sized off exactly as
    though it were real. Two research scripts already hand-mirror this
    function's fallback preconditions to avoid absorbing the constant into a
    sample (`_would_hit_iv_fallback` in scripts/validate_vol_skew_signal.py
    and validate_vol_term_structure_signal.py) — that duplication exists
    because the non-strict path cannot report the difference.

    Three conditions are un-invertible, and strict mode distinguishes them:
      1. no time to expiry, or a non-positive price;
      2. price at or below intrinsic — no time value left to invert;
      3. price outside what [0.01, 5.0] vol can produce, so bisection would
         converge on a bracket endpoint rather than a solution. The
         non-strict path returns that endpoint silently, which looks like an
         answer.
    """
    def _fallback(reason: str) -> float:
        if strict:
            raise ImpliedVolatilityError(
                f"cannot invert {option_type.value} {strike} @ {market_price} "
                f"(spot {spot}, {days_to_expiry}d): {reason}"
            )
        return FALLBACK_IV

    if days_to_expiry <= 0:
        return _fallback(f"days_to_expiry={days_to_expiry} leaves no time value")
    if market_price <= 0:
        return _fallback(f"market_price={market_price} is not positive")

    intrinsic = (max(0.0, spot - strike) if option_type == OptionType.CALL
                 else max(0.0, strike - spot))
    if market_price <= intrinsic:
        return _fallback(
            f"price {market_price} is at or below intrinsic {intrinsic:.2f} — "
            f"no time value to invert"
        )

    def _price_at(vol: float) -> float:
        return compute_greeks(
            spot=spot, strike=strike, days_to_expiry=days_to_expiry,
            implied_vol=vol, option_type=option_type,
            risk_free_rate=risk_free_rate,
        ).theoretical_price

    lo, hi = VOL_FLOOR, VOL_CEILING

    # Bracket check. Without it, a price above the ceiling's theoretical value
    # bisects toward 5.0 and is returned as though solved — the failure mode
    # this project would otherwise only notice as an implausible IV downstream.
    if market_price > _price_at(hi):
        return _fallback(
            f"price {market_price} exceeds the {hi:.0%}-vol value "
            f"{_price_at(hi):.2f}; outside the solver's bracket"
        )

    for _ in range(max_iterations):
        mid = (lo + hi) / 2.0
        price = _price_at(mid)

        if abs(price - market_price) < tolerance:
            return round(mid, 4)
        if price < market_price:
            lo = mid
        else:
            hi = mid

    # Bisection halves the bracket each pass, so 100 iterations over [0.01, 5]
    # is far more than enough; exhausting them means something is wrong with
    # the inputs rather than the search.
    if strict:
        raise ImpliedVolatilityError(
            f"did not converge in {max_iterations} iterations for "
            f"{option_type.value} {strike} @ {market_price} (spot {spot}, "
            f"{days_to_expiry}d); bracket still [{lo:.4f}, {hi:.4f}]"
        )
    return round((lo + hi) / 2.0, 4)


def estimate_probability_of_profit(
    spot: float,
    breakeven: float,
    days_to_expiry: int,
    implied_vol: float,
    is_above_breakeven_profitable: bool,
) -> float:
    """
    Estimate probability of profit using the lognormal distribution
    implied by Black-Scholes — i.e. probability that spot ends up
    on the profitable side of the breakeven at expiry.

    Returns a percentage (0-100).
    """
    if days_to_expiry <= 0 or implied_vol <= 0:
        return 50.0

    T = days_to_expiry / 365.0
    sqrt_T = math.sqrt(T)

    # Probability that final price > breakeven (risk-neutral, drift-free approx)
    d = (math.log(breakeven / spot)) / (implied_vol * sqrt_T)
    prob_above = 1.0 - _norm_cdf(d)

    prob = prob_above if is_above_breakeven_profitable else (1.0 - prob_above)
    return round(prob * 100, 1)
