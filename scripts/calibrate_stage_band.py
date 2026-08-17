"""
Calibrate the flat band in Stan_Weinstein_Stage_Analysis.md's stage block.

The question
────────────
The stage classifier separates "rising 30-week average" from "flat" with a
tolerance band:

    stage 4 when sma(150) < sma(150)[25] * (1 - b)
    stage 2 when sma(150) > sma(150)[25] * (1 + b)
    ...everything else is flat, and splits into Stage 1 / Stage 3 on prior trend

`b` decides where every boundary falls, and it has no principled value —
Weinstein drew "flat" by eye on a weekly chart. Too wide and Stages 1/3
swallow the market; too narrow and they vanish, because a 150-day average is
almost never *exactly* flat. So it is chosen empirically: run the real Nifty
500 through several widths and pick one whose distribution is not degenerate.

This exists because this vault has already shipped one unexamined threshold
that silently voided an entire strategy note — the 2.00-vs-1.25
distance-from-lows bug in Mark_Minervini_VCP_Strategy.md. A number this
load-bearing gets measured, and the measurement gets committed.

How the band is chosen
──────────────────────
There is no ground truth to score against — nobody has hand-labelled the
Nifty 500's stages, and inventing a labelling would just encode this
script's own assumptions. So the choice rests on two measurements, in order.

**1. The distribution must not be degenerate.** Every stage reachable, no
stage holding a large majority. This is a floor, not a chooser: it is
satisfied across a range so wide (0.25% to 5%) that it cannot pick between
them.

**2. Among those, minimise CHURN.** A band exists to stop a barely-moving
average from being called "rising". Its job is therefore stability: how often
does a name flip stage when nothing real has happened? Too narrow and the
slope hovers on the boundary, so names oscillate between Stage 2 and Stage 1
week to week. Too wide and stages stop meaning anything — a stock in a clear
advance is filed as "basing" — which shows up as the distribution collapsing
into Stage 1 rather than as churn.

Churn is measured as stage transitions per symbol over the trailing window,
using the same `stage_timeline` the chart draws, so the number describes the
thing a reader would actually see.

Neither measurement is evidence the classifier is CORRECT. It cannot be.
Nothing in this vault has been backtested and a stage label is not a signal —
see the note's own closing caveat.

Usage (on the VM, where Fyers auth is live):
    python scripts/calibrate_stage_band.py --config agent/config.yaml
    python scripts/calibrate_stage_band.py --universe agent/universe_alpha50.txt
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.vault.facts import MarketFacts
from core.vault.models import Stage
from core.vault.parser import parse_note
from core.vault.stages import (
    classify,
    parse_stage_clause,
    stage_timeline,
    stage_transitions,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("calibrate_stage_band")

# Mirrors run_momentum_shortlist.FETCH_WINDOW_DAYS. Measured 2026-08-17, this
# returns 271 trading bars (median and max; minimum observed 255), which is
# the binding constraint on how deep the prior-trend lag can reach — the
# Stage 3 clause's sma(150)[100] needs 250. It was sma(150)[125], needing
# 275, and classified nothing at all until this script caught it.
FETCH_WINDOW_DAYS = 400

NOTE_PATH = Path("obsidian_vault/QuantOS/brain/Stan_Weinstein_Stage_Analysis.md")

# The band width shipped in the note. Used to prove the template below
# reproduces the note exactly, so a calibration cannot silently measure
# something the vault does not actually run.
SHIPPED_BAND = 0.01

BANDS = (0.0, 0.0025, 0.005, 0.0075, 0.01, 0.015, 0.02, 0.03, 0.05)


def clauses_for(band: float, note_name: str = "calibration"):
    """The note's stage block, parameterised by band width.

    Kept as a template rather than regex-substituted into the note's text so
    the two can be COMPARED (see `_assert_template_matches_note`) instead of
    one silently drifting from the other.
    """
    up, down = 1.0 + band, 1.0 - band
    lines = [
        f"stage 4 when sma(150) < sma(150)[25] * {down:.4f}",
        f"stage 2 pivot when sma(150) > sma(150)[25] * {up:.4f} and volume_sma(5) / volume_sma(50) < 0.40",
        f"stage 2 pullback when sma(150) > sma(150)[25] * {up:.4f} and close < sma(150)",
        f"stage 2 when sma(150) > sma(150)[25] * {up:.4f}",
        "stage 3 when sma(150)[25] > sma(150)[100]",
        "stage 1",
    ]
    return [
        parse_stage_clause(line, note_name=note_name, line_number=i)
        for i, line in enumerate(lines, start=1)
    ]


def _assert_template_matches_note() -> None:
    """Fail loudly if the note and this script have diverged.

    Without this, editing the note's block would leave the calibration
    measuring a stale definition and reporting it as authoritative — which is
    exactly how a threshold ends up 'validated' against something nobody
    runs.
    """
    if not NOTE_PATH.exists():
        logger.warning("%s not found — skipping the template/note cross-check", NOTE_PATH)
        return

    note_expressions = [
        (c.stage, c.phase, _normalise(c.expression))
        for c in parse_note(NOTE_PATH).stage_clauses
    ]
    template_expressions = [
        (c.stage, c.phase, _normalise(c.expression))
        for c in clauses_for(SHIPPED_BAND)
    ]
    if note_expressions != template_expressions:
        raise SystemExit(
            "scripts/calibrate_stage_band.py's template no longer matches the "
            f"```quantos-stages``` block in {NOTE_PATH}.\n"
            f"  note:     {note_expressions}\n"
            f"  template: {template_expressions}\n"
            "Reconcile them before trusting any calibration output."
        )
    logger.info("Template matches the note's shipped block at band=%.2f%%.",
                SHIPPED_BAND * 100)


def _normalise(expression):
    """Compare expressions without tripping over float formatting — the note
    writes `1.01`, the template writes `1.0100`."""
    if expression is None:
        return None
    out = []
    for token in expression.replace("(", " ( ").replace(")", " ) ").split():
        try:
            out.append(f"{float(token):.6f}")
        except ValueError:
            out.append(token)
    return " ".join(out)


async def fetch_universe(config_path: Path, universe_path: Path) -> dict:
    """Daily bars for every symbol, via the same chunked fetch the live
    shortlist uses — Fyers caps a single history request at 366 days."""
    # Same construction path as scripts/run_momentum_shortlist.py — the point
    # is to read exactly the bars the live shortlist reads, so a band chosen
    # here is a band chosen against production data.
    from agent.main import _load_universe, load_config
    from core.brokers import get_broker
    from scripts.validate_regime_classifier import fetch_chunked_daily

    config = load_config(str(config_path))
    broker = get_broker(config)
    broker.connect()

    symbols = _load_universe(str(universe_path))
    logger.info("Fetching %d symbols (%d-day window)...", len(symbols), FETCH_WINDOW_DAYS)

    to_date = datetime.now(timezone.utc)
    from_date = to_date - timedelta(days=FETCH_WINDOW_DAYS)
    sem = asyncio.Semaphore(2)

    daily = {}
    for index, symbol in enumerate(symbols, start=1):
        candles = await fetch_chunked_daily(broker, symbol, from_date, to_date, sem)
        if candles:
            daily[symbol] = candles
        if index % 50 == 0:
            logger.info("  ... %d/%d fetched (%d usable)", index, len(symbols), len(daily))
    logger.info("Fetched %d/%d symbols with usable history.", len(daily), len(symbols))
    return daily


def distribution(daily: dict, band: float) -> Counter:
    clauses = clauses_for(band)
    counts: Counter = Counter()
    for symbol, candles in daily.items():
        result = classify(clauses, MarketFacts(symbol, candles))
        counts[result.stage.value if result.stage else "unclassified"] += 1
        if result.stage is Stage.ADVANCING and result.phase:
            counts[f"2·{result.phase}"] += 1
    return counts


def churn(daily: dict, band: float, *, window: int) -> float:
    """Mean stage transitions per symbol over the trailing `window` sessions.

    Uses `stage_timeline`, i.e. the same walk the chart draws, so this is
    literally "how many times would a reader have seen this name change
    stage" and not a proxy for it. Unclassified stretches are skipped rather
    than counted as a transition into and out of nothing.
    """
    clauses = clauses_for(band)
    totals = []
    for symbol, candles in daily.items():
        timeline = stage_timeline(clauses, MarketFacts(symbol, candles),
                                  bars=window)
        classified = [(o, r) for o, r in timeline if r.stage is not None]
        if len(classified) < 2:
            continue
        totals.append(len(stage_transitions(classified)))
    return sum(totals) / len(totals) if totals else float("nan")


def report(daily: dict, *, window: int) -> dict:
    total = len(daily)
    rows = []
    print(f"\n{'band':>7} | {'S1':>5} {'S2':>5} {'S3':>5} {'S4':>5} {'?':>5} | "
          f"{'2·pivot':>8} {'2·pull':>7} | {'churn':>6} | verdict")
    print("-" * 90)

    for band in BANDS:
        counts = distribution(daily, band)
        s1, s2, s3, s4 = (counts[i] for i in (1, 2, 3, 4))
        unknown = counts["unclassified"]
        classified = total - unknown
        flags = []
        if classified and min(s1, s2, s3, s4) == 0:
            flags.append("a stage is empty")
        if classified and max(s1, s2, s3, s4) > 0.50 * classified:
            flags.append("one stage >50%")
        band_churn = churn(daily, band, window=window)
        rows.append({
            "band": band, "stage_1": s1, "stage_2": s2, "stage_3": s3, "stage_4": s4,
            "unclassified": unknown, "pivot": counts["2·pivot"],
            "pullback": counts["2·pullback"], "churn": band_churn, "flags": flags,
        })
        print(f"{band * 100:6.2f}% | {s1:5d} {s2:5d} {s3:5d} {s4:5d} {unknown:5d} | "
              f"{counts['2·pivot']:8d} {counts['2·pullback']:7d} | {band_churn:6.2f} | "
              f"{'; '.join(flags) if flags else 'ok'}")

    usable = [r for r in rows if not r["flags"]]
    print(f"\n(churn = mean stage changes per symbol over {window} sessions; lower is "
          f"a more stable label)")
    pick = None
    if usable:
        pick = min(usable, key=lambda r: r["churn"])
        print(f"Least-churning non-degenerate band: {pick['band'] * 100:.2f}% "
              f"({pick['churn']:.2f} changes/symbol)   shipped: {SHIPPED_BAND * 100:.2f}%")
    else:
        print("No band cleared the structural checks — inspect the table by hand.")
    return {"total_symbols": total, "shipped_band": SHIPPED_BAND,
            "churn_window": window,
            "recommended_band": pick["band"] if pick else None, "rows": rows}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, default=Path("agent/config.yaml"))
    parser.add_argument("--universe", type=Path,
                        default=Path("agent/universe_nifty500.txt"))
    parser.add_argument("--churn-window", type=int, default=60,
                        help="Sessions to measure stage stability over.")
    parser.add_argument("--out", type=Path,
                        default=Path("results/stage_band_calibration.json"))
    args = parser.parse_args()

    _assert_template_matches_note()

    daily = asyncio.run(fetch_universe(args.config, args.universe))
    if not daily:
        logger.error("No history fetched — is the Fyers token refreshed?")
        return 1

    summary = report(daily, window=args.churn_window)
    summary["universe"] = str(args.universe)
    summary["generated_at"] = datetime.now(timezone.utc).isoformat()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    logger.info("Wrote %s", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
