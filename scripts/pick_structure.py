"""
QuantOS -- pick the structure for a directional view (core/ideas/structure.py)

  python scripts/pick_structure.py DLF --bull --target 720 --stop 665 --days 10 [--budget 10000] [--p 0.5]
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
from core.ideas.structure import Chain, Quote, View, best_by_family, candidates  # noqa: E402


def fetch_chain(client, symbol: str, steps: int = 10) -> Chain:
    from core.options import fyers_symbol_master as fsm
    rows = fsm._parse_rows(fsm._load_master_text("NSE_FO"), symbol)
    today = datetime.now(IST).date()
    eq = client.quotes({"symbols": f"NSE:{symbol}-EQ"})["d"][0]["v"]
    spot = float(eq["lp"])
    by_exp: dict = {}
    for r in rows:
        e = fsm._row_expiry(r)
        if e >= today:
            by_exp.setdefault(e, []).append(r)
    chain = Chain(symbol=symbol, spot=spot, lot=int(rows[0][fsm._COL_LOT_SIZE]), today=today)
    wanted = {}
    for e, rs in sorted(by_exp.items())[:2]:                     # current + next month
        strikes = sorted({float(r[fsm._COL_STRIKE]) for r in rs})
        near = sorted(strikes, key=lambda k: abs(k - spot))[: 2 * steps + 1]
        for r in rs:
            k = float(r[fsm._COL_STRIKE])
            if k in near:
                wanted[r[fsm._COL_FYERS_SYMBOL]] = (e, k, r[fsm._COL_OPTION_TYPE])
        wanted[f"NSE:{symbol}{e:%y}{e.strftime('%b').upper()}FUT"] = (e, None, "FUT")
    names = list(wanted)
    for i in range(0, len(names), 50):
        for x in client.quotes({"symbols": ",".join(names[i:i + 50])}).get("d", []):
            v, key = x.get("v") or {}, wanted.get(x.get("n"))
            if not key or not v.get("bid") or not v.get("ask"):
                continue
            q = Quote(float(v["bid"]), float(v["ask"]))
            if key[2] == "FUT":
                chain.futures[key[0]] = q
            else:
                chain.options[key] = q
    return chain


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
    ap.add_argument("--budget", type=float, default=10000, help="max loss per trade; 0 = research mode (no filter)")
    ap.add_argument("--p", type=float, default=0.5, help="chance the target comes before the stop")
    ap.add_argument("--intraday", action="store_true", help="closed before today's close (no overnight gap)")
    ap.add_argument("--vol-shift", type=float, default=0.0)
    args = ap.parse_args(argv)

    from agent.main import load_config
    from core.brokers import get_broker
    b = get_broker(load_config("agent/config.yaml"))
    if not b.connect():
        print("Fyers connect failed")
        return 1
    chain = fetch_chain(b._client, args.symbol.upper())
    view = View(direction=1 if args.bull else -1, target=args.target, stop=args.stop, horizon_days=args.days,
                risk_budget=args.budget or None, overnight=not args.intraday, vol_shift=args.vol_shift)
    print(report(chain, view, args.p))
    return 0


if __name__ == "__main__":
    sys.exit(main())
