#!/usr/bin/env python3
"""
QuantOS — F&O screener backtest (research, no orders)
──────────────────────────────────────────────────────
Re-runs the screener's own setup code (core/discovery/momentum_shortlist +
weekly Darvas box, calls on real bars, puts on price-inverted bars) for every
session of the last ~year, and records what the underlying and the option
chain did over the next 1/3/5 sessions. Built because the live outcome log
(77 picks in two weeks, one regime) is too small to choose filters from.

Stages (each writes a file under ~/.quantos/bt_fno/ that the next one reads):
  fetch-bars   Fyers daily bars, ~820 calendar days, for today's F&O universe
               and NIFTY. Run where a Fyers token is valid (the VM), then copy
               bars.pkl to the machine that runs the rest.
  fetch-bhav   NSE F&O bhavcopy for every session in the bars (archive host).
  signals      every FRESH / OUT (<= 5 sessions) / NEAR setup per session and
               side, with the trend / momentum gates the screener applies.
  outcomes     per signal: futures OI build-up label, forward underlying
               returns (close->close and next open->close) and the same-day
               universe average (so "excess" strips the market's move), the
               screener's single contract, and the option chain's closes for
               that expiry on the signal day and 1/3/5 sessions later -- so any
               spread can be priced afterwards without re-reading bhavcopies.

Known limits, stated up front:
  - Survivorship: today's F&O list applied to the whole year.
  - Fyers daily bars are not adjusted for splits/bonuses; forward moves over
    25% are dropped as likely corporate actions.
  - Options are priced at bhavcopy closes: no bid/ask, so no execution cost.
    Close-to-close from the signal day, the same convention as the live log.

Usage:
  python scripts/backtest_fno_screener.py fetch-bars          # VM
  python scripts/backtest_fno_screener.py fetch-bhav
  python scripts/backtest_fno_screener.py signals [--workers 6]
  python scripts/backtest_fno_screener.py outcomes
"""

from __future__ import annotations

import argparse
import asyncio
import json
import pickle
import sys
from collections import OrderedDict
from concurrent.futures import ProcessPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.brokers.base import OHLCV  # noqa: E402
from core.fno_screener.bhavcopy import FnoDay, parse_fno_day  # noqa: E402
from core.fno_screener.screener import (  # noqa: E402
    ScreenerConfig, bar_date, invert_bars, oi_buildup, pick_contract, setup_rank,
)
from core.options.models import OptionType  # noqa: E402

OUT_DIR = Path.home() / ".quantos" / "bt_fno"
BARS = OUT_DIR / "bars.pkl"
BHAV_DIR = OUT_DIR / "bhavcopy"
SIGNALS = OUT_DIR / "signals.jsonl"
OUTCOMES = OUT_DIR / "outcomes.jsonl"
FETCH_DAYS = 820
WINDOW_BARS = 275            # ~ the live screener's 400 calendar days
HORIZONS = (1, 3, 5)
MAX_MOVE_PCT = 25.0
LOOKBACK_SESSIONS = 5
MARKET = "NIFTY"


# ─── fetch-bars ──────────────────────────────────────────────────────────────

def fetch_bars() -> None:
    from agent.main import load_config
    from core.brokers import get_broker
    from core.options.vrp.bhavcopy import fetch_raw
    from scripts.validate_regime_classifier import fetch_chunked_daily

    d = date.today()
    while True:                                           # latest published bhavcopy = today's universe
        d -= timedelta(days=1)
        try:
            universe = parse_fno_day(fetch_raw(d, BHAV_DIR), d).symbols
            break
        except Exception:
            continue
    broker = get_broker(load_config("agent/config.yaml"))
    broker.connect()

    async def run() -> dict:
        to = datetime.now(timezone.utc)
        sem, out = asyncio.Semaphore(1), {}
        for i, s in enumerate(universe + [MARKET]):
            try:
                candles = await fetch_chunked_daily(broker, s, to - timedelta(days=FETCH_DAYS), to, sem)
            except Exception as e:
                print(f"  {s}: {e}")
                continue
            by_date = {bar_date(c): c for c in candles}
            out[s] = [(c.timestamp, c.open, c.high, c.low, c.close, c.volume) for _, c in sorted(by_date.items())]
            if i % 25 == 0:
                print(f"  {i}/{len(universe)} {s}: {len(out[s])} bars", flush=True)
        return out

    bars = asyncio.run(run())
    BARS.write_bytes(pickle.dumps(bars))
    print(f"{len(bars)} symbols -> {BARS}")


