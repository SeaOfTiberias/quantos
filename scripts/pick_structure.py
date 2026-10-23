"""
QuantOS -- pick the structure for a directional view (core/ideas/structure.py)

  python scripts/pick_structure.py DLF --bull --target 720 --stop 665 --days 10 [--budget 12000] [--p 0.5]
  python scripts/pick_structure.py NESTLEIND --bear --target 1200 --stop 1245 --days 5 --intraday

Fetches the live chain (strikes within +-10 steps of spot, every listed
expiry, both rights) and futures from Fyers, then prints the best candidate
of each family and the overall top 8. Places NO orders.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.ideas.log import IST  # noqa: E402
from core.ideas.chain import fetch_chain  # noqa: E402,F401  (kept importable from here)
from core.ideas.structure import Chain, View, best_by_family, candidates  # noqa: E402


def report(chain: Chain, view: View, p: float) -> str:
    ranked = candidates(chain, view, p=p)
    lines = [f"{chain.symbol} spot {chain.spot:g} · lot {chain.lot} · view {'BULL' if view.direction > 0 else 'BEAR'} "
             f"target {view.target:g} stop {view.stop:g} in {view.horizon_days}d · "
             f"{'budget ₹{:,.0f}'.format(view.risk_budget) if view.risk_budget else 'research mode (no budget)'} · p={p}",
             f"{'structure':<30}{'expiry':<12}{'entry':>8}{'if target':>11}{'if stop':>10}{'worst':>9}{'needs p':>9}{'EV/worst':>10}{'lots':>6}"]
    def row(c):
        return (f"{c.name:<30}{c.expiry.isoformat() if c.expiry else '':<12}{c.entry:>8.2f}{c.gain_target:>11,.0f}"
                f"{c.loss_stop:>10,.0f}{c.worst_case:>9,.0f}{c.be_p:>9.0%}{c.score:>10.2f}{c.lots:>6}")
    lines.append("— best of each family —")
    lines += [row(c) for c in best_by_family(ranked)]
    lines.append("— top 8 overall —")
    lines += [row(c) for c in ranked[:8]]
    futs = [c for c in ranked if "future" in c.name]
    if futs and futs[0] not in ranked[:8]:
        lines.append("— futures (worst = stop + gap allowance; needs the stop order actually placed) —")
        lines += [row(c) for c in futs[:2]]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("symbol")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--bull", action="store_true")
    g.add_argument("--bear", action="store_true")
    ap.add_argument("--target", type=float, required=True)
    ap.add_argument("--stop", type=float, required=True)
    ap.add_argument("--days", type=int, required=True, help="horizon in trading days")
    ap.add_argument("--budget", type=float, default=0, help="max loss per trade; 0 (default) = no budget filter, 1 lot each")
    ap.add_argument("--p", type=float, default=0.5, help="chance the target comes before the stop")
    ap.add_argument("--intraday", action="store_true", help="closed before today's close (no overnight gap)")
    ap.add_argument("--vol-shift", type=float, default=0.0)
    ap.add_argument("--gap-pct", type=float, default=View.gap_pct,
                    help="overnight gap through a futures stop, %% of spot (worst case)")
    args = ap.parse_args(argv)

    from agent.main import load_config
    from core.brokers import get_broker
    b = get_broker(load_config("agent/config.yaml"))
    if not b.connect():
        print("Fyers connect failed")
        return 1
    chain = fetch_chain(b._client, args.symbol.upper())
    view = View(direction=1 if args.bull else -1, target=args.target, stop=args.stop, horizon_days=args.days,
                risk_budget=args.budget or None, overnight=not args.intraday, vol_shift=args.vol_shift,
                gap_pct=args.gap_pct)
    print(report(chain, view, args.p))
    return 0


if __name__ == "__main__":
    sys.exit(main())
