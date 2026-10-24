#!/usr/bin/env python3
"""
QuantOS — Darvas Bucket B: universe, entry cues and exits (2026-10-23)
─────────────────────────────────────────────────────────────────────
Pre-registered in docs/DARVAS_CUES_PREREG_2026-10-23.md (committed before this
script ran). Tests T1-T8 there; results are appended to that file.

Rules are the frozen Bucket B ones (scripts/backtest_darvas_atr_stop.py). The
box detector is a plain-Python port of core/darvas/weekly_discovery.analyse_symbol
on the trailing 756 sessions (as in the OOS run), for speed: `--check` compares
it with the original on sampled real bars, and `--validate-oos` must reproduce
docs/DARVAS_ATR_STOP_OOS_RESULTS.md (991 Bucket B trades, mean net +2.16%)
before any result counts (pre-run amendment 2).

Usage:
    python scripts/backtest_darvas_cues.py --check
    python scripts/backtest_darvas_cues.py --validate-oos
    python scripts/backtest_darvas_cues.py            # the pre-registered run
"""
from __future__ import annotations

import argparse
import bisect
import csv
import io
import json
import pickle
import random
import statistics
import sys
import zipfile
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.brokers.base import OHLCV  # noqa: E402
from core.fundamentals.pead.eq_bhavcopy import DEFAULT_RAW_CACHE_DIR  # noqa: E402

DATA_FROM, DATA_TO = date(2016, 1, 1), date(2026, 6, 25)
P1 = (date(2016, 7, 1), date(2023, 9, 21))
P2 = (date(2023, 9, 22), date(2026, 3, 31))
LOOKBACK, MIN_BARS = 756, 60
UNIVERSE_WINDOW = 126
U1_RANKS, U2_RANKS, U2_MIN_VAL = (0, 500), (500, 1000), 2e7          # ₹2 cr/day median
U2_EXTRA_SLIPPAGE = 0.0025                                           # per side
ATR_PERIOD, ATR_MULT = 14, 2.0
BUCKET_B = (35.0, 50.0)
POSITION_RS = 100_000.0
BOOT, SEED = 10_000, 20261024
N_TESTS = 8
ALPHA = 0.05 / N_TESTS
ACTIONS = [Path("data_cache/nse_corporate_actions_2016_2023.json"),
           Path("data_cache/nse_corporate_actions_2024_2026.json")]
RAW_CACHE = Path.home() / ".quantos" / "darvas_cues_bhav.pkl"
TRADES_CACHE = Path.home() / ".quantos" / "darvas_cues_trades.json"
DOC = Path("docs/DARVAS_CUES_PREREG_2026-10-23.md")
UTC = timezone.utc
EXITS = ("base", "t6", "t7", "t8")


# ─── Data ─────────────────────────────────────────────────────────────────────

def _parse_day(d: date, text: str) -> list[tuple[str, dict]]:
    rows = list(csv.DictReader(io.StringIO(text)))
    out = []
    if rows and "TckrSymb" in rows[0]:                       # UDiFF format (2024-07 onwards)
        keys = ("TckrSymb", "SctySrs", "OpnPric", "HghPric", "LwPric", "ClsPric", "PrvsClsgPric",
                "TtlTradgVol", "TtlTrfVal")
    else:
        keys = ("SYMBOL", "SERIES", "OPEN", "HIGH", "LOW", "CLOSE", "PREVCLOSE", "TOTTRDQTY", "TOTTRDVAL")
    s, sr, o, h, lo, c, pv, v, val = keys
    for r in rows:
        if (r.get(sr) or "").strip() != "EQ":
            continue
        try:
            row = dict(date=d, o=float(r[o]), h=float(r[h]), l=float(r[lo]), c=float(r[c]),
                       prev=float(r[pv]), vol=float(r[v]), val=float(r[val]))
        except (KeyError, ValueError, TypeError):
            continue
        sym = r[s].strip()
        if sym.endswith("BEES") or "ETF" in sym:
            continue
        if row["c"] > 0 and row["o"] > 0:
            out.append((sym, row))
    return out


