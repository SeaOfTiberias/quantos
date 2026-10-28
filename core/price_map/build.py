"""
QuantOS — Price map: assemble one stock's map from its bars
────────────────────────────────────────────────────────────
Pure: build_map(daily, intraday, today) -> a JSON-ready dict; render() turns it
into the Obsidian page (wiki/price-maps/<SYMBOL>.md). See levels.py for the sources.
"""

from __future__ import annotations

from datetime import date
from statistics import quantiles
from typing import Optional

from core.price_map.levels import (
    _d, classical, camarilla, first_obstacle, periods, pivot_levels, sessions, swing_levels, volume_levels, zones,
)

ZONE_ATR = 0.3
STEPS = (0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50)


def atr14(daily: list) -> Optional[float]:
    if len(daily) < 15:
        return None
    trs = [max(b.high - b.low, abs(b.high - a.close), abs(b.low - a.close)) for a, b in zip(daily, daily[1:])]
    return sum(trs[-14:]) / 14


def step_for(atr: float) -> float:
    """Profile bucket: the round step nearest ATR/20 (HDFCBANK 0.5, SUPREMEIND 5)."""
    return min(STEPS, key=lambda s: abs(s - atr / 20))


def spike_p90(intraday: list, atr: float) -> Optional[float]:
    """The 1-in-10-days largest 15-minute (3 x 5-min bar) swing, in ATR."""
    sw = []
    for bars in sessions(intraday).values():
        if len(bars) >= 3:
            sw.append(max(max(b.high for b in bars[i:i + 3]) - min(b.low for b in bars[i:i + 3])
                          for i in range(len(bars) - 2)) / atr)
    return round(quantiles(sw, n=10)[8], 2) if len(sw) >= 10 else None


def build_map(symbol: str, daily: list, intraday: list, today: date) -> dict:
    atr = atr14([b for b in daily if _d(b) < today])
    if not atr:
        return {"symbol": symbol, "error": "fewer than 15 daily bars"}
    step = step_for(atr)
    width = round(ZONE_ATR * atr, 2)
    vol, vinfo = volume_levels(intraday, step) if intraday else ([], {})
    levels = swing_levels([b for b in daily if _d(b) < today], atr=atr) + pivot_levels(daily, today) + vol
    zs = zones(levels, width)
    last = [b for b in daily if _d(b) < today][-1]
    return {
        "symbol": symbol, "built_for": today.isoformat(), "close": last.close,
        "atr": round(atr, 2), "atr_pct": round(atr / last.close * 100, 2), "step": step, "zone_width": width,
        "spike_p90_atr": spike_p90(intraday, atr) if intraday else None,
        "pivots": {k: {"classical": {n: round(v, 2) for n, v in classical(*hlc).items()},
                       "camarilla": {n: round(v, 2) for n, v in camarilla(*hlc).items()}}
                   for k, hlc in periods(daily, today).items()},
        "volume": {k: v for k, v in vinfo.items()},
        "zones": [z.to_dict() for z in zs],
    }


def nearest(m: dict, price: float, strong_only: bool = True) -> dict:
    """The nearest zone below and above `price`."""
    zs = [z for z in m.get("zones", []) if z["strong"] or not strong_only]
    below = [z for z in zs if z["high"] < price]
    above = [z for z in zs if z["low"] > price]
    return {"below": max(below, key=lambda z: z["high"]) if below else None,
            "above": min(above, key=lambda z: z["low"]) if above else None}


def zone_at(m: dict, price: float) -> Optional[dict]:
    """The strong zone `price` is inside, if any."""
    return next((z for z in m.get("zones", []) if z["strong"] and z["low"] <= price <= z["high"]), None)


def rng(z: dict) -> str:
    return f"{z['low']:g}" if z["low"] == z["high"] else f"{z['low']:g}–{z['high']:g}"


def why(z: dict, n: int = 3) -> str:
    """The zone's first n reasons, swings and volume ahead of pivots."""
    order = {"swing": 0, "volume": 1, "pivot": 2}
    lv = sorted(z["levels"], key=lambda x: order.get(x["family"], 3))
    return "; ".join(x["label"] for x in lv[:n]) + (f" +{len(lv) - n}" if len(lv) > n else "")


