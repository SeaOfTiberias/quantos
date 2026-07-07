"""
QuantOS — Weekly Darvas Discovery Scanner
──────────────────────────────────────────
Stage A of the two-stage Darvas pipeline: scans a broad symbol universe on
daily/weekly bars to find *candidates* — stocks building or approaching a
classic Nicholas Darvas weekly box. This is deliberately a different,
coarser methodology than core/darvas/scanner.py's multi-timeframe 15m/1h/1d
confluence scanner (Stage B) — Stage A's job is to narrow a large universe
down to a short candidate list; Stage B then times the actual intraday
entry on that shortlist.

Ported from the user's existing DarvasTrader project
(github.com/SeaOfTiberias/DarvasTrader, scanner/darvas_scanner.py), which
used yfinance + ICICI Breeze. Here the same weekly ceiling/floor
confirmation state machine and HOT/WARM/WATCH tiering runs on **Fyers**
daily candles via the existing BrokerAdapter, so discovery, timing, and
execution all sit on one broker/data source.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd

from core.brokers.base import BrokerAdapter, OHLCV

logger = logging.getLogger(__name__)


# ─── Config (mirrors DarvasTrader's CONFIG defaults) ──────────────────────────

DEFAULT_CONFIG = {
    # Box detection (weekly bars)
    "ceil_bars":          3,      # consecutive weeks NOT making a new high
    "floor_bars":         3,      # consecutive weeks NOT making a new low

    # Breakout filter
    "atr_mult_bo":        0.1,    # close must exceed ceiling by this many daily ATRs
    "atr_period":         14,     # ATR period (daily bars)

    # Volume filter
    "vol_len":            20,     # volume SMA period (daily bars)
    "vol_mult":           1.5,    # volume surge multiplier
    "require_vol":        True,   # require volume surge for FRESH BREAKOUT classification

    # Stop loss — Darvas's actual method: enter just above the ceiling,
    # stop just below it (a valid breakout should not re-enter the box).
    "sl_ceil_buffer_pct": 2.0,    # stop placed this % below the box ceiling

    # Quality filters
    "min_rr":             1.0,    # minimum R:R to flag as a quality breakout
    "max_box_width":       35.0,  # ignore boxes wider than this % (not Darvas-style)

    # Urgency tiers for APPROACHING stocks
    "hot_dist_pct":        2.0,   # HOT if within this % of ceiling
    "hot_vol_mult":        2.0,   # HOT requires this vol surge
    "warm_dist_pct":       4.0,   # WARM if within this % of ceiling
    "warm_vol_mult":       1.3,   # WARM requires at least this vol

    # Scan settings
    "history_days":        420,   # days of daily history to fetch (>52 weeks)
    "proximity_pct":       7.0,   # flag APPROACHING when within this % of ceiling
    "watchlist_days":      45,    # auto-expire watchlist entries after N days
}


# ─── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class DiscoveryResult:
    """One symbol's weekly-box discovery result."""
    symbol:           str
    status:           str             # FRESH BREAKOUT | APPROACHING | WATCHING | BOX FORMING
    alert_tier:       str = ""        # HOT | WARM | WATCH | VOL-SURGE | ""
    close:            float = 0.0
    box_ceiling:      Optional[float] = None
    box_floor:        Optional[float] = None
    box_width_pct:    Optional[float] = None
    dist_to_ceil:     Optional[float] = None
    sl_price:         Optional[float] = None
    mm_target:        Optional[float] = None
    risk_pct:         Optional[float] = None
    rr_ratio:         Optional[float] = None
    vol_ratio:        float = 0.0
    days_in_box:      Optional[int] = None
    weeks_to_confirm: Optional[int] = None
    ceil_conf:        int = 0
    floor_conf:       int = 0


@dataclass
class _BoxState:
    box_ceiling:    Optional[float] = None
    box_floor:      Optional[float] = None
    box_conf_date:  Optional[datetime] = None
    pending_ceil:   Optional[float] = None
    pending_floor:  Optional[float] = None
    ceil_conf:      int = 0
    floor_conf:     int = 0


