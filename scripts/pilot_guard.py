#!/usr/bin/env python3
"""
QuantOS — ORB live pilot breaker: status / reset
─────────────────────────────────────────────────
The breaker itself (core/orb_scalping/pilot_guard.py) runs after every pilot
fire and halts NEW pilot entries on a live-only defect signal or a spent loss
budget. This script is the human side: look, then reset.

    python scripts/pilot_guard.py            # status: halted? why? what would trip now?
    python scripts/pilot_guard.py --reset    # after reviewing: clear the halt, acknowledge
                                             # everything so far, restart the budget

Reset only after the reason has been understood (the Reports page pilot card
lists the trades and anomalies). It never touches paper 18/18b or the global
~/.quantos/halt.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.orb_scalping import pilot_guard  # noqa: E402
from core.orb_scalping.dry_run_log import ORB_DRY_RUN_LOG_PATH, load_dry_run_trades  # noqa: E402
from core.orb_scalping.live_trade_log import load_live_events  # noqa: E402


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--reset", action="store_true", help="clear the pilot halt and acknowledge everything so far")
    args = p.parse_args(argv)

    if args.reset:
        was = pilot_guard.read_pilot_halt()
        pilot_guard.reset()
        print(f"Pilot breaker reset (was: {was or 'not halted'}). Only events from now on count; "
              f"the Rs{pilot_guard.BUDGET_RS:,.0f} budget restarts from zero.")
        return 0

    halted = pilot_guard.read_pilot_halt()
    ack = pilot_guard.acknowledged_until()
    would = pilot_guard.evaluate(load_live_events("orb_scalping_pilot"),
                                 load_dry_run_trades(ORB_DRY_RUN_LOG_PATH), acknowledged=ack)
    print(f"Halted:            {halted or 'no'}")
    print(f"Acknowledged until: {ack or 'never reset'}")
    print(f"Would trip now:    {would or 'no'}")
    print(f"Limits:            any anomaly | shortfall > Rs{pilot_guard.SHORTFALL_LIMIT_RS:,.0f} | "
          f"net <= -Rs{pilot_guard.BUDGET_RS:,.0f} since reset")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
