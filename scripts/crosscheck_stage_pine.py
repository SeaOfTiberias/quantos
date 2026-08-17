"""
Cross-check pine/weinstein_stage_journey.pine against core/vault/stages.py.

Why this exists
───────────────
The Pine indicator is a hand transcription of the ```quantos-stages``` block
in Stan_Weinstein_Stage_Analysis.md. Two implementations of one idea drift,
and this repo has the scar: darvasBox() in pine/darvas_breakout_alert.pine
reset boxReady before testing for a breakout, silently suppressing nearly
every real signal for months, while the Python engine it was supposed to
mirror was perfectly fine. A three-year Strategy Tester run producing zero
entries is what eventually surfaced it (fixed 2026-07-18, a74521a).

What this can and cannot check
──────────────────────────────
TradingView will not hand a script its computed series over an API, so this
cannot diff the two at runtime. What it CAN do is re-implement the Pine's
control flow — the branch ladder, the na-handling, the phase precedence —
directly from the .pine source's own structure, run it over the same bars as
the Python classifier, and assert identical stage timelines.

That catches the whole class of bug the Darvas incident belonged to:
transcription errors in ORDERING and GUARD CONDITIONS, which is where a
mirror actually breaks. It does not catch a TradingView-side difference in
how request.security resolves a partial session, and nothing local could.

So: a pass here means the two agree on the logic. It does not mean the chart
and the cockpit will always show the same label at 11am on a live bar.

Usage:
    python scripts/crosscheck_stage_pine.py                 # synthetic series
    python scripts/crosscheck_stage_pine.py --config agent/config.yaml \
        --universe agent/universe_alpha50.txt               # real bars, on the VM
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import math
import re
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.brokers.base import OHLCV
from core.discovery.momentum_shortlist import sma_series
from core.vault.facts import MarketFacts
from core.vault.parser import parse_note
from core.vault.stages import classify, stage_timeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("crosscheck_stage_pine")

PINE_PATH = Path("pine/weinstein_stage_journey.pine")
NOTE_PATH = Path("obsidian_vault/QuantOS/brain/Stan_Weinstein_Stage_Analysis.md")


# ── The Pine indicator's logic, transcribed back ─────────────────────────
# Deliberately written to mirror the .pine branch ladder line for line rather
# than to be idiomatic Python. If it reads awkwardly, that is the point: a
# tidied-up version would stop being a check on the thing it is checking.
def pine_stage(closes: list[float], volumes: list[float], index: int, *,
               band: float, slope_lag: int, prior_lag: int,
               dry_up_ratio: float) -> tuple[int, str]:
    """Returns (stage, phase); stage 0 means unclassified, as in the Pine."""
    sma150 = _sma_at(closes, 150, index)
    sma_slope = _sma_at(closes, 150, index - slope_lag)
    sma_prior = _sma_at(closes, 150, index - prior_lag)
    vol5 = _sma_at(volumes, 5, index)
    vol50 = _sma_at(volumes, 50, index)

    warmed_slope = sma150 is not None and sma_slope is not None
    warmed_prior = sma_prior is not None
    rising = warmed_slope and sma150 > sma_slope * (1.0 + band)
    falling = warmed_slope and sma150 < sma_slope * (1.0 - band)
    dry_up = (vol5 is not None and vol50 is not None and vol50 > 0
              and vol5 / vol50 < dry_up_ratio)
    prior_up = warmed_prior and sma_prior > 0 and sma_slope > sma_prior

    if not warmed_slope:
        return 0, ""
    if falling:
        return 4, ""
    if rising:
        if dry_up:
            return 2, "pivot"
        if closes[index] < sma150:
            return 2, "pullback"
        return 2, ""
    if not warmed_prior:
        return 0, ""
    if prior_up:
        return 3, ""
    return 1, ""


def _sma_at(series: list[float], period: int, index: int) -> Optional[float]:
    if index < 0 or index >= len(series):
        return None
    values = sma_series(series[:index + 1], period)
    return values[-1] if values and values[-1] is not None else None


# ── Reading the parameters out of the Pine source ────────────────────────
def pine_defaults() -> dict:
    """Pull the input() defaults straight from the .pine file.

    Read rather than duplicated so that changing a default in the indicator
    without changing the note is itself detected, instead of this script
    quietly testing a stale pair of numbers.
    """
    source = PINE_PATH.read_text(encoding="utf-8")
    out = {}
    for name, pattern in (
        ("band", r"bandPct\s*=\s*input\.float\(([\d.]+)"),
        ("slope_lag", r"slopeLag\s*=\s*input\.int\((\d+)"),
        ("prior_lag", r"priorLag\s*=\s*input\.int\((\d+)"),
        ("dry_up_ratio", r"dryUpRatio\s*=\s*input\.float\(([\d.]+)"),
    ):
        match = re.search(pattern, source)
        if not match:
            raise SystemExit(f"could not read {name} out of {PINE_PATH}")
        out[name] = float(match.group(1))
    out["band"] /= 100.0
    out["slope_lag"] = int(out["slope_lag"])
    out["prior_lag"] = int(out["prior_lag"])
    return out


def assert_pine_matches_note(defaults: dict) -> None:
    """The Pine's defaults must reproduce the note's shipped numbers.

    A mirror that agrees on logic but disagrees on constants is still a
    mirror that shows two different charts.
    """
    clauses = parse_note(NOTE_PATH).stage_clauses
    expressions = " ".join(c.expression or "" for c in clauses)

    note_band = {float(x) for x in re.findall(r"sma\(150\)\[\d+\] \* ([\d.]+)", expressions)}
    expected = {round(1.0 + defaults["band"], 6), round(1.0 - defaults["band"], 6)}
    if {round(b, 6) for b in note_band} != expected:
        raise SystemExit(
            f"band mismatch — note uses {sorted(note_band)}, "
            f"pine's default is {defaults['band']:.4f} (i.e. {sorted(expected)})"
        )

    lags = {int(n) for n in re.findall(r"sma\(150\)\[(\d+)\]", expressions)}
    for label, value in (("slope", defaults["slope_lag"]), ("prior", defaults["prior_lag"])):
        if value not in lags:
            raise SystemExit(
                f"{label} lag mismatch — pine uses [{value}], note uses {sorted(lags)}"
            )

    ratios = {float(x) for x in re.findall(r"volume_sma\(5\) / volume_sma\(50\) < ([\d.]+)",
                                           expressions)}
    if ratios and defaults["dry_up_ratio"] not in ratios:
        raise SystemExit(
            f"dry-up ratio mismatch — pine {defaults['dry_up_ratio']}, note {sorted(ratios)}"
        )
    logger.info("Pine defaults match the note: band=%.2f%% slope=[%d] prior=[%d] dryUp=%.2f",
                defaults["band"] * 100, defaults["slope_lag"],
                defaults["prior_lag"], defaults["dry_up_ratio"])


# ── The comparison ───────────────────────────────────────────────────────
def compare(symbol: str, candles: list[OHLCV], clauses, defaults: dict,
            *, window: int) -> list[str]:
    """Disagreements between the two implementations, as readable strings."""
    closes = [c.close for c in candles]
    volumes = [float(c.volume) for c in candles]
    facts = MarketFacts(symbol, candles)

    timeline = stage_timeline(clauses, facts, bars=window)
    mismatches = []
    for offset, result in timeline:
        index = len(candles) - 1 - offset
        pine, phase = pine_stage(closes, volumes, index, band=defaults["band"],
                                 slope_lag=defaults["slope_lag"],
                                 prior_lag=defaults["prior_lag"],
                                 dry_up_ratio=defaults["dry_up_ratio"])
        python_stage = result.stage.value if result.stage else 0
        if pine != python_stage or phase != result.phase:
            mismatches.append(
                f"{symbol} bar -{offset}: python={python_stage}"
                f"{'·' + result.phase if result.phase else ''} "
                f"pine={pine}{'·' + phase if phase else ''}"
            )
    return mismatches


def synthetic_series() -> dict[str, list[OHLCV]]:
    """Shapes that exercise every branch, including the boundaries."""
    from datetime import datetime, timedelta, timezone
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)

    def to_bars(closes, volumes=None):
        volumes = volumes or [100_000] * len(closes)
        return [OHLCV(timestamp=base + timedelta(days=i), open=c, high=c * 1.01,
                      low=c * 0.99, close=c, volume=v)
                for i, (c, v) in enumerate(zip(closes, volumes))]

    up = [100 * math.exp(i * 0.004) for i in range(400)]
    down = [100 * math.exp(-i * 0.004) for i in range(400)]
    choppy = [100 * (1 + 0.02 * math.sin(i / 9)) for i in range(400)]
    top = [100 * math.exp(i * 0.004) for i in range(250)] + \
          [100 * math.exp(250 * 0.004) * (1 + 0.02 * math.sin(i / 9)) for i in range(150)]
    basing = [300 * math.exp(-i * 0.004) for i in range(250)] + \
             [300 * math.exp(-250 * 0.004) * (1 + 0.02 * math.sin(i / 9)) for i in range(150)]
    bounce = down[:380] + [down[379] * 1.02 ** i for i in range(1, 21)]
    pivot_vol = [100_000] * 380 + [10_000] * 20

    return {
        "UPTREND": to_bars(up),
        "DOWNTREND": to_bars(down),
        "CHOPPY": to_bars(choppy),
        "TOPPING": to_bars(top),
        "BASING": to_bars(basing),
        "DEADCAT": to_bars(bounce),
        "PIVOT": to_bars(up, pivot_vol),
        "SHORT": to_bars(up[:180]),
        "TOOSHORT": to_bars(up[:60]),
    }


async def fetch_real(config_path: Path, universe_path: Path) -> dict:
    from agent.main import _load_universe, load_config
    from core.brokers import get_broker
    from scripts.validate_regime_classifier import fetch_chunked_daily
    from datetime import datetime, timedelta, timezone

    config = load_config(str(config_path))
    broker = get_broker(config)
    broker.connect()

    to_date = datetime.now(timezone.utc)
    from_date = to_date - timedelta(days=400)
    sem = asyncio.Semaphore(2)

    out = {}
    for symbol in _load_universe(str(universe_path)):
        candles = await fetch_chunked_daily(broker, symbol, from_date, to_date, sem)
        if candles:
            out[symbol] = candles
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, default=None,
                        help="Use real bars instead of synthetic series (needs live Fyers auth).")
    parser.add_argument("--universe", type=Path, default=Path("agent/universe_alpha50.txt"))
    parser.add_argument("--window", type=int, default=120,
                        help="Sessions of history to compare per symbol.")
    args = parser.parse_args()

    defaults = pine_defaults()
    assert_pine_matches_note(defaults)

    clauses = parse_note(NOTE_PATH).stage_clauses
    if not clauses:
        raise SystemExit(f"{NOTE_PATH} has no ```quantos-stages``` block")

    if args.config:
        series = asyncio.run(fetch_real(args.config, args.universe))
        logger.info("Comparing on %d real symbols.", len(series))
    else:
        series = synthetic_series()
        logger.info("Comparing on %d synthetic series (pass --config for real bars).",
                    len(series))

    all_mismatches = []
    for symbol, candles in series.items():
        all_mismatches += compare(symbol, candles, clauses, defaults, window=args.window)

    compared = len(series) * args.window
    if all_mismatches:
        print(f"\nDIVERGENCE — {len(all_mismatches)} of ~{compared} bars disagree:")
        for line in all_mismatches[:40]:
            print(f"  {line}")
        if len(all_mismatches) > 40:
            print(f"  ... and {len(all_mismatches) - 40} more")
        print("\nThe .pine and the note have drifted. Reconcile before trusting "
              "either the chart or the cockpit column.")
        return 1

    print(f"\nMATCH — {len(series)} symbols x {args.window} bars, "
          f"no disagreement between pine/weinstein_stage_journey.pine and "
          f"core/vault/stages.py.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
