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
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.ideas.log import IST  # noqa: E402
from core.ideas.chain import fetch_chain  # noqa: E402,F401  (kept importable from here)
from core.ideas.structure import Chain, View, best_by_family, candidates  # noqa: E402


def regime_lines(chain: Chain, view: View, top) -> list[str]:
    """Velocity, IV rank and the advisory warnings (core/ideas/regime.py)."""
    from core.ideas import regime
    from core.mcp_tools.market import IV_HISTORY, QUANTOS_DIR
    k = regime.velocity_k(chain.spot, view.target, view.atr, view.horizon_days)
    vel = {"k": round(k, 2), "label": regime.velocity_label(k)} if k is not None else None
    iv = regime.iv_context(chain, IV_HISTORY, QUANTOS_DIR / "nse_fo_bhavcopy")
    ivs = (f"ATM IV {iv['iv']:.1%} · IV rank {iv['rank']} ({iv['label']}, 1y {iv['low_1y']:.1%}-{iv['high_1y']:.1%})"
           if "rank" in iv else f"IV rank n/a ({iv.get('error')})")
    vw = {"thesis": view.thesis}
    top_row = {"structure": top.name} if top else None
    out = [f"velocity {vel['k']} ({vel['label']})" if vel else "velocity n/a (no ATR)", ivs]
    ev = getattr(view, "_event_ctx", None)
    if ev:
        out.append(f"results {ev.get('results_date') or 'none in the calendar'}"
                   + (f" ({ev['sessions_away']} sessions, {'INSIDE' if ev.get('inside_horizon') else 'after'} the horizon)"
                      if ev.get("results_date") else ""))
    return [" · ".join(out)] + [f"! {w}" for w in regime.warnings(vw, vel, iv, top_row, ev)]


def report(chain: Chain, view: View, p: float) -> str:
    ranked = candidates(chain, view, p=p)
    lines = [f"{chain.symbol} spot {chain.spot:g} · lot {chain.lot} · ATR {view.atr or 0:.2f} · "
             f"view {'BULL' if view.direction > 0 else 'BEAR'} ({view.thesis}) "
             f"target {view.target:g} stop {view.stop:g} in {view.horizon_days}d · "
             f"{'budget ₹{:,.0f}'.format(view.risk_budget) if view.risk_budget else 'research mode (no budget)'} · p={p}",
             f"{'structure':<30}{'expiry':<12}{'entry':>8}{'if target':>11}{'if stop':>10}{'if flat':>9}{'worst':>9}"
             f"{'needs p':>9}{'EV/worst':>10}{'lots':>6}  {'deltas':<14}rules (if_event: R7)"]
    lines[1:1] = regime_lines(chain, view, ranked[0] if ranked else None)

    def row(c):
        rules = "ok" if not c.flags else " | ".join(c.flags)
        deltas = "/".join(f"{x:+.2f}" for x in c.deltas)
        return (f"{c.name:<30}{c.expiry.isoformat() if c.expiry else '':<12}{c.entry:>8.2f}{c.gain_target:>11,.0f}"
                f"{c.loss_stop:>10,.0f}{c.flat:>9,.0f}{c.worst_case:>9,.0f}{c.be_p:>9.0%}{c.score:>10.2f}{c.lots:>6}  {deltas:<14}{rules}")
    lines.append("— best of each family —")
    lines += [row(c) for c in best_by_family(ranked)]
    lines.append("— top 8 overall —")
    lines += [row(c) for c in ranked[:8]]
    futs = [c for c in ranked if "future" in c.name]
    if futs and futs[0] not in ranked[:8]:
        lines.append("— futures (worst = stop + gap allowance; needs the stop order actually placed) —")
        lines += [row(c) for c in futs[:2]]
    return "\n".join(lines)


def fyers_atr(broker, symbol: str) -> Optional[float]:
    """ATR(14) of the underlying from completed Fyers daily bars (today's bar excluded)."""
    from core.mcp_tools.market import _atr
    try:
        now = datetime.now(IST)
        bars = broker.get_historical_data(symbol.upper(), "1d", now - timedelta(days=45), now) or []
        bars = sorted((b for b in bars if b.timestamp.astimezone(IST).date() < now.date()), key=lambda b: b.timestamp)
        return _atr(bars)
    except Exception:
        return None


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
    ap.add_argument("--thesis", choices=["move", "hold"], default="move",
                    help="move = reaches the target; hold = won't cross the stop level")
    ap.add_argument("--atr", type=float, help="ATR(14) override (default: from Fyers daily bars)")
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
                gap_pct=args.gap_pct, atr=args.atr or fyers_atr(b, args.symbol), thesis=args.thesis)
    from datetime import date as _date
    from core.ideas import events
    from core.mcp_tools.market import EVENTS
    try:
        ev = events.event_context(events.refresh(EVENTS), chain.symbol, chain.today, args.days)
    except Exception as e:
        ev = {"results_date": None, "error": type(e).__name__}
    if ev.get("inside_horizon"):
        view.event_date = _date.fromisoformat(ev["results_date"])
    view._event_ctx = ev
    print(report(chain, view, args.p))
    return 0


if __name__ == "__main__":
    sys.exit(main())
