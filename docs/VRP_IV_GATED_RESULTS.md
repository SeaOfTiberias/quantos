# IV-Gated Short Premium — Results

## Verdict

Primary arm (strangle): **FAIL**.

Methodology: docs/VRP_IV_GATED_METHODOLOGY.md (pre-committed 2026-10-06, commit 0749279, before this ran), with the data-quality rules in docs/VRP_IV_GATED_ADDENDUM_DATA_QUALITY.md (traded contracts only; zero settlement = missing). The first run, without them, is void. All figures NET of costs; returns are on margin, idle weeks count as 0.

- Cycles: 400 (2019-02-11 .. 2026-10-05); 40 without a gate state (warm-up or no ATM IV); first gated cycle 2019-11-15
- Cycles with no computable ATM IV: 0
- Strangle cycles using the 2% fallback on a leg: 0; condor cycles using a fallback wing: 0
- Expiry days where rows disagree on the settlement value: 0

## Segment A — fresh 2019-2023 (THE VERDICT)

### strangle (primary) — 193 eligible cycles, gate open 50

| Trades | Win rate | PF | Sharpe | Return/yr on margin | Max DD (pts) | Worst trade | Avg % credit | Runs | Top quarter |
|---|---|---|---|---|---|---|---|---|---|
| **gated** 50 | 72.0% | 0.709 | -0.397 | -26.1% | 156.4 | -70.6% | -20.0% | 14 | n/a |
| ungated 181 | 77.3% | 1.080 | 0.153 | +11.1% | 141.7 | -70.6% | +16.1% | 1 | 85% |

**FAIL**

- FAIL edge: PF 0.709 > 1.0 and Sharpe -0.397 > 0.5
- FAIL gate beats always-on: gated Sharpe -0.397 > ungated 0.153
- FAIL concentration: top quarter's share of net return n/a (total <= 0) <= 50%
- ok   sample: 50 gated trades >= 30

### straddle (secondary) — 193 eligible cycles, gate open 50

| Trades | Win rate | PF | Sharpe | Return/yr on margin | Max DD (pts) | Worst trade | Avg % credit | Runs | Top quarter |
|---|---|---|---|---|---|---|---|---|---|
| **gated** 50 | 64.0% | 1.005 | 0.006 | +0.6% | 161.2 | -80.9% | +0.4% | 14 | 1140% |
| ungated 181 | 63.5% | 1.136 | 0.270 | +29.9% | 161.2 | -80.9% | +4.7% | 1 | 36% |

**FAIL**

- FAIL edge: PF 1.005 > 1.0 and Sharpe 0.006 > 0.5
- FAIL gate beats always-on: gated Sharpe 0.006 > ungated 0.270
- FAIL concentration: top quarter's share of net return 1140% <= 50%
- ok   sample: 50 gated trades >= 30

### iron_condor (secondary) — 193 eligible cycles, gate open 50

| Trades | Win rate | PF | Sharpe | Return/yr on margin | Max DD (pts) | Worst trade | Avg % credit | Runs | Top quarter |
|---|---|---|---|---|---|---|---|---|---|
| **gated** 50 | 70.0% | 0.793 | -0.324 | -38.0% | 271.9 | -87.0% | -20.0% | 14 | n/a |
| ungated 181 | 75.7% | 1.214 | 0.522 | +89.4% | 250.1 | -87.8% | +11.4% | 1 | 47% |

**FAIL**

- FAIL edge: PF 0.793 > 1.0 and Sharpe -0.324 > 0.5
- FAIL gate beats always-on: gated Sharpe -0.324 > ungated 0.522
- FAIL concentration: top quarter's share of net return n/a (total <= 0) <= 50%
- ok   sample: 50 gated trades >= 30

## Segment B — 2023-2026, where the pattern was first seen (reported only)

### strangle (primary) — 157 eligible cycles, gate open 71

| Trades | Win rate | PF | Sharpe | Return/yr on margin | Max DD (pts) | Worst trade | Avg % credit | Runs | Top quarter |
|---|---|---|---|---|---|---|---|---|---|
| **gated** 71 | 74.6% | 1.447 | 0.741 | +20.0% | 31.3 | -17.6% | +17.6% | 23 | 41% |
| ungated 157 | 70.7% | 1.135 | 0.354 | +13.0% | 39.5 | -19.8% | +1.3% | 1 | 76% |


### straddle (secondary) — 157 eligible cycles, gate open 71

