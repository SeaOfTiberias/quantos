"""
QuantOS — Regime Classification Engine
────────────────────────────────────────
Scores market inputs and classifies into one of 5 regimes.

Scoring approach:
  Each input dimension scores independently, then combined:
  - Trend score:   -100 (strong bear) to +100 (strong bull)
  - VIX score:     0 (calm) to 100 (extreme fear)
  - Breadth score: -100 (all declining) to +100 (all advancing)

  Final regime determined by weighted combination + threshold logic.
"""

import logging
from datetime import datetime, timezone

from core.regime.models import (
    Regime, RegimeResult, RegimeInputs,
    NiftyData, VIXData, BreadthData,
    STRATEGY_GATE, SIZE_MULTIPLIER,
)

logger = logging.getLogger(__name__)


# ─── VIX thresholds (India VIX) ──────────────────────────────────────────────
VIX_LOW       = 13.0   # calm market
VIX_ELEVATED  = 17.0   # mild concern
VIX_HIGH      = 22.0   # fear
VIX_EXTREME   = 28.0   # crisis / extreme fear


def classify(inputs: RegimeInputs) -> RegimeResult:
    """
    Classify market regime from RegimeInputs.

    Returns a RegimeResult with regime, confidence,
    allowed strategies, and size multiplier.
    """
    trend_score   = _score_trend(inputs.nifty)
    vix_score     = _score_vix(inputs.vix)
    breadth_score = _score_breadth(inputs.breadth)

    trend_signal   = _trend_signal_label(trend_score)
    vix_signal     = _vix_signal_label(inputs.vix.current)
    breadth_signal = _breadth_signal_label(breadth_score)

    notes = []

    # ── Rule 1: Extreme VIX → VOLATILE regardless of trend ───────────────────
    if inputs.vix.current >= VIX_EXTREME:
        notes.append(f"VIX EXTREME ({inputs.vix.current:.1f}) — overrides trend")
        return _build_result(
            Regime.VOLATILE, confidence=90,
            trend_signal=trend_signal,
            vix_signal=vix_signal,
            breadth_signal=breadth_signal,
            notes=notes,
            inputs=inputs,
        )

    # ── Rule 2: High VIX + weak breadth → VOLATILE ───────────────────────────
    if inputs.vix.current >= VIX_HIGH and breadth_score < -30:
        notes.append(
            f"High VIX ({inputs.vix.current:.1f}) + weak breadth "
            f"(A/D={inputs.breadth.ad_ratio:.1f}) → VOLATILE"
        )
        return _build_result(
            Regime.VOLATILE, confidence=75,
            trend_signal=trend_signal,
            vix_signal=vix_signal,
            breadth_signal=breadth_signal,
            notes=notes,
            inputs=inputs,
        )

    # ── Rule 3: Strong trend + low VIX + good breadth → TRENDING ─────────────
    if trend_score >= 40 and inputs.vix.current < VIX_ELEVATED and breadth_score >= 20:
        confidence = min(95, 60 + (trend_score - 40) * 0.5 + breadth_score * 0.3)
        notes.append(
            f"Trend={trend_score:.0f}, VIX={inputs.vix.current:.1f}, "
            f"A/D={inputs.breadth.ad_ratio:.1f} → TRENDING BULL"
        )
        return _build_result(
            Regime.TRENDING_BULL, confidence=confidence,
            trend_signal=trend_signal,
            vix_signal=vix_signal,
            breadth_signal=breadth_signal,
            notes=notes,
            inputs=inputs,
        )

    # ── Rule 4: Strong bear trend ─────────────────────────────────────────────
    if trend_score <= -40 and breadth_score <= -20:
        confidence = min(90, 60 + abs(trend_score - 40) * 0.4)
        notes.append(
            f"Bear trend={trend_score:.0f}, "
            f"breadth={breadth_score:.0f} → TRENDING BEAR"
        )
        return _build_result(
            Regime.TRENDING_BEAR, confidence=confidence,
            trend_signal=trend_signal,
            vix_signal=vix_signal,
            breadth_signal=breadth_signal,
            notes=notes,
            inputs=inputs,
        )

    # ── Rule 5: Low VIX + flat trend → RANGING ───────────────────────────────
    if (abs(trend_score) < 30
            and inputs.vix.current < VIX_HIGH
            and inputs.vix.trend in ("FLAT", "FALLING")):
        notes.append(
            f"Flat trend ({trend_score:.0f}), VIX={inputs.vix.current:.1f} "
            f"({inputs.vix.trend}) → RANGING"
        )
        return _build_result(
            Regime.RANGING, confidence=65,
            trend_signal=trend_signal,
            vix_signal=vix_signal,
            breadth_signal=breadth_signal,
            notes=notes,
            inputs=inputs,
        )

    # ── Rule 6: Mixed signals → UNCERTAIN ────────────────────────────────────
    notes.append(
        f"Mixed signals: trend={trend_score:.0f}, "
        f"vix={inputs.vix.current:.1f}, breadth={breadth_score:.0f}"
    )
    return _build_result(
        Regime.UNCERTAIN, confidence=40,
        trend_signal=trend_signal,
        vix_signal=vix_signal,
        breadth_signal=breadth_signal,
        notes=notes,
        inputs=inputs,
    )


