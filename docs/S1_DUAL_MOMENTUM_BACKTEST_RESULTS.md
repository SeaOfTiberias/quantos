# Strategy 1 — Regime-Filtered Dual-Momentum Backtest

Methodology pre-committed in `docs/S1_DUAL_MOMENTUM_METHODOLOGY.md` before this ran. Nifty 200 universe, 250/258 symbols had enough history to ever be ranked, 168 weekly rebalance dates. Top 15 entry / Top 25 hold-eligible band, 2.5xATR initial stop, 2xATR Chandelier trail.

## Unfiltered (headline result)

**Verdict: POSITIVE net-of-cost edge** (pooled-trade `has_positive_edge`: profit factor > 1.0 AND Sharpe > 0.5)

### Pooled per-trade stats
- Total trades: 873
- Win rate: 41.2%
- Profit factor: 1.24
- Sharpe ratio: 0.82
- Net profit (sum of per-trade net %): 584.1%
- Avg holding period: 18 days
- Trades/month: 22.8
- Overfit risk flag: no

### Capital-tracked equity curve (Rs10L start)
- Final equity: Rs1,352,976
- Total return: 35.3%
- CAGR: 9.9%
- Sharpe (equity-curve daily returns): 0.70
- Max drawdown: 16.1%

## Regime-gated (NIFTY 50 > its own EMA200) — INFORMATIONAL ONLY, not the go/no-go basis

**Verdict: POSITIVE net-of-cost edge** (pooled-trade `has_positive_edge`: profit factor > 1.0 AND Sharpe > 0.5)

### Pooled per-trade stats
- Total trades: 696
- Win rate: 39.8%
- Profit factor: 1.20
- Sharpe ratio: 0.70
- Net profit (sum of per-trade net %): 416.2%
- Avg holding period: 18 days
- Trades/month: 20.4
- Overfit risk flag: no

### Capital-tracked equity curve (Rs10L start)
- Final equity: Rs1,249,966
- Total return: 25.0%
- CAGR: 7.2%
- Sharpe (equity-curve daily returns): 0.58
- Max drawdown: 15.2%

## Coverage-gap sub-period check (rebalances on/after 2023-09-29 only)

Real point-in-time Nifty 200 events only go back to 2023-09-29 — the full backtest's early rebalances (before that date) run against one static backward-projected snapshot, not true point-in-time membership. This re-runs the UNFILTERED strategy restricted to the period where the point-in-time fix is fully real, as its own fresh Rs10L account (not a slice of the full-window curve) — 148 rebalance dates.

## Coverage-clean sub-period

**Verdict: POSITIVE net-of-cost edge** (pooled-trade `has_positive_edge`: profit factor > 1.0 AND Sharpe > 0.5)

### Pooled per-trade stats
- Total trades: 767
- Win rate: 39.5%
- Profit factor: 1.14
- Sharpe ratio: 0.51
- Net profit (sum of per-trade net %): 314.8%
- Avg holding period: 17 days
- Trades/month: 22.8
- Overfit risk flag: no

### Capital-tracked equity curve (Rs10L start)
- Final equity: Rs1,193,716
- Total return: 19.4%
- CAGR: 6.5%
- Sharpe (equity-curve daily returns): 0.45
- Max drawdown: 17.9%

## Benchmark comparison (unfiltered strategy vs buy-and-hold, same window/capital)

### NIFTY 50
- Benchmark final equity: Rs1,297,718  (total return 29.8%, CAGR 8.5%, Sharpe 0.70)
- Alpha (strategy total return − benchmark total return): +5.5pp
- Alpha (CAGR): +1.4pp
- Strategy beats benchmark: YES

### NIFTY ALPHA 50 (sharper peer bar — itself a momentum/alpha index)
- Benchmark final equity: Rs1,884,730  (total return 88.5%, CAGR 21.9%, Sharpe 1.04)
- Alpha (strategy total return − benchmark total return): -53.2pp
- Alpha (CAGR): -12.0pp
- Strategy beats benchmark: NO

## First-half vs second-half Sharpe (unfiltered, pooled trades, chronological by entry date)

- First half:  n=436, PF=1.42, Sharpe=1.37
- Second half: n=437, PF=1.00, Sharpe=-0.01
- Degradation flag (first-half Sharpe minus second-half Sharpe > 0.5): YES

## Caveats

- Point-in-time Nifty 200 universe (core/rotation/nifty200_reconstitution.py), same fix S8-3 needed after its own first result turned out to be pure survivorship bias — reconstructed from real NSE press releases, not assumed. Real events only go back to 2023-09-29 (NIFTY200_RECONSTITUTION_COVERAGE_START); dates before that use one static backward-projected snapshot, not true point-in-time.
- Regime filter is informational only per S8-1's 0-for-2 regime-conditioning record in this project — never the basis for the go/no-go verdict.
- Stop-loss trigger checked against the daily CLOSE, not an intrabar low — the simplest, most auditable construction, pre-registered before running.
- DELIVERY_COST_MODEL reused unchanged from S8-3 (scripts/backtest_rs_momentum.py) — same asset class and holding style, no reason to build a second cost model.