def load_bhavcopies(to: date = DATA_TO) -> dict[str, list[dict]]:
    if RAW_CACHE.exists():
        by_sym = pickle.loads(RAW_CACHE.read_bytes())
    else:
        by_sym = defaultdict(list)
        d = DATA_FROM
        while d <= DATA_TO:
            p = DEFAULT_RAW_CACHE_DIR / f"{d:%Y%m%d}.zip"
            if d.weekday() < 5 and p.exists():
                with zipfile.ZipFile(p) as zf:
                    text = zf.read(zf.namelist()[0]).decode("utf-8", errors="replace")
                for sym, row in _parse_day(d, text):
                    by_sym[sym].append(row)
            d += timedelta(days=1)
        by_sym = dict(by_sym)
        RAW_CACHE.write_bytes(pickle.dumps(by_sym))
    if to < DATA_TO:
        by_sym = {s: [r for r in rows if r["date"] <= to] for s, rows in by_sym.items()}
        by_sym = {s: rows for s, rows in by_sym.items() if rows}
    return by_sym


def load_actions() -> dict[str, list[tuple[date, float]]]:
    from scripts.backtest_darvas_atr_stop_oos import action_factor
    out: dict[str, list[tuple[date, float]]] = defaultdict(list)
    for path in ACTIONS:
        for a in json.loads(path.read_text()):
            f = action_factor(a["subject"])
            if f:
                out[a["symbol"].strip()].append((datetime.strptime(a["exDate"], "%d-%b-%Y").date(), f))
    return out


# ─── Universes ────────────────────────────────────────────────────────────────

@dataclass
class Universe:
    dates: list[date]                 # rebalance dates
    members: list[frozenset]

    def has(self, sym: str, d: date) -> bool:
        k = bisect.bisect_right(self.dates, d) - 1
        return k >= 0 and sym in self.members[k]


def build_universe(by_sym: dict[str, list[dict]], ranks: tuple[int, int], min_val: float,
                   last_year: int) -> Universe:
    vals: dict[date, dict[str, float]] = defaultdict(dict)
    for s, rows in by_sym.items():
        for r in rows:
            vals[r["date"]][s] = r["val"]
    days = sorted(vals)
    rebal = [date(y, m, 1) for y in range(2016, last_year + 1) for m in (1, 7)]
    members = []
    for rd in rebal:
        i = bisect.bisect_left(days, rd)
        window = days[max(0, i - UNIVERSE_WINDOW):i] or days[:UNIVERSE_WINDOW]
        per: dict[str, list[float]] = defaultdict(list)
        for d in window:
            for s, v in vals[d].items():
                per[s].append(v)
        med = {s: statistics.median(v) for s, v in per.items()}
        ranked = sorted(med, key=med.get, reverse=True)[ranks[0]:ranks[1]]
        members.append(frozenset(s for s in ranked if med[s] >= min_val))
    return Universe(rebal, members)


def ew_index(adj: dict[str, list[dict]], uni: Universe) -> tuple[list[date], list[float]]:
    rets: dict[date, list[float]] = defaultdict(list)
    for s, rows in adj.items():
        for a, b in zip(rows, rows[1:]):
            if (b["date"] - a["date"]).days > 10:
                continue
            if uni.has(s, b["date"]):
                rets[b["date"]].append(b["c"] / a["c"] - 1)
    days = sorted(rets)
    level, out = 1.0, []
    for d in days:
        level *= 1 + statistics.mean(rets[d])
        out.append(level)
    return days, out


# ─── Fast port of analyse_symbol (WIDE_CFG) on the trailing LOOKBACK bars ─────

def _week_key(d: date) -> date:
    return d + timedelta(days=(4 - d.weekday()) % 7)        # W-FRI: the week's Friday


