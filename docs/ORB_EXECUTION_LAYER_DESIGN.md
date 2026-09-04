# ORB Scalping Execution Layer — Design, Written Before Any Order-Placing Code Ran

## Why this exists

Candidate 18 (Opening Range Breakout on NIFTY/BankNifty index options,
[[quantos_orb_options_scalping_status]]) has cleared its backtested cost bar after
adversarial review (NIFTY PF 1.23/Sharpe 0.88, BankNifty PF 1.16/Sharpe 0.95). It is not
live. Two things block it from trading real money: (1) an execution layer that can place
and manage real orders for it — which did not exist before this work — and (2) the user's
own explicit capital go-ahead, a standing project-wide gate
([[feedback_confirm_before_scaling_capital]]) unaffected by anything built here.

This document is the pre-registration-style record of the design, matching the project's
habit of writing the design/methodology doc before (or alongside) the code it governs
(cf. `docs/ORB_OPTIONS_SCALPING_METHODOLOGY.md`, `docs/ORB_STOPOUT_SPREAD_PROBE_METHODOLOGY.md`).
Nothing built under this design flips `dry_run:false`, sets `enabled:true`, enables a
systemd timer, or touches the cockpit. It is scaffolding: when the go-ahead eventually
arrives, going live is a config flip, not a coding project.

## Architecture decisions (made with the user before any code was written)

- **Layer 1 (execution) is deterministic code — no LLM agents, no MCP.** An LLM in the
  loop of a stop-loss/take-profit decision adds latency and non-determinism exactly where
  speed and correctness matter most; this project's execution code has always been
  boring-by-design (`core/orb_scalping/live_state.py`, the two spread probes) and layer 1
  follows the same discipline.
- **MCP, if ever, belongs only at a future strategy's layer 3** (a genuinely
  judgment-heavy strategy selector). ORB's own layer 3 is fully mechanical — opening
  range, ATM strike, DTE floor are all deterministic rules — so no MCP appears anywhere
  in this design.
- **Design for ORB's real concurrency**: at most 2 open positions (one NIFTY, one
  BankNifty, one trade per index per day) — not engineered for many simultaneous
  strategies/positions. Revisit if a future higher-frequency strategy needs more.
- **TradingView Premium's role, if used at all, is alert/conduit only.** ORB's entry
  logic stays 100% Python (`compute_live_state()`, already backtested and Fable-reviewed)
  — no new Pine re-implementation of the breakout rule. The project already hit one real
  bug from a second, divergent implementation of a rule (the Pine `darvasBox()` bug that
  silently suppressed real Darvas breakouts, [[quantos_pine_breakout_bug]]); a second
  ORB implementation in Pine would risk the same class of bug for the strategy that has
  worked hardest to earn trust. See "Webhook/queue transport seam" below for how
  TradingView (or any future off-box producer) can still plug in later without a redesign.
- **No per-trade Telegram confirm for ORB entries/exits once live.** They fire
  automatically, same precedent as the equity `auto_exit` stop-loss
  (`agent/main.py::_size_and_place_order`) and the rotation pilot's deliberate no-confirm
  carve-out — ORB's entry window is only a few minutes wide, and a confirm round-trip
  could miss it. The overall capital go-ahead is the human checkpoint, not a per-trade tap.
- **Cockpit discretionary "buy" button is explicitly deferred** to a future session. Only
  a one-paragraph forward-looking note is recorded below so this design doesn't
  accidentally box that out.

## Layer boundaries

### Layer 1 — `core/execution/order_service.py`

Named to avoid confusion with `core/execution/slicer.py`/`slicing.py`, which solve a
different problem (intra-order depth-slicing of one large order — orthogonal to
managing a position's lifecycle). Pure, `BrokerAdapter`-typed, `dry_run`-aware,
unit-testable with a fake broker (no network, no Fyers):

- `enter_position(...)` — places a MARKET entry, then (if not `dry_run`) a second SL_M
  stop order in the opposite direction. Generalizes
  `agent/main.py::_size_and_place_order`'s two-order pattern (Fyers v3 rejects Cover
  Orders outright, so a resting stop is always a second, separate order) off its
  Darvas-only assumptions.
- `update_stop(...)` — wraps `broker.modify_stop_loss()`. Fyers' `modify_stop_loss` is
  implemented but "not yet verified against a live Fyers account" per
  `core/brokers/fyers.py` — a known risk, not a blocker here since `dry_run` never calls
  it for real.
