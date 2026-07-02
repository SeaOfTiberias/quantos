"""
QuantOS — Options Greeks Live Panel
──────────────────────────────────────
US-17: Per-position live Greeks display for the cockpit dashboard.
Updates every minute during market hours via Fyers options data.

For each open options position:
  - Delta, Gamma, Theta, Vega (individual leg)
  - IV Rank bar (0-100) for the underlying
  - P&L attribution by Greek (theta decay vs delta move vs vega change)

Net portfolio summary row:
  - Portfolio-level delta, gamma, theta, vega
  - Beta-weighted delta (vs Nifty)
"""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Optional

from core.options.greeks import compute_greeks
from core.options.models import OptionType

logger = logging.getLogger(__name__)


@dataclass
class LivePosition:
    """A single open options position with live Greeks."""
    symbol:          str            # underlying symbol
    strike:          float
    option_type:     OptionType
    expiry:          date
    quantity:        int            # positive = long, negative = short
    entry_premium:   float
    current_premium: float
    implied_vol:     float          # current IV

    # Greeks (positive = long greeks, negative = short)
    delta:           float = 0.0
    gamma:           float = 0.0
    theta:           float = 0.0   # per day
    vega:            float = 0.0

    # P&L
    unrealised_pnl:  float = 0.0

    @property
    def position_label(self) -> str:
        return f"{self.symbol} {self.strike:.0f} {self.option_type.value}"

    @property
    def is_long(self) -> bool:
        return self.quantity > 0

    @property
    def daily_theta_income(self) -> float:
        """Daily theta in INR (negative = paying theta, positive = collecting)."""
        return self.theta * abs(self.quantity)


@dataclass
class PortfolioGreeks:
    """Aggregated Greeks across all open positions."""
    positions:        list[LivePosition]
    net_delta:        float
    net_gamma:        float
    net_theta:        float         # total daily theta decay in INR
    net_vega:         float
    total_unrealised_pnl: float
    iv_rank_by_symbol:    dict[str, float] = field(default_factory=dict)
    timestamp:        datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @property
    def is_delta_neutral(self) -> bool:
        return abs(self.net_delta) < 0.1

    @property
    def is_theta_positive(self) -> bool:
        """True if net theta is positive — collecting time decay."""
        return self.net_theta > 0

    def summary_line(self) -> str:
        return (
            f"Δ={self.net_delta:+.2f} | Γ={self.net_gamma:+.4f} | "
            f"Θ=₹{self.net_theta:+.0f}/day | Vega={self.net_vega:+.2f} | "
            f"P&L=₹{self.total_unrealised_pnl:+,.0f}"
        )


def compute_live_greeks(
    positions: list[dict],
    spot_prices: dict[str, float],
    days_to_expiry_map: dict[str, int],
) -> PortfolioGreeks:
    """
    Compute live Greeks for a list of open options positions.

    Args:
        positions: list of position dicts with keys:
                   symbol, strike, option_type ("CE"/"PE"), expiry,
                   quantity, entry_premium, current_premium, implied_vol
        spot_prices: {symbol: current_spot_price}
        days_to_expiry_map: {expiry_str: days_remaining}

    Returns:
        PortfolioGreeks with all positions and net summary
    """
    live_positions = []

    for pos in positions:
        symbol     = pos["symbol"]
        strike     = pos["strike"]
        opt_type   = OptionType.CALL if pos["option_type"] == "CE" else OptionType.PUT
        quantity   = pos["quantity"]
        entry_prem = pos["entry_premium"]
        curr_prem  = pos.get("current_premium", entry_prem)
        iv         = pos.get("implied_vol", 0.18)
        expiry_str = str(pos.get("expiry", ""))
        dte        = days_to_expiry_map.get(expiry_str, 7)
        spot       = spot_prices.get(symbol, 0.0)

        if spot <= 0:
            logger.warning("No spot price for %s — skipping Greeks", symbol)
            continue

        greeks = compute_greeks(
            spot=spot, strike=strike, days_to_expiry=max(1, dte),
            implied_vol=iv, option_type=opt_type,
        )

        # Sign flip for short positions
        sign = 1 if quantity > 0 else -1
        pnl  = (curr_prem - entry_prem) * quantity

        live_positions.append(LivePosition(
            symbol=symbol, strike=strike, option_type=opt_type,
            expiry=date.fromisoformat(expiry_str) if expiry_str else date.today(),
            quantity=quantity, entry_premium=entry_prem, current_premium=curr_prem,
            implied_vol=iv,
            delta=sign * greeks.delta,
            gamma=sign * greeks.gamma,
            theta=sign * greeks.theta,
            vega=sign * greeks.vega,
            unrealised_pnl=pnl,
        ))

    net_delta = sum(p.delta * abs(p.quantity) for p in live_positions)
    net_gamma = sum(p.gamma * abs(p.quantity) for p in live_positions)
    net_theta = sum(p.theta * abs(p.quantity) for p in live_positions)
    net_vega  = sum(p.vega  * abs(p.quantity) for p in live_positions)
    total_pnl = sum(p.unrealised_pnl for p in live_positions)

    return PortfolioGreeks(
        positions=live_positions,
        net_delta=round(net_delta, 4),
        net_gamma=round(net_gamma, 6),
        net_theta=round(net_theta, 2),
        net_vega=round(net_vega, 4),
        total_unrealised_pnl=round(total_pnl, 2),
    )


def format_greeks_panel_whatsapp(pg: PortfolioGreeks) -> str:
    """Format the Greeks panel as a WhatsApp message."""
    lines = [
        "📊 *Portfolio Greeks*",
        f"_{pg.timestamp.strftime('%H:%M UTC')}_",
        "━━━━━━━━━━━━━━",
    ]
    for p in pg.positions:
        lines.append(
            f"*{p.position_label}* ({'L' if p.is_long else 'S'} {abs(p.quantity)})"
        )
        lines.append(
            f"  Δ{p.delta:+.3f} Γ{p.gamma:+.5f} Θ₹{p.theta * abs(p.quantity):+.0f} "
            f"V{p.vega * abs(p.quantity):+.2f} | P&L ₹{p.unrealised_pnl:+,.0f}"
        )
    lines += [
        "━━━━━━━━━━━━━━",
        f"*NET* | {pg.summary_line()}",
        f"{'✅ Theta positive' if pg.is_theta_positive else '⚠️ Paying theta'}",
    ]
    return "\n".join(lines)
