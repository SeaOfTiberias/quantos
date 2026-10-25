"""
QuantOS — Regime inputs for structure choice: IV rank and velocity
───────────────────────────────────────────────────────────────────
Two numbers the 2026-10-25 reviews (HDFC Bank, Gemini) said were missing
from the structure step. Both are context, not rules: pick_structure shows
them and warns, the ranking ignores them, and the reviewer reads them.

  IV rank   today's ATM implied vol against the last 252 sessions' end-of-day
            ATM IV for the same stock (min 200), 0 = the year's low, 1 = its
            high. High favours selling premium (credit), low favours buying it
            (debit). Same method as the surge put-credit study
            (core/surge/put_credit.py): nearest expiry with >= 5 trading days,
            the strike nearest the future, Black-76 on the CE and PE, averaged.
            Today's value comes from live mids, the history from bhavcopy
            closes.
  velocity  how fast the view needs the stock to move:
            k = |target - spot| / (ATR x sqrt(days)).
            drift k <= 0.5, normal <= 1.0, fast > 1.0. A per-candidate k for
            the price at which a debit spread pays its maximum shows a
            structure that needs a faster move than the view does.
            The cut-offs are labels for reading, not a tested edge.

History file: ~/.quantos/atm_iv_history.csv (date,symbol,iv). Bootstrapped from
the surge study's bhavcopy pass; refresh() appends any newer daily bhavcopy in
~/.quantos/nse_fo_bhavcopy, so it maintains itself wherever reviews run.
No scipy (the VM doesn't have it).
"""

from __future__ import annotations

import csv
import math
from datetime import date
from pathlib import Path
from typing import Optional

IV_WINDOW, IV_MIN_OBS = 252, 200
IV_MIN_TDAYS = 5
IV_HIGH, IV_LOW = 0.70, 0.30
DRIFT_K, FAST_K = 0.5, 1.0
KEEP_ROWS = 320                      # sessions kept per symbol


# ─── Black-76, scalar ────────────────────────────────────────────────────────

def _ncdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def b76(F: float, K: float, T: float, vol: float, put: bool) -> float:
    sd = vol * math.sqrt(T)
    d1 = (math.log(F / K) + 0.5 * sd * sd) / sd
    call = F * _ncdf(d1) - K * _ncdf(d1 - sd)
    return call - F + K if put else call


def b76_iv(price: float, F: float, K: float, T: float, put: bool) -> Optional[float]:
    intrinsic = max(K - F, 0.0) if put else max(F - K, 0.0)
    if T <= 0 or F <= 0 or K <= 0 or price <= intrinsic + 1e-9 or price >= b76(F, K, T, 5.0, put):
        return None
    lo, hi = 0.01, 5.0
    for _ in range(60):
        m = (lo + hi) / 2
        lo, hi = (lo, m) if b76(F, K, T, m, put) > price else (m, hi)
    return (lo + hi) / 2


def atm_iv(F: float, K: float, ce: float, pe: float, T: float) -> Optional[float]:
    v = [x for x in (b76_iv(ce, F, K, T, False), b76_iv(pe, F, K, T, True)) if x]
    return sum(v) / len(v) if v else None


def _years(d: date, expiry: date) -> float:
    return max((expiry - d).days, 1) / 365.0


def _tdays(d: date, expiry: date) -> int:
    """Weekdays after d up to and including expiry (holidays ignored)."""
    n, x = 0, d.toordinal()
    for o in range(x + 1, expiry.toordinal() + 1):
        n += date.fromordinal(o).weekday() < 5
    return n


# ─── history ─────────────────────────────────────────────────────────────────

def load(path: Path) -> dict[str, list[tuple[date, float]]]:
    out: dict[str, list] = {}
    try:
        with path.open(newline="") as f:
            for r in csv.DictReader(f):
                out.setdefault(r["symbol"], []).append((date.fromisoformat(r["date"]), float(r["iv"])))
    except (OSError, KeyError, ValueError):
        return {}
    for v in out.values():
        v.sort()
    return out


def save(path: Path, hist: dict[str, list[tuple[date, float]]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "symbol", "iv"])
        for sym in sorted(hist):
            for d, iv in hist[sym][-KEEP_ROWS:]:
                w.writerow([d.isoformat(), sym, f"{iv:.5f}"])
    tmp.replace(path)


def rows_from_ivrows(ivrows) -> list[tuple[date, str, float]]:
    """(date, symbol, iv) from put_credit.pass1_day's (d, sym, expiry, F, K, ce, pe) tuples."""
    out = []
    for d, sym, e, F, K, ce, pe in ivrows:
        iv = atm_iv(F, K, ce, pe, _years(d, e))
        if iv:
            out.append((d, sym, iv))
    return out


