"""
L1 price store: raw NSE daily bars, one small CSV per stock, plus the corporate actions,
adjusted when a stock is read (sprint plan S5, slice 1; definitions v1 §0).

Why per stock: the VM has under 1 GB of memory, so the 1.7 GB techno-funda panel can't
load there. A stock's file is about 4,000 rows; reading and adjusting it takes milliseconds.

Layout under the root (default ~/.quantos/l1_store, override QUANTOS_L1_STORE):
  bars/<SYM>.csv     date,series,o,h,l,c,vol,val   raw bhavcopy prices (EQ, BE, BZ; no ETFs)
  actions.json       {sym: [{ex, factor, purpose, source}]}   price factor per ex-date
  meta.json          {last_session, ...}
  raw/cm/, raw/pr/   the daily NSE files the refresh job downloaded
  universe.json      the top-500 list for the next session

Adjustment is `core.techno_funda.prices.adjust_symbol`, the same code as the techno-funda
panel. Filings can't be read from the VM (NSE's main site blocks it), so a big unexplained
drop is never confirmed there: it starts a new segment and is reported. The drops the PC
confirmed from filings up to 2026-10-23 are stored as actions (source "filings"), so the
VM's adjusted prices match the panel's.

Symbols are canonical (NSE's symbol-change file, chained per row date).
"""

from __future__ import annotations

import json
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable, Optional

import numpy as np
import pandas as pd

from core.techno_funda import prices as pr
from core.techno_funda.symbols import SymbolChain

COLS = ["date", "series", "o", "h", "l", "c", "vol", "val"]
TOP_N, MED_N = 500, 60          # same universe rule as the S3 / CCI tests


def default_root() -> Path:
    return Path(os.environ.get("QUANTOS_L1_STORE") or Path.home() / ".quantos" / "l1_store")


def _no_ratio(sym, day):        # filings aren't reachable from the VM
    return None


