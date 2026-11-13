"""
Playbook v1 S8 test (docs/MARKET_PLAYBOOK_S8_PREREG_2026-11-13.md, approved and frozen 1cebb0f
before this code): the pieces the runner (scripts/playbook_s8.py) is built from, each unit-
tested on synthetic bars.

  universe_table     the Store.universe rule for every session at once
  p1_read_dates      first session of each even ISO week in the read period
  segment_at         the price segment a historical read must use (prereg §1)
  SegBars            a segment resampled once (structure.completed without the re-resampling)
  p1_gate            W in a trend and M not against it (P1's own first check)
  p2_triggers        the session after each D CHoCH (prereg §2)
  compact_read       what the test keeps from a full L1 read
  placebo_setups     §4.1: same trade, entry band at a random zone-free level in the discount
  market_setup       §4.1 (reported only): enter at the next open, same risk
  plan_p2_control    §4.2: the shift after a plain break instead of a sweep
  score              R per setup, net of the stressed delivery costs (§3)
  month_boot / holm  §5
  verdict            §6

Every price and R comes from core.market_map.playbook; this module adds no trading rule.
"""

from __future__ import annotations

import hashlib
import math
import random
from bisect import bisect_left
from collections import defaultdict
from datetime import date
from typing import Iterable, Optional

import numpy as np
import pandas as pd

from core.market_map import playbook as pb
from core.market_map import structure as st
from core.market_map import zones as zn

READ_START, READ_END = date(2013, 1, 1), date(2026, 8, 31)
K_PLACEBO, DRAWS = 3, 200
EXCL_SESSIONS = 60
CASES = [("KEI", "2025-06-23"), ("DMART", "2026-08-28"), ("JSL", "2026-03-04"), ("LTM", "2026-10-13"),
         ("HCLTECH", "2025-07-14"), ("ANTELOPUS", "2026-08-24"), ("NEOGEN", "2026-10-21"), ("GRSE", "2026-08-07"),
         ("IRFC", "2025-07-28"), ("TEJASNET", "2025-04-21"), ("BIOCON", "2026-05-13"), ("SSWL", "2025-09-17"),
         ("BLUESTARCO", "2025-08-07"), ("NBCC", "2025-05-30"), ("CHOLAFIN", "2024-12-19")]
LATE_EXCL = {"HDFCBANK": date(2026, 9, 1), "SUPREMEIND": date(2026, 9, 1)}
POSITION_RS = 100_000.0
ERA_SPLIT = date(2020, 1, 1)
BOOT_N, BOOT_SEED = 10_000, 20261113
MIN_DIFF = 0.10
P1_MIN_FILLS, P1_MIN_MATCHED, MIN_SIDE = 300, 300, 100
P2_MIN_FILLS, P2_MIN_CONTROL = 200, 200
P1_MIN_PROJECTED = 600
ALPHA = 0.05


# ─── calendar, universe, segments ────────────────────────────────────────────

def p1_read_dates(sessions: Iterable[date]) -> list[date]:
    """The first session of each even-numbered ISO week inside the read period."""
    out, seen = [], set()
    for d in sorted(sessions):
        if not READ_START <= d <= READ_END:
            continue
        y, w, _ = d.isocalendar()
        if w % 2 == 0 and (y, w) not in seen:
            seen.add((y, w))
            out.append(d)
    return out


def universe_table(raw: dict, etfs: Iterable[str] = (), top_n: int = 500, med_n: int = 60) -> dict:
    """{session d: frozenset of symbols}: Store.universe(d) for every d at once. Traded EQ on d,
    at least `med_n` rows up to d, ranked by the median traded value of the last `med_n` rows
    (ties by symbol). A read on D uses the set of the session before D."""
    etfs, frames = set(etfs), []
    for sym, g in raw.items():
        if sym in etfs or len(g) < med_n:
            continue
        med = g["val"].astype(float).rolling(med_n).median()
        ok = ((g["series"] == "EQ") & med.notna()).to_numpy()
        if ok.any():
            frames.append(pd.DataFrame({"date": g["date"].to_numpy()[ok], "sym": sym, "med": med.to_numpy()[ok]}))
    if not frames:
        return {}
    df = pd.concat(frames, ignore_index=True)
    df["neg"] = -df["med"]
    df = df.sort_values(["date", "neg", "sym"], kind="mergesort")
    df = df[df.groupby("date").cumcount() < top_n]
    return {pd.Timestamp(d).date(): frozenset(g["sym"]) for d, g in df.groupby("date")}


