# Darvas Bucket B: structural stop vs ATR stop -- results (2026-11-19)

Pre-registered in `docs/DARVAS_STRUCTURAL_STOP_PREREG_2026-11-19.md` (29fe6aa, amendment 1 347ab6a) before any code or run. Runner `scripts/research/darvas_structural_stop.py`.

## discovery

- trades 991: breakout not reproduced 9, not in store 77, ok 905
- **reproduction gate:** the re-simulated ATR arm matches the cached trade on 84.5% of the 905 simulated trades (need >= 90%)
- **GATE FAILS: no comparison is reported for this period.**

## confirmation

- trades 275: breakout not reproduced 5, ok 270
- **reproduction gate:** the re-simulated ATR arm matches the cached trade on 98.1% of the 270 simulated trades (need >= 90%)
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

**NO VERDICT: the reproduction gate failed or a period is missing.**

## Notes (2026-11-19, after the run)

- **A runner bug was fixed and only the affected trades re-run:** 42 trades crashed (`TypeError`: the L1 read returns no price on some historical dates). The pre-registered handling for "no read" is to keep the ATR stop; the runner now does that. The figures above are after the fix (discovery gate 85.1% → 84.5%).
- **Why the discovery gate fails:** of the 140 trades that don't reproduce, **129 have an entry price more than 0.5% off and 138 have the same exit reason.** The L1 store adjusts prices for splits and bonuses up to 2026, while the OOS run adjusted only up to its 2023 data end. The same trade sits at a different price scale, and the gate as written compares absolute exit prices within 1%.
- **Measured on returns** (exit ÷ entry within 1%, exit date within one session), the ATR arm reproduces **98.2%** of discovery trades and 99.6% of confirmation trades. The trades are the same; the gate's definition is at fault.
- **The discovery comparison has not been computed.** Changing a gate after it failed needs the user's decision (amendment 3, proposed: a return-based reproduction check). Until then, discovery has no verdict.
- Confirmation (2024-26), gate passed: structural − ATR **+0.42% per trade, CI −0.12% .. +0.98%**. Running-sum drawdown 164% vs 226%. The GLAND pattern is unchanged (47% vs 48% of losing stops come back above the entry within 15 sessions).
