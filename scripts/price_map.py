#!/usr/bin/env python3
"""
QuantOS — price_map: build a stock's price map from Fyers bars (on the VM)
──────────────────────────────────────────────────────────────────────────
Swing levels, volume profile (composite, recent sessions, naked POCs), classical
and Camarilla pivots, and the zones where they agree (core/price_map/). Writes
~/.quantos/price_maps/<SYMBOL>.json (read by the position manager) and
<SYMBOL>.md (copied into the vault at wiki/price-maps/ from the PC).

    python scripts/price_map.py SUPREMEIND HDFCBANK
    python scripts/price_map.py --positions        # every stock with an open ICICI futures position
    python scripts/price_map.py --watch            # plus ~/.quantos/price_map_watch.txt (one symbol a line)
    python scripts/price_map.py --fno --pause 2    # every F&O stock (Fyers master), 2 s between Fyers calls

Places no orders. Two Fyers history calls per stock. Fyers is shared with the live
jobs, so the universe run is throttled (--pause) and stops at a rate-limit refusal.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.price_map.build import build_map, nearest, render  # noqa: E402
from core.price_map.levels import IST  # noqa: E402

OUT = Path.home() / ".quantos" / "price_maps"
WATCH = Path.home() / ".quantos" / "price_map_watch.txt"
INTRADAY_DAYS = 99           # Fyers allows 100 days of 5-minute bars per call
FO_MASTER = Path.home() / ".quantos" / "fyers_symbol_master_NSE_FO.csv"
INDICES = {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50", "SENSEX", "BANKEX"}


def fno_symbols() -> list[str]:
    """Every stock with futures in the Fyers F&O master (col 13 underlying, col 16 XX = a future)."""
    import csv
    with FO_MASTER.open() as f:
        return sorted({r[13] for r in csv.reader(f) if len(r) > 16 and r[16] == "XX" and r[13] not in INDICES})


def open_position_symbols() -> list[str]:
    import json as _j
    state = Path.home() / ".quantos" / "position_manager_state.json"
    try:
        return sorted({p["symbol"] for p in _j.loads(state.read_text()).values()})
    except (OSError, ValueError, KeyError):
        return []


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("symbols", nargs="*")
    ap.add_argument("--positions", action="store_true", help="add every open position's stock")
    ap.add_argument("--watch", action="store_true", help=f"add the symbols in {WATCH}")
    ap.add_argument("--fno", action="store_true", help="add every F&O stock")
    ap.add_argument("--pause", type=float, default=1.0, help="seconds between Fyers calls")
    a = ap.parse_args(argv)
    watched = [ln.split("#")[0].strip() for ln in WATCH.read_text().splitlines()] if a.watch and WATCH.exists() else []
    symbols = ([s.upper() for s in a.symbols] + (open_position_symbols() if a.positions else [])
               + [w.upper() for w in watched if w] + (fno_symbols() if a.fno else []))
    if not symbols:
        print("no symbols: no open positions and nothing watched")
        return 0
    from core.mcp_tools.live import LiveMarket
    m = LiveMarket("agent/config.yaml")
    OUT.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    today = now.astimezone(IST).date()
    done = failed = 0
    for s in dict.fromkeys(symbols):
        try:
            daily = m.daily(s, 365)
            time.sleep(a.pause)
            intraday = sorted(m.broker.get_historical_data(f"NSE:{s}-EQ", "5m", now - timedelta(days=INTRADAY_DAYS), now)
                              or [], key=lambda b: b.timestamp)
            time.sleep(a.pause)
        except Exception as e:                      # one bad symbol doesn't stop the run; a rate limit does
            if "-360" in str(e) or "request limit" in str(e):
                print(f"{s}: Fyers rate limit -- stopping after {done} maps")
                break
            print(f"{s}: skipped ({str(e)[:120]})")
            failed += 1
            continue
        mp = build_map(s, daily, intraday, today)
        done += 1
        (OUT / f"{s}.json").write_text(json.dumps(mp, indent=1, default=str))
        (OUT / f"{s}.md").write_text(render(mp), encoding="utf-8")
        if "error" in mp:
            print(f"{s}: {mp['error']}")
            continue
        n = nearest(mp, mp["close"])
        fmt = (lambda z: f"{z['low']:g}-{z['high']:g}" if z else "none")
        print(f"{s}: close {mp['close']:g}, ATR {mp['atr']:g} ({mp['atr_pct']:g}%), "
              f"strong zone below {fmt(n['below'])}, above {fmt(n['above'])} -> {OUT / (s + '.json')}")
    print(f"{done} maps written, {failed} skipped -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