- `reconcile_position(...)` — cross-checks `broker.get_positions()` against a tracked
  symbol; if closed, walks `broker.get_order_history()` to find the fill (the SL_M order
  filling is the exit; otherwise the latest executed fill for the symbol, with the
  now-orphaned stop cancelled). Extracted from `agent/main.py::_manage_open_positions`'s
  inline logic so ORB (and any future strategy) doesn't reimplement this a fourth time.
  The extraction is read-only against `agent/main.py` — the live Darvas path is not
  rewired to use it in this pass, keeping that already-live code untouched.
- `flatten_position(...)` — 15:20 IST session-flatten: an opposite-direction MARKET
  close, plus cancelling the resting stop order.

Respects the known Fyers landmine: order-management success is `response["s"]=="ok"`,
not `response["code"]==200` — already fixed once in `core/brokers/fyers.py` after a real
order-misfiling bug; layer 1 only calls the already-correct `BrokerAdapter` methods, it
does not re-parse raw Fyers responses itself.

### Position state — `core/orb_scalping/live_positions.py` (new sibling, not a reuse of `agent/positions.py`)

`agent/positions.py::OpenPosition` has no room for what ORB genuinely needs: both an
index symbol *and* a resolved option symbol, **two** stop levels (index-points from
`compute_live_state().current_stop`, plus the 25%-of-premium stop from
`core/orb_scalping/premium.py::PREMIUM_STOP_PCT`), a `dte_floor_rolled` flag, and the
`armed` trailing-arm state. Forcing these into `OpenPosition` would mean dead fields on
every Darvas position, or fields whose meaning silently depends on `strategy==...` — both
worse than a small, separate JSON-store sibling. `OrbOpenPosition` persists at
`~/.quantos/orb_open_positions.json` (never shared with Darvas's file — its loader does
`OpenPosition(**data)` unconditionally and would crash on ORB's extra fields).

Consolidating the three position-JSON stores that now exist (Darvas, rotation, ORB) into
one generic store is a real future cleanup opportunity — explicitly **not** done here.

### Shared contract-selection helpers — `core/orb_scalping/contract_selection.py`

Extracted, not duplicated, from the two existing (untouched) spread probes:
`select_expiry()` + the per-underlying DTE-floor constants (previously split across
`scripts/probe_orb_scalping_real_spreads.py` and
`scripts/probe_orb_scalping_stopout_spreads.py`), and the tolerant nearest-strike chain
lookup (previously `_fetch_chain_row` in the stopout probe, renamed
`fetch_chain_row_near_strike`). This project already hit one real bug from duplicated
DTE-floor logic drifting (`scripts/probe_orb_scalping_real_spreads.py`'s 2026-09-02 fix,
where NIFTY's floor was silently applied to BankNifty too) — worth the extraction rather
than a third copy for layer 2.

`scripts/probe_orb_scalping_real_spreads.py` now imports `select_expiry` from this new
module instead of defining it. **`scripts/probe_orb_scalping_stopout_spreads.py` is not
modified** — it is mid-way through its own separate pre-registered data collection
(earliest recheck 2026-10-01) and must not be touched by this work.

### Layer 2 — `scripts/run_orb_scalping_live.py`

Same deployment shape as `quantos-orb-stopout-probe`: a stateless oneshot, fired by a
market-hours-gated systemd timer, self-healing on failure, no `Restart=`. Per fire, for
each underlying:

1. Fetch today's closed 5m candles → `compute_live_state()`.
2. On a transition to `in_position` with no `OrbOpenPosition` on record for
   `(underlying, trade_date)`: resolve ATM strike → expiry → tradeable symbol →
   `order_service.enter_position()` (places a MARKET entry + a real resting SL_M at the
   fixed 25%-of-premium stop) → persist `OrbOpenPosition`.
3. If a position is on record (and not `dry_run`): `order_service.reconcile_position()`
   first — this is how a fill of the real resting premium stop is noticed; the broker
   closes it on its own, this script just has to notice and record the trade. Only if
   still open does the script actively check the INDEX-level stop (live LTP vs.
   `compute_live_state()`'s trailing stop) and the 15:20 IST session-flatten — **neither
   has a backing broker order** (see "Why `update_stop()` has no caller here" below) — and
   force-exits via `order_service.flatten_position()` when either fires. `dry_run` skips
   the broker-side reconcile (nothing was really bought) and relies solely on these
   script-side checks.
4. Any close — broker-side premium-stop fill, index-stop force-exit, or session-flatten —
   records a `ClosedTrade` via the existing `TradeHistoryService.record_closed_trade()`
   (the same `~/.quantos/trade_history.json` pool `agent/main.py`'s Darvas execution
   already writes to — deliberately shared, not per-strategy: Kelly sizing is designed to
   draw on the full cross-strategy history for a larger sample) and removes the
   `OrbOpenPosition`. A `dry_run` exit is logged and removed from tracking WITHOUT a
   `ClosedTrade` record — there is no real fill price to record, and a fabricated one has
   no place polluting the sizing history.

**Why `order_service.update_stop()` has no caller in this build**: ORB's methodology has
two independently-behaving stops, not one trailed stop. The 25%-of-premium stop
(`core/orb_scalping/premium.py::PREMIUM_STOP_PCT`) is computed once at entry and used as a
constant threshold for the whole trade — never trailed, even in the backtest — so a real
resting SL_M order placed once at entry is the exact right implementation, and it never
needs `modify_stop_loss()`. The index-level stop DOES trail (`compute_live_state()`'s
arm/trail logic), but it has no corresponding broker order to move: Fyers option stop
orders trigger on the option's own premium, and translating an index-points stop level
into an equivalent premium trigger would require re-deriving option pricing (the
Black-Scholes machinery this project has deliberately kept out of live execution, and an
untested translation is worse than none). So the index-level stop is enforced by the
script itself, re-checked every fire, force-exiting via `flatten_position()` when
breached — `update_stop()` remains a real, tested primitive in layer 1 (a future strategy
whose stop is naturally priced in the same terms as its entry would use it), just not one
ORB happens to need.

### Layer 3 — config only, plus one interface shape

ORB has no discretion to encode, so layer 3 is just the new `orb_scalping` block in
`agent/config.yaml` (`enabled`/`dry_run` convention, same as `rotation`/`rotation_pilot`/
`options`). One small interface dataclass, `core/execution/trade_intent.py::TradeIntent`,
fixes the *shape* of "a trade should happen now" (underlying, direction, index entry
price, timestamp, source) so a future, less-mechanical or human-discretionary producer
can feed the same layer 1/2 functions without a redesign — without this pass needing to
build any dispatcher, queue, or registry for it.

### Webhook/queue transport seam — decision: not built in this pass

Considered reusing `cloud/api/options_webhook_routes.py`'s proven queue/claim shape
(built for TradingView) as the hand-off between "whatever detects a trade intent" and
layer 1. **Not built now**: that shape bridges two different machines (TradingView →
cloud API on Railway → the agent on the VM, which alone holds the broker session). ORB's
layer 2 runs as a oneshot on the *same VM, same process invocation* that calls layer 1 —
there is no cross-machine boundary to bridge, so an HTTP round-trip would add latency and
a new failure mode for zero decoupling benefit. Because `TradeIntent` already fixes the
handoff shape independent of transport, nothing is foreclosed: if TradingView, or a
future discretionary cockpit button, later need to feed a `TradeIntent` from a different
process, a small sibling of `options_webhook_routes.py` can be added at that point
(~180 lines, a proven template) — not a redesign of anything built here.

**Forward-looking note only (no code in this pass)**: a future discretionary cockpit
"buy" button should call the same `order_service` functions with the same `TradeIntent`
shape as its input, whichever transport it needs at that time.

## Non-goals for this pass

- No `dry_run:false`, anywhere, ever. No `enabled:true` for `orb_scalping`.
- No `systemctl enable`/`enable --now` for the new timer.
- No cockpit/UI changes beyond the one forward-looking note above.
- No new Pine script / TradingView alert.
- No consolidation of the three existing position-JSON stores.
- No MCP anywhere in this design.
- No modification of `scripts/probe_orb_scalping_stopout_spreads.py`, its timer, or its
  data file.
- No modification of `agent/main.py`'s live Darvas execution path.

## Go/no-go checklist for eventually flipping `dry_run:false`

This checklist records what this design can and cannot certify on its own — it is not a
substitute for the user's fresh, explicit go-ahead, which remains the actual gate
([[feedback_confirm_before_scaling_capital]]):

1. Code + tests for all four layers merged and passing (this document's build order).
2. The stop-out spread probe's own pre-registered gate (N≥20 stop-out events per index
   AND ≥4 elapsed weeks, [[quantos_orb_options_scalping_status]]) has cleared — a
   separate, already-running decision this design does not influence.
3. At least one supervised `dry_run:true` cycle of `scripts/run_orb_scalping_live.py`
   observed end-to-end on a real trading day (entry detection, stop trailing,
   reconciliation, no real orders placed) — the same "watch one supervised dry cycle"
   precedent `rotation_pilot`'s config comment already documents.
4. The user's own fresh, explicit go-ahead — not implied by 1-3 clearing.
