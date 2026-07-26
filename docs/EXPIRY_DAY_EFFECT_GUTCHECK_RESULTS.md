# F&O Monthly Expiry-Day Effect Gut-Check

Methodology: docs/EXPIRY_DAY_EFFECT_GUTCHECK_METHODOLOGY.md. NIFTY spot, 2024-01-01 to 2026-07-24 (631 trading days, 31 expiries).

## Mean |daily return| by day-group

| Group | n | Mean return % | Mean \|return\| % |
|---|---|---|---|
| expiry | 31 | -0.121 | 0.555 |
| pre_expiry | 31 | -0.030 | 0.604 |
| post_expiry | 30 | +0.368 | 0.732 |
| other | 538 | +0.009 | 0.616 |

## Verdict

- `expiry` mean |return| (0.555%, n=31) vs `other` (0.616%, n=538): gap = -0.062pp (-10.0% relative).
- `pre_expiry` mean |return| (0.604%, n=31) vs `other` (0.616%, n=538): gap = -0.012pp (-2.0% relative).
- `post_expiry` mean |return| (0.732%, n=30) vs `other` (0.616%, n=538): gap = +0.115pp (+18.7% relative).
Read the gaps above against the sample sizes (`n`) in the table -- only ~31 expiries in this window, the disclosed thin-sample limitation in the methodology doc. No demeaning, no market adjustment, no invented significance test, same style as docs/VOL_SPREAD_VALIDATION.md and docs/VOL_SKEW_VALIDATION.md.
