#!/usr/bin/env python3
"""
QuantOS — Darvas Bucket B go/no-go bands from the frozen OOS backtest (E2, 2026-11-19)
────────────────────────────────────────────────────────────────────────────────────────
docs/EXECUTION_PLAN_2026-11-19.md, E2. Computes what k closed trades of Darvas ATR-stop
Bucket B (box width 35-50%) look like in the 2016-2023 out-of-sample backtest, so the paper
record can be judged against it. Reads only the backtest's own results cache
(~/.quantos/darvas_atr_stop_oos_results.json, written by scripts/backtest_darvas_atr_stop_oos.py
on 2026-10-05) with that script's own trade assembly and Stressed cost. It reads NO paper trade.

Check first: the rebuilt Bucket B must reproduce the published OOS numbers (991 trades, mean
net +2.16%, docs/DARVAS_ATR_STOP_OOS_RESULTS.md) or nothing is written.

For k = 10, 20, 30, every run of k consecutive trades in EXIT order (the order a paper record
closes in; runs keep the clustering by market regime that independent draws would hide):
  - mean net return per trade: 5th, 10th, 25th, 50th percentiles;
  - drawdown: the largest peak-to-trough fall of the running SUM of net returns (equal size per
    trade, in % of one position): 50th, 90th, 95th percentiles.
An independent (iid) bootstrap of the same statistics is printed beside them, for comparison only.
Power: the share of rolling windows of a ZERO-EDGE copy (every net minus the mean) whose mean falls
below that k's 10th percentile, i.e. how often the consistency check would catch a system with no edge.

    python scripts/research/darvas_go_no_go_bands.py      # writes docs/DARVAS_GO_NO_GO_BANDS.json
"""
from __future__ import annotations

import json
import random
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.backtest_darvas_atr_stop_oos import CACHE, net_return  # noqa: E402
from scripts.backtest_darvas_box_width import BUCKETS, STRESSED_COST_MODEL  # noqa: E402
from scripts.backtest_darvas_trailing_stop import all_trades  # noqa: E402

OUT = ROOT / "docs" / "DARVAS_GO_NO_GO_BANDS.json"
KS = (10, 20, 30, 60)
BOOT, SEED = 10_000, 20261119
EXPECT_N, EXPECT_MEAN = 991, 0.0216          # docs/DARVAS_ATR_STOP_OOS_RESULTS.md, Bucket B


def max_drawdown(xs: list[float]) -> float:
    """Largest peak-to-trough fall of the running sum (>= 0). Pure."""
    run = peak = dd = 0.0
    for x in xs:
        run += x
        peak = max(peak, run)
        dd = max(dd, peak - run)
    return dd


def pct(xs: list[float], q: float) -> float:
    s = sorted(xs)
    return s[min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))]


def bands(nets: list[float], k: int) -> dict:
    """Rolling windows of k consecutive trades (nets already in exit order). Pure."""
    means = [statistics.mean(nets[i:i + k]) for i in range(len(nets) - k + 1)]
    dds = [max_drawdown(nets[i:i + k]) for i in range(len(nets) - k + 1)]
    return {"windows": len(means),
            "mean_p05": pct(means, .05), "mean_p10": pct(means, .10), "mean_p25": pct(means, .25),
            "mean_p50": pct(means, .50), "share_mean_below_0": sum(m < 0 for m in means) / len(means),
            "dd_p50": pct(dds, .50), "dd_p90": pct(dds, .90), "dd_p95": pct(dds, .95)}


def iid(nets: list[float], k: int, rng: random.Random) -> dict:
    draws = [[rng.choice(nets) for _ in range(k)] for _ in range(BOOT)]
    means, dds = [statistics.mean(d) for d in draws], [max_drawdown(d) for d in draws]
    return {"mean_p10": pct(means, .10), "dd_p90": pct(dds, .90)}


def main() -> int:
    results = json.loads(CACHE.read_text())
    pred = dict(BUCKETS)["35-50%"]
    tr = sorted((t for t in all_trades(results) if pred(t["width_pct"])), key=lambda t: (t["exit_date"], t["entry_date"]))
    nets = [net_return(t, STRESSED_COST_MODEL) for t in tr]
    n, mean = len(nets), statistics.mean(nets)
    print(f"rebuilt Bucket B: n={n}, mean net {mean:+.2%}")
    if n != EXPECT_N or round(mean, 4) != EXPECT_MEAN:
        print(f"does NOT reproduce the published OOS result (n={EXPECT_N}, {EXPECT_MEAN:+.2%}): nothing written")
        return 1
    rng = random.Random(SEED)
    out = {"source": "docs/DARVAS_ATR_STOP_OOS_RESULTS.md (2016-07..2023-09 breakouts, Stressed costs)",
           "n_trades": n, "mean_net": mean, "median_net": statistics.median(nets),
           "win_rate": sum(x > 0 for x in nets) / n, "order": "exit date",
           "rolling": {k: bands(nets, k) for k in KS}, "iid_for_comparison": {k: iid(nets, k, rng) for k in KS}}
    zero = [x - mean for x in nets]
    for k in KS:
        thr = out["rolling"][k]["mean_p10"]
        zm = [statistics.mean(zero[i:i + k]) for i in range(len(zero) - k + 1)]
        out["rolling"][k]["power_zero_edge_below_p10"] = sum(m < thr for m in zm) / len(zm)
    OUT.write_text(json.dumps(out, indent=1))
    for k in KS:
        b, i = out["rolling"][k], out["iid_for_comparison"][k]
        print(f"k={k}: mean p05 {b['mean_p05']:+.2%} p10 {b['mean_p10']:+.2%} p25 {b['mean_p25']:+.2%} "
              f"p50 {b['mean_p50']:+.2%} (<0 in {b['share_mean_below_0']:.0%}); dd p50 {b['dd_p50']:.1%} "
              f"p90 {b['dd_p90']:.1%} p95 {b['dd_p95']:.1%} | zero-edge caught {b['power_zero_edge_below_p10']:.0%} "
              f"| iid mean p10 {i['mean_p10']:+.2%} dd p90 {i['dd_p90']:.1%}")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
