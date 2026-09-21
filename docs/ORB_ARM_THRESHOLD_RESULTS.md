# ORB Options Scalping — Arm-Threshold Grid Results (Candidate 18)

Methodology: docs/ORB_ARM_THRESHOLD_METHODOLOGY.md, pre-registered 2026-09-21 before this backtest ran. Grid, materiality bar, mining/holdout split, and the tie-break rule were all fixed there -- nothing below was decided after seeing a result.

## NIFTY

Mining: 855 days. Holdout: 214 days.

| Multiplier | Mining N | Mining PF | Mining Sharpe | Holdout N | Holdout PF | Holdout Sharpe |
|---|---|---|---|---|---|---|
| 0.25x | 835 | 1.05 | 0.10 | 214 | 0.61 | -2.33 |
| 0.50x | 835 | 1.22 | 0.74 | 214 | 0.76 | -1.13 |
| 0.75x | 835 | 1.34 | 1.10 | 214 | 0.89 | -0.40 |
| 1.00x | 835 | 1.34 | 1.13 | 214 | 0.92 | -0.15 |

Baseline (1.00x): mining PF 1.34/Sharpe 1.13, holdout PF 0.92/Sharpe -0.15.

**0.25x — not adoptable.** Mining: PF 1.05/Sharpe 0.10 fails the bar itself. Holdout: PF 0.61/Sharpe -2.33 fails the bar itself.
**0.50x — not adoptable.** Mining: Sharpe delta -0.39 < required +0.10. Holdout: PF 0.76/Sharpe -1.13 fails the bar itself.
**0.75x — not adoptable.** Mining: Sharpe delta -0.04 < required +0.10. Holdout: PF 0.89/Sharpe -0.40 fails the bar itself.

## BANKNIFTY

Mining: 1054 days. Holdout: 264 days.

| Multiplier | Mining N | Mining PF | Mining Sharpe | Holdout N | Holdout PF | Holdout Sharpe |
|---|---|---|---|---|---|---|
| 0.25x | 1025 | 1.02 | 0.49 | 255 | 0.80 | -0.07 |
| 0.50x | 1025 | 1.05 | 0.50 | 255 | 0.94 | 0.45 |
| 0.75x | 1025 | 1.11 | 0.77 | 255 | 1.15 | 0.88 |
| 1.00x | 1025 | 1.14 | 0.93 | 255 | 1.25 | 1.06 |

Baseline (1.00x): mining PF 1.14/Sharpe 0.93, holdout PF 1.25/Sharpe 1.06.

**0.25x — not adoptable.** Mining: PF 1.02/Sharpe 0.49 fails the bar itself. Holdout: PF 0.80/Sharpe -0.07 fails the bar itself.
**0.50x — not adoptable.** Mining: Sharpe delta -0.43 < required +0.10. Holdout: PF 0.94/Sharpe 0.45 fails the bar itself.
**0.75x — not adoptable.** Mining: Sharpe delta -0.17 < required +0.10. Holdout: Sharpe delta -0.18 < required +0.10.

## Verdict

**No grid point clears the pre-registered bar on both indices.** Per the methodology doc, the current 1.0x arm threshold stays as-is -- this is reported as a real, legitimate negative result, not grounds to widen the grid or lower the materiality bar after the fact.
