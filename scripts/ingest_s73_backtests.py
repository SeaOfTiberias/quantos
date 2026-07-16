#!/usr/bin/env python3
"""
S7-3 — Ingest per-symbol TradingView Strategy Tester exports and produce the
aggregate go/no-go verdict for the pre-committed Darvas backtest sample.

Usage:
    python scripts/ingest_s73_backtests.py data/s73_backtests/ \
        --sample docs/S7_3_BACKTEST_SAMPLE.md \
        --slippage-bps 20 \
        --out docs/S7_3_BACKTEST_RESULTS.md

Each file in the input directory must be named SYMBOL.csv (e.g.
APOLLOTYRE.csv) — TradingView's trade-list export doesn't carry the ticker
inside the CSV itself, so the filename is the only place to recover it from.

Cross-checks the input directory against docs/S7_3_BACKTEST_SAMPLE.md and
refuses to produce a verdict if the analyzed set doesn't match the
pre-committed one exactly (missing OR extra symbols) unless --allow-partial
is passed. The whole point of pre-committing the sample was that it can't
shift after seeing results — a script that silently tolerated a partial or
padded set would defeat that.

--slippage-bps models breakout-entry fill friction that TradingView's
frictionless backtest fills don't include (see core/risk/costs.py and
docs/EXPECTANCY_CHECK.md, which used 15-40bps as the plausible range).
Default 20bps sits in the middle of that range.
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.backtest.parser import parse_tradingview_csv, _compute_metrics, BacktestTrade  # noqa: E402
from core.risk.costs import CostModel  # noqa: E402

SAMPLE_LINE_RE = re.compile(r"^- ([A-Z0-9\-]+)\s*$")


def read_sample(sample_path: Path) -> tuple[set[str], set[str]]:
    """Return (large_mid_symbols, small_symbols) from the pre-committed sample doc."""
    text = sample_path.read_text(encoding="utf-8")
    large_mid, small, section = set(), set(), None
    for line in text.splitlines():
        if "Large/mid cap tier" in line:
            section = "large_mid"
            continue
        if "Small cap tier" in line:
            section = "small"
            continue
        m = SAMPLE_LINE_RE.match(line.strip())
        if m and section == "large_mid":
            large_mid.add(m.group(1))
        elif m and section == "small":
            small.add(m.group(1))
    return large_mid, small


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv_dir", type=Path, help="directory of SYMBOL.csv trade-list exports")
    ap.add_argument("--sample", type=Path, default=Path("docs/S7_3_BACKTEST_SAMPLE.md"))
    ap.add_argument("--slippage-bps", type=float, default=20.0)
    ap.add_argument("--out", type=Path, default=Path("docs/S7_3_BACKTEST_RESULTS.md"))
    ap.add_argument("--allow-partial", action="store_true",
                     help="proceed even if the CSV set doesn't exactly match the pre-committed sample")
    args = ap.parse_args()

    large_mid, small = read_sample(args.sample)
    expected = large_mid | small
    tier_of = {s: "large_mid" for s in large_mid}
    tier_of.update({s: "small" for s in small})

    found = {p.stem.upper(): p for p in args.csv_dir.glob("*.csv")}

    missing = expected - found.keys()
    extra = found.keys() - expected
    if extra:
        print(f"ERROR: {len(extra)} CSV(s) not in the pre-committed sample: {sorted(extra)}")
        print("The analyzed set can't include symbols outside the pre-commit - remove them.")
        return 1
    if missing and not args.allow_partial:
        print(f"ERROR: {len(missing)} pre-committed symbol(s) have no CSV yet: {sorted(missing)}")
        print("Either supply all 40, or re-run with --allow-partial to report on what's in so far "
              "(the output will say so loudly - this is not a substitute for the full sample).")
        return 1

    cost_model = CostModel(slippage_bps=args.slippage_bps)
    all_trades: list[BacktestTrade] = []
    tier_trades: dict[str, list[BacktestTrade]] = {"large_mid": [], "small": []}
    per_symbol_rows = []
    no_trade_symbols = []

    for symbol in sorted(found.keys() & expected):
        csv_text = found[symbol].read_text(encoding="utf-8-sig")
        try:
            report = parse_tradingview_csv(csv_text, strategy_name=symbol, cost_model=cost_model)
        except ValueError:
            no_trade_symbols.append(symbol)
            continue
        all_trades.extend(report.total_trades)
        tier_trades[tier_of[symbol]].extend(report.total_trades)
        m = report.overall
        per_symbol_rows.append(
            f"| {symbol} | {tier_of[symbol]} | {m.total_trades} | {m.win_rate:.0%} | "
            f"{m.profit_factor:.2f} | {m.net_profit_pct:.1f}% |"
        )

    if not all_trades:
        print("No trades parsed across any symbol - nothing to report.")
        return 1

    overall = _compute_metrics(all_trades)
    lm_metrics = _compute_metrics(tier_trades["large_mid"]) if tier_trades["large_mid"] else None
    sm_metrics = _compute_metrics(tier_trades["small"]) if tier_trades["small"] else None

    verdict = "POSITIVE net-of-cost edge" if overall.has_positive_edge else "NO demonstrated edge"

    lines = [
        "# S7-3 Backtest Results — go/no-go verdict",
        "",
        f"**Sample:** {len(found.keys() & expected)} "
        f"of {len(expected)} pre-committed symbols analyzed"
        + (f" ({len(missing)} missing: {sorted(missing)} — PARTIAL, not a full verdict)" if missing else ""),
        f"**Cost model:** NSE stack + {args.slippage_bps:.0f}bps slippage/leg (core/risk/costs.py)",
        f"**No-trade symbols (box never fired in the tested window):** "
        f"{', '.join(no_trade_symbols) if no_trade_symbols else 'none'}",
        "",
        f"## Verdict: {verdict}",
        "",
        f"- Total trades (pooled, all symbols): {overall.total_trades}",
        f"- Win rate: {overall.win_rate:.1%}",
        f"- Profit factor: {overall.profit_factor:.2f}",
        f"- Sharpe ratio: {overall.sharpe_ratio:.2f}",
        f"- Max drawdown: {overall.max_drawdown_pct:.1f}%",
        f"- Net profit (sum of per-trade net %): {overall.net_profit_pct:.1f}%",
        f"- Overfit risk flag: {'YES' if overall.is_overfit_risk else 'no'}",
        "",
        "## By cap tier",
        "",
        "| Tier | Trades | Win rate | Profit factor | Net % |",
        "|---|---|---|---|---|",
    ]
    if lm_metrics:
        lines.append(f"| Large/mid | {lm_metrics.total_trades} | {lm_metrics.win_rate:.0%} | "
                      f"{lm_metrics.profit_factor:.2f} | {lm_metrics.net_profit_pct:.1f}% |")
    if sm_metrics:
        lines.append(f"| Small | {sm_metrics.total_trades} | {sm_metrics.win_rate:.0%} | "
                      f"{sm_metrics.profit_factor:.2f} | {sm_metrics.net_profit_pct:.1f}% |")

    lines += [
        "",
        "## By symbol",
        "",
        "| Symbol | Tier | Trades | Win rate | Profit factor | Net % |",
        "|---|---|---|---|---|---|",
        *per_symbol_rows,
        "",
        "Remember: this sample is survivorship-biased (current Nifty 500 constituents) "
        "and thus an UPPER BOUND. A negative verdict here is conclusive (costs beat the "
        "edge even with the bias helping); a positive verdict here is necessary but not "
        "sufficient — it still needs S7-4's veto instrumentation before the live record "
        "is interpretable.",
    ]

    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote verdict ({verdict}) to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
