# Darvas second chance: results (2026-11-19) — FAIL

Pre-registered in `docs/DARVAS_REENTRY_PREREG_2026-11-17.md` (47833c9) before any run. Run with the frozen runner `scripts/research/darvas_reentry.py` and `scripts/call_plans.py --replay-from` (map plan d06b88d + fixes, no starter), three chunks on the L1 snapshot `l1_snap_20261113`, on the PC. Five worked cases were checked first (ATUL 2016-07-29 swept a strong W bull OB at 1903.3, entered 1909, target 2020: +3.04R; RCF, COX&KINGS, EQUITAS and BASF lapsed).

**Picks:** losing Bucket B stop-outs. 175 (2016-19), 253 (2020-23), 131 (2024-26); 32 dropped (not in the store).

## Main entries, net R (0.25% round trip inside R)

| Period | n | net R | t | net % |
|---|---|---|---|---|
| 2016-19 | 18 | +1.05 | +1.46 | +1.43% |
| 2020-23 | 36 | **−0.09** | −0.33 | −0.46% |
| **2016-23 discovery** | **54** | +0.29 | **+0.94** | +0.17% |
| **2024-26 confirmation** | 15 | **−0.39** | −1.19 | −2.33% |

## Verdict: FAIL

- Discovery: n 54 < 60, t 0.94 < 2, and 2020-23 is below 0. Three of the four discovery conditions fail.
- Confirmation: mean −0.39R (and n 15 < 20).

Reported as failed; not re-tuned this round.

## Reported, not scored

- **By exit:** targets average +2.6 to +3.7R, but stops outnumber them 42 to 18 overall.
- **By level:** D protected lows (34 entries, −0.16R) dominate. D equal lows +0.44R on 15 entries.
- **Entered:** 17 of 175, 30 of 253, 13 of 131 (about 10%).
- **What the map re-entry adds per Bucket B trade:** +0.07%, −0.03%, −0.13%.
- **Plain re-entry** (next open, hold 15 sessions, net): −0.81% (t −1.00, n 175), +0.90% (t +1.10, n 253), +1.96% (t +2.01, n 131).
  - This is a reported control, not a lead. Under the execution plan's rules, no new pre-registration is spun from a failed test's side results.