INTRADAY_DIR = OUT_DIR / "m15"
INTRADAY_CHUNK_DAYS = 95      # Fyers caps minute resolutions at 100 days per request


def fetch_intraday() -> None:
    """15-minute bars for every symbol in bars.pkl over the signal window, one
    .npy per symbol (epoch_s, open, high, low, close) -- small enough for the VM."""
    import time
    import numpy as np
    from agent.main import load_config
    from core.brokers import get_broker

    INTRADAY_DIR.mkdir(parents=True, exist_ok=True)
    bars = pickle.loads(BARS.read_bytes())
    cal = [t for t, *_ in bars[MARKET]]
    start = cal[max(WINDOW_BARS - 5, 0)]
    end = datetime.now(timezone.utc)
    broker = get_broker(load_config("agent/config.yaml"))
    broker.connect()
    syms = [s for s in bars if s != MARKET]
    for n, s in enumerate(syms):
        path = INTRADAY_DIR / f"{s}.npy"
        if path.exists():
            continue
        rows, cs = {}, start
        while cs < end:
            ce = min(cs + timedelta(days=INTRADAY_CHUNK_DAYS), end)
            for attempt in range(3):
                try:
                    for c in broker.get_historical_data(s, "15m", cs, ce) or []:
                        rows[c.timestamp.timestamp()] = (c.open, c.high, c.low, c.close)
                    break
                except Exception as e:
                    print(f"  {s} {cs:%Y-%m-%d}: {e} (retry {attempt + 1})", flush=True)
                    time.sleep(3)
            time.sleep(0.5)
            cs = ce
        arr = np.array([(t, *v) for t, v in sorted(rows.items())], dtype=np.float64)
        np.save(path, arr)
        if n % 20 == 0:
            print(f"  {n}/{len(syms)} {s}: {len(arr)} bars", flush=True)
    print(f"done -> {INTRADAY_DIR}")


def load_bars() -> dict[str, list[OHLCV]]:
    raw = pickle.loads(BARS.read_bytes())
    return {s: [OHLCV(timestamp=t, open=o, high=h, low=lo, close=c, volume=v) for t, o, h, lo, c, v in rows]
            for s, rows in raw.items()}


def sessions(bars: dict) -> list[date]:
    return [bar_date(c) for c in bars[MARKET]]


# ─── fetch-bhav ──────────────────────────────────────────────────────────────

def fetch_bhav() -> None:
    from core.options.vrp.bhavcopy import BhavcopyNotAvailable, fetch_raw
    days = sessions(load_bars())[WINDOW_BARS - LOOKBACK_SESSIONS - 5:]
    missing = 0
    for i, d in enumerate(days):
        try:
            fetch_raw(d, BHAV_DIR)
        except BhavcopyNotAvailable:
            missing += 1
        if i % 25 == 0:
            print(f"  {i}/{len(days)} {d}", flush=True)
    print(f"{len(days) - missing}/{len(days)} bhavcopies in {BHAV_DIR}")


_day_cache: "OrderedDict[date, Optional[FnoDay]]" = OrderedDict()