# ─── Individual scorers ───────────────────────────────────────────────────────

def _score_trend(nifty: NiftyData) -> float:
    """
    Score Nifty trend: -100 (strong bear) to +100 (strong bull).
    Uses EMA alignment + price slope.
    """
    score = 0.0

    # EMA alignment (golden/death cross logic)
    if nifty.ema_20 > nifty.ema_50 > nifty.ema_200:
        score += 40    # full bull alignment
    elif nifty.ema_20 > nifty.ema_50:
        score += 20    # short-term bullish
    elif nifty.ema_20 < nifty.ema_50 < nifty.ema_200:
        score -= 40    # full bear alignment
    elif nifty.ema_20 < nifty.ema_50:
        score -= 20    # short-term bearish

    # Price vs EMAs
    if nifty.ltp > nifty.ema_200:
        score += 20
    else:
        score -= 20

    if nifty.ltp > nifty.ema_50:
        score += 10
    else:
        score -= 10

    # 5-day slope
    if nifty.slope_5d > 2.0:
        score += 20
    elif nifty.slope_5d > 0.5:
        score += 10
    elif nifty.slope_5d < -2.0:
        score -= 20
    elif nifty.slope_5d < -0.5:
        score -= 10

    return max(-100.0, min(100.0, score))


def _score_vix(vix: VIXData) -> float:
    """Score VIX fear: 0 (calm) to 100 (extreme fear)."""
    if vix.current < VIX_LOW:
        return 0
    elif vix.current < VIX_ELEVATED:
        return 20
    elif vix.current < VIX_HIGH:
        return 50
    elif vix.current < VIX_EXTREME:
        return 75
    else:
        return 100


def _score_breadth(breadth: BreadthData) -> float:
    """Score breadth: -100 (all declining) to +100 (all advancing)."""
    pct = breadth.breadth_pct  # % advancing
    if pct >= 70:
        return 100
    elif pct >= 60:
        return 60
    elif pct >= 50:
        return 20
    elif pct >= 40:
        return -20
    elif pct >= 30:
        return -60
    else:
        return -100


# ─── Label helpers ────────────────────────────────────────────────────────────

def _trend_signal_label(score: float) -> str:
    if score >= 40:
        return "BULL"
    elif score <= -40:
        return "BEAR"
    return "NEUTRAL"


def _vix_signal_label(vix: float) -> str:
    if vix < VIX_LOW:
        return "LOW"
    elif vix < VIX_ELEVATED:
        return "MODERATE"
    elif vix < VIX_HIGH:
        return "ELEVATED"
    elif vix < VIX_EXTREME:
        return "HIGH"
    return "EXTREME"


def _breadth_signal_label(score: float) -> str:
    if score >= 60:
        return "STRONG"
    elif score >= 0:
        return "NEUTRAL"
    return "WEAK"


def _build_result(
    regime: Regime,
    confidence: float,
    trend_signal: str,
    vix_signal: str,
    breadth_signal: str,
    notes: list[str],
    inputs: RegimeInputs,
) -> RegimeResult:
    return RegimeResult(
        regime=regime,
        confidence=round(confidence, 1),
        allowed_strategies=STRATEGY_GATE[regime],
        size_multiplier=SIZE_MULTIPLIER[regime],
        timestamp=inputs.timestamp,
        trend_signal=trend_signal,
        vix_signal=vix_signal,
        breadth_signal=breadth_signal,
        notes=notes,
        advance_count=inputs.breadth.advance_count,
        decline_count=inputs.breadth.decline_count,
        unchanged_count=inputs.breadth.unchanged_count,
    )