def wilder_atr(bars: list[OHLCV], period: int = ATR_PERIOD) -> list[float]:
    """atr[j] == core.darvas.weekly_discovery._atr(bars[:j+1], period)."""
    out = [0.0] * len(bars)
    trs: list[float] = []
    atr = 0.0
    for j in range(1, len(bars)):
        h, lo, pc = bars[j].high, bars[j].low, bars[j - 1].close
        trs.append(max(h - lo, abs(h - pc), abs(lo - pc)))
        k = len(trs)
        if k < period:
            atr = sum(trs) / k
        elif k == period:
            atr = sum(trs) / period
        else:
            atr = trs[-1] * (1 / period) + atr * (1 - 1 / period)
        out[j] = atr
    return out


@dataclass
class Res:
    status: str
    ceil: Optional[float]
    floor: Optional[float]
    width: Optional[float]
    mm: Optional[float]


class FastBox:
    """analyse_symbol(sym, bars[max(0, j-755): j+1], cfg=WIDE_CFG) for every j, in plain Python.
    ATR uses the full-history Wilder value: after 740+ steps the window seed's weight is
    (13/14)^740 ~ 1e-24, and for j < 756 the window IS the full history."""

    def __init__(self, bars: list[OHLCV]):
        from scripts.backtest_darvas_box_width import WIDE_CFG
        self.cfg = WIDE_CFG
        self.bars = bars
        self.atr = wilder_atr(bars, self.cfg["atr_period"])
        self.wk = [_week_key(b.timestamp.date()) for b in bars]
        self.wk_start: dict[date, int] = {}
        self.wk_end: dict[date, int] = {}
        for i, k in enumerate(self.wk):
            self.wk_start.setdefault(k, i)
            self.wk_end[k] = i
        self.wk_hl = {k: (max(b.high for b in bars[self.wk_start[k]:self.wk_end[k] + 1]),
                          min(b.low for b in bars[self.wk_start[k]:self.wk_end[k] + 1])) for k in self.wk_start}
        self.keys = sorted(self.wk_start)

    def _weekly(self, s: int, j: int) -> list[tuple[float, float]]:
        ks, ke = self.wk[s], self.wk[j]
        a, b = bisect.bisect_left(self.keys, ks), bisect.bisect_left(self.keys, ke)
        out = []
        for idx in range(a, b + 1):
            k = self.keys[idx]
            lo_i, hi_i = max(self.wk_start[k], s), min(self.wk_end[k], j)
            if lo_i == self.wk_start[k] and hi_i == self.wk_end[k]:
                out.append(self.wk_hl[k])
            else:
                seg = self.bars[lo_i:hi_i + 1]
                out.append((max(x.high for x in seg), min(x.low for x in seg)))
        return out

    def at(self, j: int) -> Optional[Res]:
        cfg = self.cfg
        s = max(0, j - LOOKBACK + 1)
        if j - s + 1 < 60:
            return None
        weekly = self._weekly(s, j)
        if len(weekly) < cfg["ceil_bars"] + cfg["floor_bars"] + 2:
            return None
        pc = pf = box_c = box_f = None
        cc = fc = 0
        for i in range(1, len(weekly)):
            ph, pl = weekly[i - 1]
            ch, cl = weekly[i]
            if pc is None:
                pc, cc = ph, 0
            elif ph <= pc:
                cc += 1
            else:
                pc, cc = ph, 0
            if pf is None:
                pf, fc = pl, 0
            elif pl >= pf:
                fc += 1
            else:
                pf, fc = pl, 0
            if cc >= cfg["ceil_bars"] and fc >= cfg["floor_bars"]:
                box_c, box_f = pc, pf
                cc = fc = 0
                pc, pf = ch, cl
        if box_c is None:
            return Res("BOX FORMING", round(pc, 2) if pc else None, None, None, None)
        width = (box_c - box_f) / box_f * 100
        if width > cfg["max_box_width"]:
            return None
        bars = self.bars
        close = bars[j].close
        prev_close = bars[j - 1].close if j > s else close
        vols = [b.volume for b in bars[max(s, j - cfg["vol_len"] + 1):j + 1]]
        vol_sma = sum(vols) / len(vols) if vols else 0.0
        vol_ratio = bars[j].volume / vol_sma if vol_sma > 0 else 0.0
        breakout_raw = close > (box_c + self.atr[j] * cfg["atr_mult_bo"])
        vol_ok = (vol_ratio >= cfg["vol_mult"]) if cfg["require_vol"] else True
        fresh = breakout_raw and vol_ok and (prev_close <= box_c)
        status = "FRESH BREAKOUT" if fresh else "WATCHING/APPROACHING"
        return Res(status, round(box_c, 2), round(box_f, 2), round(width, 1), round(box_c + (box_c - box_f), 2))


