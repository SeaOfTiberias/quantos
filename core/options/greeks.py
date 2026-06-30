"""
QuantOS — Black-Scholes Greeks Calculator
─────────────────────────────────────────────
US-05b: Computes option Greeks (delta, gamma, theta, vega) using the
Black-Scholes model. Used as a fallback when the broker doesn't supply
live Greeks directly (Fyers option chain does include some Greeks,
but this provides a consistent, broker-independent calculation).

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
