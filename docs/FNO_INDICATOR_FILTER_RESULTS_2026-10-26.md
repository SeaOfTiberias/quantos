# F&O screener — CCI(34)/EMA52 and SMA 5/40 filters: results

Rules: docs/FNO_INDICATOR_FILTER_PREREG_2026-10-26.md. One trade per breakout episode; halves split at 2026-03-27; 0 signal rows skipped for indicator warm-up. Returns are % per trade after 0.1% cost (futures on the underlying).

**Verdicts:** CE baseline × cci: FAIL; CE baseline × sma: FAIL; CE baseline × both: FAIL; PE baseline × cci: FAIL; PE baseline × sma: PASS; PE baseline × both: FAIL; PE H1 retest × cci: FAIL; PE H1 retest × sma: FAIL; PE H1 retest × both: FAIL

## CE baseline

| | n | days | mean/trade | win | t (day-clustered) | H1 | H2 | verdict |
|---|---|---|---|---|---|---|---|---|
| unfiltered | 2310 | 273 | -0.11% | 58% | -1.2 | -0.11% | -0.11% |  |
| cci: kept | 2142 | 268 | -0.11% | 58% | -1.6 | -0.12% | -0.09% | FAIL |
| cci: rejected | 168 | 109 | -0.11% | 60% | -0.5 | +0.03% | -0.29% |  |
| sma: kept | 2282 | 273 | -0.11% | 58% | -1.2 | -0.11% | -0.11% | FAIL |
| sma: rejected | 28 | 20 | +0.04% | 61% | -0.4 | +0.17% | -0.11% |  |
| both: kept | 2114 | 268 | -0.11% | 58% | -1.6 | -0.12% | -0.09% | FAIL |
| both: rejected | 196 | 126 | -0.09% | 60% | -0.7 | +0.05% | -0.27% |  |

## PE baseline

| | n | days | mean/trade | win | t (day-clustered) | H1 | H2 | verdict |
|---|---|---|---|---|---|---|---|---|
| unfiltered | 2646 | 275 | +0.23% | 67% | +2.6 | +0.40% | +0.03% |  |
| cci: kept | 2504 | 273 | +0.23% | 67% | +2.7 | +0.41% | +0.02% | FAIL |
| cci: rejected | 142 | 99 | +0.22% | 68% | +0.3 | +0.20% | +0.24% |  |
| sma: kept | 2612 | 275 | +0.25% | 67% | +2.8 | +0.42% | +0.04% | PASS |
| sma: rejected | 34 | 31 | -0.84% | 50% | -1.4 | -1.12% | -0.57% |  |
| both: kept | 2472 | 273 | +0.25% | 67% | +2.8 | +0.43% | +0.03% | FAIL |
| both: rejected | 174 | 125 | -0.00% | 64% | -0.4 | -0.07% | +0.08% |  |

## PE H1 retest

| | n | days | mean/trade | win | t (day-clustered) | H1 | H2 | verdict |
|---|---|---|---|---|---|---|---|---|
| unfiltered | 1672 | 269 | +0.34% | 69% | +3.7 | +0.41% | +0.25% |  |
| cci: kept | 1556 | 263 | +0.33% | 69% | +3.5 | +0.41% | +0.24% | FAIL |
| cci: rejected | 116 | 86 | +0.42% | 71% | +1.7 | +0.38% | +0.47% |  |
| sma: kept | 1646 | 268 | +0.34% | 69% | +3.9 | +0.43% | +0.24% | FAIL |
| sma: rejected | 26 | 24 | +0.10% | 65% | +0.3 | -1.12% | +1.32% |  |
| both: kept | 1531 | 262 | +0.33% | 69% | +3.8 | +0.43% | +0.22% | FAIL |
| both: rejected | 141 | 107 | +0.35% | 70% | +1.5 | +0.10% | +0.63% |  |