def fno_day(d: date) -> Optional[FnoDay]:
    from core.options.vrp.bhavcopy import BhavcopyNotAvailable, fetch_raw
    if d not in _day_cache:
        try:
            _day_cache[d] = parse_fno_day(fetch_raw(d, BHAV_DIR), d)
        except BhavcopyNotAvailable:
            _day_cache[d] = None
        while len(_day_cache) > 14:
            _day_cache.popitem(last=False)
    _day_cache.move_to_end(d)
    return _day_cache[d]


# ─── signals ─────────────────────────────────────────────────────────────────

_BARS: dict = {}


def _init_worker() -> None:
    global _BARS
    _BARS = load_bars()


def _signals_for(i: int) -> list[dict]:
    """Every setup on session index i of the market calendar, both sides."""
    from core.discovery.momentum_shortlist import build_shortlist
    cal = _BARS[MARKET]
    t = bar_date(cal[i])
    real = {}
    for s, bs in _BARS.items():
        if s == MARKET:
            continue
        cut = [c for c in bs if bar_date(c) <= t][-WINDOW_BARS:]
        if cut and bar_date(cut[-1]) == t:
            real[s] = cut
    if not real:
        return []
    as_of = max(b[-1].timestamp for b in real.values())
    rows = []
    for side, bars_map in ((OptionType.CALL, real), (OptionType.PUT, {s: invert_bars(b) for s, b in real.items()})):
        for e in build_shortlist(bars_map, as_of):
            if setup_rank(e, 5) is None:          # FRESH, OUT <= 5 sessions, NEAR; trend + tier gates
                continue
            close = real[e.symbol][-1].close
            level = None
            if e.dist_to_ceil is not None:
                inv_ceiling = close * (1 + e.dist_to_ceil / 100)
                level = inv_ceiling if side == OptionType.CALL else close ** 2 / inv_ceiling
            rows.append(dict(date=t.isoformat(), symbol=e.symbol, side=side.value, close=close,
                             state=e.breakout_state, days_out=e.days_above_ceil, tier=e.momentum_tier,
                             momentum_pct=e.momentum_pct, box_width_pct=e.box_width_pct, vol_ratio=e.vol_ratio,
                             box_level=round(level, 2) if level else None, bucket=e.bucket, ma_cross=e.ma_cross,
                             universe=len(real)))
    return rows


def signals(workers: int) -> None:
    cal = load_bars()[MARKET]
    idx = list(range(WINDOW_BARS, len(cal)))
    print(f"{len(idx)} sessions {bar_date(cal[idx[0]])} .. {bar_date(cal[idx[-1]])}, {workers} workers", flush=True)
    n = 0
    with ProcessPoolExecutor(max_workers=workers, initializer=_init_worker) as ex, SIGNALS.open("w") as f:
        for k, rows in enumerate(ex.map(_signals_for, idx, chunksize=4)):
            for r in rows:
                f.write(json.dumps(r) + "\n")
            n += len(rows)
            if k % 20 == 0:
                print(f"  {k}/{len(idx)} sessions, {n} signals", flush=True)
    print(f"{n} signals -> {SIGNALS}")


# ─── outcomes ────────────────────────────────────────────────────────────────

def _ema(closes: list[float], period: int = 20) -> list[float]:
    k, out = 2 / (period + 1), []
    for c in closes:
        out.append(c if not out else out[-1] + k * (c - out[-1]))
    return out