# ─── Trades ───────────────────────────────────────────────────────────────────

def _ema(xs: list[float], n: int) -> list[float]:
    k, out, e = 2 / (n + 1), [], xs[0]
    for x in xs:
        e = x * k + e * (1 - k)
        out.append(e)
    return out


def features(bars: list[OHLCV], atr: list[float], i: int) -> dict:
    closes = [b.close for b in bars[: i + 1]]
    macd = [a - b for a, b in zip(_ema(closes, 12), _ema(closes, 26))]
    prior_high = max((b.high for b in bars[max(0, i - 252):i]), default=float("inf"))
    vol50 = [b.volume for b in bars[max(0, i - 50):i]]
    return {
        "t2_clear_air": bars[i].close >= prior_high,
        "t3_macd_confirms": macd[i] >= max(macd[max(0, i - 60):i], default=float("-inf")),
        "t4_volume": bool(vol50) and bars[i].volume >= 1.5 * (sum(vol50) / len(vol50)),
        "t5_not_extended": i >= 2 and atr[i] > 0 and (bars[i].close - bars[i - 2].close) / atr[i] < 2.5,
    }


def walk(bars: list[OHLCV], res: list[Optional[Res]], atr: list[float], t: dict, variant: str,
         gap_aware: bool) -> tuple[int, float, str]:
    """The frozen ATR-stop walk (scripts/backtest_darvas_atr_stop._simulate_exit_atr) plus the
    pre-registered fills and exit variants. Returns (exit index, exit price, reason)."""
    e, n = t["entry_idx"], len(bars)
    stop, target, seen = t["stop0"], t["target0"], t["ceil0"]
    entry, atr_i = t["entry_price"], t["atr_i"]
    trailed, be_armed, pending = False, False, None

    def tradeable(b: OHLCV) -> bool:
        return not gap_aware or b.high > b.low

    for j in range(e, n):
        bar = bars[j]
        if pending is not None:
            if tradeable(bar):
                return j, bar.open, pending
            continue
        if bar.low <= stop:
            if not gap_aware:
                return j, stop, "stop"
            if not tradeable(bar):
                pending = "stop"
                continue
            return j, min(bar.open, stop), "stop"
        if bar.high >= target:
            return j, target, "target"
        if variant == "t6" and not trailed and bar.close < t["ceil0"]:
            pending = "t6_early_failure"
        if variant == "t8" and j == e and bar.close < bar.open and \
                (bar.close - bar.low) < (bar.high - bar.low) / 3:
            pending = "t8_weak_day1"
        if variant == "t7" and not be_armed and bar.high >= entry + atr_i:
            be_armed = True
            stop = max(stop, entry)
        r = res[j]
        if r is not None and r.ceil and r.ceil > seen:
            new_stop = r.ceil - ATR_MULT * atr[j]
            if new_stop > stop:
                stop, seen, trailed = new_stop, r.ceil, True
                if r.mm and r.mm > target:
                    target = r.mm
    if pending is not None:
        return n - 1, bars[n - 1].close, "still-open"
    return n - 1, bars[n - 1].close, "still-open"


