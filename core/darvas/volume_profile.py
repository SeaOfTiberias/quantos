"""
QuantOS — Volume Profile (VPVR) Engine
──────────────────────────────────────────
US-12: Computes a Volume Profile from OHLCV candle data and identifies
High Volume Nodes (HVNs) and Low Volume Nodes (LVNs).

A Darvas breakout above an HVN is a significantly stronger signal than
one that breaks through thin air — it means the market has transacted
heavily at that price level, giving it genuine support/resistance meaning.

Volume Profile approach:
  1. Divide the price range into N equally-spaced bins (default 24)
  2. Distribute each candle's volume across the bins it spans
  3. HVN = bins with volume > 1.5× average bin volume
  4. LVN = bins with volume < 0.5× average bin volume
  5. Point of Control (POC) = bin with highest total volume

This is a simplified VPVR (Volume Profile Visible Range) —
suitable for NSE daily/weekly data without tick-level precision.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from core.brokers.base import OHLCV

logger = logging.getLogger(__name__)

# ─── Config ──────────────────────────────────────────────────────────────────

DEFAULT_BINS        = 24     # price range split into this many buckets
HVN_THRESHOLD       = 1.5   # bins with volume > threshold × avg are HVNs
LVN_THRESHOLD       = 0.5   # bins with volume < threshold × avg are LVNs
PROXIMITY_PCT       = 0.015  # breakout must be within 1.5% of an HVN to qualify


# ─── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class VolumeBin:
    """A single price bucket in the volume profile."""
    price_low:  float
    price_high: float
    volume:     float
    is_hvn:     bool = False
    is_lvn:     bool = False

    @property
    def price_mid(self) -> float:
        return (self.price_low + self.price_high) / 2


@dataclass
class VolumeProfile:
    """Full volume profile for a symbol over the lookback period."""
    symbol:           str
    bins:             list[VolumeBin]
    poc_price:        float     # Point of Control — price with most volume
    poc_volume:       float
    total_volume:     float
    avg_bin_volume:   float
    price_low:        float
    price_high:       float
    lookback_candles: int

    def hvns(self) -> list[VolumeBin]:
        """All High Volume Nodes, sorted by price ascending."""
        return sorted([b for b in self.bins if b.is_hvn], key=lambda b: b.price_mid)

    def lvns(self) -> list[VolumeBin]:
        """All Low Volume Nodes."""
        return sorted([b for b in self.bins if b.is_lvn], key=lambda b: b.price_mid)

    def nearest_hvn_above(self, price: float) -> Optional[VolumeBin]:
        """Find the nearest HVN above a given price — breakout target/resistance."""
        hvns_above = [b for b in self.hvns() if b.price_mid > price]
        return hvns_above[0] if hvns_above else None

    def nearest_hvn_below(self, price: float) -> Optional[VolumeBin]:
        """Find the nearest HVN below a given price — support level."""
        hvns_below = [b for b in self.hvns() if b.price_mid < price]
        return hvns_below[-1] if hvns_below else None

    def is_near_hvn(self, price: float, proximity_pct: float = PROXIMITY_PCT) -> bool:
        """True if price is within proximity_pct of any HVN."""
        for hvn in self.hvns():
            if abs(price - hvn.price_mid) / hvn.price_mid <= proximity_pct:
                return True
        return False

    def is_clearing_hvn(self, breakout_price: float, proximity_pct: float = PROXIMITY_PCT) -> bool:
        """
        True if a breakout price is just above an HVN — meaning it has
        cleared a significant volume level. This is the key Darvas fusion check.
        """
        for hvn in self.hvns():
            if (hvn.price_mid <= breakout_price
                    and (breakout_price - hvn.price_mid) / hvn.price_mid <= proximity_pct):
                return True
        return False


@dataclass
class DarvasFusionResult:
    """Result of checking a Darvas breakout against the Volume Profile."""
    symbol:              str
    breakout_price:      float
    has_hvn_clearance:   bool        # Did the breakout clear an HVN?
    nearest_hvn_below:   Optional[VolumeBin]
    nearest_hvn_above:   Optional[VolumeBin]
    poc_price:           float
    fusion_score:        float       # Combined Darvas + VP score (0-100)
    notes:               list[str] = field(default_factory=list)


# ─── Core computation ─────────────────────────────────────────────────────────

def compute_volume_profile(
    candles: list[OHLCV],
    symbol: str,
    n_bins: int = DEFAULT_BINS,
) -> VolumeProfile:
    """
    Compute volume profile from OHLCV candle data.

    Args:
        candles: list of OHLCV (daily recommended for meaningful VP)
        symbol: symbol name for labelling
        n_bins: number of price bins to split the range into

    Returns:
        VolumeProfile with HVN/LVN classification
    """
    if not candles:
        raise ValueError("Cannot compute volume profile from empty candle list")

    price_low  = min(c.low for c in candles)
    price_high = max(c.high for c in candles)

    if price_high == price_low:
        price_high = price_low * 1.001  # avoid zero-width range

    bin_size = (price_high - price_low) / n_bins
    bins = [
        VolumeBin(
            price_low=price_low + i * bin_size,
            price_high=price_low + (i + 1) * bin_size,
            volume=0.0,
        )
        for i in range(n_bins)
    ]

    # Distribute each candle's volume proportionally across the bins it spans
    for candle in candles:
        candle_range = candle.high - candle.low
        if candle_range <= 0:
            continue
        for bin_ in bins:
            overlap_low  = max(candle.low, bin_.price_low)
            overlap_high = min(candle.high, bin_.price_high)
            if overlap_high > overlap_low:
                overlap_pct = (overlap_high - overlap_low) / candle_range
                bin_.volume += candle.volume * overlap_pct

    total_volume   = sum(b.volume for b in bins)
    avg_bin_volume = total_volume / n_bins if n_bins > 0 else 0

    # Classify HVN / LVN
    for bin_ in bins:
        if avg_bin_volume > 0:
            bin_.is_hvn = bin_.volume >= HVN_THRESHOLD * avg_bin_volume
            bin_.is_lvn = bin_.volume <= LVN_THRESHOLD * avg_bin_volume

    # Point of Control
    poc_bin    = max(bins, key=lambda b: b.volume)
    poc_price  = poc_bin.price_mid
    poc_volume = poc_bin.volume

    return VolumeProfile(
        symbol=symbol,
        bins=bins,
        poc_price=poc_price,
        poc_volume=poc_volume,
        total_volume=total_volume,
        avg_bin_volume=avg_bin_volume,
        price_low=price_low,
        price_high=price_high,
        lookback_candles=len(candles),
    )


def check_darvas_fusion(
    symbol: str,
    breakout_price: float,
    darvas_score: float,
    volume_profile: VolumeProfile,
    proximity_pct: float = PROXIMITY_PCT,
) -> DarvasFusionResult:
    """
    Check if a Darvas breakout clears a High Volume Node.

    The fusion score boosts the Darvas signal when HVN clearance is confirmed,
    and penalises when breaking through an LVN (weak, thin air breakout).

    Args:
        symbol: symbol being checked
        breakout_price: close price of the breakout candle
        darvas_score: confluence score from the MTF Darvas scanner (0-100)
        volume_profile: pre-computed volume profile
        proximity_pct: how close to an HVN counts as "clearing" it

    Returns:
        DarvasFusionResult with combined fusion_score
    """
    notes = []
    hvn_below = volume_profile.nearest_hvn_below(breakout_price)
    hvn_above = volume_profile.nearest_hvn_above(breakout_price)
    has_hvn_clearance = volume_profile.is_clearing_hvn(breakout_price, proximity_pct)

    # Base fusion score = Darvas score
    fusion_score = darvas_score

    if has_hvn_clearance and hvn_below:
        bonus = 15.0
        fusion_score = min(100.0, fusion_score + bonus)
        notes.append(
            f"✅ HVN clearance confirmed — breakout ₹{breakout_price:,.2f} "
            f"cleared HVN at ₹{hvn_below.price_mid:,.2f} (+{bonus:.0f} pts)"
        )
    elif hvn_below and (breakout_price - hvn_below.price_mid) / hvn_below.price_mid > proximity_pct * 2:
        # Breaking well above the nearest HVN below — stretched, extended
        penalty = 10.0
        fusion_score = max(0.0, fusion_score - penalty)
        notes.append(
            f"⚠️  Extended above nearest HVN (₹{hvn_below.price_mid:,.2f}) "
            f"— potential exhaustion (-{penalty:.0f} pts)"
        )
    else:
        notes.append(
            f"ℹ️  No HVN clearance — nearest HVN below: "
            f"{'₹' + f'{hvn_below.price_mid:,.2f}' if hvn_below else 'none'}"
        )

    if hvn_above:
        notes.append(
            f"🔴 Resistance HVN above at ₹{hvn_above.price_mid:,.2f} "
            f"— consider as target/exit zone"
        )

    notes.append(f"POC: ₹{volume_profile.poc_price:,.2f}")

    return DarvasFusionResult(
        symbol=symbol,
        breakout_price=breakout_price,
        has_hvn_clearance=has_hvn_clearance,
        nearest_hvn_below=hvn_below,
        nearest_hvn_above=hvn_above,
        poc_price=volume_profile.poc_price,
        fusion_score=round(fusion_score, 1),
        notes=notes,
    )
