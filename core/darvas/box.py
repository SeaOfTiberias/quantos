"""
QuantOS — Darvas Box Detection Engine
──────────────────────────────────────
US-02: Multi-Timeframe Darvas Box Scanner

A Darvas Box forms when:
1. Price makes a new N-period high (box top)
2. Price consolidates for MIN_CONSOLIDATION candles
   without exceeding that high (box forms)
3. Box bottom = lowest low during consolidation period
4. Breakout = close above box top on above-average volume

References: Nicolas Darvas, "How I Made $2,000,000 in the Stock Market"
Adapted for NSE intraday + swing timeframes.
"""

from dataclasses import dataclass, field
from typing import Optional

from core.brokers.base import OHLCV


# ─── Config ──────────────────────────────────────────────────────────────────

LOOKBACK_PERIOD      = 20    # candles to look back for high
MIN_CONSOLIDATION    = 3     # min candles price must hold below top
VOLUME_MULTIPLIER    = 1.3   # breakout volume must be 1.3× avg volume
BOX_MAX_WIDTH_PCT    = 0.08  # box height must be ≤ 8% of price (avoid wide, sloppy boxes)


# ─── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class DarvasBox:
    """A confirmed Darvas Box."""
    top:          float
    bottom:       float
    formed_at:    int          # candle index where box was confirmed
    candles_held: int          # how many candles price held inside box
    width_pct:    float        # (top - bottom) / bottom * 100

    @property
    def midpoint(self) -> float:
        return (self.top + self.bottom) / 2

    @property
    def is_tight(self) -> bool:
        """Tight boxes (< 4%) are higher quality setups."""
        return self.width_pct < 4.0


@dataclass
class DarvasSignal:
    """A breakout signal from a single timeframe."""
    timeframe:        str
    symbol:           str
    breakout_price:   float        # close that broke above box top
    box_top:          float
    box_bottom:       float
    box_width_pct:    float
    volume_ratio:     float        # breakout volume / avg volume
    candle_index:     int          # index in the OHLCV list
    box:              DarvasBox
    quality_score:    float = 0.0  # 0–100, computed after creation

    @property
    def is_valid_breakout(self) -> bool:
        return (
            self.breakout_price > self.box_top
            and self.volume_ratio >= VOLUME_MULTIPLIER
        )


@dataclass
class MultiTimeframeResult:
    """Combined result from scanning all timeframes."""
    symbol:              str
    confluence_score:    float         # 0–100
    signals:             list[DarvasSignal] = field(default_factory=list)
    timeframes_triggered: list[str]    = field(default_factory=list)
    primary_signal:      Optional[DarvasSignal] = None   # highest TF signal
    notes:               list[str]     = field(default_factory=list)

    @property
    def should_fire(self) -> bool:
        return self.confluence_score >= 70


# ─── Core Detection ───────────────────────────────────────────────────────────

def detect_darvas_boxes(candles: list[OHLCV], symbol: str, timeframe: str) -> list[DarvasBox]:
    """
    Scan a list of OHLCV candles and return all confirmed Darvas Boxes.

    A box is confirmed when:
    1. A new N-period high is set (box top)
    2. Price holds below that high for MIN_CONSOLIDATION candles
    3. Box bottom = lowest low during consolidation
    4. Box width is within BOX_MAX_WIDTH_PCT
    """
    if len(candles) < LOOKBACK_PERIOD + MIN_CONSOLIDATION:
        return []

    boxes = []
    i = LOOKBACK_PERIOD

    while i < len(candles):
        # Step 1: identify potential box top — highest high in lookback window
        window = candles[i - LOOKBACK_PERIOD:i]
        box_top = max(c.high for c in window)
        top_idx = max(range(len(window)), key=lambda j: window[j].high)
        abs_top_idx = i - LOOKBACK_PERIOD + top_idx

        # Step 2: check consolidation — price holds below top for MIN_CONSOLIDATION candles
        consol_candles = []
        j = abs_top_idx + 1
        while j < len(candles) and candles[j].high <= box_top * 1.002:  # 0.2% tolerance
            consol_candles.append(candles[j])
            j += 1

        if len(consol_candles) < MIN_CONSOLIDATION:
            i += 1
            continue

        # Step 3: box bottom = lowest low in consolidation
        box_bottom = min(c.low for c in consol_candles)

        # Step 4: quality filter — box must not be too wide
        width_pct = (box_top - box_bottom) / box_bottom * 100
        if width_pct > BOX_MAX_WIDTH_PCT * 100:
            i = j
            continue

        box = DarvasBox(
            top=box_top,
            bottom=box_bottom,
            formed_at=j - 1,
            candles_held=len(consol_candles),
            width_pct=width_pct,
        )
        boxes.append(box)
        i = j  # advance past this box

    return boxes


