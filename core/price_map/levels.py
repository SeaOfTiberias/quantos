"""
QuantOS — Price map: where a stock has done business, and where it turned
──────────────────────────────────────────────────────────────────────────
Pure. Bars in, levels out; no broker, no clock, no file. scripts/price_map.py
fetches the bars and writes the map; the position manager reads it.

Sources (each level carries its family, so agreement between families counts):

  swing     daily swing lows / highs (lowest low or highest high within +/-K sessions)
  volume    volume profile from intraday bars (each bar's volume spread evenly over
            its range): composite POC and value area, high-volume shelves, and the
            last sessions' POCs that later prices never traded back through (naked)
  pivot     classical (P, S1-S3, R1-R3) and Camarilla (L3/L4, H3/H4), from the
            last completed day, week and month

A zone is a cluster of levels within `width` (0.3 ATR by default) of each other.
Each level carries a weight (WEIGHTS): a swing that price left by >= 1 ATR or a
volume level 2, a weekly/monthly pivot 1, a daily pivot 0.5 (those are for
managing a trade intraday). A zone is STRONG at a score >= STRONG_SCORE with at
least two families agreeing. first_obstacle() is the nearest
strong zone in the trade's direction, measured in R.

These levels describe the market; that they predict a turn is not tested.
A map informs a plan; it never moves an order by itself.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta, timezone
from typing import Iterable, Optional

IST = timezone(timedelta(hours=5, minutes=30))
SWING_K = 5
VALUE_SHARE = 0.70
SHELF_X = 1.5          # a profile bucket this many times the median is a shelf
NAKED_SESSIONS = 20
STRONG_FAMILIES = 2
STRONG_SCORE = 4.0
WEIGHTS = {"swing": 2.0, "volume": 2.0, "pivot": 1.0}
DAILY_PIVOT_WEIGHT = 0.5
PIVOTS_KEPT = ("P", "S1", "S2", "R1", "R2")    # weekly / monthly classical; Camarilla on the daily only


@dataclass(frozen=True)
class Level:
    price:  float
    family: str          # swing | volume | pivot
    label:  str          # e.g. "swing low 2026-07-08", "weekly S2", "naked POC 2026-10-27"
    weight: float = 0.0  # 0 -> the family's WEIGHTS entry

    @property
    def score(self) -> float:
        return self.weight or WEIGHTS[self.family]


@dataclass
class Zone:
    low:      float
    high:     float
    levels:   list = field(default_factory=list)

    @property
    def mid(self) -> float:
        return round((self.low + self.high) / 2, 2)

    @property
    def families(self) -> set:
        return {lv.family for lv in self.levels}

    @property
    def score(self) -> float:
        return round(sum(lv.score for lv in self.levels), 2)

    @property
    def strong(self) -> bool:
        return len(self.families) >= STRONG_FAMILIES and self.score >= STRONG_SCORE

    def to_dict(self) -> dict:
        return {"low": self.low, "high": self.high, "mid": self.mid, "strong": self.strong, "score": self.score,
                "families": sorted(self.families), "levels": [asdict(lv) for lv in self.levels]}


# ─── Pivots ──────────────────────────────────────────────────────────────────

def classical(h: float, l: float, c: float) -> dict:
    p = (h + l + c) / 3
    return {"P": p, "S1": 2 * p - h, "S2": p - (h - l), "S3": l - 2 * (h - p),
            "R1": 2 * p - l, "R2": p + (h - l), "R3": h + 2 * (p - l)}


def camarilla(h: float, l: float, c: float) -> dict:
    r = h - l
    return {"L3": c - r * 1.1 / 4, "L4": c - r * 1.1 / 2, "H3": c + r * 1.1 / 4, "H4": c + r * 1.1 / 2}


def _hlc(bars: list) -> tuple:
    return max(b.high for b in bars), min(b.low for b in bars), bars[-1].close


def periods(daily: list, today: date) -> dict:
    """The last COMPLETED day, week and month before `today`, as (H, L, C)."""
    done = [b for b in daily if _d(b) < today]
    if not done:
        return {}
    weeks, months = defaultdict(list), defaultdict(list)
    for b in done:
        weeks[_d(b).isocalendar()[:2]].append(b)
        months[(_d(b).year, _d(b).month)].append(b)
    out = {"daily": _hlc([done[-1]])}
    this_week, this_month = today.isocalendar()[:2], (today.year, today.month)
    wk = [k for k in sorted(weeks) if k < this_week]
    mo = [k for k in sorted(months) if k < this_month]
    if wk:
        out["weekly"] = _hlc(weeks[wk[-1]])
    if mo:
        out["monthly"] = _hlc(months[mo[-1]])
    return out


def pivot_levels(daily: list, today: date) -> list[Level]:
    out = []
    for name, (h, l, c) in periods(daily, today).items():
        if name == "daily":
            out.append(Level(round(classical(h, l, c)["P"], 2), "pivot", "daily P", DAILY_PIVOT_WEIGHT))
            out += [Level(round(v, 2), "pivot", f"daily Camarilla {k}", DAILY_PIVOT_WEIGHT)
                    for k, v in camarilla(h, l, c).items()]
        else:
            out += [Level(round(v, 2), "pivot", f"{name} {k}") for k, v in classical(h, l, c).items() if k in PIVOTS_KEPT]
    return out


# ─── Swings ──────────────────────────────────────────────────────────────────

def swing_levels(daily: list, k: int = SWING_K, atr: float = 0.0) -> list[Level]:
    """Turns: the extreme within +/-k sessions that price then left by at least `atr` within k sessions."""
    out = []
    for i in range(k, len(daily) - 1):
        w = daily[max(0, i - k):i + k + 1]
        b, after = daily[i], daily[i + 1:i + k + 1]
        if b.low == min(x.low for x in w) and max(x.high for x in after) - b.low >= atr:
            out.append(Level(round(b.low, 2), "swing", f"swing low {_d(b)}"))
        if b.high == max(x.high for x in w) and b.high - min(x.low for x in after) >= atr:
            out.append(Level(round(b.high, 2), "swing", f"swing high {_d(b)}"))
    return out


# ─── Volume profile ──────────────────────────────────────────────────────────

def profile(bars: Iterable, step: float) -> dict:
    """Volume at each price bucket (bucket floor -> volume)."""
    h: dict = defaultdict(float)
    for b in bars:
        lo, hi = int(b.low // step), int(b.high // step)
        n = hi - lo + 1
        for k in range(lo, hi + 1):
            h[round(k * step, 2)] += b.volume / n
    return dict(h)


def value_area(h: dict, share: float = VALUE_SHARE) -> Optional[tuple]:
    """(POC, VAL, VAH): grow from the POC toward the heavier neighbour until `share` of volume."""
    if not h:
        return None
    ks = sorted(h)
    tot = sum(h.values())
    poc = max(ks, key=lambda k: h[k])
    i = j = ks.index(poc)
    acc = h[poc]
    while acc < share * tot and (i > 0 or j < len(ks) - 1):
        up = h[ks[j + 1]] if j + 1 < len(ks) else -1
        dn = h[ks[i - 1]] if i > 0 else -1
        if up >= dn:
            j += 1
            acc += up
        else:
            i -= 1
            acc += dn
    return poc, ks[i], ks[j]


def shelves(h: dict, step: float, x: float = SHELF_X) -> list[tuple]:
    """Runs of adjacent buckets at >= x times the median bucket: (low, high)."""
    if not h:
        return []
    vals = sorted(h.values())
    med = vals[len(vals) // 2]
    out, run = [], []
    for k in sorted(h):
        if h[k] >= x * med:
            if run and k - run[-1] > step + 1e-9:
                out.append((run[0], run[-1] + step))
                run = []
            run.append(k)
        elif run:
            out.append((run[0], run[-1] + step))
            run = []
    if run:
        out.append((run[0], run[-1] + step))
    return out


def sessions(bars: Iterable) -> dict:
    by = defaultdict(list)
    for b in bars:
        by[_d(b)].append(b)
    return dict(sorted(by.items()))


def naked_pocs(by_session: dict, step: float, n: int = NAKED_SESSIONS) -> list[tuple]:
    """(date, POC) for each of the last n sessions whose POC no later bar traded through."""
    days = list(by_session)
    out = []
    for i, d in enumerate(days[-n:], start=max(0, len(days) - n)):
        va = value_area(profile(by_session[d], step))
        if va is None:
            continue
        poc = va[0] + step / 2
        later = [b for dd in days[i + 1:] for b in by_session[dd]]
        if later and not any(b.low <= poc <= b.high for b in later):
            out.append((d, round(poc, 2)))
    return out


def volume_levels(intraday: list, step: float) -> tuple[list[Level], dict]:
    h = profile(intraday, step)
    va = value_area(h)
    out: list[Level] = []
    info: dict = {}
    if va:
        poc, val, vah = va
        info = {"poc": poc + step / 2, "val": val, "vah": vah + step}
        out += [Level(info["poc"], "volume", "composite POC"), Level(val, "volume", "value area low"),
                Level(info["vah"], "volume", "value area high")]
    info["shelves"] = shelves(h, step)
    for lo, hi in info["shelves"]:
        if hi - lo <= 4 * step:                       # a thin shelf is one level, not two edges
            out.append(Level(round((lo + hi) / 2, 2), "volume", f"shelf {lo:g}-{hi:g}"))
        else:
            out += [Level(lo, "volume", f"shelf {lo:g}-{hi:g} (low edge)"),
                    Level(hi, "volume", f"shelf {lo:g}-{hi:g} (high edge)")]
    by = sessions(intraday)
    info["naked_pocs"] = naked_pocs(by, step)
    out += [Level(p, "volume", f"naked POC {d}") for d, p in info["naked_pocs"]]
    info["recent"] = []
    for d in list(by)[-5:]:
        v = value_area(profile(by[d], step))
        if v:
            info["recent"].append({"date": d.isoformat(), "poc": v[0] + step / 2, "val": v[1], "vah": v[2] + step})
    return out, info


# ─── Zones ───────────────────────────────────────────────────────────────────

def zones(levels: list[Level], width: float) -> list[Zone]:
    """Cluster levels sorted by price: a level within `width` of the zone's last level joins it,
    as long as the zone stays within 1.5 x width (no chaining a ladder of levels into one band)."""
    out: list[Zone] = []
    for lv in sorted(levels, key=lambda x: x.price):
        if out and lv.price - out[-1].levels[-1].price <= width and lv.price - out[-1].low <= 1.5 * width:
            z = out[-1]
            z.levels.append(lv)
            z.high = lv.price
        else:
            out.append(Zone(lv.price, lv.price, [lv]))
    return out


def first_obstacle(zs: list, entry: float, side: int, r: float) -> Optional[dict]:
    """Nearest strong zone in the trade's direction (below a short, above a long), in R.
    Takes Zones or their to_dict() form (a map read back from JSON)."""
    if r <= 0:
        return None
    ds = [z.to_dict() if isinstance(z, Zone) else z for z in zs]
    ahead = [z for z in ds if z["strong"] and (z["mid"] - entry) * side > 0]
    if not ahead:
        return None
    z = min(ahead, key=lambda z: abs(z["mid"] - entry))
    near = z["high"] if side < 0 else z["low"]                 # the edge price meets first
    return {"zone": z, "edge": near, "r": round(abs(near - entry) / r, 2)}


def _d(b) -> date:
    t = b.timestamp
    return t.astimezone(IST).date() if getattr(t, "tzinfo", None) else (t.date() if hasattr(t, "date") else t)
