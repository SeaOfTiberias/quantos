---
title: 'Put retest context review — claude-opus-5-5, 2026-10-26'
ingested: 2026-10-26
origin: '/home/ubuntu/quantos/obsidian_vault/QuantOS/raw/_inbox/PUT_RETEST_CONTEXT_REVIEW_LLM_2026-10-26.md'
checksum: 7b6992d0a7ddc9bdb06614e12bffc396aa9f6db973bc8506cd113b4e18e1e316
body_checksum: 1bcc3739364967f964744c15866dc9cf64fa5e75a184bfcac0e5947c27222bca
tags:
  - source/strategies
quantos:
  layer: raw
  immutable: true
---

# Put retest context review — claude-opus-5-5, 2026-10-26

> [!info] Ingested source
> Filed 2026-10-26 from `/home/ubuntu/quantos/obsidian_vault/QuantOS/raw/_inbox/PUT_RETEST_CONTEXT_REVIEW_LLM_2026-10-26.md`. Do not edit — wiki pages cite this
> file's contents, and `vault lint` re-hashes it to check.

Protocol: docs/PUT_RETEST_CONTEXT_REVIEW_PREREG_2026-10-26.md. The model saw the first half only (signals before 2026-03-27, 900 trades), with symbols and dates removed. Tokens: 105493 in, 2630 out.

## Model response

## What the context tables show

**Ideas the data contradicts**
- **Results coming up.** This is only a mild effect. Trades with 15 or fewer days to results won 64% with a mean of +0.06%, which is weaker than average but still not losing. The clearer signal is the other side of the same cycle: stocks a long time past their last results (see Rule 2).
- **A market rally fighting the short.** No support for this. With NIFTY above its 20-day EMA, trades won 67% (+0.39%), against 70% (+0.41%) below it. The top quintile of nifty_ret20 (> +0.93%) won 70% (+0.41%), the same as the whole sample. The bottom nifty_ret20 quintile (≤ −6.2%) was the best bucket, but that is a "skip nothing" observation, not a filter.
- **A stock already far below its range or near its lows.** The data says the opposite. Close to the 52-week low (≤1.6 ATR) won 74% (+0.88%). Far from it (>8.3 ATR) won 65% (+0.02%). How deep the close sat below the floor made no difference (every quintile was 67–71%).
- **A crowded short.** "Short build-up" OI won 68% (+0.39%), in line with the average. "Short covering" was weaker at 65% (+0.08%), but n=31 is too small to act on.
- **Noise I am not using:**
  - sector_ret20's weak middle bucket (53%) is not monotonic.
  - The Monday weakness (59%) has no mechanism.
  - The iv dip in its second quintile is not monotonic.
  - Small-sector results (oilgas, metal, cpse with n=12–28) are too thin.
  - days_to_expiry >12 (61–65%) has no clear mechanism.

**Patterns with a recognisable reason**
- **Low India VIX.** This is the single worst bucket. VIX ≤ 10.87 won 54% with a mean of −0.40%. All other VIX quintiles won 71–77%. In complacent, low-volatility markets, breakdowns tend to get bought back and a retest short gets stopped out rather than following through. Low stock ATR shows the same thing: atr_pct ≤ 2.0 won 62% (−0.04%), which supports the reading that the edge needs volatility.
- **A long time since the last results.** days_since_results > 46.2 won 60% with a mean of −0.14%. The 14–46 range won 70–78%. A stock more than about 9 weeks past its last board meeting is usually heading into its next results window. The breakdown is then more likely a pre-results drift that can reverse sharply, and the fresh post-results information that drives clean follow-through is missing.

## Proposed rules (effects in this half, from the quintile tables)

**1. skip_low_vix: VIX < 11**
- The table bucket used is VIX ≤ 10.87: 182 trades skipped (about 20%), win 54%, mean −0.40%.
- Kept: about 718 trades, win about 73%, mean about +0.62%. These are derived from the totals: (900×0.41 + 182×0.40)/718.
- The round threshold of 11 will catch a few extra trades in the 10.87–11 range, so the live effect will differ slightly.

**2. skip_stale_results: days_since_results > 45**
- The table bucket used is > 46.2: 180 trades skipped (20%), win 60%, mean −0.14%.
- Kept: about 720 trades, win about 71%, mean about +0.55%.
- The value 99 means "none known", and those trades fall into this skip too.

**Overlap between the two rules.** The tables can't show how much they overlap. Several low-VIX trades in this half also had days_since_results in the 40s–50s. The combined skip rate should therefore come in under 40%, most likely around 30%. I did not add a third rule, because the remaining candidates are either weak or lack a reason.

```json
{"rules": [{"name": "skip_low_vix", "reason": "In complacent, very low-volatility markets breakdowns tend to get bought back, so the retest short stops out instead of reaching 0.75 ATR; VIX at or below about 11 was the worst bucket (54% win, -0.40% mean).", "conditions": [{"feature": "vix", "op": "<", "value": 11}]}, {"name": "skip_stale_results", "reason": "More than ~9 weeks since the last results means the next results window is near and the breakdown lacks fresh fundamental drive; this bucket won only 60% with a negative mean.", "conditions": [{"feature": "days_since_results", "op": ">", "value": 45}]}]}
```

