---
title: 'Candidate 23 Stage 2 — Bull Call Spreads on Non-52-Week-High Surges — Results'
ingested: 2026-10-15
origin: 'D:\Exodus_14_14\QuantOS\quantos\obsidian_vault\QuantOS\raw\_inbox\SURGE_SPREAD_STAGE2_RESULTS.md'
checksum: 16fc8a9119c8180e23b5574fdc3e34f45ade3980e830f78c012635b827be8513
body_checksum: 7bccdcf337a119b49b65ad4763d32b94539a30b0d834ce5560457121d5f0e015
tags:
  - source/strategies
quantos:
  layer: raw
  immutable: true
---

# Candidate 23 Stage 2 — Bull Call Spreads on Non-52-Week-High Surges — Results

> [!info] Ingested source
> Filed 2026-10-15 from `D:\Exodus_14_14\QuantOS\quantos\obsidian_vault\QuantOS\raw\_inbox\SURGE_SPREAD_STAGE2_RESULTS.md`. Do not edit — wiki pages cite this
> file's contents, and `vault lint` re-hashes it to check.

Methodology: docs/SURGE_SPREAD_STAGE2_METHODOLOGY.md (pre-registered 2026-10-15). Entry at the surge-day close, exit at the close of min(t+8, the day before expiry), bhavcopy closing prices. Returns are on risk (net P&L / debit), so every trade carries equal weight. Statutory costs are in every scenario; Clean has no bid-ask, Base 1% and Stressed 2% of each leg price per side (₹0.05 minimum). Mining before 2025-01-07, holdout from 2025-01-07.

## Verdict: **FAIL**

- no structure has >= 100 mining trades with Stressed PF > 1

## All 16 structures — mining

| Structure | Clean: n, win, PF, Sharpe | Base: n, win, PF, Sharpe | Stressed: n, win, PF, Sharpe |
|---|---|---|---|
| L0W1 | 1717, 45%, 1.26, 0.72 | 1717, 33%, 0.58, -1.97 | 1717, 23%, 0.31, -4.70 |
| L0W2 | 1748, 46%, 1.89, 0.56 | 1748, 40%, 1.26, 0.23 | 1748, 34%, 0.92, -0.10 |
| L0W3 | 1683, 46%, 1.13, 0.93 | 1683, 41%, 0.83, -1.40 | 1683, 38%, 0.67, -3.08 |
| L0W4 | 1693, 46%, 1.19, 1.22 | 1693, 42%, 0.93, -0.50 | 1693, 40%, 0.80, -1.65 |
| L1W1 | 1687, 42%, 1.31, 1.04 | 1687, 31%, 0.63, -2.03 | 1687, 23%, 0.38, -4.44 |
| L1W2 | 1718, 43%, 1.30, 0.79 | 1718, 37%, 0.83, -0.61 | 1718, 32%, 0.63, -1.64 |
| L1W3 | 1665, 43%, 1.19, 1.11 | 1665, 39%, 0.86, -1.01 | 1665, 36%, 0.71, -2.32 |
| L1W4 | 1635, 42%, 1.17, 0.99 | 1635, 40%, 0.91, -0.61 | 1635, 38%, 0.80, -1.53 |
| L2W1 | 1625, 39%, 1.38, 0.67 | 1625, 28%, 0.64, -1.20 | 1625, 23%, 0.40, -3.02 |
| L2W2 | 1664, 39%, 1.05, 0.32 | 1664, 35%, 0.59, -1.78 | 1664, 31%, 0.43, -1.64 |
| L2W3 | 1577, 39%, 1.27, 0.78 | 1577, 36%, 0.92, -0.30 | 1577, 34%, 0.79, -0.80 |
| L2W4 | 1537, 39%, 1.10, 0.60 | 1537, 37%, 0.84, -1.06 | 1537, 36%, 0.75, -1.81 |
| L3W1 | 1565, 37%, 1.40, 1.04 | 1565, 27%, 0.60, -1.86 | 1565, 21%, 0.38, -3.27 |
| L3W2 | 1586, 37%, 1.15, 0.71 | 1586, 33%, 0.70, -2.02 | 1586, 30%, 0.57, -3.28 |
| L3W3 | 1471, 37%, 1.09, 0.51 | 1471, 34%, 0.77, -1.59 | 1471, 32%, 0.67, -2.43 |
| L3W4 | 1380, 36%, 1.02, 0.12 | 1380, 34%, 0.76, -1.67 | 1380, 33%, 0.69, -2.34 |

