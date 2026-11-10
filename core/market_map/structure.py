"""
L1 structure: weekly and monthly bars, swing points, BOS / CHoCH, protected and weak
levels, and M/W/D alignment (sprint plan S5, slice 2; docs/MARKET_MAP_DEFINITIONS.md
v1, frozen 2026-11-05: §0, §1, §2, §7; amended by docs/MARKET_MAP_DEFINITIONS_V2.md,
2026-11-11: G1 structure follows the latest swings, G3 equal highs and lows are swings
and D EQH/EQL are shown, G4 sweeps and failed breaks are frozen).

Everything is point in time. A read for day D uses daily bars dated before D, and only the
weeks and months that closed before D's week and month. The swing zig-zag and the
structure run bar by bar, so a swing that a later, more extreme one replaces is still the
swing the structure used while it stood: nothing leaks backwards.

Choices v1 leaves open, fixed here before any golden-set chart was seen:
  - The zig-zag's 1-ATR test uses the ATR(TF) of the bar that confirms the new swing (the
    last value known when the swing is accepted). Swings confirmed before ATR has its 14
    bars are skipped.
  - A bar that is both a swing high and a swing low (an outside bar) is offered to the
    zig-zag opposite-kind first.
  - "The most recent confirmed swing high not yet broken": the latest swing high the
    zig-zag holds; once a close goes above it, there is no target until a new one is
    confirmed. Lows mirror.
  - v2 G1, a CHoCH reached both ways on one bar (a close below the latest swing low and
    the protected low): the level reported is the higher (nearer) of the two, and the new
    protected high is measured from that level's bar.
  - v2 G4: a sweep's ATR(TF) is the sweeping bar's; swings replaced by a more extreme one
    in the zig-zag stop being tracked.
  - From `none`, the first close above the latest swing high, or below the latest swing
    low, sets the state.
  - Age = completed bars since the bar of the event that started the state (0 = that
    event was the last completed bar).
  - A stock whose history has an unexplained drop of 35% or more (a new segment, see
    l1_store) is read from its latest segment only: earlier prices aren't comparable.

These rules are untested: no fidelity test (§9) has run yet. They describe structure;
they are not signals.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Optional

import numpy as np
import pandas as pd

from core.backtest.cci_cpr import wilder_atr

TF_K = {"M": 2, "W": 3, "D": 5}          # §1
ATR_N = 14                               # §0
SIZE_ATR = 1.0                           # §1 zig-zag
TFS = ("M", "W", "D")
UNTESTED = "untested"
DEFS = "definitions v2"
N_D_LIQ = 2                              # v2 G3: D EQH/EQL shown on each side of the price


# ─── §0 bars ─────────────────────────────────────────────────────────────────

def _period(dates: pd.Series, tf: str) -> pd.Series:
    if tf == "W":
        iso = dates.dt.isocalendar()
        return iso["year"].astype(int).astype(str) + "-W" + iso["week"].astype(int).map("{:02d}".format)
    if tf == "M":
        return dates.dt.strftime("%Y-%m")
    if tf == "Q":
        return dates.dt.year.astype(str) + "-Q" + dates.dt.quarter.astype(str)
    if tf == "Y":
        return dates.dt.year.astype(str)
    return dates.dt.strftime("%Y-%m-%d")


def period_of(d: date, tf: str) -> str:
    return _period(pd.Series([pd.Timestamp(d)]), tf).iat[0]


def resample(daily: pd.DataFrame, tf: str) -> pd.DataFrame:
    """Daily bars (date, o, h, l, c, vol) -> bars on `tf` (D, W = ISO week, M, Q, Y =
    calendar month, quarter, year): open first, high max, low min, close last, volume sum. Columns: period, start,
    date (the period's last session), o, h, l, c, vol."""
    d = daily.sort_values("date").reset_index(drop=True)
    p = _period(d["date"], tf)
    g = d.groupby(p, sort=False).agg(start=("date", "first"), date=("date", "last"), o=("o", "first"),
                                     h=("h", "max"), l=("l", "min"), c=("c", "last"), vol=("vol", "sum"))
    return g.rename_axis("period").reset_index()


def completed(daily: pd.DataFrame, tf: str, as_of: date) -> pd.DataFrame:
    """The `tf` bars a read for day `as_of` may use: daily bars before `as_of`, and on W and M
    only periods that closed before `as_of`'s own week or month."""
    d = daily[daily["date"] < pd.Timestamp(as_of)]
    bars = resample(d, tf) if len(d) else resample(daily.iloc[:0], tf)
    if tf != "D" and len(bars):
        bars = bars[bars["period"] != period_of(as_of, tf)]
    return bars.reset_index(drop=True)


def atr(bars: pd.DataFrame, n: int = ATR_N) -> np.ndarray:
    return wilder_atr(bars["h"].to_numpy(float), bars["l"].to_numpy(float), bars["c"].to_numpy(float), n)


# ─── §1 swings ───────────────────────────────────────────────────────────────

@dataclass
class Swing:
    kind: str                 # "H" or "L"
    i: int                    # bar of the extreme
    price: float
    confirm_i: int            # bar i + k: usable from here on
    label: str = ""           # HH / LH / HL / LL, or "" for the first of its kind
    broken: bool = False      # a close has gone beyond it
    swept: bool = False       # v2 G4: swept once


def candidates(h: np.ndarray, l: np.ndarray, k: int) -> dict[int, list[tuple[str, int, float]]]:
    """Raw swing points keyed by their confirmation bar (v2 G3): bar i's high strictly above
    the highs of the k bars before it and at least the highs of the k bars after it, so the
    first of a run of equal highs is the swing (lows mirror); confirmed on bar i + k."""
    out: dict[int, list] = {}
    for i in range(k, len(h) - k):
        if h[i] > h[i - k:i].max() and h[i] >= h[i + 1:i + k + 1].max():
            out.setdefault(i + k, []).append(("H", i, float(h[i])))
        if l[i] < l[i - k:i].min() and l[i] <= l[i + 1:i + k + 1].min():
            out.setdefault(i + k, []).append(("L", i, float(l[i])))
    return out


class ZigZag:
    """§1 size filter, fed one confirmed candidate at a time."""

    def __init__(self) -> None:
        self.kept: list[Swing] = []

    def last(self, kind: str) -> Optional[Swing]:
        for s in reversed(self.kept):
            if s.kind == kind:
                return s
        return None

    def _label(self, s: Swing) -> str:
        prev = self.last(s.kind)
        if prev is None:
            return ""
        if s.kind == "H":
            return "HH" if s.price > prev.price else "LH"
        return "LL" if s.price < prev.price else "HL"

    def offer(self, kind: str, i: int, price: float, confirm_i: int, atr_now: float) -> Optional[Swing]:
        """Returns the swing if it was kept (appended or replacing the last one)."""
        s = Swing(kind, i, price, confirm_i)
        if not self.kept:
            self.kept.append(s)
            return s
        last = self.kept[-1]
        if last.kind == kind:                    # two in a row: keep the more extreme
            if (price > last.price) if kind == "H" else (price < last.price):
                self.kept.pop()
                s.label = self._label(s)
                self.kept.append(s)
                return s
            return None
        if abs(price - last.price) < SIZE_ATR * atr_now:
            return None
        s.label = self._label(s)
        self.kept.append(s)
        return s


# ─── §2 structure (v2 G1) and sweeps (v2 G4) ──────────────────────────────────

N_EVENTS = 5                     # BOS / CHoCH shown per timeframe
N_SWEEPS = 3                     # sweeps and failed breaks shown per timeframe
SWEEP_ATR = 0.1                  # v2 G4: minimum overshoot, in ATR(TF)
FAIL_BARS = 3                    # v2 G4: a break closed back inside within 3 bars failed
SWEEP_NOTE = "frozen v2"


@dataclass
class Level:
    price: float
    i: int


@dataclass
class Structure:
    state: str = "none"
    events: list[dict] = field(default_factory=list)
    protected: Optional[Level] = None
    weak: Optional[Level] = None
    state_i: Optional[int] = None
    swings: list[Swing] = field(default_factory=list)
    sweeps: list[dict] = field(default_factory=list)
    failed: list[dict] = field(default_factory=list)
    n: int = 0


def _ext(a: np.ndarray, i0: int, i1: int, hi: bool) -> Level:
    seg = a[i0:i1 + 1]
    j = int(np.argmax(seg) if hi else np.argmin(seg))
    return Level(float(seg[j]), i0 + j)


def run(bars: pd.DataFrame, k: int, atr_arr: Optional[np.ndarray] = None) -> Structure:
    """§1 + §2 as amended by v2 (G1, G3, G4), one bar at a time.

    Up break: a close above the most recent confirmed swing high not yet broken (BOS in
    `up` or from `none`, CHoCH in `down`); a close below the protected low in `up` is also
    a CHoCH. The protected low is set after every up break (lowest low from the broken
    swing high's bar to the break bar) and moves to each newer swing low confirmed while
    the state is `up`. Down breaks mirror. Sweeps and failed breaks are tracked on every
    confirmed zig-zag swing not yet broken by a close."""
    h, l, c = (bars[x].to_numpy(float) for x in ("h", "l", "c"))
    a = atr(bars) if atr_arr is None else np.asarray(atr_arr, float)
    cand = candidates(h, l, k)
    zz = ZigZag()
    st = Structure(n=len(bars))
    brk_i = None                                         # bar of the last break in the state's direction
    live: list[Swing] = []                               # confirmed swings not yet broken by a close
    pending: list[tuple[Swing, int]] = []                # (swing, break bar) waiting for a failed break

    def event(t, typ, direction, level):
        st.events.append(dict(type=typ, direction=direction, i=t, level=level))

    def prot():                                          # the protected bar set by the last event (§3.3)
        st.events[-1]["prot_i"] = st.protected.i

    wk = None                                            # the running weak extreme since brk_i
    for t in range(len(bars)):
        hi, lo = zz.last("H"), zz.last("L")
        up_ok = hi is not None and not hi.broken and c[t] > hi.price
        dn_ok = lo is not None and not lo.broken and c[t] < lo.price
        if st.state == "none":
            if up_ok:
                st.state, st.state_i, brk_i = "up", t, t
                st.protected = _ext(l, hi.i, t, hi=False)
                event(t, "BOS", "up", hi.price); prot()
            elif dn_ok:
                st.state, st.state_i, brk_i = "down", t, t
                st.protected = _ext(h, lo.i, t, hi=True)
                event(t, "BOS", "down", lo.price); prot()
        elif st.state == "up":
            if up_ok:
                st.protected, brk_i = _ext(l, hi.i, t, hi=False), t
                event(t, "BOS", "up", hi.price); prot()
            elif dn_ok or c[t] < st.protected.price:
                by_swing = dn_ok and lo.price >= st.protected.price
                lvl = Level(lo.price, lo.i) if by_swing else st.protected
                event(t, "CHoCH", "down", lvl.price)
                st.protected = _ext(h, lvl.i, t, hi=True); prot()
                st.state, st.state_i, brk_i = "down", t, t
        else:
            if dn_ok:
                st.protected, brk_i = _ext(h, lo.i, t, hi=True), t
                event(t, "BOS", "down", lo.price); prot()
            elif up_ok or c[t] > st.protected.price:
                by_swing = up_ok and hi.price <= st.protected.price
                lvl = Level(hi.price, hi.i) if by_swing else st.protected
                event(t, "CHoCH", "up", lvl.price)
                st.protected = _ext(l, lvl.i, t, hi=False); prot()
                st.state, st.state_i, brk_i = "up", t, t
        if st.state != "none":
            x = float(h[t] if st.state == "up" else l[t])
            wk = x if brk_i == t or wk is None else (max(wk, x) if st.state == "up" else min(wk, x))

        # G4: failed breaks, then sweeps and breaks of the live swings
        wait = []
        for sw, b in pending:
            if t - b > FAIL_BARS:
                continue
            if (c[t] <= sw.price) if sw.kind == "H" else (c[t] >= sw.price):
                st.failed.append(dict(side="high" if sw.kind == "H" else "low", level=sw.price, break_i=b, i=t,
                                      close=float(c[t])))
                continue
            wait.append((sw, b))
        pending = wait
        tol = SWEEP_ATR * a[t] if not np.isnan(a[t]) else None
        still = []
        for sw in live:
            beyond = (c[t] > sw.price) if sw.kind == "H" else (c[t] < sw.price)
            if beyond:
                sw.broken = True
                pending.append((sw, t))
                continue
            still.append(sw)
            over = (h[t] - sw.price) if sw.kind == "H" else (sw.price - l[t])
            if tol is not None and not sw.swept and over >= tol:
                sw.swept = True
                st.sweeps.append(dict(side="high" if sw.kind == "H" else "low", i=t, level=sw.price,
                                      extreme=float(h[t] if sw.kind == "H" else l[t]), swing_i=sw.i))
        live = still

        if t in cand and not np.isnan(a[t]):
            kinds = sorted(cand[t], key=lambda x: x[0] == (zz.kept[-1].kind if zz.kept else "L"))
            for kind, i, p in kinds:                     # outside bar: opposite kind first
                before = zz.kept[-1] if zz.kept else None
                kept = zz.offer(kind, i, p, t, float(a[t]))
                if kept is None:
                    continue
                if before is not None and before is not kept and before.kind == kind:
                    live = [x for x in live if x is not before]   # replaced by a more extreme swing
                closes = c[i + 1:t + 1]
                if (closes > p).any() if kind == "H" else (closes < p).any():
                    kept.broken = True                   # already closed beyond before confirmation
                else:
                    live.append(kept)
                # G1: a newer swing against the trend becomes the protected level
                if st.protected is not None and i > st.protected.i and (
                        (st.state == "up" and kind == "L") or (st.state == "down" and kind == "H")):
                    st.protected = Level(p, i)

    if st.state != "none":
        st.weak = _ext(h if st.state == "up" else l, brk_i, len(bars) - 1, hi=st.state == "up")
    st.swings = zz.kept
    return st


# ─── outputs ─────────────────────────────────────────────────────────────────

def _lvl(bars: pd.DataFrame, x: Optional[Level]) -> Optional[dict]:
    if x is None:
        return None
    return dict(price=round(x.price, 2), period=bars["period"].iat[x.i], date=bars["date"].iat[x.i].date().isoformat())


def summary(bars: pd.DataFrame, st: Structure, tf: str, n_swings: int = 6) -> dict:
    """§2's output per timeframe, plus the last swings with their labels."""
    last = st.events[-1] if st.events else None
    a = atr(bars) if len(bars) else np.array([])
    return dict(
        tf=tf, k=TF_K.get(tf), bars=len(bars),
        last_bar=bars["period"].iat[-1] if len(bars) else None,
        atr=round(float(a[-1]), 2) if len(a) and not np.isnan(a[-1]) else None,
        state=st.state,
        last_event=None if last is None else dict(
            type=last["type"], direction=last["direction"], level=round(last["level"], 2),
            period=bars["period"].iat[last["i"]], date=bars["date"].iat[last["i"]].date().isoformat()),
        protected=_lvl(bars, st.protected), weak=_lvl(bars, st.weak),
        age_bars=None if st.state_i is None else len(bars) - 1 - st.state_i,
        events=[dict(type=e["type"], direction=e["direction"], level=round(e["level"], 2),
                     period=bars["period"].iat[e["i"]], date=bars["date"].iat[e["i"]].date().isoformat())
                for e in st.events[-N_EVENTS:]],
        sweeps=[dict(side=w["side"], level=round(w["level"], 2), extreme=round(w["extreme"], 2),
                     swing=bars["period"].iat[w["swing_i"]],
                     period=bars["period"].iat[w["i"]], date=bars["date"].iat[w["i"]].date().isoformat(),
                     status=SWEEP_NOTE) for w in st.sweeps[-N_SWEEPS:]],
        failed_breaks=[dict(side=w["side"], level=round(w["level"], 2), close=round(w["close"], 2),
                            broke=bars["period"].iat[w["break_i"]],
                            period=bars["period"].iat[w["i"]], date=bars["date"].iat[w["i"]].date().isoformat(),
                            status=SWEEP_NOTE) for w in st.failed[-N_SWEEPS:]],
        swings=[dict(kind=s.kind, label=s.label, price=round(s.price, 2), period=bars["period"].iat[s.i],
                     confirmed=bars["period"].iat[s.confirm_i]) for s in st.swings[-n_swings:]],
    )


def alignment(states: dict[str, str]) -> dict:
    """§7: aligned up / down when M, W and D agree; otherwise the timeframes that conflict
    with the majority (all three when there is none)."""
    vals = [states.get(t, "none") for t in TFS]
    if all(v == "up" for v in vals):
        return dict(aligned="up", conflicts=[], text="aligned up")
    if all(v == "down" for v in vals):
        return dict(aligned="down", conflicts=[], text="aligned down")
    counts = {v: vals.count(v) for v in set(vals)}
    major = max(counts, key=counts.get)
    if counts[major] >= 2:
        conf = [t for t, v in zip(TFS, vals) if v != major]
        text = f"not aligned: {major} on {', '.join(t for t in TFS if t not in conf)}, " + \
               ", ".join(f"{t} {states.get(t, 'none')}" for t in conf)
    else:
        conf = list(TFS)
        text = "not aligned: " + ", ".join(f"{t} {v}" for t, v in zip(TFS, vals))
    return dict(aligned=None, conflicts=conf, text=text)


def latest_segment(adj: pd.DataFrame) -> pd.DataFrame:
    if "seg" in adj and len(adj):
        adj = adj[adj["seg"] == adj["seg"].iat[-1]]
    return adj.reset_index(drop=True)


def l1_read(daily: pd.DataFrame, as_of: date, m5: Optional[pd.DataFrame] = None) -> dict:
    """The L1 structure read for day `as_of` from adjusted daily bars (date, o, h, l, c, vol;
    seg if present)."""
    seg = latest_segment(daily)
    out = {"as_of": as_of.isoformat(), "status": UNTESTED, "definitions": DEFS,
           "history_from": seg["date"].iat[0].date().isoformat() if len(seg) else None,
           "segment_break": bool(len(seg) < len(daily))}
    from core.market_map import zones as zn             # zones builds on this module
    tfs, zs, swings_all = {}, [], {}
    dbars = completed(seg, "D", as_of)
    price = float(dbars["c"].iat[-1]) if len(dbars) else None
    for tf in TFS:
        bars = completed(seg, tf, as_of)
        if not len(bars):
            tfs[tf] = dict(tf=tf, bars=0, state="none")
            continue
        r = run(bars, TF_K[tf])
        tfs[tf] = summary(bars, r, tf)
        tfs[tf]["premium_discount"] = zn.premium_discount(tfs[tf], price)
        if tf in ("M", "W"):
            for v in zn.tf_zones(bars, r, tf).values():
                zs += v
            swings_all[tf] = [(w.kind, w.label, w.price, bars["period"].iat[w.i]) for w in r.swings
                              if not w.broken]                        # v2 G2: unbroken swings only
        else:                                                         # v2 G3: D EQH/EQL, shown, never clustered
            eq = [z for z in zn.equal_levels(bars, r.swings, atr(bars)) if z["status"] == "active"]
            if price is not None:
                tfs[tf]["liquidity"] = dict(
                    above=sorted([z for z in eq if z["level"] > price], key=lambda z: z["level"])[:N_D_LIQ],
                    below=sorted([z for z in eq if z["level"] < price], key=lambda z: -z["level"])[:N_D_LIQ])
    from core.market_map import pivots as pv
    out["pivots"] = pv.all_pivots({tf: completed(seg, tf, as_of) for tf in pv.PERIODS})
    from core.market_map import profiles as pf
    if m5 is not None and len(m5) and len(seg):
        m5 = m5[m5["date"] >= seg["date"].iat[0]]
    out["profiles"] = pf.read(seg, as_of, price, m5) if len(seg) else None
    from core.market_map import daily as dl             # L2: shown beside the zones, never in them (§8)
    out["l2"] = dl.read(seg, as_of, price, m5) if len(seg) else None
    out["price"] = price
    out["tf"] = tfs
    out["alignment"] = alignment({t: tfs[t]["state"] for t in TFS})
    out["zones"] = zs
    from core.market_map import htf
    atr_w = tfs.get("W", {}).get("atr")
    els = htf.elements(out, swings_all)
    allz = htf.htf_zones(els, atr_w)
    strong = [z for z in allz if z["strong"]]
    out["htf"] = dict(status=UNTESTED, source=htf.SOURCE, atr_w=atr_w, rule=htf.RULE,
                      width=round(htf.HTF_ATR * atr_w, 2) if atr_w else None,
                      n_elements=len(els), n_zones=len(allz),
                      zones=[htf.compact(z) for z in allz],
                      strong=[htf.compact(z) for z in strong],
                      hot=htf.hot_zones(els, atr_w, out, strong))
    return out


ZONE_NAMES = {"demand": "demand", "supply": "supply", "bull_ob": "bull OB", "bear_ob": "bear OB",
              "multi_touch": "multi-touch", "EQH": "EQH", "EQL": "EQL"}


def nearest_zones(l1: dict, n: int = 2) -> tuple[list[dict], list[dict], list[dict]]:
    """Valid zones (EQH/EQL only while active): those around the price, then those wholly
    below and wholly above it, nearest first."""
    px = l1.get("price")
    if px is None:
        return [], [], []
    zs = [z for z in l1.get("zones", []) if z["kind"] not in ("EQH", "EQL") or z["status"] == "active"]
    inside = sorted([z for z in zs if z["lo"] <= px <= z["hi"]], key=lambda z: z["hi"] - z["lo"])
    below = sorted([z for z in zs if z["hi"] < px], key=lambda z: px - z["hi"])
    above = sorted([z for z in zs if z["lo"] > px], key=lambda z: z["lo"] - px)
    return inside[:n], below[:n], above[:n]


def _zfmt(z: dict) -> str:
    rng = f"{z['lo']:.2f}-{z['hi']:.2f}" if z["hi"] - z["lo"] > 1e-9 else f"{z['lo']:.2f}"
    return f"{ZONE_NAMES[z['kind']]} {z['tf']} {rng}"


def lines(l1: dict) -> list[str]:
    """The L1 read as text, under the map read's lines."""
    if not l1 or "error" in l1:
        return [f"L1   none ({(l1 or {}).get('error', 'no read')})"]
    seg = f", history from {l1['history_from']} (segment break)" if l1.get("segment_break") else ""
    out = [f"L1   structure ({l1['status']}: no fidelity test yet{seg}) -- {l1['alignment']['text']}"]
    for tf in TFS:
        s = l1["tf"][tf]
        if s["state"] == "none":
            out.append(f"     {tf}: none ({s['bars']} bars)")
            continue
        e, p, w = s["last_event"], s["protected"], s["weak"]
        pk, wk = ("low", "high") if s["state"] == "up" else ("high", "low")
        out.append(f"     {tf}: {s['state']} for {s['age_bars']} bars; last {e['type']} {e['direction']} "
                   f"{e['period']} at {e['level']:g}; protected {pk} {p['price']:g} ({p['period']}), "
                   f"weak {wk} {w['price']:g} ({w['period']})"
                   + (f"; {s['premium_discount']['side']} {s['premium_discount']['position_pct']:g}%"
                      if s.get("premium_discount") else ""))
        if s.get("sweeps"):
            w = s["sweeps"][-1]
            out.append(f"        last sweep: swing {w['side']} {w['level']:g} ({w['swing']}) taken to {w['extreme']:g} "
                       f"on {w['date']}, closed back inside ({w['status']})")
        if s.get("failed_breaks"):
            w = s["failed_breaks"][-1]
            out.append(f"        last failed break: swing {w['side']} {w['level']:g} closed beyond in {w['broke']}, "
                       f"back inside on {w['date']} at {w['close']:g} ({w['status']})")
        if s.get("liquidity"):
            q = s["liquidity"]
            f = (lambda zs: "; ".join(f"{z['kind']} {z['level']:g} ({', '.join(z['swings'])})" for z in zs) or "none")
            out.append(f"        D equal highs/lows (shown, not in the HTF zones): above {f(q['above'])} | "
                       f"below {f(q['below'])}")
    if "zones" in l1:
        inside, below, above = nearest_zones(l1)
        out.append(f"     zones (untested) below: {'; '.join(map(_zfmt, below)) or 'none'} | "
                   f"above: {'; '.join(map(_zfmt, above)) or 'none'}"
                   + (f" | inside: {'; '.join(map(_zfmt, inside))}" if inside else ""))
    if l1.get("htf") and l1.get("price") is not None:
        from core.market_map import htf
        n = htf.nearest_strong(l1["htf"]["strong"], l1["price"])
        f = (lambda z: f"{z['low']:g}-{z['high']:g} [{'+'.join(z['families'])}] ({z['why']})" if z else "none")
        out.append(f"     HTF strong zones (untested; 2+ families incl. structure, imbalance or liquidity; "
                   f"{l1['htf'].get('rule', '')}, 0.3 ATR(W) = {l1['htf']['width']}): "
                   f"below {f(n['below'])} | above {f(n['above'])}" + (f" | inside {f(n['inside'])}" if n["inside"] else ""))
        hot = l1["htf"]["hot"]
        g = "; ".join(f"{x['tf']} {x['member']} {x['price']:g}" + (f" {x['direction']}" if x["direction"] else "")
                      for x in hot["gpz"])
        out.append(f"     hot zones (Ochoa, recorded only): {len(hot['dpz'])} DPZ, "
                   f"{sum(x['mtz'] for x in hot['dpz'])} multi-timeframe; GPZ: {g or 'none'}")
    if l1.get("pivots"):
        from core.market_map import pivots as pv
        out += pv.lines(l1["pivots"], l1.get("price"))
    if l1.get("profiles"):
        from core.market_map import profiles as pf
        out += pf.lines(l1["profiles"], l1.get("price"))
    if l1.get("l2"):
        from core.market_map import daily as dl
        out += dl.lines(l1["l2"], l1.get("price"))
    return out
