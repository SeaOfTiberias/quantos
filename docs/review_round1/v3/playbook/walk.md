# Playbook v1 walk-through (2026-11-13)

Code 0746807 (`core/market_map/playbook.py`; rules in `docs/MARKET_PLAYBOOK_V1.md`, c00010e). Run on the VM from a scratch copy, against the live stores (read-only).

**A walk-through, not a test.** No P&L verdict comes from 15 reads (playbook "Testing"). The verdict needs the S8 pre-registration with a placebo. Paper only.

Full plans and logs: `walk.json`.

## The 15 round 1 reads (v3 maps)

| Read | Plan | What happened |
|---|---|---|
| R01 KEI 2025-06-23 | P1 short: limit 3875.5, stop 3988.8, target 2424 (12.8R) | Filled 06-25. +1R on 07-09, stop to break-even. Stopped at break-even 07-15. **0R** (best +2.42R, worst −0.57R) |
| R02 DMART 2026-08-28 | P1 short: limit 4670, stop 4972.4, target 3755.1 | **C3:** the target traded on 08-31 before any rally to 4670. No trade |
| R03 JSL 2026-03-04 | P1 long: limit 714.85, stop 644.65, target 884 | Filled 03-09. W turned down at the 03-13 close. **E1** exit at the 03-16 open, 706.9: **−0.11R** (the stop would have cost −1R) |
| R04 LTM | No trade | Zone too wide: risk 648.65 > 1.5 ATR(W) = 441.22 |
| R05 HCLTECH 2025-07-14 | P1 long: limit 1598, stop 1536.9, target 1752.5 | Filled at the 1590 gap open 07-15. Stopped 07-18: **−0.87R** |
| R06 ANTELOPUS | No trade | Zone too wide |
| R07 NEOGEN 2026-10-21 | P1 long: limit 2259, stop 2055.35, target 2785 | Filled 10-22. Stopped 11-02: **−1R** (best +0.49R) |
| R08 GRSE 2026-08-07 | P1 long: limit 2249, stop 2042.15, target 3339 | **C4:** no fill in 10 sessions |
| R09 IRFC | Wait | W up, M down: wait for a monthly close above 166.9 |
| R10 TEJASNET, R11 BIOCON, R12 SSWL, R13 BLUESTARCO | No trade | Zone too wide (each) |
| R14 NBCC | Wait | W up, M down: wait for a monthly close above 121.13 |
| R15 CHOLAFIN | Wait | W down, M up: wait for a monthly close below 1011.2 |

No P2 (reversal) setup was present at any of the 15 dates.

**Counts:** 7 setups, 4 filled, all 4 closed: 0, −0.11, −0.87 and −1.0R. 2 were cancelled (both C3), 1 expired. 6 reads were refused as zone too wide, 3 were waits.

## Discussion cases (not scored)

| Case | Plan | What happened |
|---|---|---|
| HDFCBANK 2026-10-28 | P1 short: limit 805, stop 846.65, target 681.9 | **C3** on day one. Price (680.2) was already below its target. |
| HDFCBANK 2026-11-05 | P1 short: limit 805, stop 846.9, target 669.2 | **C1:** W turned up at the 11-06 close, so the order was cancelled before it could fill (it would have filled on 11-11). |
| HDFCBANK 2026-11-05 | **P2 long:** limit 690.25, stop 665.3, target 749.3, half risk. The W swing low 682.5 was swept to 669.2 on 10-28; D CHoCH up 11-04 | **C3:** the target traded on 11-05, the setup's own first session, after a gap up. It never filled. |
| DMART 2026-11-13 | P1 short: limit 3688, stop 3917.8, target 3102.3 | Pending |
| KOTAKBANK 2026-11-13 | P1 long: limit 420.6, stop 396.65, target 480 | Pending |
| KEI and HDFCBANK 2026-11-13 | Wait (timeframes disagree) | — |

## What the walk-through shows (reported; any change is a playbook v2, written first)

1. **The salvage rules worked as written.**
   - E1 cut JSL at −0.11R instead of −1R.
   - Break-even turned KEI's open +2.4R into 0R instead of a loss.
   - C1 cancelled the HDFCBANK short that the old rules would have filled after the weekly flip.
2. **Break-even, then nothing.** KEI ran to +2.4R and gave all of it back. The D-structure trail never moved the stop beyond break-even, because D never printed a protected high below it.
   - Partial profit-taking or an R-based trail would change this.
   - That is a v2 question. It is not tuned here.
3. **The risk cap refuses 6 of 15 reads.** Strong zones made of whole W or M bars are often wider than 1.5 ATR(W) (map finding 3).
4. **A plan whose target has already traded should say "missed" at once,** not wait for C3 on day one (HDFCBANK 10-28).
5. **P2 waits for a pullback,** so a V-shaped turn leaves it unfilled. On HDFCBANK, the target traded in the setup's first session.
6. **4 filled trades say nothing about edge either way.** The verdict is S8's.