| Trades | Win rate | PF | Sharpe | Return/yr on margin | Max DD (pts) | Worst trade | Avg % credit | Runs | Top quarter |
|---|---|---|---|---|---|---|---|---|---|
| **gated** 71 | 69.0% | 1.684 | 1.064 | +49.7% | 41.3 | -21.7% | +13.2% | 23 | 37% |
| ungated 157 | 62.4% | 1.211 | 0.553 | +32.6% | 50.9 | -23.6% | +1.7% | 1 | 45% |


### iron_condor (secondary) — 157 eligible cycles, gate open 71

| Trades | Win rate | PF | Sharpe | Return/yr on margin | Max DD (pts) | Worst trade | Avg % credit | Runs | Top quarter |
|---|---|---|---|---|---|---|---|---|---|
| **gated** 71 | 74.6% | 1.200 | 0.364 | +45.0% | 142.8 | -83.7% | +7.0% | 23 | 90% |
| ungated 157 | 70.7% | 0.854 | -0.438 | -89.5% | 424.2 | -88.3% | -14.5% | 1 | n/a |


## Segment C — 2026-07-23 onward (reported only)

### strangle (primary) — 10 eligible cycles, gate open 1

| Trades | Win rate | PF | Sharpe | Return/yr on margin | Max DD (pts) | Worst trade | Avg % credit | Runs | Top quarter |
|---|---|---|---|---|---|---|---|---|---|
| **gated** 1 | 100.0% | inf | 2.280 | +17.0% | 0.0 | 3.3% | +99.8% | 1 | 100% |
| ungated 9 | 66.7% | 0.612 | -0.976 | -37.9% | 15.2 | -15.2% | -52.4% | 1 | n/a |


### straddle (secondary) — 10 eligible cycles, gate open 1

| Trades | Win rate | PF | Sharpe | Return/yr on margin | Max DD (pts) | Worst trade | Avg % credit | Runs | Top quarter |
|---|---|---|---|---|---|---|---|---|---|
| **gated** 1 | 100.0% | inf | 2.280 | +41.9% | 0.0 | 8.1% | +73.8% | 1 | 100% |
| ungated 9 | 22.2% | 0.413 | -1.914 | -97.5% | 20.2 | -18.6% | -30.9% | 1 | n/a |


### iron_condor (secondary) — 10 eligible cycles, gate open 1

| Trades | Win rate | PF | Sharpe | Return/yr on margin | Max DD (pts) | Worst trade | Avg % credit | Runs | Top quarter |
|---|---|---|---|---|---|---|---|---|---|
| **gated** 1 | 100.0% | inf | 2.280 | +67.9% | 0.0 | 13.1% | +99.7% | 1 | 100% |
| ungated 9 | 55.6% | 0.507 | -1.380 | -311.8% | 94.8 | -88.0% | -63.6% | 1 | n/a |


## Reading the result

- **The gate did the opposite of what was hoped on fresh data.** High IV
  arrives at the start of a crash, not after it. The gate opened in the
  week of 2020-03-06 (strangle −70.6% of margin) and stayed open through
  the COVID crash and the April rebound; 2020 Q1–Q2 alone lost −95.7% of
  margin. Budget week 2021-01-29 (−37.8%) was another gate-open week.
  Every trade checked here is a real move, not a data defect.
- **The 2023–2026 pattern was real in that window, but it didn't carry over.**
  Segment B still shows the gated strangle beating always-on (Sharpe
  0.74 vs 0.35), which is the exploratory finding. Segment A, data it
  never saw, reverses it (−0.40 vs 0.15). This is what a pattern that
  doesn't generalize looks like.
- **Excluding 2020 to "rescue" it would be the forbidden move.** The
  gated quarters after mid-2021 are mildly positive, but dropping the
  COVID crash is exactly what the methodology rules out. A gate that
  only works when you remove the crash it walks into isn't a gate.
- **Always-on selling is not a pass either.** The ungated arms in
  Segment A (strangle Sharpe 0.15, straddle 0.27, iron condor 0.52 with
  85%/36%/47% of return from one quarter) are not the test, and none
  is a validated edge. The condor's 0.52 is a secondary arm with the
  ungated rule never pre-registered as a candidate; reading it as a
  find would be the cherry-pick this project's discipline forbids.
- **Caveat on the rerun:** the data-quality rules in the addendum were
  written after the void first run. They are hygiene, not tuning, and
  they cut the profit, not created it, but the run is not fully blind.
