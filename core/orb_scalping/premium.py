"""
QuantOS — ORB Options Scalping Premium Reconstruction (candidate 18)
──────────────────────────────────────────────────────────────────────
Turns one core.orb_scalping.signal.IndexTrade (NIFTY or BankNifty INDEX
points) into real entry/exit option premiums, per
docs/ORB_OPTIONS_SCALPING_METHODOLOGY.md's "Premium reconstruction" and
"Secondary hard premium stop" sections. Reuses core/options/greeks.py's
compute_greeks() unchanged — same Black-Scholes reconstruction approach as
candidate 15 (core/breakout1010/premium.py), extended here with a
per-candle premium walk between entry and the index-level exit, because
this candidate (unlike 15) has a SECOND, premium-based stop that the
index-level signal alone cannot see (IV crush / vega decay from a slow
reversal that never actually reaches the index-level stop).

If both the index-level exit and the 25% premium stop would trigger on
the SAME candle, the premium stop takes precedence (checked first in the
loop below) — a disclosed, conservative tie-break, same spirit as
candidate 15's "stop wins over target on the same candle" convention.

Every premium value this module produces is a Black-Scholes THEORETICAL
price, not a real traded price — same disclosed limitation as candidate
15 (docs/CANDIDATE15_OPTION_DATA_FEASIBILITY.md): real historical option
intraday data is confirmed unfetchable from Fyers for any expired
contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from datetime import date, datetime, time, timedelta, timezone

from core.brokers.base import OHLCV
from core.options.greeks import compute_greeks
from core.options.models import OptionType
from core.orb_scalping.signal import IndexTrade

PREMIUM_STOP_PCT = 0.25   # methodology doc: 25% loss of entry premium, OR condition


def _option_type(direction: str) -> OptionType:
    return OptionType.CALL if direction == "CALL" else OptionType.PUT


def _vix_at(vix_day_candles: list[OHLCV], index: int) -> float:
    """The VIX 5m candle CLOSE at the same candle position as the index
    candle series — both series fetched over the identical UTC window, so
    a matching index is the contemporaneous VIX reading. Falls back to the
    last available VIX candle if the two series have drifted out of
    alignment (a missing print on one side), same disclosed approximation
    as candidate 15."""
    if not vix_day_candles:
        raise ValueError("no VIX candles available for this day")
    idx = min(index, len(vix_day_candles) - 1)
    return vix_day_candles[idx].close


def atm_strike(index_level: float, interval: float) -> float:
    """Nearest strike to `index_level` at the given near-the-money
    interval (50 for NIFTY, 100 for BankNifty — both confirmed live 2026-
    07-28/candidate 15). ATM is fixed at entry, never re-struck."""
    return round(index_level / interval) * interval


@dataclass(frozen=True)
class PremiumTrade:
    """core.orb_scalping.signal.IndexTrade, with entry/exit reconstructed
    as real option premiums (points) rather than index levels."""
    direction:         str     # "CALL" or "PUT"
    entry_timestamp:   object  # datetime
    entry_index_level: float
    entry_premium:     float
    exit_timestamp:    object  # datetime
    exit_index_level:  float
    exit_premium:      float
    strike:            float
    expiry:            date
    exit_reason:       str     # signal.py's reasons, or "premium_stop"


# NSE index options expire at the 15:30 IST close.
EXPIRY_CLOSE_UTC = time(10, 0)
CANDLE_MINUTES = 5


def days_to_expiry_close(expiry: date, at: datetime) -> float:
    """Fractional calendar days from `at` to the 15:30 IST close on
    `expiry`. <= 0 at/after the close (compute_greeks then prices
    intrinsic value)."""
    close = datetime.combine(expiry, EXPIRY_CLOSE_UTC, tzinfo=timezone.utc)
    return (close - at).total_seconds() / 86400.0


SESSION_OPEN_UTC = time(3, 45)     # 09:15 IST
_SESSION_HOURS = 6.25
_WEEKNIGHT_HOURS = 17.75
_WEEKEND_HOURS = 65.75             # Fri 15:30 IST -> Mon 09:15 IST


@dataclass(frozen=True)
class TimeWeights:
    """How many calendar-day-equivalents of option time decay each stretch
    of the week carries (2026-09-30, after Fable's review of fix 2). Calendar
    time spreads decay evenly over 24h; the market loads it onto trading
    hours. `calendar()` reproduces days_to_expiry_close() exactly. Fitted
    values come from scripts/calibrate_orb_time_convention.py and are frozen
    in its committed results doc."""
    session: float      # one full 09:15-15:30 IST session
    weeknight: float    # 15:30 IST -> next weekday's 09:15 IST
    weekend: float      # Fri 15:30 IST -> Mon 09:15 IST (a longer gap scales pro rata)

    @staticmethod
    def calendar() -> "TimeWeights":
        return TimeWeights(_SESSION_HOURS / 24, _WEEKNIGHT_HOURS / 24, _WEEKEND_HOURS / 24)

    @staticmethod
    def trading_252() -> "TimeWeights":
        """Standard trading-day convention: 365/252 calendar-day-equivalents
        per session, nothing overnight or over weekends."""
        return TimeWeights(365 / 252, 0.0, 0.0)


def _next_session_open(t: datetime) -> datetime:
    d = t.date()
    while True:
        start = datetime.combine(d, SESSION_OPEN_UTC, tzinfo=timezone.utc)
        if d.weekday() < 5 and start > t:
            return start
        d += timedelta(days=1)


def _prev_session_close(t: datetime) -> datetime:
    d = t.date()
    while True:
        end = datetime.combine(d, EXPIRY_CLOSE_UTC, tzinfo=timezone.utc)
        if d.weekday() < 5 and end <= t:
            return end
        d -= timedelta(days=1)


def effective_days_to_expiry(expiry: date, at: datetime, w: TimeWeights) -> float:
    """Calendar-day-equivalents of decay left from `at` to the 15:30 IST close
    on `expiry`, weighting each stretch by `w`. Weekdays are sessions (NSE
    holidays are not known here; a gap over one scales the weekend weight pro
    rata by its length). <= 0 at/after the close."""
    end = datetime.combine(expiry, EXPIRY_CLOSE_UTC, tzinfo=timezone.utc)
    if at >= end:
        return (end - at).total_seconds() / 86400.0
    total, t = 0.0, at
    while t < end:
        s_open = datetime.combine(t.date(), SESSION_OPEN_UTC, tzinfo=timezone.utc)
        s_close = datetime.combine(t.date(), EXPIRY_CLOSE_UTC, tzinfo=timezone.utc)
        if t.weekday() < 5 and s_open <= t < s_close:
            seg_end = min(end, s_close)
            total += w.session * (seg_end - t).total_seconds() / 3600 / _SESSION_HOURS
        else:
            gap_start, gap_end = _prev_session_close(t), _next_session_open(t)
            gap_hours = (gap_end - gap_start).total_seconds() / 3600
            weight = (w.weeknight if abs(gap_hours - _WEEKNIGHT_HOURS) < 1e-6
                      else w.weekend * gap_hours / _WEEKEND_HOURS)
            seg_end = min(end, gap_end)
            total += weight * (seg_end - t).total_seconds() / 3600 / gap_hours
        t = seg_end
    return total


def reconstruct_premium(
    index_trade: IndexTrade,
    day_candles: list[OHLCV],
    vix_day_candles: list[OHLCV],
    expiry: date,
    strike_interval: float,
    intraday_dte: bool = False,
    time_weights: Optional[TimeWeights] = None,
    vol_scale: float = 1.0,
) -> PremiumTrade:
    """Reconstruct entry/exit premiums for one IndexTrade, walking every
    candle from entry to the index-determined exit to check the 25%
    secondary premium stop — whichever of the two stops (index-level,
    already applied by signal.py; or this premium-based one) triggers
    FIRST in time wins. `expiry` is the already-resolved contract for this
    trading day (including any DTE-floor roll — see
    core/orb_scalping/expiry.py) — this function does no expiry-date logic
    of its own.

    `intraday_dte` (default False, unchanged behaviour): price with the
    actual fraction of time left to the expiry close instead of
    `max(1, whole days)`. The clamp prices a 0-DTE option as if a full day
    remained all session, so it never decays toward intrinsic -- the case
    behind 2026-09-29's BANKNIFTY put (220.35 -> 2.95 on its expiry day).
    Added 2026-09-30 for the fix-2 comparison; the locked-final results
    were produced with False.

    `time_weights` (default None): price with effective_days_to_expiry()
    under these weights instead -- overrides `intraday_dte`. See TimeWeights.
    `vol_scale` (default 1.0): implied vol = vol_scale x India VIX, the per-index
    level calibrated alongside the weights (BANKNIFTY trades above VIX)."""
    if time_weights is not None:
        def dte_at(ts: datetime) -> float:
            return effective_days_to_expiry(expiry, ts, time_weights)
    elif intraday_dte:
        def dte_at(ts: datetime) -> float:
            return days_to_expiry_close(expiry, ts)
    else:
        dte_at = None
    option_type = _option_type(index_trade.direction)
    strike = atm_strike(index_trade.entry_price, strike_interval)

    entry_dt = day_candles[index_trade.entry_index].timestamp
    entry_vix = _vix_at(vix_day_candles, index_trade.entry_index)
    entry_dte = dte_at(entry_dt) if dte_at else max(1, (expiry - entry_dt.date()).days)
    entry_premium = compute_greeks(
        spot=index_trade.entry_price, strike=strike, days_to_expiry=entry_dte,
        implied_vol=vol_scale * entry_vix / 100.0, option_type=option_type,
    ).theoretical_price
    premium_stop_level = entry_premium * (1 - PREMIUM_STOP_PCT)

    last_timestamp, last_spot, last_premium = entry_dt, index_trade.entry_price, entry_premium

    for i in range(index_trade.entry_index + 1, index_trade.exit_index + 1):
        candle = day_candles[i]
        # The final candle uses the exact index-level exit price signal.py
        # already determined (a stop/trailing-stop LEVEL, not necessarily
        # this candle's close); every earlier candle uses its own close —
        # same close-only discipline as the entry/breakout signal.
        spot = index_trade.exit_price if i == index_trade.exit_index else candle.close
        vix = _vix_at(vix_day_candles, i)
        # The candle's CLOSE is what's priced (see below), at the candle's end.
        dte = (dte_at(candle.timestamp + timedelta(minutes=CANDLE_MINUTES)) if dte_at
               else max(1, (expiry - candle.timestamp.date()).days))
        premium = compute_greeks(
            spot=spot, strike=strike, days_to_expiry=dte,
            implied_vol=vol_scale * vix / 100.0, option_type=option_type,
        ).theoretical_price

        last_timestamp, last_spot, last_premium = candle.timestamp, spot, premium

        if premium <= premium_stop_level:
            return PremiumTrade(
                direction=index_trade.direction,
                entry_timestamp=entry_dt, entry_index_level=index_trade.entry_price,
                entry_premium=entry_premium,
                exit_timestamp=candle.timestamp, exit_index_level=spot,
                exit_premium=premium_stop_level,
                strike=strike, expiry=expiry, exit_reason="premium_stop",
            )

    # Secondary stop never triggered before the index-level exit — use it
    # as-is. `last_*` already holds exactly this exit's own values from the
    # loop's final iteration (index_trade.exit_index), no recompute needed.
    return PremiumTrade(
        direction=index_trade.direction,
        entry_timestamp=entry_dt, entry_index_level=index_trade.entry_price,
        entry_premium=entry_premium,
        exit_timestamp=last_timestamp, exit_index_level=last_spot,
        exit_premium=last_premium,
        strike=strike, expiry=expiry, exit_reason=index_trade.exit_reason,
    )
