"""
QuantOS — live option chain + futures for one underlying, from Fyers
──────────────────────────────────────────────────────────────────────
Strikes within +-`steps` of spot for the current and next monthly expiry,
both rights, plus each expiry's future, as two-sided quotes only. Shared by
scripts/pick_structure.py and the MCP market tools (core/mcp_tools/market.py).
"""

from __future__ import annotations

from datetime import datetime

from core.ideas.log import IST
from core.ideas.structure import Chain, Quote


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
