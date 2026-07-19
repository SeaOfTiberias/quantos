# S8-1 Regime Classifier Validation

**Replayed 1254 trading days** (2021-06-28 to 2026-07-17).

## Forward NIFTY return by regime

| Regime | n | Mean 5d fwd % | Mean 10d fwd % | Mean 20d fwd % | Mean 20d realized vol |
|---|---|---|---|---|---|
| TRENDING_BULL | 334 | 0.27 | 0.41 | 0.89 | 0.63 |
| TRENDING_BEAR | 106 | 0.31 | 0.39 | 1.43 | 0.85 |
| RANGING | 172 | -0.12 | -0.33 | 0.05 | 0.83 |
| VOLATILE | 39 | 0.95 | 1.93 | 3.64 | 1.27 |
| UNCERTAIN | 603 | 0.16 | 0.46 | 0.58 | 0.83 |

## Verdict

- TRENDING_BULL's mean 10-day forward return (0.41%, n=334) vs UNCERTAIN's (0.46%, n=603): gap = -0.06pp.
- TRENDING_BEAR's mean 10-day forward return (0.39%, n=106) vs UNCERTAIN's (0.46%, n=603): gap = -0.07pp.
- RANGING's mean 20-day realized vol (0.83) vs VOLATILE's (1.27) — RANGING should be lower if the classifier is actually separating calm from turbulent regimes.
Read the gaps above against the sample sizes (`n`) in the table — a few percentage points on a handful of days is noise, not signal. This report presents the numbers; it does not compute a significance test, matching the zero-code, direct-arithmetic style of docs/EXPECTANCY_CHECK.md.
