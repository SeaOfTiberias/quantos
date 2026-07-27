# Momentum Turnover Walk-Forward — Methodology, Pre-Committed 2026-07-27 Before Any Paper Trade Exists

## Why this exists

`docs/MOMENTUM_TURNOVER_ABLATION_METHODOLOGY.md` (candidate 11) found that
switching S8-3's rebalance cadence from weekly to quarterly, holding the
ranking formula/universe/costs/capital fixed, closed ~80% of the Sharpe gap
and ~40% of the CAGR gap to Nifty Alpha 50 — in-sample, on the one ~3-year
window this project's point-in-time Nifty 500 data covers (2022-06-20 to
now). Two follow-up diagnostics (coverage-clean sub-period, first/second-half
stability split) came back clean, but Fable's second review declined to
green-light pre-registering this as a new strategy candidate: **everything
so far is in-sample**, drawn from a single sustained-uptrend window with no
bear leg, and 244 trades come from only 14 correlated quarterly decisions,
not independent draws.

A genuine out-of-sample test was investigated and found infeasible as a
backtest: real point-in-time Nifty 500 membership data starts 2023-09-29,
and the original ablation's window already runs from before that to "now" —
there is no untouched historical slice left that wouldn't reintroduce the
survivorship bias the point-in-time universe was built to exclude (see
`quantos_momentum_turnover_ablation_status` memory, 2026-07-25 follow-up).
**Forward paper-trading is therefore the only method that can produce a
genuinely out-of-sample data point for this candidate.** This is that test.

**This is a walk-forward confirmation, not a fresh strategy pre-registration
with a fixed strategy content.** The strategy content (ranking formula,
universe, cadence rule, cost model) is entirely inherited from the
already-pre-registered ablation — nothing new is being invented or tuned
here. What's new is the data: real, live, never-touched-by-any-backtest
prices, accumulated one quarter at a time, starting from this document's
commit date forward.

## What is held fixed (identical to the ablation, not rebuilt)

- **Ranking function**: `core/rotation/ranker.py`'s `rank_universe()`,
  unchanged — 52-week-high proximity, `TOP_N = 20`, `LOOKBACK_DAYS = 252`.
- **Universe**: `agent/universe_nifty500.txt`, the same list the live S8-3
  rotation already trades against. No point-in-time reconstruction is
  needed live (unlike a backtest) — "today's constituent list" is already
  point-in-time-correct for a forward-only run.
- **Exit rule**: rank-dropout only (`rank_only`) — no stop-loss/EMA layered
  on, matching the ablation exactly.
- **Cost model**: `DELIVERY_COST_MODEL` (`scripts/backtest_rs_momentum.py`),
  applied to every simulated fill via `CostModel.cost_of()` — so the paper
  P&L isn't flattered by ignoring brokerage/STT/slippage.
- **Capital and position size**: virtual ₹1,000,000 initial capital,
  ₹50,000/position — identical to the ablation's control, so the eventual
  OOS Sharpe/CAGR are directly comparable to the in-sample 0.81/10.2% and
  the weekly control's 0.34/4.0%, not a different-scale run that needs
  re-normalizing.
- **Rebalance rule**: last NIFTY trading day of each calendar quarter, same
  `(year, quarter)` grouping as the ablation's `quarterly_rebalance_dates()`.

## What is genuinely new here (the mechanism, not the strategy)

- **No real capital, ever.** This never calls `broker.place_order()`. It
  reads live prices via `broker.get_ltp()` (read-only) and simulates fills
  against a virtual cash ledger stored in
  `~/.quantos/paper_rotation_positions.json` on the VM — entirely separate
  from `agent/rotation_positions.py`, which tracks the real S8-3 rotation's
  real holdings. There is no path by which this walk-forward can place a
  real order or touch real funds.
- **Self-healing daily gate, not a single quarterly shot.** The systemd
  timer fires daily (mirroring `quantos-agent-daily-restart.timer`'s
  cadence), but the script itself only acts once each calendar quarter has
  reached its last NIFTY trading day AND that quarter hasn't already been
  recorded. If a given day's run fails (most likely cause: the Fyers auth
  token the user refreshes manually most days, per the VM's existing daily
  routine, happened to be stale that particular day), the next day's run
  retries automatically — a quarter is only actually missed if the token
  stays stale for the entire quarter-end window, not a single bad day.
- **No cloud/Telegram integration in this first version.** Deliberately
  scoped out to avoid touching `cloud/api/rotation_routes.py` (shared,
  deployed infrastructure) for a candidate that's still speculative.
  Failures are visible via `journalctl -u quantos-paper-momentum` on the VM
  — checked during the user's existing daily SSH routine, not proactively
  alerted. Known limitation, acceptable given the self-healing daily retry.

## Minimum duration before reading a verdict

**At least 4 completed quarters (~1 year)** from first rebalance before any
verdict is drawn — matching Fable's stated concern about the in-sample run's
thin 14-decision sample. Checking the log more often than that is fine for
monitoring (is it running, are trades sane), but **no early stopping and no
early verdict** — a good or bad first quarter is not a sample, it's one
data point. 6-8 quarters (1.5-2 years) is preferable if the user is willing
to let it run that long; 4 is the floor, not the target.

## Pass / inconclusive / fail bar — fixed now, before any live quarter exists

Read only after the minimum duration above. Computed via the same
`core/rotation/equity_curve.py` machinery (CAGR, Sharpe) applied to the
accumulated virtual equity curve.

- **PASS** (replication): OOS Sharpe > 0.5 — roughly the midpoint between
  the weekly control's in-sample 0.34 and the quarterly ablation's in-sample
  0.81, a deliberately generous band given the small sample. This would
  mean the gap-closure finding survived contact with real, never-backtested
  data, and a properly pre-registered quarterly-momentum candidate becomes
  worth building.
- **INCONCLUSIVE**: OOS Sharpe between the weekly control's 0.34 and 0.5.
  Directionally consistent with turnover mattering, but not a clear enough
  signal to act on — would need more quarters before either promoting or
  closing.
- **FAIL**: OOS Sharpe <= 0.34 (no better than the weekly control already
  known to underperform) — the in-sample gap-closure finding does not
  replicate out of sample; close the candidate, the gap was a property of
  the fitted window, not the cadence change itself.

## What would make this untrustworthy after the fact

- Changing the ranking formula, `TOP_N`, `LOOKBACK_DAYS`, cadence rule, or
  the Sharpe thresholds above once live quarters start coming in — that
  would be tuning against results, exactly what this walk-forward exists to
  rule out.
- Reading a verdict before 4 completed quarters, in either direction.
- Restarting the virtual ledger (e.g. "reset and try again") after a bad
  quarter — the whole point is one continuous, un-cherry-picked forward
  path.
- Quietly extending position size / capital before a verdict is reached —
  this is paper money, but the discipline of not moving parameters
  mid-flight still applies, matching this project's standing rule for real
  capital (`feedback_confirm_before_scaling_capital`).

## Deployment

Runs on the same Oracle VM as the real S8-3 rotation
(`quantos_vm_deployment` memory), as a new, independent systemd
service+timer (`deploy/systemd/quantos-paper-momentum.service`/`.timer`) —
does not touch, share state with, or depend on `quantos-rotation.service`.
Deploying this (installing new systemd units on the production VM) requires
the user's explicit go-ahead before it happens, per this project's standing
practice for changes to shared/production infrastructure.