def segment_at(adj: pd.DataFrame, as_of: date) -> pd.DataFrame:
    """The segment that holds the last completed bar before `as_of` (prereg §1); playbook and
    structure then take it as the 'latest' segment, so nothing from another segment leaks in."""
    before = adj[adj["date"] < pd.Timestamp(as_of)]
    if not len(before):
        return adj.iloc[0:0].reset_index(drop=True)
    if "seg" not in adj:
        return adj.reset_index(drop=True)
    return adj[adj["seg"] == before["seg"].iat[-1]].reset_index(drop=True)


def excluded(sym: str, d: date, sessions: list[date]) -> bool:
    """Within 60 sessions of a case that shaped the rules (prereg §1)."""
    if sym in LATE_EXCL and d >= LATE_EXCL[sym]:
        return True
    i = bisect_left(sessions, d)
    for s, c in CASES:
        if s == sym:
            j = bisect_left(sessions, date.fromisoformat(c))
            if abs(i - j) <= EXCL_SESSIONS:
                return True
    return False


# ─── reads ───────────────────────────────────────────────────────────────────

class SegBars:
    """One segment resampled once. `completed(tf, as_of)` equals structure.completed(seg, tf,
    as_of): a period other than as_of's own is either wholly before as_of or wholly after it,
    so filtering the full resample gives the same bars (unit-tested). `at(nxt)` is
    playbook._States.at on these bars, with the same cache key."""

    def __init__(self, seg: pd.DataFrame):
        self.seg = seg
        self.full = {tf: st.resample(seg, tf) for tf in ("M", "W", "D")}
        self.dates = {tf: self.full[tf]["date"].to_numpy() for tf in self.full}
        self.cache = {}

    def completed(self, tf: str, as_of: date) -> pd.DataFrame:
        f = self.full[tf]
        n = int(np.searchsorted(self.dates[tf], np.datetime64(pd.Timestamp(as_of)), side="left"))
        bars = f.iloc[:n]
        if tf != "D" and len(bars) and bars["period"].iat[-1] == st.period_of(as_of, tf):
            bars = bars.iloc[:-1]
        return bars.reset_index(drop=True)

    def summary(self, tf: str, as_of: date) -> dict:
        bars = self.completed(tf, as_of)
        key = (tf, len(bars))
        if key not in self.cache:
            self.cache[key] = st.summary(bars, st.run(bars, st.TF_K[tf]), tf) if len(bars) else dict(state="none")
        return self.cache[key]

    def at(self, nxt: date) -> dict:
        return {tf: self.summary(tf, nxt) for tf in ("M", "W", "D")}


def p1_gate(sb: SegBars, as_of: date) -> bool:
    """P1's first check (W trend, M not the opposite) on the same bars l1_read uses."""
    w = sb.summary("W", as_of)["state"]
    if w not in ("up", "down"):
        return False
    return sb.summary("M", as_of)["state"] != ("down" if w == "up" else "up")


def d_events(seg: pd.DataFrame) -> list[dict]:
    return st.run(seg, st.TF_K["D"]).events if len(seg) else []


def p2_triggers(seg: pd.DataFrame) -> list[tuple[date, str]]:
    """(the session after the CHoCH bar, direction) for every D CHoCH in the segment."""
    dates = seg["date"]
    return [(dates.iat[ev["i"] + 1].date(), ev["direction"]) for ev in d_events(seg)
            if ev["type"] == "CHoCH" and ev["i"] + 1 < len(seg)]


