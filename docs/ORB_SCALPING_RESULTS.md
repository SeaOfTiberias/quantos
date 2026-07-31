# ORB Options Scalping — Backtest Results (Candidate 18)

Methodology: docs/ORB_OPTIONS_SCALPING_METHODOLOGY.md. NIFTY and BankNifty reported independently below -- never pooled.

**Harsh, Real-spread, and Sampled-spread are POST-HOC additional stress tests** (added 2026-07-28/2026-07-30, `core/orb_scalping/costs.py`) — NONE are part of the pre-registered methodology doc's pass/fail bar, which gates on Stressed alone. Real-spread uses ONE live bid-ask option-chain snapshot; Sampled-spread uses the same probe fired 3x/day by `deploy/systemd/quantos-orb-spread-probe.timer` and averaged over multiple sessions (`data_cache/orb_scalping_spread_samples.csv`) -- still a small sample, but a better directional read than the single snapshot. Reported for transparency, not to move the goalposts after the fact.

NIFTY window: 2022-06-01 to 2026-07-30 (1013 trades). BankNifty window: 2021-06-01 to 2026-07-30 (1247 trades).

## NIFTY

| Variant | Trades | Win rate | Profit factor | Sharpe | Net P&L % | Max DD % |
|---|---|---|---|---|---|---|
| Clean | 1013 | 47.9% | 1.30 | 1.19 | +3124.8% | 394.2% |
| Stressed (+15bps/leg) | 1013 | 47.9% | 1.27 | 1.08 | +2815.8% | 420.4% |
| Harsh (post-hoc, see below) | 1013 | 47.7% | 1.21 | 0.84 | +2196.2% | 492.5% |
| Real-spread (post-hoc, single snapshot) | 1013 | 46.7% | 1.04 | 0.16 | +417.6% | 774.8% |
| Sampled-spread (post-hoc, multi-session) | 1013 | 47.8% | 1.24 | 0.93 | +2429.9% | 472.2% |

### Per-year breakdown (Sampled-spread)

| Year | Trades | Win rate | Profit factor | Sharpe | Net P&L % | Max DD % |
|---|---|---|---|---|---|---|
| 2022 | 145 | 54.5% | 1.34 | 1.52 | +464.8% | 199.7% |
| 2023 | 240 | 42.5% | 0.97 | -0.11 | -65.2% | 472.2% |
| 2024 | 242 | 49.6% | 1.66 | 1.82 | +1357.7% | 221.2% |
| 2025 | 244 | 50.0% | 1.28 | 1.17 | +720.4% | 204.7% |
| 2026 | 142 | 43.0% | 0.92 | -0.14 | -47.8% | 271.1% |

**Verdict (NIFTY, gates on Stressed per the pre-registered methodology doc)**: PASS (PF 1.27, Sharpe 1.08, bar is PF > 1.0 AND Sharpe > 0.5).

**Harsh read (post-hoc, NOT part of the pre-registered pass/fail bar)**: still clears the same bar under a flat Rs20/leg brokerage + liquidity-tiered slippage on the DTE-floor-rolled subset (PF 1.21, Sharpe 0.84).

**Real-spread read (post-hoc, ONE live bid-ask snapshot 2026-07-28, NOT a rigorously sampled rate)**: FAILS the same bar under the actual measured round-trip bid-ask spread (PF 1.04, Sharpe 0.16).

**Sampled-spread read (post-hoc, 3x/day timer, 2026-07-29 to 2026-07-30, n=7 fires/leg -- still a small sample, but multi-session not single-snapshot)**: still clears the same bar under the sampled round-trip bid-ask spread (PF 1.24, Sharpe 0.93).

## BankNifty

| Variant | Trades | Win rate | Profit factor | Sharpe | Net P&L % | Max DD % |
|---|---|---|---|---|---|---|
| Clean | 1247 | 46.4% | 1.23 | 1.19 | +4006.7% | 482.4% |
| Stressed (+15bps/leg) | 1247 | 46.2% | 1.19 | 1.08 | +3626.2% | 512.9% |
| Harsh (post-hoc, see below) | 1247 | 46.0% | 1.16 | 0.95 | +3195.8% | 543.8% |
| Real-spread (post-hoc, single snapshot) | 1247 | 45.1% | 1.05 | 0.57 | +1927.3% | 646.5% |
| Sampled-spread (post-hoc, multi-session) | 1247 | 46.0% | 1.17 | 0.97 | +3277.0% | 537.2% |

### Per-year breakdown (Sampled-spread)

| Year | Trades | Win rate | Profit factor | Sharpe | Net P&L % | Max DD % |
|---|---|---|---|---|---|---|
| 2021 | 145 | 42.1% | 1.07 | 1.51 | +746.4% | 145.5% |
| 2022 | 244 | 45.1% | 1.08 | 0.48 | +292.6% | 537.2% |
| 2023 | 238 | 45.4% | 1.17 | 0.70 | +478.5% | 441.0% |
| 2024 | 241 | 46.5% | 1.32 | 1.26 | +851.5% | 331.4% |
| 2025 | 241 | 45.2% | 0.99 | 0.46 | +254.7% | 441.3% |
| 2026 | 138 | 53.6% | 1.45 | 1.98 | +653.3% | 141.9% |

**Verdict (BankNifty, gates on Stressed per the pre-registered methodology doc)**: PASS (PF 1.19, Sharpe 1.08, bar is PF > 1.0 AND Sharpe > 0.5).

**Harsh read (post-hoc, NOT part of the pre-registered pass/fail bar)**: still clears the same bar under a flat Rs20/leg brokerage + liquidity-tiered slippage on the DTE-floor-rolled subset (PF 1.16, Sharpe 0.95).

**Real-spread read (post-hoc, ONE live bid-ask snapshot 2026-07-28, NOT a rigorously sampled rate)**: still clears the same bar under the actual measured round-trip bid-ask spread (PF 1.05, Sharpe 0.57).

**Sampled-spread read (post-hoc, 3x/day timer, 2026-07-29 to 2026-07-30, n=7 fires/leg -- still a small sample, but multi-session not single-snapshot)**: still clears the same bar under the sampled round-trip bid-ask spread (PF 1.17, Sharpe 0.97).

## Overall read

Read each index's own per-year table before trusting the pooled row -- same discipline every prior candidate's per-fold/per-year breakdown has used. A pass on Clean/Stressed that fails under Harsh or Real-spread/Sampled-spread is a real finding (the pre-registered Stressed cost model still understates real F&O brokerage/liquidity friction at this trade size), not something to average away.