## Tables it was given (first half)

```
days_to_results:
  (-inf, 15.00]: n=186, win 64%, mean +0.06%
  (15.00, 27.60]: n=174, win 66%, mean +0.21%
  (27.60, 38.00]: n=198, win 71%, mean +0.63%
  (38.00, 50.00]: n=177, win 78%, mean +0.87%
  (50.00, inf]: n=165, win 67%, mean +0.25%

days_since_results:
  (-inf, 14.00]: n=184, win 66%, mean +0.23%
  (14.00, 25.00]: n=178, win 78%, mean +0.89%
  (25.00, 34.00]: n=188, win 72%, mean +0.63%
  (34.00, 46.20]: n=170, win 70%, mean +0.42%
  (46.20, inf]: n=180, win 60%, mean -0.14%

nifty_above_ema20:
  False: n=602, win 70%, mean +0.41%
  True: n=298, win 67%, mean +0.39%

nifty_ret5:
  (-inf, -2.58]: n=199, win 73%, mean +0.71%
  (-2.58, -1.51]: n=161, win 70%, mean +0.37%
  (-1.51, -0.35]: n=193, win 69%, mean +0.36%
  (-0.35, 0.45]: n=167, win 64%, mean +0.23%
  (0.45, inf]: n=180, win 68%, mean +0.32%

nifty_ret20:
  (-inf, -6.21]: n=181, win 81%, mean +1.14%
  (-6.21, -1.44]: n=188, win 64%, mean +0.04%
  (-1.44, 0.06]: n=173, win 67%, mean +0.16%
  (0.06, 0.93]: n=187, win 64%, mean +0.30%
  (0.93, inf]: n=171, win 70%, mean +0.41%

vix:
  (-inf, 10.87]: n=182, win 54%, mean -0.40%
  (10.87, 11.81]: n=178, win 71%, mean +0.36%
  (11.81, 13.35]: n=186, win 73%, mean +0.81%
  (13.35, 19.88]: n=176, win 71%, mean +0.35%
  (19.88, inf]: n=178, win 77%, mean +0.91%

vix_chg5:
  (-inf, -4.66]: n=182, win 60%, mean -0.00%
  (-4.66, 1.16]: n=192, win 68%, mean +0.33%
  (1.16, 7.67]: n=167, win 68%, mean +0.22%
  (7.67, 17.93]: n=183, win 78%, mean +0.84%
  (17.93, inf]: n=176, win 72%, mean +0.64%

sector:
  auto: n=25, win 64%, mean -0.06%
  bank: n=35, win 74%, mean +0.70%
  commodities: n=46, win 74%, mean +0.40%
  consumerdurables: n=51, win 67%, mean +0.21%
  consumption: n=57, win 79%, mean +0.85%
  cpse: n=15, win 53%, mean -0.65%
  energy: n=79, win 58%, mean -0.21%
  fmcg: n=53, win 74%, mean +0.46%
  healthcare: n=17, win 65%, mean -0.29%
  it: n=43, win 58%, mean +0.20%
  metal: n=12, win 50%, mean -0.32%
  oilgas: n=28, win 43%, mean -0.57%
  other: n=355, win 73%, mean +0.62%
  pharma: n=43, win 60%, mean +0.15%
  realty: n=40, win 90%, mean +1.54%

sector_ret20:
  (-inf, -9.10]: n=109, win 81%, mean +1.05%
  (-9.10, -4.37]: n=109, win 66%, mean +0.08%
  (-4.37, -2.07]: n=109, win 68%, mean +0.38%
  (-2.07, 0.50]: n=109, win 53%, mean -0.32%
  (0.50, inf]: n=109, win 66%, mean +0.16%

ret5:
  (-inf, -6.27]: n=180, win 68%, mean +0.46%
  (-6.27, -4.00]: n=180, win 67%, mean +0.42%
  (-4.00, -2.54]: n=180, win 75%, mean +0.65%
  (-2.54, -1.16]: n=180, win 71%, mean +0.38%
  (-1.16, inf]: n=180, win 64%, mean +0.12%

ret20:
  (-inf, -10.70]: n=180, win 70%, mean +0.53%
  (-10.70, -7.33]: n=180, win 73%, mean +0.68%
  (-7.33, -5.19]: n=180, win 73%, mean +0.56%
  (-5.19, -3.21]: n=180, win 64%, mean +0.08%
  (-3.21, inf]: n=180, win 64%, mean +0.18%

atr_pct:
  (-inf, 2.01]: n=180, win 62%, mean -0.04%
  (2.01, 2.40]: n=180, win 67%, mean +0.15%
  (2.40, 2.78]: n=180, win 67%, mean +0.26%
  (2.78, 3.37]: n=180, win 73%, mean +0.50%
  (3.37, inf]: n=180, win 77%, mean +1.16%

dist_52w_low_atr:
  (-inf, 1.61]: n=180, win 74%, mean +0.88%
  (1.61, 3.59]: n=180, win 73%, mean +0.60%
  (3.59, 5.66]: n=181, win 69%, mean +0.38%
  (5.66, 8.32]: n=179, win 64%, mean +0.14%
  (8.32, inf]: n=180, win 65%, mean +0.02%

depth_below_floor_atr:
  (-inf, 0.17]: n=183, win 68%, mean +0.40%
  (0.17, 0.32]: n=177, win 70%, mean +0.39%
  (0.32, 0.51]: n=180, win 71%, mean +0.36%
  (0.51, 0.84]: n=180, win 67%, mean +0.51%
  (0.84, inf]: n=180, win 69%, mean +0.36%

box_width_pct:
  (-inf, 9.20]: n=184, win 70%, mean +0.36%
  (9.20, 13.10]: n=178, win 78%, mean +0.82%
  (13.10, 16.50]: n=182, win 60%, mean +0.14%
  (16.50, 21.30]: n=177, win 65%, mean +0.25%
  (21.30, inf]: n=179, win 74%, mean +0.47%

vol_ratio:
  (-inf, 0.63]: n=186, win 68%, mean +0.40%
  (0.63, 0.85]: n=177, win 72%, mean +0.56%
  (0.85, 1.12]: n=178, win 67%, mean +0.25%
  (1.12, 1.51]: n=180, win 64%, mean +0.11%
  (1.51, inf]: n=179, win 75%, mean +0.71%

days_out:
  (-inf, 1.00]: n=364, win 66%, mean +0.21%
  (1.00, 1.00]: n=0
  (1.00, 2.00]: n=217, win 71%, mean +0.48%
  (2.00, 3.00]: n=151, win 71%, mean +0.48%
  (3.00, inf]: n=168, win 73%, mean +0.65%

tier:
  LEADER: n=551, win 70%, mean +0.48%
  MIDPACK: n=349, win 68%, mean +0.30%

bucket:
  BUILDING_BASE: n=146, win 74%, mean +0.62%
  LEADER_EXTENDED: n=340, win 69%, mean +0.43%
  LEADER_TIGHT_BASE: n=211, win 72%, mean +0.55%
  WATCH: n=203, win 63%, mean +0.06%

momentum_pct:
  (-inf, 79.37]: n=180, win 66%, mean +0.31%
  (79.37, 86.08]: n=180, win 69%, mean +0.24%
  (86.08, 89.69]: n=180, win 69%, mean +0.24%
  (89.69, 95.20]: n=180, win 69%, mean +0.41%
  (95.20, inf]: n=180, win 73%, mean +0.83%

oi:
  OI flat: n=163, win 71%, mean +0.50%
  long build-up: n=35, win 69%, mean +0.28%
  long unwinding: n=105, win 71%, mean +0.45%
  short build-up: n=518, win 68%, mean +0.39%
  short covering: n=31, win 65%, mean +0.08%

iv:
  (-inf, 0.22]: n=123, win 67%, mean +0.19%
  (0.22, 0.27]: n=124, win 56%, mean -0.19%
  (0.27, 0.31]: n=121, win 74%, mean +0.53%
  (0.31, 0.36]: n=121, win 73%, mean +0.64%
  (0.36, inf]: n=123, win 65%, mean +0.32%

fill_session:
  (-inf, 1.00]: n=715, win 68%, mean +0.36%
  (1.00, 1.00]: n=0
  (1.00, 1.00]: n=0
  (1.00, 2.00]: n=118, win 69%, mean +0.43%
  (2.00, inf]: n=67, win 78%, mean +0.90%

fill_gap_atr:
  (-inf, -0.01]: n=180, win 70%, mean +0.48%
  (-0.01, 0.03]: n=185, win 71%, mean +0.40%
  (0.03, 0.12]: n=175, win 63%, mean +0.27%
  (0.12, 0.28]: n=180, win 67%, mean +0.23%
  (0.28, inf]: n=180, win 74%, mean +0.65%

filled_at_open:
  False: n=542, win 68%, mean +0.36%
  True: n=358, win 70%, mean +0.48%

weekday:
  Fri: n=160, win 73%, mean +0.61%
  Mon: n=147, win 59%, mean -0.18%
  Thu: n=126, win 68%, mean +0.31%
  Tue: n=234, win 70%, mean +0.43%
  Wed: n=228, win 72%, mean +0.68%

days_to_expiry:
  (-inf, 3.00]: n=190, win 74%, mean +0.74%
  (3.00, 8.00]: n=213, win 72%, mean +0.60%
  (8.00, 12.00]: n=152, win 72%, mean +0.57%
  (12.00, 16.00]: n=210, win 61%, mean +0.03%
  (16.00, inf]: n=135, win 65%, mean +0.05%
```