def events_prefix_ok(seg: pd.DataFrame, cuts: Iterable[int]) -> bool:
    """Prereg §2 check: the D events of a run on the first n bars are the full run's events
    confirmed within those n bars."""
    full = [(e["type"], e["direction"], e["i"]) for e in d_events(seg)]
    for n in cuts:
        part = [(e["type"], e["direction"], e["i"]) for e in d_events(seg.iloc[:n])]
        if part != [e for e in full if e[2] < n]:
            return False
    return True


def compact_read(l1: dict) -> dict:
    """What the test keeps from a full read: enough for the placebo, E2 and the reports."""
    tf = l1["tf"]
    w = tf["W"]
    return dict(price=l1.get("price"), w_state=w.get("state"), m_state=tf["M"].get("state"),
                w_prot=(w.get("protected") or {}).get("price"), w_weak=(w.get("weak") or {}).get("price"),
                atr_d=(tf.get("D") or {}).get("atr"), atr_w=(l1.get("htf") or {}).get("atr_w"),
                zones=[(z["low"], z["high"]) for z in (l1.get("htf") or {}).get("zones", [])],
                opp_long=pb.opposing_strong(l1, True), opp_short=pb.opposing_strong(l1, False))


# ─── controls ────────────────────────────────────────────────────────────────

def rng_for(sym: str, d: date) -> random.Random:
    return random.Random(int(hashlib.sha256(f"{sym}|{d.isoformat()}".encode()).hexdigest()[:16], 16))


def placebo_setups(rd: dict, setup: dict, rng: random.Random, k: int = K_PLACEBO, draws: int = DRAWS) -> list[dict]:
    """§4.1: up to k bands of the real band's width, inside the W dealing range on the
    discount side (premium for shorts), entry beyond the price, overlapping no zone of the
    read; same stop rule, target, checks. None for an at-open setup."""
    if setup.get("status") != "SETUP" or setup.get("entry_at_open"):
        return []
    long = setup["side"] == "long"
    px, prot, weak, atr_d, atr_w = rd["price"], rd["w_prot"], rd["w_weak"], rd["atr_d"], rd["atr_w"]
    eq = (prot + weak) / 2
    width = (setup["entry"] - setup["far"]) if long else (setup["far"] - setup["entry"])
    if long:
        a, b = prot + width, min(px, eq)                   # range of the band's top
    else:
        a, b = max(px, eq), prot - width                   # range of the band's bottom
    out = []
    for _ in range(draws):
        if len(out) >= k or b <= a:
            break
        t = rng.uniform(a, b)
        lo, hi = (t - width, t) if long else (t, t + width)
        if any(lo <= zh and zl <= hi for zl, zh in rd["zones"]):
            continue
        entry = pb._down(hi) if long else pb._up(lo)
        if (entry >= px or entry >= eq) if long else (entry <= px or entry <= eq):
            continue
        stop = pb._down(lo - pb.BUF_ATR_D * atr_d) if long else pb._up(hi + pb.BUF_ATR_D * atr_d)
        risk = (entry - stop) if long else (stop - entry)
        reward = (setup["target"] - entry) if long else (entry - setup["target"])
        if risk <= 0 or reward <= 0 or reward / risk < pb.MIN_RR or risk > pb.RISK_CAP_ATR_W * atr_w:
            continue
        out.append(dict(setup, entry=entry, stop=stop, far=lo if long else hi, risk=round(risk, 2),
                        rr=round(reward / risk, 2), band=f"placebo {lo:.2f}-{hi:.2f}", entry_at_open=False))
    return out


def market_setup(rd: dict, setup: dict) -> dict:
    """Reported only: enter at the next open with the real setup's risk, target and rules."""
    long = setup["side"] == "long"
    px = rd["price"]
    stop = pb._down(px - setup["risk"]) if long else pb._up(px + setup["risk"])
    return dict(setup, entry=px, stop=stop, far=stop, risk=round(abs(px - stop), 2), entry_at_open=True,
                band="market entry")