def detect_breakout(
    candles: list[OHLCV],
    symbol: str,
    timeframe: str,
) -> Optional[DarvasSignal]:
    """
    Check if the most recent candle is breaking out of a Darvas Box.

    Returns a DarvasSignal if a valid breakout is detected, else None.
    """
    if len(candles) < LOOKBACK_PERIOD + MIN_CONSOLIDATION + 2:
        return None

    boxes = detect_darvas_boxes(candles[:-1], symbol, timeframe)  # exclude current candle
    if not boxes:
        return None

    latest_box = boxes[-1]
    current    = candles[-1]

    # Breakout condition: current close > box top
    if current.close <= latest_box.top:
        return None

    # Volume confirmation
    avg_volume = _average_volume(candles, lookback=20)
    volume_ratio = current.volume / avg_volume if avg_volume > 0 else 0

    signal = DarvasSignal(
        timeframe=timeframe,
        symbol=symbol,
        breakout_price=current.close,
        box_top=latest_box.top,
        box_bottom=latest_box.bottom,
        box_width_pct=latest_box.width_pct,
        volume_ratio=volume_ratio,
        candle_index=len(candles) - 1,
        box=latest_box,
    )

    signal.quality_score = _score_signal(signal)
    return signal if signal.is_valid_breakout else None


# ─── Multi-Timeframe Confluence ───────────────────────────────────────────────

def score_confluence(signals: list[DarvasSignal]) -> MultiTimeframeResult:
    """
    Score multi-timeframe confluence from a list of per-TF signals.

    Scoring logic:
    - Daily breakout:  40 pts  (highest weight — trend confirmation)
    - 1H breakout:     35 pts  (intermediate — entry timing)
    - 15m breakout:    25 pts  (short — precise entry)
    - Volume bonus:    up to +10 pts across all TFs
    - Tight box bonus: +5 pts per TF with width < 4%

    Max base score: 100. Bonuses can push quality but score is capped at 100.
    """
    if not signals:
        return MultiTimeframeResult(symbol="", confluence_score=0)

    symbol = signals[0].symbol
    tf_weights = {"1d": 40, "1h": 35, "15m": 25}
    base_score = 0.0
    notes = []
    triggered = []

    for sig in signals:
        weight = tf_weights.get(sig.timeframe, 20)
        base_score += weight
        triggered.append(sig.timeframe)

        # Volume bonus: up to +5 pts per TF
        if sig.volume_ratio >= 2.0:
            base_score += 5
            notes.append(f"{sig.timeframe}: strong volume ({sig.volume_ratio:.1f}× avg)")
        elif sig.volume_ratio >= 1.5:
            base_score += 2.5

        # Tight box bonus
        if sig.box.is_tight:
            base_score += 5
            notes.append(f"{sig.timeframe}: tight box ({sig.box_width_pct:.1f}%)")

    confluence_score = min(100.0, base_score)

    # Primary signal = highest timeframe
    tf_priority = ["1d", "1h", "15m"]
    primary = None
    for tf in tf_priority:
        match = next((s for s in signals if s.timeframe == tf), None)
        if match:
            primary = match
            break

    if len(triggered) >= 2:
        notes.append(f"✅ {len(triggered)}-TF confluence: {' + '.join(triggered)}")
    elif len(triggered) == 1:
        notes.append(f"⚠️  Single TF signal ({triggered[0]}) — lower conviction")

    return MultiTimeframeResult(
        symbol=symbol,
        confluence_score=confluence_score,
        signals=signals,
        timeframes_triggered=triggered,
        primary_signal=primary,
        notes=notes,
    )


# ─── Trailing Stop ────────────────────────────────────────────────────────────

def next_trailing_stop(candles: list[OHLCV], current_stop: float) -> Optional[float]:
    """
    Recompute Darvas boxes on the latest candles and return a tightened
    (higher) stop-loss if a newer box has formed with a bottom above
    `current_stop`. Returns None if no box has formed yet, or the latest
    box's bottom isn't an improvement over the current stop.
    """
    boxes = detect_darvas_boxes(candles, symbol="", timeframe="")
    if not boxes:
        return None

    latest_bottom = boxes[-1].bottom
    return latest_bottom if latest_bottom > current_stop else None


# ─── Utilities ────────────────────────────────────────────────────────────────

def _average_volume(candles: list[OHLCV], lookback: int = 20) -> float:
    recent = candles[-lookback - 1:-1]  # exclude current candle
    if not recent:
        return 0
    return sum(c.volume for c in recent) / len(recent)


def _score_signal(signal: DarvasSignal) -> float:
    """Quality score for a single-TF signal (0–100)."""
    score = 50.0

    # Volume quality
    if signal.volume_ratio >= 2.0:
        score += 20
    elif signal.volume_ratio >= 1.5:
        score += 10
    elif signal.volume_ratio >= 1.3:
        score += 5

    # Box tightness
    if signal.box_width_pct < 2.0:
        score += 20
    elif signal.box_width_pct < 4.0:
        score += 10
    elif signal.box_width_pct < 6.0:
        score += 5

    # Consolidation duration (longer = stronger)
    if signal.box.candles_held >= 10:
        score += 10
    elif signal.box.candles_held >= 5:
        score += 5

    return min(100.0, score)