## All 16 structures — holdout (information only; cannot replace the chosen structure)

| Structure | Clean: n, win, PF, Sharpe | Base: n, win, PF, Sharpe | Stressed: n, win, PF, Sharpe |
|---|---|---|---|
| L0W1 | 547, 54%, 1.41, 2.44 | 547, 39%, 0.59, -3.70 | 547, 28%, 0.26, -9.13 |
| L0W2 | 544, 54%, 1.49, 2.98 | 544, 49%, 0.95, -0.40 | 544, 43%, 0.64, -3.27 |
| L0W3 | 536, 53%, 1.56, 3.27 | 536, 50%, 1.17, 1.16 | 536, 47%, 0.94, -0.48 |
| L0W4 | 526, 52%, 1.52, 3.05 | 526, 49%, 1.22, 1.45 | 526, 48%, 1.04, 0.29 |
| L1W1 | 539, 48%, 1.27, 1.63 | 539, 37%, 0.52, -4.32 | 539, 25%, 0.27, -8.76 |
| L1W2 | 539, 48%, 1.43, 2.45 | 539, 45%, 0.91, -0.65 | 539, 40%, 0.68, -2.70 |
| L1W3 | 526, 48%, 1.44, 2.53 | 526, 46%, 1.04, 0.25 | 526, 44%, 0.86, -1.04 |
| L1W4 | 518, 49%, 1.49, 2.78 | 518, 47%, 1.15, 1.00 | 518, 45%, 1.01, 0.05 |
| L2W1 | 529, 46%, 1.43, 2.12 | 529, 36%, 0.59, -2.69 | 529, 28%, 0.36, -5.27 |
| L2W2 | 522, 47%, 1.45, 2.29 | 522, 43%, 0.87, -0.82 | 522, 38%, 0.68, -2.38 |
| L2W3 | 508, 46%, 1.48, 2.62 | 508, 44%, 1.06, 0.38 | 508, 42%, 0.90, -0.66 |
| L2W4 | 505, 47%, 1.52, 2.76 | 505, 45%, 1.22, 1.30 | 505, 43%, 1.08, 0.49 |
| L3W1 | 507, 43%, 1.21, 1.20 | 507, 34%, 0.50, -3.08 | 507, 29%, 0.32, -4.85 |
| L3W2 | 510, 44%, 1.31, 1.78 | 510, 40%, 0.84, -1.08 | 510, 37%, 0.67, -2.47 |
| L3W3 | 495, 43%, 1.45, 1.60 | 495, 40%, 1.07, 0.30 | 495, 39%, 0.91, -0.38 |
| L3W4 | 461, 43%, 1.37, 1.88 | 461, 40%, 1.07, 0.41 | 461, 39%, 0.96, -0.21 |

## Coverage

2571 branch events; 2467 produced at least one valid structure; 34263 structure-trades in total.

