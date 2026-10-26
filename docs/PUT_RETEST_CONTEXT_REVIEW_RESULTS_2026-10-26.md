# Put retest context review — results (2026-10-26)

Rules from claude-opus-5-5 (docs/PUT_RETEST_CONTEXT_REVIEW_LLM_2026-10-26.md), judged on the second half (signals from 2026-03-27) per docs/PUT_RETEST_CONTEXT_REVIEW_PREREG_2026-10-26.md. Returns % per trade after cost.

**Verdicts (held-out half):** skip_low_vix: FAIL; skip_stale_results: PASS; ALL rules (skip if any): FAIL

## first (seen) half — unfiltered: 900 | 69% | +0.41% | 1.41

| rule | kept n | kept win | kept mean | kept PF | skipped n | skipped win | skipped mean | skipped PF | t (kept − skipped) | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| skip_low_vix | 685 | 73% | +0.61% | 1.67 | 215 | 58% | -0.25% | 0.78 | +4.62 |  |
| skip_stale_results | 703 | 71% | +0.53% | 1.57 | 197 | 62% | -0.03% | 0.97 | +2.70 |  |
| ALL rules (skip if any) | 527 | 75% | +0.73% | 1.82 | 373 | 61% | -0.05% | 0.96 | +4.55 |  |

## second (held out) half — unfiltered: 772 | 70% | +0.25% | 1.24

| rule | kept n | kept win | kept mean | kept PF | skipped n | skipped win | skipped mean | skipped PF | t (kept − skipped) | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| skip_low_vix | 755 | 69% | +0.23% | 1.22 | 17 | 88% | +1.13% | 4.67 | -2.41 | FAIL |
| skip_stale_results | 552 | 72% | +0.38% | 1.39 | 220 | 63% | -0.07% | 0.94 | +2.11 | PASS |
| ALL rules (skip if any) | 536 | 72% | +0.36% | 1.36 | 236 | 65% | +0.01% | 1.00 | +1.72 | FAIL |

## Rules

- **skip_low_vix**: In complacent, very low-volatility markets breakdowns tend to get bought back, so the retest short stops out instead of reaching 0.75 ATR; VIX at or below about 11 was the worst bucket (54% win, -0.40% mean). Conditions: `[{"feature": "vix", "op": "<", "value": 11}]`
- **skip_stale_results**: More than ~9 weeks since the last results means the next results window is near and the breakdown lacks fresh fundamental drive; this bucket won only 60% with a negative mean. Conditions: `[{"feature": "days_since_results", "op": ">", "value": 45}]`