# ─── Weekly resample ───────────────────────────────────────────────────────────

def _to_weekly(daily: list[OHLCV]) -> list[OHLCV]:
    """Resample daily OHLCV to weekly bars (week ending Friday)."""
    if not daily:
        return []
    df = pd.DataFrame([{
        "timestamp": c.timestamp, "open": c.open, "high": c.high,
        "low": c.low, "close": c.close, "volume": c.volume,
    } for c in daily])
    df = df.set_index(pd.DatetimeIndex(df["timestamp"])).sort_index()
    weekly = df.resample("W-FRI").agg(
        open=("open", "first"), high=("high", "max"),
        low=("low", "min"), close=("close", "last"), volume=("volume", "sum"),
    ).dropna(subset=["close"])
    return [
        OHLCV(
            timestamp=idx.to_pydatetime(), open=float(row["open"]),
            high=float(row["high"]), low=float(row["low"]),
            close=float(row["close"]), volume=int(row["volume"]),
        )
        for idx, row in weekly.iterrows()
    ]


# ─── Box state machine (exact port of DarvasTrader's detect_box) ──────────────

def _detect_box(weekly: list[OHLCV], cfg: dict) -> _BoxState:
    """
    Track ceiling/floor confirmation across weekly bars.

    Each new week: if the prior week's high didn't exceed the pending
    ceiling, confirmation count increments; otherwise the ceiling resets
    to the prior week's high. Same for the floor with lows. A box is
    confirmed once both counts reach their thresholds.
    """
    ceil_bars, floor_bars = cfg["ceil_bars"], cfg["floor_bars"]
    state = _BoxState()

    for i in range(1, len(weekly)):
        prev_high, prev_low = weekly[i - 1].high, weekly[i - 1].low
        curr_high, curr_low = weekly[i].high, weekly[i].low

        if state.pending_ceil is None:
            state.pending_ceil, state.ceil_conf = prev_high, 0
        elif prev_high <= state.pending_ceil:
            state.ceil_conf += 1
        else:
            state.pending_ceil, state.ceil_conf = prev_high, 0

        if state.pending_floor is None:
            state.pending_floor, state.floor_conf = prev_low, 0
        elif prev_low >= state.pending_floor:
            state.floor_conf += 1
        else:
            state.pending_floor, state.floor_conf = prev_low, 0

        if state.ceil_conf >= ceil_bars and state.floor_conf >= floor_bars:
            state.box_ceiling = state.pending_ceil
            state.box_floor = state.pending_floor
            state.box_conf_date = weekly[i].timestamp

            # Reset — start hunting for the next box
            state.ceil_conf = 0
            state.floor_conf = 0
            state.pending_ceil = curr_high
            state.pending_floor = curr_low

    return state


# ─── Per-symbol analysis (port of DarvasTrader's analyse()) ───────────────────