class Store:
    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = Path(root or default_root())
        self.bars = self.root / "bars"
        self.raw = self.root / "raw"
        self.actions_path = self.root / "actions.json"
        self.meta_path = self.root / "meta.json"
        self.universe_path = self.root / "universe.json"

    # ── meta ──────────────────────────────────────────────────────────────
    def meta(self) -> dict:
        try:
            return json.loads(self.meta_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}

    def set_meta(self, **kw) -> None:
        m = self.meta()
        m.update(kw)
        self.root.mkdir(parents=True, exist_ok=True)
        _atomic_write(self.meta_path, json.dumps(m, indent=1, default=str))

    def last_session(self) -> Optional[date]:
        s = self.meta().get("last_session")
        return date.fromisoformat(s) if s else None

    # ── bars ──────────────────────────────────────────────────────────────
    def symbols(self) -> list[str]:
        return sorted(p.stem for p in self.bars.glob("*.csv")) if self.bars.exists() else []

    def _path(self, sym: str) -> Path:
        return self.bars / f"{sym}.csv"

    def read_raw(self, sym: str) -> pd.DataFrame:
        """Raw bars, one row per date (a re-run append leaves duplicates: the last wins)."""
        p = self._path(sym)
        if not p.exists():
            return pd.DataFrame(columns=COLS)
        df = pd.read_csv(p, dtype={"series": str})
        df["date"] = pd.to_datetime(df["date"])
        return df.drop_duplicates("date", keep="last").sort_values("date").reset_index(drop=True)

    def write_symbol(self, sym: str, df: pd.DataFrame) -> None:
        self.bars.mkdir(parents=True, exist_ok=True)
        out = df[COLS].copy()
        out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
        _atomic_write(self._path(sym), out.to_csv(index=False, float_format="%.15g", lineterminator="\n"))

    def append_day(self, day: pd.DataFrame, d: date) -> int:
        """Append one session's rows (columns sym + COLS). Returns the row count."""
        self.bars.mkdir(parents=True, exist_ok=True)
        ds = d.isoformat()
        n = 0
        for r in day.itertuples(index=False):
            p = self._path(r.sym)
            new = not p.exists()
            with open(p, "a", encoding="utf-8", newline="\n") as f:
                if new:
                    f.write(",".join(COLS) + "\n")
                f.write(f"{ds},{r.series},{r.o:.15g},{r.h:.15g},{r.l:.15g},{r.c:.15g},{r.vol:.15g},{r.val:.15g}\n")
            n += 1
        return n

    # ── corporate actions ─────────────────────────────────────────────────
    def actions(self) -> dict[str, list[dict]]:
        try:
            return json.loads(self.actions_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}

    def write_actions(self, acts: dict[str, list[dict]]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        for v in acts.values():
            v.sort(key=lambda a: (a["ex"], a["factor"]))
        _atomic_write(self.actions_path, json.dumps(acts, indent=0, sort_keys=True))

    def add_actions(self, rows: Iterable[dict]) -> list[dict]:
        """Merge new actions ({sym, ex, factor, purpose, source}); an action already stored
        for the same symbol, ex-date and factor is not added again (the PR file repeats an
        action every day until its ex-date, and the API list may hold it too). Returns the
        rows actually added."""
        acts = self.actions()
        added = []
        for a in rows:
            have = acts.setdefault(a["sym"], [])
            key = (a["ex"], round(float(a["factor"]), 6))
            if any((h["ex"], round(float(h["factor"]), 6)) == key for h in have):
                continue
            rec = {k: a[k] for k in ("ex", "factor", "purpose", "source")}
            have.append(rec)
            added.append(dict(sym=a["sym"], **rec))
        if added:
            self.write_actions(acts)
        return added

    # ── reads ─────────────────────────────────────────────────────────────
    def adjusted(self, sym: str, actions: Optional[dict] = None) -> tuple[pd.DataFrame, list[dict]]:
        """Split- and bonus-adjusted daily bars (adds raw_c, mult, seg) and the log of
        unexplained drops of 35% or more (each starts a new segment)."""
        g = self.read_raw(sym)
        if g.empty:
            return g, []
        g.insert(0, "sym", sym)
        acts = (actions if actions is not None else self.actions()).get(sym, [])
        lst = [(pd.Timestamp(a["ex"]), float(a["factor"])) for a in acts]
        adj, gaps = pr.adjust_symbol(g, lst, _no_ratio, 0.0)
        return adj.drop(columns=["ath", "ath_known"]), gaps

    def etfs(self) -> set[str]:
        try:
            return set(json.loads((self.root / "etfs.json").read_text(encoding="utf-8")))
        except FileNotFoundError:
            return set()

    def add_etfs(self, syms: Iterable[str]) -> int:
        have = self.etfs()
        new = set(syms) - have
        if new:
            self.root.mkdir(parents=True, exist_ok=True)
            _atomic_write(self.root / "etfs.json", json.dumps(sorted(have | new), indent=0))
        return len(new)

    def universe(self, d: date, top_n: int = TOP_N, med_n: int = MED_N) -> list[dict]:
        """Top `top_n` stocks for the session after `d`: not on NSE's ETF list (`etfs()`;
        the bhavcopy name filter misses liquid funds and many index ETFs), traded in the EQ series on `d`,
        ranked by the median traded value of their last `med_n` sessions up to `d`
        (at least `med_n` of them). The tests rank on D by the 60 sessions before D and
        need EQ on D itself; EQ on D isn't known the evening before, so `d`'s series stands
        in for it."""
        ts = pd.Timestamp(d)
        rows, etfs = [], self.etfs()
        for sym in self.symbols():
            if sym in etfs:
                continue
            g = self.read_raw(sym)
            if len(g) < med_n or g["date"].iat[-1] != ts or g["series"].iat[-1] != "EQ":
                continue
            rows.append((sym, float(np.median(g["val"].to_numpy()[-med_n:]))))
        rows.sort(key=lambda r: (-r[1], r[0]))
        return [dict(rank=i + 1, sym=s, med_val=v) for i, (s, v) in enumerate(rows[:top_n])]

    # ── renames ───────────────────────────────────────────────────────────
    def apply_renames(self, chain: SymbolChain) -> list[tuple[str, str, int]]:
        """Move rows filed under a symbol that has since been renamed to the new symbol,
        row by row (NSE reuses retired symbols, so only rows dated before the rename move).
        Actions move the same way. Returns (old, new, rows moved)."""
        moved = []
        renamed = chain.renamed()
        acts = self.actions()
        acts_changed = False
        for sym in self.symbols():
            if sym not in renamed:
                continue
            g = self.read_raw(sym)
            canon = np.array([chain.canonical(sym, t.date()) for t in g["date"]])
            for new in sorted(set(canon) - {sym}):
                part = g[canon == new]
                tgt = self.read_raw(new)
                merged = pd.concat([part, tgt]).drop_duplicates("date", keep="last").sort_values("date")
                self.write_symbol(new, merged)
                moved.append((sym, new, len(part)))
            keep = g[canon == sym]
            if len(keep) < len(g):
                if keep.empty:
                    self._path(sym).unlink()
                else:
                    self.write_symbol(sym, keep)
            for a in list(acts.get(sym, [])):
                new = chain.canonical(sym, date.fromisoformat(a["ex"]) - timedelta(days=1))
                if new != sym:
                    acts[sym].remove(a)
                    acts.setdefault(new, []).append(a)
                    acts_changed = True
        if acts_changed:
            self.write_actions({k: v for k, v in acts.items() if v})
        return moved


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:     # write_text has no newline= before 3.10
        f.write(text)
    os.replace(tmp, path)