def outcomes() -> None:
    bars = load_bars()
    cal = sessions(bars)
    pos = {d: i for i, d in enumerate(cal)}
    by_sym = {s: {bar_date(c): c for c in bs} for s, bs in bars.items()}
    nifty_close = [c.close for c in bars[MARKET]]
    nifty_ema = _ema(nifty_close)
    cfg = ScreenerConfig()

    def fwd(sym: str, i: int, h: int, sign: int) -> tuple[Optional[float], Optional[float]]:
        """(close->close, next open->close) % at session i+h, signed; None if missing / implausible."""
        if i + h >= len(cal):
            return None, None
        b0, b1, bh = by_sym[sym].get(cal[i]), by_sym[sym].get(cal[i + 1]), by_sym[sym].get(cal[i + h])
        if not (b0 and b1 and bh):
            return None, None
        cc = (bh.close / b0.close - 1) * 100
        oc = (bh.close / b1.open - 1) * 100
        ok = abs(cc) <= MAX_MOVE_PCT and abs(oc) <= MAX_MOVE_PCT
        return (round(sign * cc, 3), round(sign * oc, 3)) if ok else (None, None)

    # Same-day universe average forward move (unsigned, close->close), the baseline.
    base: dict[tuple[int, int], float] = {}
    syms = [s for s in bars if s != MARKET]
    sig_days = sorted({pos[date.fromisoformat(json.loads(l)["date"])] for l in SIGNALS.read_text().splitlines()})
    for i in sig_days:
        for h in HORIZONS:
            xs = [v for s in syms if (v := fwd(s, i, h, 1)[0]) is not None]
            if xs:
                base[(i, h)] = sum(xs) / len(xs)

    rows = [json.loads(l) for l in SIGNALS.read_text().splitlines()]
    rows.sort(key=lambda r: r["date"])
    n = 0
    with OUTCOMES.open("w") as f:
        for r in rows:
            t = date.fromisoformat(r["date"])
            i = pos[t]
            side = OptionType(r["side"])
            sign = 1 if side == OptionType.CALL else -1
            r["nifty_above_ema20"] = nifty_close[i] >= nifty_ema[i]
            for h in HORIZONS:
                cc, oc = fwd(r["symbol"], i, h, sign)
                r[f"cc{h}"], r[f"oc{h}"] = cc, oc
                b = base.get((i, h))
                r[f"ex{h}"] = None if cc is None or b is None else round(cc - sign * b, 3)
            day = fno_day(t)
            past = fno_day(cal[i - LOOKBACK_SESSIONS]) if i >= LOOKBACK_SESSIONS else None
            r["oi"] = None
            r["contract"] = None
            r["chain"] = None
            if day is not None:
                oi = oi_buildup(day, past, r["symbol"], cfg.oi_flat_pct)
                r["oi"] = oi.label if oi else None
                r["oi_chg_pct"] = oi.oi_chg_pct if oi else None
                k, why = pick_contract(day, r["symbol"], side, cfg)
                r["skip_reason"] = why
                if k is not None:
                    q = k.quote
                    r["contract"] = dict(expiry=q.expiry.isoformat(), strike=q.strike, close=q.close,
                                         lot=q.lot_size, dte=k.dte, iv=k.iv, delta=k.delta, theta_pct=k.theta_pct,
                                         oi_lots=q.oi_lots, volume=q.volume)
                    chain = {"spot": [day.spot.get(r["symbol"])], "strikes": {}}
                    later = [cal[i + h] if i + h < len(cal) else None for h in HORIZONS]
                    days = [day] + [fno_day(d) if d else None for d in later]
                    for j, dd in enumerate(days):
                        if j:
                            chain["spot"].append(dd.spot.get(r["symbol"]) if dd else None)
                        for oq in (dd.options.get(r["symbol"], []) if dd else []):
                            if oq.expiry == q.expiry and oq.option_type == side:
                                chain["strikes"].setdefault(str(oq.strike), [None] * 4)[j] = oq.close or None
                    r["chain"] = chain
            f.write(json.dumps(r) + "\n")
            n += 1
            if n % 500 == 0:
                print(f"  {n}/{len(rows)} ({r['date']})", flush=True)
    print(f"{n} outcomes -> {OUTCOMES}")


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stage", choices=["fetch-bars", "fetch-intraday", "fetch-bhav", "signals", "outcomes"])
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args(argv)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    BHAV_DIR.mkdir(parents=True, exist_ok=True)
    {"fetch-bars": fetch_bars, "fetch-intraday": fetch_intraday, "fetch-bhav": fetch_bhav, "outcomes": outcomes,
     "signals": lambda: signals(args.workers)}[args.stage]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
