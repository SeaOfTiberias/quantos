# ORB Options Scalping — Backtest Results (Candidate 18)

Methodology: docs/ORB_OPTIONS_SCALPING_METHODOLOGY.md. NIFTY and BankNifty reported independently below -- never pooled.

**Harsh, Real-spread, Sampled-spread, and Stratified are POST-HOC additional stress tests** (added 2026-07-28 through 2026-08-31, `core/orb_scalping/costs.py`) — NONE are part of the pre-registered methodology doc's pass/fail bar, which gates on Stressed alone and never changes retroactively. Stratified is the LOCKED FINAL variant in this post-hoc series: Fable's 2026-07-31 adversarial review found the four-variant progression up to Sampled-spread had no pre-registered stopping rule and had happened to stop exactly when the number turned favorable — the same shape as parameter-fitting even though no signal parameter was touched. Stratified is the properly-sized, pre-specified recheck Fable's review prescribed as the fix, using a full month of `deploy/systemd/quantos-orb-spread-probe.timer` samples (`data_cache/orb_scalping_spread_samples.csv`) split by whether the sample's own calendar day was itself an expiry day. No further cost-model variant is planned after this one.

NIFTY window: 2022-06-01 to 2026-08-31 (1035 trades). BankNifty window: 2021-06-01 to 2026-08-31 (1267 trades).

## NIFTY

| Variant | Trades | Win rate | Profit factor | Sharpe | Net P&L % | Max DD % |
|---|---|---|---|---|---|---|
| Clean | 1035 | 47.7% | 1.30 | 1.16 | +3095.5% | 394.2% |
| Stressed (+15bps/leg) | 1035 | 47.7% | 1.26 | 1.05 | +2780.0% | 420.4% |
| Harsh (post-hoc, see below) | 1035 | 47.5% | 1.20 | 0.81 | +2149.1% | 492.5% |
| Real-spread (post-hoc, single snapshot) | 1035 | 46.6% | 1.04 | 0.13 | +332.1% | 774.8% |
| Sampled-spread (post-hoc, superseded) | 1035 | 47.6% | 1.23 | 0.90 | +2387.2% | 472.2% |
| Stratified (post-hoc, LOCKED FINAL) | 1035 | 47.5% | 1.22 | 0.87 | +2318.1% | 478.0% |

### Per-year breakdown (Stratified — the locked-final variant)

| Year | Trades | Win rate | Profit factor | Sharpe | Net P&L % | Max DD % |
|---|---|---|---|---|---|---|
| 2022 | 145 | 54.5% | 1.33 | 1.49 | +455.1% | 201.6% |
| 2023 | 240 | 42.5% | 0.96 | -0.14 | -81.1% | 478.0% |
| 2024 | 242 | 49.6% | 1.65 | 1.80 | +1341.6% | 223.3% |
| 2025 | 244 | 49.6% | 1.27 | 1.14 | +703.8% | 206.4% |
| 2026 | 164 | 42.7% | 0.91 | -0.27 | -101.3% | 316.8% |

**Verdict (NIFTY, gates on Stressed per the pre-registered methodology doc — this line never changes retroactively)**: PASS (PF 1.26, Sharpe 1.05, bar is PF > 1.0 AND Sharpe > 0.5).

**Harsh read (post-hoc, NOT part of the pre-registered pass/fail bar)**: still clears the same bar under a flat Rs20/leg brokerage + liquidity-tiered slippage on the DTE-floor-rolled subset (PF 1.20, Sharpe 0.81).

**Real-spread read (post-hoc, ONE live bid-ask snapshot 2026-07-28, NOT a rigorously sampled rate)**: FAILS the same bar under the actual measured round-trip bid-ask spread (PF 1.04, Sharpe 0.13).

**Sampled-spread read (post-hoc, 2026-07-29 to 2026-07-30, n=7 fires/leg, SUPERSEDED by Stratified below — it had zero expiry-day samples, so its blended rate was a non-expiry-day-only rate by accident)**: still clears the same bar under the sampled round-trip bid-ask spread (PF 1.23, Sharpe 0.90).

