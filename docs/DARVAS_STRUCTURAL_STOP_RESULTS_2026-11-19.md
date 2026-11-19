# Darvas Bucket B: structural stop vs ATR stop -- results (2026-11-19)

Pre-registered in `docs/DARVAS_STRUCTURAL_STOP_PREREG_2026-11-19.md` (29fe6aa, amendment 1 347ab6a) before any code or run. Reproduction gate on returns per amendment 3 (user, 2026-11-20). Runner `scripts/research/darvas_structural_stop.py`.

## discovery

- trades 991: breakout not reproduced 9, not in store 77, ok 905
- **reproduction gate:** the re-simulated ATR arm matches the cached trade on 98.2% of the 905 simulated trades (need >= 90%)
- **paired difference (structural - ATR), net per trade: -0.26%**, week-bootstrap 90% CI -0.64% .. +0.11%; 2016-19 +0.19% (n 339); 2020-23 -0.54% (n 566)

| | ATR arm | structural arm |
|---|---|---|
| mean net | +1.94% | +1.67% |
| win rate | 46.5% | 41.1% |
| running-sum drawdown (exit order) | 602% | 518% |
| mean initial risk (% of entry) | 11.6% | 10.3% |
| mean R (reported, not compared) | +0.27 | +0.24 |
| losing stops back above entry within 15 sessions (GLAND pattern) | 44% of 466 | 52% of 517 |

- initial stop differs on 660 of 905 trades (290 wider, 370 tighter); no level 245; gap at entry 1
- level kinds: D protected 240, W protected 164, D equal lows 161, W multi-touch x3 96, M protected 56, W multi-touch x4 42, W multi-touch x5 20, EQL 16

## confirmation

- trades 275: breakout not reproduced 5, ok 270
- **reproduction gate:** the re-simulated ATR arm matches the cached trade on 99.6% of the 270 simulated trades (need >= 90%)
- **paired difference (structural - ATR), net per trade: +0.42%**, week-bootstrap 90% CI -0.12% .. +0.98%; 2024-26 +0.42% (n 270)

| | ATR arm | structural arm |
|---|---|---|
| mean net | +0.75% | +1.17% |
| win rate | 43.3% | 42.2% |
| running-sum drawdown (exit order) | 226% | 164% |
| mean initial risk (% of entry) | 11.3% | 11.0% |
| mean R (reported, not compared) | +0.14 | +0.12 |
| losing stops back above entry within 15 sessions (GLAND pattern) | 48% of 142 | 47% of 142 |

- initial stop differs on 186 of 270 trades (101 wider, 85 tighter); no level 84; gap at entry 2
- level kinds: D protected 95, D equal lows 65, W protected 33, W multi-touch x3 22, M protected 12, W multi-touch x4 5, W multi-touch x5 3, STRONG W bull OB 216.225-227.675 (2023-W51) 1

## Verdict

1. discovery mean > 0 and CI lower > 0: **FAILS**
2. both discovery halves > 0: **FAILS**
3. confirmation mean > 0: holds

**FAIL**


## Notes

- **2026-11-19, first scoring: NO VERDICT.** The reproduction gate as first written compared absolute exit prices and failed for discovery (84.5% < 90%). Cause: the L1 store adjusts for splits and bonuses up to 2026, the OOS run only to 2023, so one trade sits at two price scales (129 of the 140 misses had the entry more than 0.5% off; 138 had the same exit reason). Confirmation passed (98.1%) and was reported then: +0.42%, CI −0.12% .. +0.98%.
- **2026-11-20, amendment 3 (user-approved, 99b358d) before the discovery comparison was computed:** the gate compares returns (exit ÷ entry within 1%, exit date within 3 days). Same stored rows, no re-simulation. Discovery now reproduces 98.2%, confirmation 99.6%.
- **Result: FAIL, as pre-registered, not re-tuned.** Over 905 discovery trades the structural stop costs **−0.26% per trade** (CI −0.64% .. +0.11%). It helps in 2016-19 (+0.19%) and hurts in 2020-23 (−0.54%). The +0.42% in 2024-26 is the only positive period, and on its own it doesn't meet the bar.
- **What the structural stop does:** it is tighter on more trades than it is wider (370 vs 290 in discovery), cuts the win rate from 46.5% to 41.1%, and makes the GLAND pattern **worse**: 52% of its losing stops come back above entry within 15 sessions, against 44% for the ATR stop. Map levels under the box shake out more trades that would have worked.
- A bug fix during the run: 42 trades crashed because the L1 read returns no price on some historical dates. The pre-registered "no read" handling (keep the ATR stop) was applied, and only those trades were re-run.
- **Consequence:** the Darvas executor keeps the ATR stop. No structural-stop paper variant.