| Skip reason | Count |
|---|---|
| L3W4: leg untraded on entry | 568 |
| L3W3: leg untraded on entry | 509 |
| L2W4: leg untraded on entry | 445 |
| L2W3: leg untraded on entry | 443 |
| L3W1: leg untraded on entry | 427 |
| L3W2: leg untraded on entry | 422 |
| L1W4: leg untraded on entry | 383 |
| L1W3: leg untraded on entry | 362 |
| L2W1: leg untraded on entry | 358 |
| L2W2: leg untraded on entry | 355 |
| L0W4: leg untraded on entry | 337 |
| L0W3: leg untraded on entry | 336 |
| L1W2: leg untraded on entry | 297 |
| L1W1: leg untraded on entry | 293 |
| L0W1: leg untraded on entry | 268 |
| L0W2: leg untraded on entry | 264 |
| L3W4: strike off the chain | 156 |
| L2W4: strike off the chain | 82 |
| L3W3: strike off the chain | 82 |
| L3W1: debit outside (0, width) | 58 |
| L2W1: debit outside (0, width) | 55 |
| L1W1: debit outside (0, width) | 49 |
| L0W1: debit outside (0, width) | 38 |
| L1W4: strike off the chain | 34 |
| L2W3: strike off the chain | 34 |
| L3W2: strike off the chain | 34 |
| L3W2: debit outside (0, width) | 19 |
| L2W2: debit outside (0, width) | 16 |
| L3W3: debit outside (0, width) | 14 |
| L0W4: strike off the chain | 14 |
| L1W3: strike off the chain | 14 |
| L2W2: strike off the chain | 14 |
| L3W1: strike off the chain | 14 |
| L1W2: debit outside (0, width) | 13 |
| L0W2: debit outside (0, width) | 12 |
| L0W3: debit outside (0, width) | 12 |
| L2W3: debit outside (0, width) | 9 |
| L3W4: debit outside (0, width) | 6 |
| L1W3: debit outside (0, width) | 4 |
| L0W3: strike off the chain | 4 |
| L1W2: strike off the chain | 4 |
| L2W1: strike off the chain | 4 |
| L0W2: strike off the chain | 3 |
| L1W1: strike off the chain | 3 |
| L2W4: debit outside (0, width) | 2 |
| L0W1: strike off the chain | 1 |
| L1W4: debit outside (0, width) | 1 |
| L0W4: debit outside (0, width) | 1 |
## Post-run checks (2026-10-15, after the verdict; NOT part of it)

**1. Cost-level correction to the methodology's wording.** The methodology describes Stressed (2% of each leg's price per side) as "about the measured stock-option round trip per side". The measured figures (docs/GOODNIGHT_SCALPER_FEASIBILITY.md: 1.7% median / 3.1% mean of mid, ATM, at the open) are full bid-ask spreads, i.e. a ROUND trip. Per side they are about 0.85% / 1.55%. So **Base (1% per side, 2% round trip) is the level closest to the measured ATM spread**, and Stressed (4% round trip) is about 1.3–2.4× it. OTM legs are usually wider than ATM in % terms, so the true cost of the far strikes is likely between the two. **The verdict does not depend on this**: at Base, no structure has a mining Sharpe above 0.5 (best L0W2: PF 1.26, Sharpe 0.23).

**2. Data errors that flatter the result.** Some trades are impossible for a bull call spread. Their exit value (long − short) is above the strike width or below 0 (e.g. SAIL 2024-01-24: a 2-point spread valued at 8.5), from a stale close or settlement on one leg. Others have a stale tiny entry debit (e.g. MINDTREE 2020-04-23: an ATM 20-point spread at ₹0.05). Removing trades whose exit value is outside [0, width] or whose debit is below 5% of the width drops 2,029 of 34,263 structure-trades:

| Split | Scenario | Best structure (Sharpe) | Structures with PF > 1 |
|---|---|---|---|
| Mining | Clean (statutory only) | L0W4: PF 1.08, Sharpe 0.55 | 5 of 16 |
| Mining | Base | L2W4: PF 0.82, Sharpe −1.29 | **0 of 16** |
| Mining | Stressed | L2W4: PF 0.73, Sharpe −2.12 | 0 of 16 |
| Holdout | Clean | L0W4: PF 1.42, Sharpe 2.57 | 14 of 16 |
| Holdout | Base | L2W4: PF 1.18, Sharpe 1.10 | 6 of 16 |
| Holdout | Stressed | L2W4: PF 1.04, Sharpe 0.25 | 2 of 16 |

Removing the bad prints makes mining worse, not better: the cleaned 2020–2024 sample has no structure above PF 1 at a realistic cost. The median clean return on risk was negative for every structure checked (e.g. L0W2 −5%, L0W4 −7%, L2W4 −27%). The positive clean means came from a skewed minority of trades.

**3. Why spreads are so cost-sensitive.** The bid-ask is paid on the GROSS premium of both legs, four times, but the trade risks only the NET debit. At Base, bid-ask alone was a median 6–12% of the debit per trade (L0W4 6.3%, L0W2 11.7%). That is larger than the 5-day continuation the spread is trying to capture.

**4. The 2025–26 holdout looks better** (wide structures L0W4 / L2W4 / L3W4 clear PF 1 at Base). This matches Stage 1, where the holdout drift (+0.98%) was double the mining drift (+0.49%). The rules forbid picking a structure from the holdout. Whether this is a regime change or chance can only be tested on new data (prospectively), not by re-reading this window.