def analyse_symbol(symbol: str, daily: list[OHLCV], cfg: Optional[dict] = None) -> Optional[DiscoveryResult]:
    """
    Full weekly-box analysis for one symbol given its daily candles.
    Returns None if there isn't enough history, or the confirmed box is
    too wide to be a genuine Darvas setup.
    """
    cfg = {**DEFAULT_CONFIG, **(cfg or {})}

    if len(daily) < 60:
        return None

    weekly = _to_weekly(daily)
    if len(weekly) < cfg["ceil_bars"] + cfg["floor_bars"] + 2:
        return None

    state = _detect_box(weekly, cfg)
    atr_val = _atr(daily, cfg["atr_period"])

    latest = daily[-1]
    prev_bar = daily[-2] if len(daily) > 1 else latest
    close, prev_close = latest.close, prev_bar.close
    vol_today = latest.volume
    vol_sma = _sma([c.volume for c in daily[-cfg["vol_len"]:]])
    vol_ratio = vol_today / vol_sma if vol_sma > 0 else 0.0

    # ── No confirmed box yet — report forming progress ──────────────────────
    if state.box_ceiling is None:
        weeks_needed = max(cfg["ceil_bars"] - state.ceil_conf,
                            cfg["floor_bars"] - state.floor_conf)
        return DiscoveryResult(
            symbol=symbol, status="BOX FORMING", close=round(close, 2),
            box_ceiling=round(state.pending_ceil, 2) if state.pending_ceil else None,
            box_floor=round(state.pending_floor, 2) if state.pending_floor else None,
            vol_ratio=round(vol_ratio, 2), weeks_to_confirm=weeks_needed,
            ceil_conf=state.ceil_conf, floor_conf=state.floor_conf,
        )

    box_ceil, box_floor = state.box_ceiling, state.box_floor
    box_width_pct = (box_ceil - box_floor) / box_floor * 100
    if box_width_pct > cfg["max_box_width"]:
        return None

    # Darvas stop: just below the ceiling, not the floor.
    sl_price = box_ceil * (1.0 - cfg["sl_ceil_buffer_pct"] / 100.0)
    mm_target = box_ceil + (box_ceil - box_floor)   # measured move = 1 box height
    dist_to_ceil = (box_ceil - close) / close * 100  # +ve = still below ceiling

    days_in_box = (datetime.now(timezone.utc) - state.box_conf_date).days \
        if state.box_conf_date else None

    breakout_raw = close > (box_ceil + atr_val * cfg["atr_mult_bo"])
    vol_ok = (vol_ratio >= cfg["vol_mult"]) if cfg["require_vol"] else True
    fresh_breakout = breakout_raw and vol_ok and (prev_close <= box_ceil)

    if fresh_breakout:
        status = "FRESH BREAKOUT"
    elif breakout_raw and vol_ok:
        status = "WATCHING"          # already above ceiling — prior breakout
    elif 0 <= dist_to_ceil <= cfg["proximity_pct"]:
        status = "APPROACHING"
    else:
        status = "WATCHING"

    entry_for_rr = box_ceil
    risk_pct = (entry_for_rr - sl_price) / entry_for_rr * 100 if entry_for_rr > 0 else None
    reward_pct = (mm_target - entry_for_rr) / entry_for_rr * 100 if entry_for_rr > 0 else None
    rr_ratio = reward_pct / risk_pct if (risk_pct and risk_pct > 0) else None

    alert_tier = ""
    if status == "APPROACHING":
        if dist_to_ceil <= cfg["hot_dist_pct"] and vol_ratio >= cfg["hot_vol_mult"]:
            alert_tier = "HOT"
        elif dist_to_ceil <= cfg["warm_dist_pct"] and vol_ratio >= cfg["warm_vol_mult"]:
            alert_tier = "WARM"
        else:
            alert_tier = "WATCH"
    elif status == "WATCHING" and vol_ratio >= cfg["hot_vol_mult"] * 1.5:
        alert_tier = "VOL-SURGE"

    return DiscoveryResult(
        symbol=symbol, status=status, alert_tier=alert_tier, close=round(close, 2),
        box_ceiling=round(box_ceil, 2), box_floor=round(box_floor, 2),
        box_width_pct=round(box_width_pct, 1), dist_to_ceil=round(dist_to_ceil, 1),
        sl_price=round(sl_price, 2), mm_target=round(mm_target, 2),
        risk_pct=round(risk_pct, 1) if risk_pct is not None else None,
        rr_ratio=round(rr_ratio, 2) if rr_ratio is not None else None,
        vol_ratio=round(vol_ratio, 2), days_in_box=days_in_box,
        ceil_conf=state.ceil_conf, floor_conf=state.floor_conf,
    )


# ─── Scanner ──────────────────────────────────────────────────────────────────

