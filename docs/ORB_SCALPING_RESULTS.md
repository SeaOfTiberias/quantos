# ORB Options Scalping — Backtest Results (Candidate 18)

Methodology: docs/ORB_OPTIONS_SCALPING_METHODOLOGY.md. NIFTY and BankNifty reported independently below -- never pooled.

**Harsh and Real-spread are POST-HOC additional stress tests** (added 2026-07-28, `core/orb_scalping/costs.py`) — NEITHER is part of the pre-registered methodology doc's pass/fail bar, which gates on Stressed alone. Real-spread uses ONE live bid-ask option-chain snapshot (`scripts/probe_orb_scalping_real_spreads.py`), not a sampled average across sessions -- a directional sanity check, not a fourth rigorously pre-registered tier. Reported for transparency, not to move the goalposts after the fact.

NIFTY window: 2022-06-01 to 2026-07-28 (1011 trades). BankNifty window: 2021-06-01 to 2026-07-28 (1245 trades).

## NIFTY

| Variant | Trades | Win rate | Profit factor | Sharpe | Net P&L % | Max DD % |
|---|---|---|---|---|---|---|
| Clean | 1011 | 47.9% | 1.31 | 1.19 | +3119.1% | 394.2% |
| Stressed (+15bps/leg) | 1011 | 47.9% | 1.27 | 1.08 | +2810.8% | 420.4% |
| Harsh (post-hoc, see below) | 1011 | 47.7% | 1.21 | 0.84 | +2193.0% | 492.5% |
| Real-spread (post-hoc, live snapshot) | 1011 | 46.7% | 1.05 | 0.16 | +417.5% | 774.8% |

### Per-year breakdown (Real-spread)

| Year | Trades | Win rate | Profit factor | Sharpe | Net P&L % | Max DD % |
|---|---|---|---|---|---|---|
| 2022 | 145 | 53.8% | 1.10 | 0.58 | +175.7% | 256.6% |
| 2023 | 240 | 42.1% | 0.82 | -0.91 | -536.1% | 774.8% |
| 2024 | 242 | 48.8% | 1.41 | 1.18 | +869.5% | 287.7% |
| 2025 | 244 | 47.5% | 1.08 | 0.38 | +234.4% | 257.1% |
| 2026 | 140 | 42.1% | 0.78 | -1.00 | -326.0% | 392.9% |

**Verdict (NIFTY, gates on Stressed per the pre-registered methodology doc)**: PASS (PF 1.27, Sharpe 1.08, bar is PF > 1.0 AND Sharpe > 0.5).

**Harsh read (post-hoc, NOT part of the pre-registered pass/fail bar)**: still clears the same bar under a flat Rs20/leg brokerage + liquidity-tiered slippage on the DTE-floor-rolled subset (PF 1.21, Sharpe 0.84).

**Real-spread read (post-hoc, ONE live bid-ask snapshot 2026-07-28, NOT a rigorously sampled rate)**: FAILS the same bar under the actual measured round-trip bid-ask spread (PF 1.05, Sharpe 0.16).

## BankNifty

| Variant | Trades | Win rate | Profit factor | Sharpe | Net P&L % | Max DD % |
|---|---|---|---|---|---|---|
| Clean | 1245 | 46.4% | 1.23 | 1.20 | +4057.2% | 482.4% |
| Stressed (+15bps/leg) | 1245 | 46.3% | 1.20 | 1.09 | +3677.2% | 512.9% |
| Harsh (post-hoc, see below) | 1245 | 46.0% | 1.17 | 0.97 | +3248.9% | 543.8% |
| Real-spread (post-hoc, live snapshot) | 1245 | 45.1% | 1.05 | 0.59 | +1982.1% | 646.5% |

### Per-year breakdown (Real-spread)

| Year | Trades | Win rate | Profit factor | Sharpe | Net P&L % | Max DD % |
|---|---|---|---|---|---|---|
| 2021 | 145 | 41.4% | 0.97 | 1.19 | +587.5% | 159.7% |
| 2022 | 244 | 44.3% | 0.96 | 0.05 | +30.4% | 646.5% |
| 2023 | 238 | 44.5% | 1.05 | 0.32 | +221.6% | 588.3% |
| 2024 | 241 | 45.2% | 1.19 | 0.87 | +589.6% | 404.4% |
| 2025 | 241 | 44.0% | 0.87 | -0.01 | -4.1% | 601.8% |
| 2026 | 136 | 53.7% | 1.31 | 1.72 | +557.2% | 162.5% |

**Verdict (BankNifty, gates on Stressed per the pre-registered methodology doc)**: PASS (PF 1.20, Sharpe 1.09, bar is PF > 1.0 AND Sharpe > 0.5).

**Harsh read (post-hoc, NOT part of the pre-registered pass/fail bar)**: still clears the same bar under a flat Rs20/leg brokerage + liquidity-tiered slippage on the DTE-floor-rolled subset (PF 1.17, Sharpe 0.97).

**Real-spread read (post-hoc, ONE live bid-ask snapshot 2026-07-28, NOT a rigorously sampled rate)**: still clears the same bar under the actual measured round-trip bid-ask spread (PF 1.05, Sharpe 0.59).

## Overall read

Read each index's own per-year table before trusting the pooled row -- same discipline every prior candidate's per-fold/per-year breakdown has used. A pass on Clean/Stressed that fails under Harsh or Real-spread is a real finding (the pre-registered Stressed cost model still understates real F&O brokerage/liquidity friction at this trade size), not something to average away.
