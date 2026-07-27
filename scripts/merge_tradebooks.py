#!/usr/bin/env python3
"""
QuantOS — Merge Fyers Tradebook Exports Into One Deduped, PII-Redacted CSV
────────────────────────────────────────────────────────────────────────────
Fyers tradebook exports overlap across periodic re-downloads (the account's
own real trade history, re-pulled over a wider or shifted date window each
time) and always carry PII in their header rows (Client Name, Client ID,
PAN) that must never be committed — see
docs/S8_2_TRADE_HISTORY_ANALYSIS.md's PII handling note and
backtest_results/nifty_ema_options_tradebook.csv's redacted precedent.

This merges any number of raw exports into one deduped fill list and writes
it back out in the exact column format
scripts/analyze_s82_trade_history.py's load_fills() already parses, with a
fully redacted header — so a fresh export can just be pointed at this
script and folded in, without ever committing the raw file or hand-editing
PII out.

Usage:
    python scripts/merge_tradebooks.py <raw1.csv> <raw2.csv> ... --out backtest_results/nifty_ema_options_tradebook.csv
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.analyze_s82_trade_history import Fill, load_fills  # noqa: E402


def dedupe_fills(fills: list[Fill]) -> list[Fill]:
    seen = set()
    out = []
    for f in fills:
        key = (f.symbol, f.side, f.dt, f.qty, f.price, f.product)
        if key not in seen:
            seen.add(key)
            out.append(f)
    return out


def write_tradebook(fills: list[Fill], out_path: Path) -> None:
    fills = sorted(fills, key=lambda f: f.dt)
    lines = [
        "Report Title,Tradebook report,,,,,,,,",
        "Date Range,REDACTED (merged export),,,,,,,,",
        "Client Name,REDACTED,,,,,,,,",
        "Client ID,REDACTED,,,,,,,,",
        "PAN,REDACTED,,,,,,,,",
        "Download Timestamp,REDACTED,,,,,,,,",
        ",,,,,,,,,",
        "Name,Date & time,Side,Product type,Qty,Traded price,Total value,Segment,Exchange order ID,OMS order ID",
    ]
    for f in fills:
        total_value = f.qty * f.price
        lines.append(
            f'{f.symbol},"{f.dt.strftime("%d %b %Y, %I:%M:%S %p")}",{f.side},{f.product},'
            f'{f.qty:.2f},{f.price:.2f},"{total_value:,.2f}",Derivatives,REDACTED,REDACTED'
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("csv_paths", nargs="+", type=Path)
    parser.add_argument("--out", default="backtest_results/nifty_ema_options_tradebook.csv")
    args = parser.parse_args()

    all_fills = []
    for p in args.csv_paths:
        fills = load_fills(p)
        print(f"  {p.name}: {len(fills)} fills")
        all_fills.extend(fills)

    merged = dedupe_fills(all_fills)
    print(f"Merged: {len(all_fills)} raw fills across {len(args.csv_paths)} file(s) -> "
          f"{len(merged)} deduped fills")
    write_tradebook(merged, Path(args.out))
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