class WeeklyDiscoveryScanner:
    """
    Scans a symbol universe for weekly Darvas box candidates via the
    broker's daily historical data. Throttled (semaphore + delay + retry)
    since core/brokers/fyers.py doesn't implement its own rate limiting
    and a full-universe scan can mean hundreds of sequential API calls.

    Confirmed live: even 5 concurrent requests immediately exhausts
    Fyers' history endpoint rate limit — every symbol in a 247-symbol
    universe came back HTTP 429 on the first real run. Default
    concurrency dropped to 2 with a longer inter-request delay, plus a
    short retry-with-backoff for 429s specifically (the limit window is
    typically per-second/per-minute and resets quickly, so a transient
    hit shouldn't just permanently drop a symbol from the scan).
    """

    MAX_RETRIES = 3
    RETRY_BACKOFF_SECONDS = 3.0

    def __init__(self, broker: BrokerAdapter, cfg: Optional[dict] = None, max_concurrent: int = 2):
        self.broker = broker
        self.cfg = {**DEFAULT_CONFIG, **(cfg or {})}
        self._max_concurrent = max_concurrent
        self._sem: Optional[asyncio.Semaphore] = None

    async def scan_universe(self, symbols: list[str]) -> list[DiscoveryResult]:
        logger.info("Discovery scan starting: %d symbols", len(symbols))
        # Created here, not in __init__: agent/main.py constructs this
        # scanner synchronously and then calls asyncio.run(scan_universe(...)),
        # which spins up a brand new event loop. Python 3.9's asyncio.Semaphore
        # binds to whatever loop is current at construction time — creating it
        # in __init__ bound it to a *different* loop than the one scan_universe
        # actually runs on, causing every _scan_one() call to fail with
        # "Future attached to a different loop." Constructing it here, inside
        # the coroutine itself, guarantees it's bound to the loop that's
        # actually running.
        self._sem = asyncio.Semaphore(self._max_concurrent)
        results = await asyncio.gather(
            *(self._scan_one(s) for s in symbols), return_exceptions=True,
        )

        out = []
        for symbol, result in zip(symbols, results):
            if isinstance(result, Exception):
                logger.warning("Discovery scan failed for %s: %s", symbol, result)
                continue
            if result is not None:
                out.append(result)

        logger.info("Discovery scan complete: %d/%d symbols produced a result",
                     len(out), len(symbols))
        return out

    async def _scan_one(self, symbol: str) -> Optional[DiscoveryResult]:
        async with self._sem:
            candles = await self._fetch_daily(symbol)
            await asyncio.sleep(0.5)   # be polite to the Fyers API
        if not candles:
            return None
        return analyse_symbol(symbol, candles, self.cfg)

    async def _fetch_daily(self, symbol: str) -> list[OHLCV]:
        to_date = datetime.now(timezone.utc)
        from_date = to_date - timedelta(days=self.cfg["history_days"])
        loop = asyncio.get_event_loop()

        for attempt in range(self.MAX_RETRIES):
            try:
                return await loop.run_in_executor(
                    None,
                    lambda: self.broker.get_historical_data(symbol, "1d", from_date, to_date),
                )
            except Exception as e:
                is_rate_limited = "429" in str(e)
                if is_rate_limited and attempt < self.MAX_RETRIES - 1:
                    wait = self.RETRY_BACKOFF_SECONDS * (attempt + 1)
                    logger.debug(
                        "Rate limited fetching %s (attempt %d/%d) — retrying in %.0fs",
                        symbol, attempt + 1, self.MAX_RETRIES, wait,
                    )
                    await asyncio.sleep(wait)
                    continue
                logger.warning("Failed to fetch daily candles for %s: %s", symbol, e)
                return []
        return []


# ─── Utilities ────────────────────────────────────────────────────────────────

def _sma(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _atr(daily: list[OHLCV], period: int = 14) -> float:
    """Wilder's Average True Range on daily bars (last value)."""
    if len(daily) < 2:
        return 0.0
    trs = []
    for i in range(1, len(daily)):
        high, low, prev_close = daily[i].high, daily[i].low, daily[i - 1].close
        trs.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    if not trs:
        return 0.0
    n = min(period, len(trs))
    atr = sum(trs[:n]) / n
    alpha = 1 / period
    for tr in trs[n:]:
        atr = tr * alpha + atr * (1 - alpha)
    return atr