def markers(m: dict, price: float, entry: float, side: int, r: float, target: Optional[float]) -> list[str]:
    """Plan-message lines: the strong zones either side of `price`, and the first one in the trade's way."""
    if not m or "zones" not in m:
        return ["• Map: none built -- run scripts/price_map.py"]
    n = nearest(m, price)
    out = [f"• Map ({m['built_for']}): below {rng(n['below']) + ' (' + why(n['below']) + ')' if n['below'] else 'no strong zone'}; "
           f"above {rng(n['above']) + ' (' + why(n['above']) + ')' if n['above'] else 'no strong zone'}"]
    ob = first_obstacle(m["zones"], entry, side, r)
    if ob is None:
        out.append("• First obstacle: none before the target" if target is not None else "• First obstacle: none")
    else:
        beyond = target is not None and (target - ob["edge"]) * side > 0
        out.append(f"• First obstacle {rng(ob['zone'])} at {ob['r']:g}R" + (" -- the target is beyond it ⚠️" if beyond else ""))
    return out


def _zone_line(z: dict) -> str:
    rng = f"{z['low']:g}" if z["low"] == z["high"] else f"{z['low']:g}–{z['high']:g}"
    return f"| {rng} | {'**strong**' if z['strong'] else 'single'} | " + "; ".join(lv["label"] for lv in z["levels"]) + " |"


def render(m: dict) -> str:
    if "error" in m:
        return f"# {m['symbol']} price map\n\n{m['error']}\n"
    v = m.get("volume", {})
    near = nearest(m, m["close"])
    lines = [
        "---", "tags:", "  - price-map", "quantos:", f"  id: map_{m['symbol'].lower()}", f"  symbol: {m['symbol']}",
        f"  built_for: {m['built_for']}", "---", "",
        f"# {m['symbol']} price map", "",
        f"Generated by `scripts/price_map.py` for {m['built_for']} from Fyers bars. Regenerated, so don't edit "
        "here: put observations in `raw/` and link them below.", "",
        f"Last close **{m['close']:g}** · ATR {m['atr']:g} ({m['atr_pct']:g}%) · 15-min spike 1 day in 10: "
        f"{m['spike_p90_atr'] if m['spike_p90_atr'] is not None else '-'} ATR · zone width {m['zone_width']:g}", "",
        "## Nearest strong zones", "",
        f"- below: {_short(near['below'])}", f"- above: {_short(near['above'])}", "",
        "## Volume profile", "",
    ]
    if v.get("poc") is not None:
        lines.append(f"Composite POC **{v['poc']:g}**, value area {v['val']:g}–{v['vah']:g}. "
                     "Shelves: " + (", ".join(f"{a:g}–{b:g}" for a, b in v.get("shelves", [])) or "none") + ".")
        lines.append("")
        lines.append("Naked POCs (never traded back through): "
                     + (", ".join(f"{p:g} ({d})" for d, p in v.get("naked_pocs", [])) or "none") + ".")
        lines += ["", "| Session | POC | Value area |", "|---|---|---|"]
        lines += [f"| {r['date']} | {r['poc']:g} | {r['val']:g}–{r['vah']:g} |" for r in v.get("recent", [])]
    lines += ["", "## Pivots", "", "| | S3 | S2 | S1 | P | R1 | R2 | R3 | L4 | L3 | H3 | H4 |", "|---|" + "---|" * 11]
    for k, p in m["pivots"].items():
        c, cm = p["classical"], p["camarilla"]
        lines.append(f"| {k} | " + " | ".join(f"{c[n]:g}" for n in ("S3", "S2", "S1", "P", "R1", "R2", "R3"))
                     + " | " + " | ".join(f"{cm[n]:g}" for n in ("L4", "L3", "H3", "H4")) + " |")
    lines += ["", "## Zones", "", "| Zone | Strength | Levels |", "|---|---|---|"]
    lines += [_zone_line(z) for z in m["zones"] if z["strong"]]
    lines += ["", "## Notes and trades", "", "_Links to `raw/` observations and our trades in this name._", ""]
    return "\n".join(lines)


def _short(z: Optional[dict]) -> str:
    if not z:
        return "none"
    rng = f"{z['low']:g}" if z["low"] == z["high"] else f"{z['low']:g}–{z['high']:g}"
    return f"**{rng}** ({'; '.join(lv['label'] for lv in z['levels'])})"