def symbol_trades(args) -> tuple[str, list[dict]]:
    sym, rows, windows, gap_aware, last_breakout = args
    bars = [OHLCV(timestamp=datetime(r["date"].year, r["date"].month, r["date"].day, tzinfo=UTC),
                  open=r["o"], high=r["h"], low=r["l"], close=r["c"], volume=r["vol"]) for r in rows]
    n = len(bars)
    if n <= MIN_BARS:
        return sym, []
    fb = FastBox(bars)
    res: list[Optional[Res]] = [None] * n
    for j in range(MIN_BARS, n):
        res[j] = fb.at(j)
    out = []
    for i in range(MIN_BARS, n - 1):
        r = res[i]
        if r is None or r.status != "FRESH BREAKOUT":
            continue
        d = bars[i].timestamp.date()
        if d > last_breakout:
            continue
        uni = next((name for name, members in windows if _in(members, d, sym)), None)
        if uni is None:
            continue
        t = {"symbol": sym, "universe": uni, "breakout_date": d.isoformat(), "width_pct": r.width,
             "entry_idx": i + 1, "entry_date": bars[i + 1].timestamp.date().isoformat(),
             "entry_price": bars[i + 1].open, "ceil0": r.ceil, "target0": r.mm,
             "stop0": r.ceil - ATR_MULT * fb.atr[i], "atr_i": fb.atr[i],
             "median_val": statistics.median([x["val"] for x in rows[max(0, i - 125):i + 1]])}
        if not (BUCKET_B[0] < r.width <= BUCKET_B[1]):
            continue
        t.update(features(bars, fb.atr, i))
        for v in (EXITS if gap_aware else ("base",)):
            k, px, reason = walk(bars, res, fb.atr, t, v, gap_aware)
            t[v] = {"exit_date": bars[k].timestamp.date().isoformat(), "exit_price": px, "reason": reason}
        out.append({k: v for k, v in t.items() if k != "entry_idx"})
    return sym, out


def _in(members: tuple[list[date], list[frozenset]], d: date, sym: str) -> bool:
    dates, mem = members
    k = bisect.bisect_right(dates, d) - 1
    return k >= 0 and sym in mem[k]


# ─── Stats ────────────────────────────────────────────────────────────────────