def refresh(path: Path, bhav_dir: Path) -> int:
    """Append ATM IVs from every bhavcopy zip in `bhav_dir` newer than the history. Returns days added."""
    hist = load(path)
    if not hist:
        return 0
    last = max(v[-1][0] for v in hist.values())
    days = []
    for p in sorted(bhav_dir.glob("*.zip")):
        try:
            d = date(int(p.stem[:4]), int(p.stem[4:6]), int(p.stem[6:8]))
        except ValueError:
            continue
        if d > last:
            days.append((d, p))
    if not days:
        return 0
    from core.surge import put_credit as pc
    known = [d for v in hist.values() for d, _ in v[-30:]]
    cal = sorted(set(known) | {d for d, _ in days})
    added = 0
    for d, p in days:
        try:
            _, ivrows = pc.pass1_day((p, d, set(hist), cal))
        except Exception:
            continue
        for dd, sym, iv in rows_from_ivrows(ivrows):
            hist.setdefault(sym, []).append((dd, iv))
        added += 1
    if added:
        save(path, hist)
    return added


# ─── today ───────────────────────────────────────────────────────────────────

def live_atm_iv(chain) -> Optional[dict]:
    """ATM IV from a structure.Chain's live mids: the nearest expiry with >= 5 trading days."""
    exps = sorted({k[0] for k in chain.options if _tdays(chain.today, k[0]) >= IV_MIN_TDAYS})
    for e in exps:
        F = chain.futures[e].mid if e in chain.futures else (
            chain.futures[min(chain.futures)].mid if chain.futures else chain.spot)
        strikes = sorted({k[1] for k in chain.options if k[0] == e})
        if not strikes:
            continue
        K = min(strikes, key=lambda k: (abs(k - F), k))
        ce, pe = chain.options.get((e, K, "CE")), chain.options.get((e, K, "PE"))
        if not ce or not pe or ce.bid <= 0 or pe.bid <= 0:
            continue
        iv = atm_iv(F, K, ce.mid, pe.mid, _years(chain.today, e))
        if iv:
            return {"iv": iv, "expiry": e, "strike": K}
    return None


def iv_rank(iv_now: float, series: list[tuple[date, float]], today: date) -> Optional[dict]:
    past = [v for d, v in series if d < today][-IV_WINDOW:]
    if len(past) < IV_MIN_OBS:
        return None
    lo, hi = min(past), max(past)
    rank = (iv_now - lo) / (hi - lo) if hi > lo else 0.5
    rank = min(max(rank, 0.0), 1.0)
    label = "high" if rank >= IV_HIGH else "low" if rank <= IV_LOW else "mid"
    return {"rank": round(rank, 2), "label": label, "low_1y": round(lo, 4), "high_1y": round(hi, 4),
            "history_to": max(d for d, _ in series if d < today).isoformat(), "n": len(past)}


def iv_context(chain, history: Path, bhav_dir: Optional[Path] = None) -> dict:
    """{"iv", "rank", "label", ...} best effort; {"error": ...} when there's no live IV or history."""
    if bhav_dir is not None:
        try:
            refresh(history, bhav_dir)
        except Exception:
            pass
    now = live_atm_iv(chain)
    if not now:
        return {"error": "no live ATM IV"}
    out = {"iv": round(now["iv"], 4), "expiry": now["expiry"].isoformat(), "strike": now["strike"]}
    r = iv_rank(now["iv"], load(history).get(chain.symbol, []), chain.today)
    out.update(r or {"error": f"under {IV_MIN_OBS} sessions of IV history"})
    return out


def velocity_k(spot: float, price: float, atr: Optional[float], days: int) -> Optional[float]:
    if not atr or atr <= 0:
        return None
    return abs(price - spot) / (atr * math.sqrt(max(days, 1)))


def velocity_label(k: Optional[float]) -> Optional[str]:
    if k is None:
        return None
    return "drift" if k <= DRIFT_K else "normal" if k <= FAST_K else "fast"


def warnings(view: dict, velocity: Optional[dict], iv: dict, top: Optional[dict]) -> list[str]:
    """Plain-language mismatches between the view, the regime and the tool's top row. Advisory."""
    out = []
    thesis = view.get("thesis")
    lab = (velocity or {}).get("label")
    if thesis == "move" and lab == "fast":
        out.append(f"the target needs a fast move ({velocity['k']} ATR x sqrt(days)): the hit rate is likely "
                   f"below what a normal move would give -- check the view, or the horizon")
    if thesis == "move" and lab == "drift":
        out.append("the target is a drift-sized move: if_flat decides; an at-the-money debit or a credit "
                   "spread (--thesis hold) may fit better than an out-of-the-money long")
    fam = (top or {}).get("structure", "")
    if iv.get("label") == "high" and top and "credit" not in fam:
        out.append(f"IV rank {iv['rank']} (high): the long leg is expensive; compare the credit row")
    if iv.get("label") == "low" and "credit" in fam:
        out.append(f"IV rank {iv['rank']} (low): a credit spread collects little premium")
    return out
