#!/usr/bin/env python3
"""
QuantOS — BankNifty residual mean reversion (shortcut).

Same as `python scripts/statarb_residual.py --universe niftybank ...`;
kept so the BankNifty commands in docs/memory still work.

Usage:
    python scripts/statarb_banknifty.py scan
    python scripts/statarb_banknifty.py backtest
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from statarb_residual import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(default_universe="niftybank"))