def no_e3(setup: dict) -> dict:
    return dict(setup, swept_level=-math.inf if setup["side"] == "long" else math.inf)


def plan_p2_control(l1: dict, daily: pd.DataFrame, as_of: date, p2: Optional[dict] = None) -> dict:
    """§4.2: P2's context and shift with no qualifying sweep, where the 10 sessions before
    the CHoCH reached the W weak level (a plain break). Stop beyond that extreme; no E3."""
    p2 = p2 or pb.plan_p2(l1, daily, as_of)
    if "no sweep" not in (p2.get("reason") or ""):
        return pb._no("P2C", "no P2 context without a sweep")
    tf = l1["tf"]
    w = tf["W"]
    long = w["state"] == "down"
    side = "long" if long else "short"
    atr_d, atr_w = tf["D"]["atr"], l1["htf"]["atr_w"]
    d = st.completed(st.latest_segment(daily), "D", as_of)
    ev = st.run(d, st.TF_K["D"]).events[-1]
    lo_i = max(ev["i"] - pb.SHIFT_WINDOW, 0)
    if lo_i >= ev["i"]:
        return pb._no("P2C", "no bars before the shift", side=side)
    ext = float(d["l"].iloc[lo_i:ev["i"]].min()) if long else float(d["h"].iloc[lo_i:ev["i"]].max())
    weak = w["weak"]["price"]
    if (ext > weak) if long else (ext < weak):
        return pb._no("P2C", "the W weak level was not reached", side=side)
    obs = zn.order_blocks(d, [ev])
    if not obs:
        return pb._no("P2C", "the shift's D order block is already broken", side=side)
    ob = obs[0]
    entry = pb._down(ob["hi"]) if long else pb._up(ob["lo"])
    stop = pb._down(ext - pb.BUF_ATR_D * atr_d) if long else pb._up(ext + pb.BUF_ATR_D * atr_d)
    tgt = w["protected"]["price"]
    opp = [b for z in l1["htf"]["zones"] if z["strong"] for b in z.get("bands", [])
           if b["at_break"] and b["fresh"] and b["kind"] in (pb.BEAR if long else pb.BULL)]
    beyond = [(b["lo"] if long else b["hi"]) for b in opp if ((b["lo"] > entry) if long else (b["hi"] < entry))]
    if beyond:
        tgt = min(tgt, min(beyond)) if long else max(tgt, max(beyond))
    target = pb._down(tgt) if long else pb._up(tgt)
    risk = (entry - stop) if long else (stop - entry)
    reward = (target - entry) if long else (entry - target)
    base = dict(side=side, band=f"D {ob['kind']} {ob['lo']:g}-{ob['hi']:g}", entry=entry, stop=stop,
                target=target, risk=round(risk, 2))
    if risk <= 0 or reward <= 0:
        return pb._no("P2C", "entry, stop and target out of order", **base)
    base["rr"] = rr = round(reward / risk, 2)
    if risk > pb.RISK_CAP_ATR_W * atr_w:
        return pb._no("P2C", "break extreme too far", **base)
    if rr < pb.MIN_RR:
        return pb._no("P2C", f"only {rr:g}R", **base)
    return dict(setup="P2C", status="SETUP", reason="shift after a plain break (control)", entry_at_open=False,
                far=ext, valid=pb.VALID, half_risk=True, swept_level=-math.inf if long else math.inf, **base)


# ─── scoring ─────────────────────────────────────────────────────────────────

def _cost_model():
    from scripts.backtest_darvas_box_width import STRESSED_COST_MODEL
    return STRESSED_COST_MODEL


