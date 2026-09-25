# Kickoff prompt: Darvas ATR-Stop (Bucket B) live dry-run executor

Written 2026-09-25, for a fresh Claude Code session working in this repo.
Paste the section below the line into that session.

---

Build a live, systematic, dry-run-first paper-trading executor for the
Darvas ATR-Stop (Bucket B) candidate — the one strategy in this project,
alongside candidate 18 (ORB scalping), that has actually cleared both its
statistical bar AND a real-capital equity-curve/position-sizing analysis.
It currently has ZERO live execution code. That's the gap to close.

## Read first, in this order

1. `docs/DARVAS_ATR_STOP_BACKTEST_METHODOLOGY.md` and
   `docs/DARVAS_ATR_STOP_BACKTEST_RESULTS.md` — what was actually
   validated: Bucket B = box width strictly between 35% and 50%
   (`scripts/backtest_darvas_box_width.py::BUCKETS`), ATR-scaled trailing
   stop (`ATR_MULTIPLIER = 2.0`, 14-period ATR), Stressed cost model gate.
2. `docs/DARVAS_ATR_STOP_EQUITY_CURVE_RESULTS.md` — the capital-readiness
   and sizing analysis. Headline: **size at ~9% of current equity per
   trade** (`optimal_fraction_by_growth`'s grid-searched figure — beat
   every other policy including a naive quarter-Kelly guess on every
   risk-adjusted metric on the full window), with ₹100,000–250,000
   starting capital as the range where this policy is cleanly profitable.
   Read its whole "Interpretation" section, including the caveat that the
   holdout sample is small and the correlation-regime risk isn't fully
   closed.
3. `scripts/run_orb_scalping_live.py` in full — this is the PATTERN to
   mirror: config-gated (`enabled`/`dry_run`, both default to the safest
   setting), a dedicated position-store module
   (`core/orb_scalping/live_positions.py`), a halt-check
   (`agent/risk_guard.py::read_halt_reason`) checked before every new
   entry, systemd oneshot+timer deployment
   (`deploy/systemd/quantos-orb-scalping-live.service/.timer`), its own
   dry-run log. Candidate 18's version of this file got the halt-check
   and Kelly sizing wired in on 2026-09-25 (see git log around commit
   `f619b43`) — read that commit too, it's the most recent worked example
   of exactly this kind of wiring.
4. `docs/SHARPE_SWEEP_AND_EQUITY_CURVE_PLAN.md` — background on why this
   project builds real-capital equity curves before any live executor,
   and the project's standing anti-overfitting discipline (mining/holdout
   splits, pre-registered gates, "do not peek").

## What NOT to reuse, and why

`core/darvas/scanner.py`, `core/darvas/alerts.py`, and the `scanner:`
config block in `agent/config.yaml` (wired into `agent/main.py`) are an
EXISTING live Darvas pipeline — but for a different, unvalidated variant:

- Its `DEFAULT_CONFIG` caps `max_box_width` at 35.0 — this would EXCLUDE
  every Bucket B trade (35–50% width) outright. The signal that has an
  edge is literally outside that pipeline's filter.
- It uses a static 2%-below-ceiling stop-loss, not the ATR-scaled
  trailing stop that is the entire point of this candidate.
- It POSTs fired signals to a webhook that routes through Telegram
  human-confirm (ADR-05) before any order fires. This project's own
  earlier review (memory: `quantos_fable_rationale_review`) already
  found that a human veto corrupts a systematic strategy's track record —
  the backtest that validated Bucket B/ATR-stop assumed pure systematic
  execution, no veto. Routing the validated edge through this pipeline
  would mean live-trading something that was never actually backtested.

Confirmed by SSH into the production VM (2026-09-25): no darvas/scanner
systemd units exist there at all, and the VM's own `agent/config.yaml`
has `scanner.enabled: false`. Clean slate — nothing needs to be disabled,
and nothing from that pipeline should be extended or built on top of.
The ONLY thing worth reusing from it is the universe symbol list file
(`agent/universe_nifty500.txt`) — that's just data, not the discretionary
architecture.

## What to actually build

A new module/script pair, config-gated the same way as ORB:

1. **Config block** (`darvas_atr_stop:` in `agent/config.yaml.example`,
   mirroring `orb_scalping:`'s own structure and comments) — `enabled:
   false`, `dry_run: true` by default, `starting_capital`,
   `min_capital_floor`, `fraction_per_trade: 0.09` (or wire in
   `core/risk/kelly.py`'s existing rolling sizing the same way candidate
   18's executor now does — your call, but state which one you chose and
   why; a fixed 9% is simpler and directly matches what was validated,
   rolling Kelly adapts as more live trades accumulate but wasn't
   validated at 9% specifically).
2. **Signal detection**: reuse `core/darvas/weekly_discovery.py::analyse_symbol`
   and `_atr` directly (the SAME functions the validated backtest itself
   imports and uses — do not reimplement box/breakout detection from
   scratch). Filter to `35 < box_width_pct <= 50` (Bucket B) before acting
   on anything. Port the ATR-scaled stop logic from
   `scripts/backtest_darvas_atr_stop.py::_stop_from_atr` /
   `_simulate_exit_atr` for the live trailing-stop calculation.
3. **Position tracking**: a new position-store module mirroring
   `core/orb_scalping/live_positions.py`'s shape (persisted JSON under
   `~/.quantos/`, survives a restart) — but for MULTI-DAY holds and
   potentially DOZENS of concurrent symbols (mean 12.2, max 29 in the
   backtest's own mining window), not a single intraday position per
   underlying. Design the store and the position-sizing call to handle
   real concurrent-position accounting (current equity = cash + all open
   positions' cost basis, matching how
   `scripts/simulate_darvas_atr_stop_equity_curve.py::simulate` computes
   it) — this is NOT optional, it's the exact thing the whole portfolio-
   Kelly exercise was about.
4. **Halt-check**: `agent/risk_guard.py::read_halt_reason()` checked
   before every new entry, exactly like candidate 18's executor, from
   day one — not bolted on after the fact this time.
5. **Cadence**: signal detection here runs on DAILY bars (weekly box
   state), not 5-minute intraday like ORB — a once/day scan of the
   universe file is the right cadence for finding NEW breakouts (matches
   the old pipeline's own "Stage A — once/day" comment, which is sound
   scanning-frequency guidance even though that pipeline's architecture
   isn't being reused). Managing already-open positions (checking the
   ATR trailing stop, deciding exits) also only needs daily-bar
   granularity, since the backtest itself only ever checks stops on daily
   closes — confirm this against `_simulate_exit_atr`'s own logic before
   assuming otherwise.
6. **Tests**: mirror `tests/unit/test_run_orb_scalping_live.py`'s style —
   broker-mocked, no network, isolate the halt-flag path via monkeypatch
   (see that file's `_patch_common` for the pattern), cover entry sizing,
   concurrent-position equity accounting, stop-trailing, and the halt
   check blocking new entries.
7. **systemd unit files** mirroring
   `deploy/systemd/quantos-orb-scalping-live.service/.timer` — daily
   cadence instead of every-minute, `enabled:false`/`dry_run:true` in the
   committed config so deploying the unit file is inert until a deliberate
   `enabled:true` step, same pattern as every other new unit in this
   project's history (deploy/systemd files exist for review before
   `systemctl enable --now` is ever run).

## What NOT to do

- Do not touch `dry_run` or `enabled` — this build stays paper-only.
  `feedback_confirm_before_scaling_capital` in memory is the standing
  rule: only the user's own fresh, explicit go-ahead flips those, later,
  separately from this build.
- Do not enable, modify, or build on top of `core/darvas/scanner.py` /
  `alerts.py` / the `scanner:` config block.
- Do not skip the mining/holdout-derived 9% sizing figure in favor of a
  fresh in-sample "optimization" — if you find yourself tuning the
  fraction against the SAME data that already produced 9%, stop; that's
  the exact overfitting shape this project has rejected everywhere else.
- Once built, this needs a real dry-run observation period (weeks, not
  a single session) before ANY capital conversation is appropriate — same
  two-stage discipline candidate 18 is currently going through. Don't
  present a clean test suite as equivalent to live-validated behavior.