def net_return(entry: float, exit_: float, extra_slip: float = 0.0) -> float:
    from scripts.backtest_darvas_box_width import STRESSED_COST_MODEL
    qty = max(1, int(POSITION_RS // entry))
    cost = STRESSED_COST_MODEL.cost_of(entry, exit_, qty, "BUY")
    return ((exit_ - entry) * qty - cost) / (entry * qty) - 2 * extra_slip


def _week(t: dict) -> tuple:
    return date.fromisoformat(t["entry_date"]).isocalendar()[:2]


def boot(groups: list[list], stat, rng_seed: int = SEED) -> list[float]:
    rng, out = random.Random(rng_seed), []
    for _ in range(BOOT):
        pick = [x for _ in groups for x in rng.choice(groups)]
        v = stat(pick)
        if v is not None:
            out.append(v)
    out.sort()
    return out


def q(xs: list[float], p: float) -> float:
    return xs[min(len(xs) - 1, max(0, int(p * len(xs))))] if xs else float("nan")


def by_week(trades: list[dict], key) -> list[list]:
    g = defaultdict(list)
    for t in trades:
        g[_week(t)].append(key(t))
    return list(g.values())


def mean(xs):
    return statistics.mean(xs) if xs else float("nan")


# ─── Run ──────────────────────────────────────────────────────────────────────

def prepare(to: date):
    raw = load_bhavcopies(to)
    print(f"loaded {len(raw)} symbols", flush=True)
    from scripts.backtest_darvas_atr_stop_oos import adjust
    acts = load_actions()
    adj = {s: adjust(rows, acts.get(s, [])) for s, rows in raw.items()}
    return raw, adj


def run_trades(adj, unis: dict[str, Universe], gap_aware: bool, last_breakout: date, workers: int):
    windows = [(name, (u.dates, u.members)) for name, u in unis.items()]
    ever = set().union(*(set().union(*u.members) for u in unis.values()))
    jobs = [(s, adj[s], windows, gap_aware, last_breakout) for s in sorted(ever) if s in adj]
    print(f"{len(jobs)} symbols ever in a universe", flush=True)
    trades = []
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for k, (sym, tr) in enumerate(ex.map(symbol_trades, jobs, chunksize=4)):
            trades += tr
            if k % 200 == 0:
                print(f"  {k}/{len(jobs)} symbols, {len(trades)} Bucket B trades", flush=True)
    return trades


def cmd_check(n_samples: int = 400) -> int:
    from core.darvas.weekly_discovery import analyse_symbol
    from scripts.backtest_darvas_box_width import WIDE_CFG
    raw, adj = prepare(DATA_TO)
    rng = random.Random(7)
    syms = rng.sample(sorted(s for s, r in adj.items() if len(r) > 900), 12)
    bad = checked = fresh = 0
    for s in syms:
        rows = adj[s]
        bars = [OHLCV(timestamp=datetime(r["date"].year, r["date"].month, r["date"].day, tzinfo=UTC),
                      open=r["o"], high=r["h"], low=r["l"], close=r["c"], volume=r["vol"]) for r in rows]
        fb = FastBox(bars)
        js = rng.sample(range(MIN_BARS, len(bars)), n_samples // len(syms))
        # every FRESH BREAKOUT bar of the symbol too, where exactness matters most
        js += [j for j in range(MIN_BARS, len(bars)) if (fb.at(j) or Res("", 0, 0, 0, 0)).status == "FRESH BREAKOUT"]
        for j in js:
            a = analyse_symbol(s, bars[max(0, j - LOOKBACK + 1): j + 1], cfg=WIDE_CFG)
            b = fb.at(j)
            checked += 1
            if a is None or b is None:
                ok = a is None and b is None
            else:
                ok = ((a.status == "FRESH BREAKOUT") == (b.status == "FRESH BREAKOUT") and a.box_ceiling == b.ceil
                      and (a.box_floor == b.floor if a.status != "BOX FORMING" else True)
                      and a.box_width_pct == b.width and a.mm_target == b.mm)
                fresh += b.status == "FRESH BREAKOUT"
            if not ok:
                bad += 1
                print(f"  MISMATCH {s} {bars[j].timestamp.date()}: {a} vs {b}")
    print(f"port check: {checked} bars ({fresh} FRESH BREAKOUT), {bad} mismatches")
    return 1 if bad else 0


def cmd_validate(workers: int) -> int:
    """U1, data to 2023-12-31, the frozen stop fills -> must reproduce the OOS report."""
    raw, adj = prepare(date(2023, 12, 31))
    u1 = build_universe(raw, U1_RANKS, 0.0, 2023)
    trades = run_trades(adj, {"U1": u1}, False, P1[1], workers)
    tr = [t for t in trades if date.fromisoformat(t["breakout_date"]) >= P1[0]]
    nets = [net_return(t["entry_price"], t["base"]["exit_price"]) for t in tr]
    print(f"validate-oos: {len(tr)} Bucket B trades, mean net {mean(nets):+.2%} "
          f"(OOS report: 991 trades, +2.16%)")
    return 0


def cmd_run(workers: int) -> int:
    raw, adj = prepare(DATA_TO)
    unis = {"U1": build_universe(raw, U1_RANKS, 0.0, 2026),
            "U2": build_universe(raw, U2_RANKS, U2_MIN_VAL, 2026)}
    if TRADES_CACHE.exists():
        trades = json.loads(TRADES_CACHE.read_text())
    else:
        trades = run_trades(adj, unis, True, P2[1], workers)
        TRADES_CACHE.write_text(json.dumps(trades))
    ew = {name: ew_index(adj, u) for name, u in unis.items()}
    report = summarize(trades, ew)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # α etc. on a cp1252 console
    print(report)
    text = DOC.read_text(encoding="utf-8")
    marker = "\n---\n\n## Results"
    text = text.split(marker)[0]
    DOC.write_text(text + marker + report[len("## Results"):], encoding="utf-8")
    return 0


def summarize(trades: list[dict], ew: dict) -> str:
    def lvl(name, d):
        days, levels = ew[name]
        k = bisect.bisect_right(days, d) - 1
        return levels[k] if k >= 0 else None

    def period(t):
        d = date.fromisoformat(t["breakout_date"])
        return "P1" if P1[0] <= d <= P1[1] else "P2" if P2[0] <= d <= P2[1] else None

    trades = [t for t in trades if period(t)]
    for t in trades:
        t["period"] = period(t)
        slip = U2_EXTRA_SLIPPAGE if t["universe"] == "U2" else 0.0
        a = lvl(t["universe"], date.fromisoformat(t["entry_date"]))
        for v in EXITS:
            x = t[v]
            x["net"] = net_return(t["entry_price"], x["exit_price"], slip)
            b = lvl(t["universe"], date.fromisoformat(x["exit_date"]))
            x["excess"] = x["net"] - (b / a - 1) if a and b else None
    trades = [t for t in trades if all(t[v]["excess"] is not None for v in EXITS)]
    lo_p = ALPHA
    L = ["## Results", "",
         f"Run {datetime.now().date()}: `python scripts/backtest_darvas_cues.py`. "
         f"{len(trades)} Bucket B trades (U1 {sum(t['universe'] == 'U1' for t in trades)}, "
         f"U2 {sum(t['universe'] == 'U2' for t in trades)}). Gap-aware fills, Stressed costs (+0.25%/side for U2). "
         f"Excess is over each trade's own universe. Bound = the {lo_p:.2%} bootstrap quantile (one-sided α = 0.05/8).", ""]

    # T1
    L += ["### T1, the universe (baseline exit)", "",
          "| Universe | Period | Trades | Won | Mean net | Mean excess | Bound (excess) |", "|---|---|---|---|---|---|---|"]
    t1 = {}
    for u in ("U1", "U2"):
        pooled = [t for t in trades if t["universe"] == u]
        for p in ("P1", "P2", "both"):
            tr = pooled if p == "both" else [t for t in pooled if t["period"] == p]
            if not tr:
                L.append(f"| {u} | {p} | 0 | | | | |")
                continue
            ex = [t["base"]["excess"] for t in tr]
            bnd = q(boot(by_week(tr, lambda t: t["base"]["excess"]), mean), lo_p) if p == "both" else None
            won = sum(t["base"]["net"] > 0 for t in tr) / len(tr)
            L.append(f"| {u} | {p} | {len(tr)} | {won:.0%} | {mean([t['base']['net'] for t in tr]):+.2%} | "
                     f"{mean(ex):+.2%} | {'' if bnd is None else f'{bnd:+.2%}'} |")
            t1[(u, p)] = (len(tr), mean(ex), bnd)
    u2 = [t1.get(("U2", p), (0, float("nan"), None)) for p in ("P1", "P2", "both")]
    t1_pass = u2[0][1] > 0 and u2[1][1] > 0 and (u2[2][2] or -1) > 0 and u2[2][0] >= 300
    L += ["", f"**T1 {'PASS' if t1_pass else 'FAIL'}** (U2: excess > 0 in P1 and P2, bound > 0, ≥ 300 trades).", ""]

    # T2-T5
    u1 = [t for t in trades if t["universe"] == "U1"]
    L += ["### Entry filters T2–T5 (U1, baseline exit)", "",
          "| Test | Kept | Dropped | Kept excess | Dropped excess | Diff P1 | Diff P2 | Bound (diff) | Verdict |",
          "|---|---|---|---|---|---|---|---|---|"]
    for key, label in (("t2_clear_air", "T2 clear air"), ("t3_macd_confirms", "T3 MACD confirms"),
                       ("t4_volume", "T4 volume ≥ 1.5× 50d"), ("t5_not_extended", "T5 not extended (control)")):
        kept = [t for t in u1 if t[key]]
        drop = [t for t in u1 if not t[key]]

        def diff(tr):
            k = [t["base"]["excess"] for t in tr if t[key]]
            d = [t["base"]["excess"] for t in tr if not t[key]]
            return (mean(k) - mean(d)) if k and d else None

        d1 = diff([t for t in u1 if t["period"] == "P1"])
        d2 = diff([t for t in u1 if t["period"] == "P2"])
        bs = boot(by_week(u1, lambda t: t), diff)
        bnd = q(bs, lo_p)
        dex = mean([t["base"]["excess"] for t in drop])
        ok = (d1 or -1) > 0 and (d2 or -1) > 0 and bnd > 0 and dex <= 0 and len(kept) >= 250
        f = lambda x: "n/a" if x is None else f"{x:+.2%}"  # noqa: E731
        L.append(f"| {label} | {len(kept)} | {len(drop)} | {mean([t['base']['excess'] for t in kept]):+.2%} | "
                 f"{dex:+.2%} | {f(d1)} | {f(d2)} | {bnd:+.2%} | {'**PASS**' if ok else 'fail'} |")

    # T6-T8
    L += ["", "### Exits T6–T8 (U1, paired against the baseline exit)", "",
          "| Test | Trades | Mean net | Mean excess | Paired diff P1 | Paired diff P2 | Bound | Top-5% winners: base → variant | Verdict |",
          "|---|---|---|---|---|---|---|---|---|"]
    top = sorted(u1, key=lambda t: t["base"]["net"], reverse=True)[:max(1, len(u1) // 20)]
    for v, label in (("t6", "T6 early failure"), ("t7", "T7 breakeven"), ("t8", "T8 weak day 1 (control)")):
        pd_ = lambda tr: mean([t[v]["net"] - t["base"]["net"] for t in tr]) if tr else None  # noqa: E731
        d1 = pd_([t for t in u1 if t["period"] == "P1"])
        d2 = pd_([t for t in u1 if t["period"] == "P2"])
        bnd = q(boot(by_week(u1, lambda t: t[v]["net"] - t["base"]["net"]), mean), lo_p)
        ok = (d1 or -1) > 0 and (d2 or -1) > 0 and bnd > 0
        L.append(f"| {label} | {len(u1)} | {mean([t[v]['net'] for t in u1]):+.2%} | "
                 f"{mean([t[v]['excess'] for t in u1]):+.2%} | {d1:+.2%} | {d2:+.2%} | {bnd:+.2%} | "
                 f"{mean([t['base']['net'] for t in top]):+.1%} → {mean([t[v]['net'] for t in top]):+.1%} | "
                 f"{'**PASS**' if ok else 'fail'} |")
    base_u1 = mean([t["base"]["net"] for t in u1])
    L += ["", f"U1 baseline mean net {base_u1:+.2%}, excess {mean([t['base']['excess'] for t in u1]):+.2%}.", ""]

    # Business view
    L += ["### Business view (description only)", "",
          "| Universe | Trades/yr | Won | Avg win / avg loss | Mean net | Mean excess | Excess ₹/yr on ₹5L (9% slots) | "
          "Median traded value | ₹45k slot | ₹4.5L slot |", "|---|---|---|---|---|---|---|---|---|---|"]
    years = ((P1[1] - P1[0]).days + (P2[1] - P2[0]).days) / 365.25
    for u in ("U1", "U2"):
        tr = [t for t in trades if t["universe"] == u]
        if not tr:
            continue
        nets = [t["base"]["net"] for t in tr]
        wins, losses = [x for x in nets if x > 0], [x for x in nets if x <= 0]
        ex = mean([t["base"]["excess"] for t in tr])
        mv = statistics.median([t["median_val"] for t in tr])
        L.append(f"| {u} | {len(tr) / years:.0f} | {len(wins) / len(tr):.0%} | "
                 f"{mean(wins):+.1%} / {mean(losses):+.1%} | {mean(nets):+.2%} | {ex:+.2%} | "
                 f"₹{len(tr) / years * ex * 45_000:,.0f} | ₹{mv / 1e7:,.1f} cr | {45_000 / mv:.3%} | {450_000 / mv:.2%} |")
    L += ["", "Trades/yr is every signal; the live book takes fewer (cash limit at 9% per slot).", ""]
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--validate-oos", action="store_true")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args(argv)
    if args.check:
        return cmd_check()
    if args.validate_oos:
        return cmd_validate(args.workers)
    return cmd_run(args.workers)


if __name__ == "__main__":
    sys.exit(main())