def score(setup: dict, res: dict, model=None) -> dict:
    """§3: R per setup. Unfilled = 0R. A trade still open when its segment's data ends is
    closed at the last close and flagged seg_end."""
    out = dict(outcome=res["outcome"], reason=res.get("reason"), end=res.get("end"), filled=False,
               gross_r=0.0, cost_r=0.0, net_r=0.0, seg_end=False)
    if res["outcome"] not in ("closed", "open"):
        return out
    long = setup["side"] == "long"
    fill = res["fill"]
    exit_px = res["exit"] if res["outcome"] == "closed" else res["mark"]
    risk = setup["risk"]
    gross = ((exit_px - fill) if long else (fill - exit_px)) / risk
    qty = max(1, int(POSITION_RS // fill))
    cost = (model or _cost_model()).cost_of(fill, exit_px, qty, "BUY" if long else "SELL") / (risk * qty)
    out.update(filled=True, fill=fill, exit=exit_px, gross_r=round(gross, 4), cost_r=round(cost, 4),
               net_r=round(gross - cost, 4), seg_end=res["outcome"] == "open", mfe=res.get("mfe"),
               mae=res.get("mae"), sessions=res.get("sessions"), risk_pct=round(100 * risk / fill, 3))
    return out


# ─── statistics ──────────────────────────────────────────────────────────────

def _month(d) -> str:
    return str(d)[:7]


def month_boot(groups: dict[str, list[tuple[str, float]]], stat, n: int = BOOT_N, seed: int = BOOT_SEED) -> dict:
    """Calendar-month block bootstrap. `groups`: name -> [(read date, value)]; `stat` maps
    {name: (sum, count)} to a number. Months are drawn with replacement from every month that
    has a row in any group; each draw takes all the rows of its months."""
    months = sorted({_month(d) for rows in groups.values() for d, _ in rows})
    idx = {m: i for i, m in enumerate(months)}
    S, C = {}, {}
    for g, rows in groups.items():
        s, c = np.zeros(len(months)), np.zeros(len(months))
        for d, v in rows:
            s[idx[_month(d)]] += v
            c[idx[_month(d)]] += 1
        S[g], C[g] = s, c
    point = stat({g: (S[g].sum(), C[g].sum()) for g in groups})
    if not months:
        return dict(point=point, lo=None, hi=None, p=None, months=0)
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, len(months), size=(n, len(months)))
    sums = {g: S[g][draws].sum(axis=1) for g in groups}
    cnts = {g: C[g][draws].sum(axis=1) for g in groups}
    vals = np.array([stat({g: (sums[g][i], cnts[g][i]) for g in groups}) for i in range(n)], dtype=float)
    vals = vals[~np.isnan(vals)]
    p = 2 * min((vals <= 0).mean(), (vals >= 0).mean()) if len(vals) else None
    return dict(point=point, lo=float(np.percentile(vals, 2.5)), hi=float(np.percentile(vals, 97.5)),
                p=min(1.0, float(p)), months=len(months))


def mean_of(g: str):
    return lambda t: t[g][0] / t[g][1] if t[g][1] else float("nan")


def diff_of(a: str, b: str):
    return lambda t: (t[a][0] / t[a][1] - t[b][0] / t[b][1]) if t[a][1] and t[b][1] else float("nan")


def holm(ps: dict[str, Optional[float]], alpha: float = ALPHA) -> dict[str, bool]:
    """Holm-Bonferroni: True where the hypothesis is rejected (passes)."""
    items = sorted([(p, k) for k, p in ps.items() if p is not None])
    out, m, stopped = {k: False for k in ps}, len(items), False
    for r, (p, k) in enumerate(items):
        if stopped or p > alpha / (m - r):
            stopped = True
            continue
        out[k] = True
    return out


def _mean(xs: list[float]) -> Optional[float]:
    return sum(xs) / len(xs) if xs else None


def p1_matched(rows: list[dict]) -> list[dict]:
    """Real P1 setups (scored, not excluded, not at-open) that have placebos, with the
    difference real net R − mean placebo net R."""
    pl = defaultdict(list)
    for r in rows:
        if r["track"] == "P1-placebo":
            pl[r["match"]].append(r["net_r"])
    out = []
    for r in rows:
        if r["track"] == "P1" and not r["excluded"] and pl.get(r["id"]):
            out.append(dict(r, diff=r["net_r"] - sum(pl[r["id"]]) / len(pl[r["id"]])))
    return out


def verdict(rows: list[dict], n: int = BOOT_N) -> dict:
    """§6 from the scored rows (one per setup: track, id, match, sym, read, side, at_open,
    excluded, filled, net_r, ...)."""
    sc = [r for r in rows if not r["excluded"]]
    p1 = [r for r in sc if r["track"] == "P1"]
    m = p1_matched(rows)
    a1 = month_boot({"x": [(r["read"], r["net_r"]) for r in p1]}, mean_of("x"), n)
    a2 = month_boot({"x": [(r["read"], r["diff"]) for r in m]}, mean_of("x"), n)
    p2 = [r for r in sc if r["track"] == "P2"]
    p2c = [r for r in sc if r["track"] == "P2C"]
    b1 = month_boot({"x": [(r["read"], r["net_r"]) for r in p2]}, mean_of("x"), n)
    b2 = month_boot({"a": [(r["read"], r["net_r"]) for r in p2], "b": [(r["read"], r["net_r"]) for r in p2c]},
                    diff_of("a", "b"), n)
    h = holm({"P1": a2["p"], "P2": b2["p"]})

    def era(xs, key, early):
        return _mean([r[key] for r in xs if (date.fromisoformat(r["read"]) < ERA_SPLIT) == early])

    eras = {e: dict(a1=era(p1, "net_r", e == "2013-2019"), a2=era(m, "diff", e == "2013-2019"),
                    b1=era(p2, "net_r", e == "2013-2019"),
                    b2=(lambda a, b: None if a is None or b is None else a - b)(
                        era(p2, "net_r", e == "2013-2019"), era(p2c, "net_r", e == "2013-2019")))
            for e in ("2013-2019", "2020-2026")}
    sides = {s: dict(n=len([r for r in m if r["side"] == s]), a2=_mean([r["diff"] for r in m if r["side"] == s]))
             for s in ("long", "short")}
    fills1 = sum(r["filled"] for r in p1)
    pos = lambda x: x is not None and x > 0
    judged = [s for s in sides if sides[s]["n"] >= MIN_SIDE]
    c = dict(
        A1=a1["lo"] is not None and a1["point"] > 0 and a1["lo"] > 0,
        A2=a2["point"] is not None and a2["point"] >= MIN_DIFF and h["P1"],
        A3=all(pos(eras[e]["a1"]) and pos(eras[e]["a2"]) for e in eras),
        A4=bool(judged) and all(pos(sides[s]["a2"]) for s in judged),
        A5=fills1 >= P1_MIN_FILLS and len(m) >= P1_MIN_MATCHED,
    )
    fills2 = sum(r["filled"] for r in p2)
    testable2 = fills2 >= P2_MIN_FILLS and len(p2c) >= P2_MIN_CONTROL
    c2 = dict(
        B1=b1["lo"] is not None and b1["point"] > 0 and b1["lo"] > 0,
        B2=b2["point"] is not None and not math.isnan(b2["point"]) and b2["point"] >= MIN_DIFF and h["P2"],
        B3=all(pos(eras[e]["b1"]) and pos(eras[e]["b2"]) for e in eras),
        B4=testable2,
    )
    one_sided = [s for s in sides if s not in judged]
    return dict(
        p1=dict(criteria=c, passed=all(c.values()), a1=a1, a2=a2, eras=eras, sides=sides, fills=fills1,
                setups=len(p1), matched=len(m), untested_sides=one_sided),
        p2=dict(criteria=c2, passed=all(c2.values()), testable=testable2, b1=b1, b2=b2, fills=fills2,
                setups=len(p2), control=len(p2c)),
        holm=h)
