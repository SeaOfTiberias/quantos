#!/usr/bin/env python3
"""Monthly benchmark report (execution plan E4): the Darvas paper record and the momentum walk-forward
against the Nifty 50 and Nifty200 Momentum 30 index funds, over the same dates, after costs.

Each strategy section stays LOCKED (counts and index returns only, no strategy return computed) until
its own frozen gate opens; see core/ops/benchmark.py. Code-only: no model call.

Writes ~/.quantos/reports/benchmark_latest.json (read by GET /reports/benchmark) and a dated copy,
then sends the text to Telegram.

    python scripts/benchmark_report.py            # write + Telegram
    python scripts/benchmark_report.py --dry-run  # print only
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.ops import benchmark as bm  # noqa: E402

Q = Path.home() / ".quantos"
OUT = Q / "reports"
IST = timezone(timedelta(hours=5, minutes=30))


def _section(fn) -> dict:
    try:
        return fn()
    except Exception as e:                                     # noqa: BLE001 -- one section never kills the report
        return dict(name=fn.__name__, locked=True, error=f"{type(e).__name__}: {e}"[:200])


def build(today, q: Path = Q, index_root: Optional[Path] = None) -> dict:
    from core.market_map.index_bars import IndexBars
    ib = IndexBars(index_root)
    idx = {s: ib.load(s) for s in bm.FUND_TER}

    def darvas():
        from core.darvas_atr_stop.dry_run_log import load_dry_run_trades
        rows = load_dry_run_trades(q / "darvas_atr_stop_dry_run_trades.jsonl")
        closed = [bm.DarvasTrade(t.symbol, datetime.fromisoformat(t.entry_timestamp[:10]).date(),
                                 datetime.fromisoformat(t.exit_timestamp[:10]).date(),
                                 float(t.entry_price), float(t.exit_ltp if t.exit_ltp is not None else t.boundary_price))
                  for t in rows]   # exit_ltp, else the boundary (as E2)
        op = q / "darvas_atr_stop_open_positions.json"
        n_open = len(json.loads(op.read_text())) if op.exists() else 0

        def net_fn(entry: float, exit_: float) -> float:       # imported only once the gate opens
            from scripts.backtest_darvas_atr_stop_oos import net_return
            from scripts.backtest_darvas_box_width import STRESSED_COST_MODEL
            return net_return(dict(entry_price=entry, exit_price=exit_), STRESSED_COST_MODEL)
        return bm.darvas_section(closed, n_open, idx, today, net_fn)

    def momentum():
        p = q / "paper_rotation_walkforward.json"
        state = json.loads(p.read_text()) if p.exists() else {}
        return bm.momentum_section(state, idx, today)

    last = {s: (df["date"].max().date().isoformat() if len(df) else None) for s, df in idx.items()}
    return dict(as_of=today.isoformat(), index_last_bar=last, fund_ter_pct=bm.FUND_TER,
                price_index_not_tri=True, tax_modelled=False,
                darvas=_section(darvas), momentum=_section(momentum))


def send(msg: str) -> bool:
    from cloud.api.notifier import send_telegram
    try:
        ok = bool(asyncio.run(send_telegram(msg)))
    except Exception as e:                                     # noqa: BLE001
        print(f"telegram error ({type(e).__name__})")
        return False
    if not ok:
        print("telegram not sent")
    return ok


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    today = datetime.now(IST).date()
    rep = build(today)
    text = bm.render_text(rep)
    print(text)
    if a.dry_run:
        return 0
    OUT.mkdir(parents=True, exist_ok=True)
    body = json.dumps(rep, indent=1, default=str)
    (OUT / f"benchmark_{today:%Y%m}.json").write_text(body)
    (OUT / "benchmark_latest.json").write_text(body)
    return 0 if send(text) else 1


if __name__ == "__main__":
    sys.exit(main())
