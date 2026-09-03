# ORB Options Scalping — Backtest Results (Candidate 18)

Methodology: docs/ORB_OPTIONS_SCALPING_METHODOLOGY.md. NIFTY and BankNifty reported independently below -- never pooled.

**Harsh, Real-spread, Sampled-spread, and Stratified are POST-HOC additional stress tests** (added 2026-07-28 through 2026-09-02, `core/orb_scalping/costs.py`) — NONE are part of the pre-registered methodology doc's pass/fail bar, which gates on Stressed alone and never changes retroactively. Stratified is the LOCKED FINAL variant in this post-hoc series: Fable's 2026-07-31 adversarial review found the four-variant progression up to Sampled-spread had no pre-registered stopping rule and had happened to stop exactly when the number turned favorable — the same shape as parameter-fitting even though no signal parameter was touched. Stratified is the properly-sized, pre-specified recheck Fable's review prescribed as the fix, using a full month of `deploy/systemd/quantos-orb-spread-probe.timer` samples (`data_cache/orb_scalping_spread_samples.csv`) split by whether the sample's own calendar day was itself an expiry day. A second Fable review of that recheck (2026-09-01) found two pre-market rows had contaminated the expiry-day mean, manufacturing a false "expiry-day spread roughly doubles" finding for NIFTY; the sample is now filtered to trading-session hours and the rates corrected (`core/orb_scalping/costs.py`'s module docstring has the full before/after). No further cost-model VARIANT is planned after this one — a correction within it, caught by inspection, is not the same failure mode.

NIFTY window: 2022-06-01 to 2026-09-01 (1036 trades). BankNifty window: 2021-06-01 to 2026-09-01 (1268 trades).

## NIFTY

| Variant | Trades | Win rate | Profit factor | Sharpe | Net P&L % | Max DD % |
|---|---|---|---|---|---|---|
| Clean | 1036 | 47.7% | 1.30 | 1.15 | +3069.5% | 394.2% |
| Stressed (+15bps/leg) | 1036 | 47.7% | 1.26 | 1.03 | +2753.8% | 420.4% |
| Harsh (post-hoc, see below) | 1036 | 47.5% | 1.20 | 0.80 | +2121.3% | 492.5% |
| Real-spread (post-hoc, single snapshot) | 1036 | 46.5% | 1.04 | 0.12 | +303.0% | 774.8% |
| Sampled-spread (post-hoc, superseded) | 1036 | 47.6% | 1.23 | 0.89 | +2359.8% | 472.2% |
| Stratified (post-hoc, LOCKED FINAL) | 1036 | 47.6% | 1.23 | 0.88 | +2330.9% | 474.6% |

### Per-year breakdown (Stratified — the locked-final variant)

| Year | Trades | Win rate | Profit factor | Sharpe | Net P&L % | Max DD % |
|---|---|---|---|---|---|---|
| 2022 | 145 | 54.5% | 1.33 | 1.51 | +460.8% | 200.5% |
| 2023 | 240 | 42.5% | 0.97 | -0.12 | -71.8% | 474.6% |
| 2024 | 242 | 49.6% | 1.65 | 1.81 | +1350.9% | 222.1% |
| 2025 | 244 | 50.0% | 1.28 | 1.16 | +713.5% | 205.4% |
| 2026 | 165 | 42.4% | 0.91 | -0.32 | -122.4% | 341.1% |

**Verdict (NIFTY, gates on Stressed per the pre-registered methodology doc — this line never changes retroactively)**: PASS (PF 1.26, Sharpe 1.03, bar is PF > 1.0 AND Sharpe > 0.5).

**Harsh read (post-hoc, NOT part of the pre-registered pass/fail bar)**: still clears the same bar under a flat Rs20/leg brokerage + liquidity-tiered slippage on the DTE-floor-rolled subset (PF 1.20, Sharpe 0.80).

**Real-spread read (post-hoc, ONE live bid-ask snapshot 2026-07-28 18:03 IST, ROOT-CAUSED 2026-09-03 as a post-close quote and, for BankNifty, also a wrong-contract one -- see core/orb_scalping/costs.py's module docstring; kept unchanged as a historical record, NOT a rigorously sampled rate)**: FAILS the same bar under the actual measured round-trip bid-ask spread (PF 1.04, Sharpe 0.12). **This FAIL should not be read as evidence the strategy's real-world cost is 8-10x the sampled mean** -- it is the known-contaminated single reading, not an independent adverse signal.

**Sampled-spread read (post-hoc, 2026-07-29 to 2026-07-30, n=7 fires/leg, SUPERSEDED by Stratified below — it had zero expiry-day samples, so its blended rate was a non-expiry-day-only rate by accident)**: still clears the same bar under the sampled round-trip bid-ask spread (PF 1.23, Sharpe 0.89).

**Stratified read (post-hoc, LOCKED FINAL variant, first computed 2026-08-31, CORRECTED 2026-09-01/02 after Fable's review found two pre-market rows had contaminated the expiry-day mean -- 244 in-session samples / 20 IST days / 2+ NIFTY weeklies + 1 BankNifty monthly, 5 expiry days sampled -- this is the recheck Fable's 2026-07-31 review required before the Sampled-spread PASS could be trusted, and it prices expiry-day spread separately from ordinary-day spread instead of blending them; see core/orb_scalping/costs.py's module docstring for the correction)**: still clears the same bar under the expiry-day-stratified sampled spread (PF 1.23, Sharpe 0.88). **This is the number any go/no-go decision should read** — it is the best available cost estimate and no further post-hoc cost variant is planned after it (see core/orb_scalping/costs.py's module docstring for why the series stops here).

## BankNifty

| Variant | Trades | Win rate | Profit factor | Sharpe | Net P&L % | Max DD % |
|---|---|---|---|---|---|---|
| Clean | 1268 | 46.0% | 1.22 | 1.17 | +4051.0% | 482.4% |
| Stressed (+15bps/leg) | 1268 | 45.8% | 1.19 | 1.06 | +3664.1% | 512.9% |
| Harsh (post-hoc, see below) | 1268 | 45.6% | 1.16 | 0.94 | +3225.8% | 543.8% |
| Real-spread (post-hoc, single snapshot) | 1268 | 44.7% | 1.04 | 0.56 | +1936.0% | 646.5% |
| Sampled-spread (post-hoc, superseded) | 1268 | 45.7% | 1.16 | 0.96 | +3308.3% | 537.2% |
| Stratified (post-hoc, LOCKED FINAL) | 1268 | 45.7% | 1.16 | 0.95 | +3264.6% | 540.6% |

### Per-year breakdown (Stratified — the locked-final variant)

| Year | Trades | Win rate | Profit factor | Sharpe | Net P&L % | Max DD % |
|---|---|---|---|---|---|---|
| 2021 | 145 | 42.1% | 1.07 | 1.50 | +741.5% | 146.0% |
| 2022 | 244 | 45.1% | 1.07 | 0.47 | +284.2% | 540.6% |
| 2023 | 238 | 45.4% | 1.17 | 0.69 | +470.2% | 445.7% |
| 2024 | 241 | 46.5% | 1.32 | 1.24 | +843.1% | 333.6% |
| 2025 | 241 | 45.2% | 0.98 | 0.45 | +246.6% | 446.4% |
| 2026 | 159 | 49.7% | 1.37 | 1.64 | +679.0% | 203.1% |

**Verdict (BankNifty, gates on Stressed per the pre-registered methodology doc — this line never changes retroactively)**: PASS (PF 1.19, Sharpe 1.06, bar is PF > 1.0 AND Sharpe > 0.5).

**Harsh read (post-hoc, NOT part of the pre-registered pass/fail bar)**: still clears the same bar under a flat Rs20/leg brokerage + liquidity-tiered slippage on the DTE-floor-rolled subset (PF 1.16, Sharpe 0.94).

**Real-spread read (post-hoc, ONE live bid-ask snapshot 2026-07-28 18:03 IST, ROOT-CAUSED 2026-09-03 as a post-close quote and, for BankNifty, also a wrong-contract one -- see core/orb_scalping/costs.py's module docstring; kept unchanged as a historical record, NOT a rigorously sampled rate)**: still clears the same bar under the actual measured round-trip bid-ask spread (PF 1.04, Sharpe 0.56). **This near-pass should not be read as a reliable measurement** -- it is the known-contaminated single reading, not an independent signal.

**Sampled-spread read (post-hoc, 2026-07-29 to 2026-07-30, n=7 fires/leg, SUPERSEDED by Stratified below — it had zero expiry-day samples, so its blended rate was a non-expiry-day-only rate by accident)**: still clears the same bar under the sampled round-trip bid-ask spread (PF 1.16, Sharpe 0.96).

**Stratified read (post-hoc, LOCKED FINAL variant, first computed 2026-08-31, CORRECTED 2026-09-01/02 after Fable's review found two pre-market rows had contaminated the expiry-day mean -- 244 in-session samples / 20 IST days / 2+ NIFTY weeklies + 1 BankNifty monthly, 5 expiry days sampled -- this is the recheck Fable's 2026-07-31 review required before the Sampled-spread PASS could be trusted, and it prices expiry-day spread separately from ordinary-day spread instead of blending them; see core/orb_scalping/costs.py's module docstring for the correction)**: still clears the same bar under the expiry-day-stratified sampled spread (PF 1.16, Sharpe 0.95). **This is the number any go/no-go decision should read** — it is the best available cost estimate and no further post-hoc cost variant is planned after it (see core/orb_scalping/costs.py's module docstring for why the series stops here).

## Overall read

Read each index's own per-year table before trusting the pooled row -- same discipline every prior candidate's per-fold/per-year breakdown has used. A pass on Clean/Stressed that fails under Harsh or the spread variants is a real finding (the pre-registered Stressed cost model still understates real F&O brokerage/liquidity friction at this trade size), not something to average away.