**Stratified read (post-hoc, LOCKED FINAL variant, 2026-08-31, 240 samples / 19 IST days / 2+ NIFTY weeklies + 1 BankNifty monthly, 4 expiry days sampled — this is the recheck Fable's 2026-07-31 review required before the Sampled-spread PASS could be trusted, and it prices expiry-day spread separately from ordinary-day spread instead of blending them)**: still clears the same bar under the expiry-day-stratified sampled spread (PF 1.22, Sharpe 0.87). **This is the number any go/no-go decision should read** — it is the best available cost estimate and no further post-hoc cost variant is planned after it (see core/orb_scalping/costs.py's module docstring for why the series stops here).

## BankNifty

| Variant | Trades | Win rate | Profit factor | Sharpe | Net P&L % | Max DD % |
|---|---|---|---|---|---|---|
| Clean | 1267 | 46.0% | 1.23 | 1.18 | +4080.6% | 482.4% |
| Stressed (+15bps/leg) | 1267 | 45.9% | 1.19 | 1.07 | +3693.9% | 512.9% |
| Harsh (post-hoc, see below) | 1267 | 45.6% | 1.16 | 0.94 | +3256.8% | 543.8% |
| Real-spread (post-hoc, single snapshot) | 1267 | 44.8% | 1.04 | 0.57 | +1967.9% | 646.5% |
| Sampled-spread (post-hoc, superseded) | 1267 | 45.7% | 1.17 | 0.97 | +3339.3% | 537.2% |
| Stratified (post-hoc, LOCKED FINAL) | 1267 | 45.6% | 1.16 | 0.95 | +3286.0% | 541.4% |

### Per-year breakdown (Stratified — the locked-final variant)

| Year | Trades | Win rate | Profit factor | Sharpe | Net P&L % | Max DD % |
|---|---|---|---|---|---|---|
| 2021 | 145 | 42.1% | 1.07 | 1.49 | +740.3% | 146.1% |
| 2022 | 244 | 45.1% | 1.07 | 0.47 | +282.4% | 541.4% |
| 2023 | 238 | 45.4% | 1.16 | 0.68 | +468.4% | 446.7% |
| 2024 | 241 | 46.1% | 1.31 | 1.24 | +841.3% | 334.2% |
| 2025 | 241 | 45.2% | 0.98 | 0.45 | +244.7% | 447.5% |
| 2026 | 158 | 50.0% | 1.37 | 1.72 | +708.9% | 203.3% |

**Verdict (BankNifty, gates on Stressed per the pre-registered methodology doc — this line never changes retroactively)**: PASS (PF 1.19, Sharpe 1.07, bar is PF > 1.0 AND Sharpe > 0.5).

**Harsh read (post-hoc, NOT part of the pre-registered pass/fail bar)**: still clears the same bar under a flat Rs20/leg brokerage + liquidity-tiered slippage on the DTE-floor-rolled subset (PF 1.16, Sharpe 0.94).

**Real-spread read (post-hoc, ONE live bid-ask snapshot 2026-07-28, NOT a rigorously sampled rate)**: still clears the same bar under the actual measured round-trip bid-ask spread (PF 1.04, Sharpe 0.57).

**Sampled-spread read (post-hoc, 2026-07-29 to 2026-07-30, n=7 fires/leg, SUPERSEDED by Stratified below — it had zero expiry-day samples, so its blended rate was a non-expiry-day-only rate by accident)**: still clears the same bar under the sampled round-trip bid-ask spread (PF 1.17, Sharpe 0.97).

**Stratified read (post-hoc, LOCKED FINAL variant, 2026-08-31, 240 samples / 19 IST days / 2+ NIFTY weeklies + 1 BankNifty monthly, 4 expiry days sampled — this is the recheck Fable's 2026-07-31 review required before the Sampled-spread PASS could be trusted, and it prices expiry-day spread separately from ordinary-day spread instead of blending them)**: still clears the same bar under the expiry-day-stratified sampled spread (PF 1.16, Sharpe 0.95). **This is the number any go/no-go decision should read** — it is the best available cost estimate and no further post-hoc cost variant is planned after it (see core/orb_scalping/costs.py's module docstring for why the series stops here).

## Overall read

Read each index's own per-year table before trusting the pooled row -- same discipline every prior candidate's per-fold/per-year breakdown has used. A pass on Clean/Stressed that fails under Harsh or the spread variants is a real finding (the pre-registered Stressed cost model still understates real F&O brokerage/liquidity friction at this trade size), not something to average away.
