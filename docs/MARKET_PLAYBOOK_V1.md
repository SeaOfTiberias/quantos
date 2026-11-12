# Market playbook v1: from a map read to a position, and what to do when it goes wrong

Written 2026-11-13, before any playbook code. The user set the standard the same day: being wrong is acceptable; not knowing how to salvage a wrong read is not. So every plan carries its own exit and salvage rules from the start.

**Status: untested; paper only.**
- Real-money trading stays paused (2026-11-02). Every live order still goes through `core/orders/gateway.py` and the user's release (`scripts/qorder.py --yes`).
- Rule-driven exits are placed by code, never by a model (CLAUDE.md). This file is the rule set that code will implement.
- Every level here is a number from the v3 map read (`docs/MARKET_MAP_DEFINITIONS_V3.md`). Every computed price, R and stop comes from unit-tested code, not from a model.
- Discussion cases are excluded from any scoring of this playbook:
  - HDFCBANK as of 2026-10-28 (it prompted P2 and the cancel-on-flip rule);
  - KEI, DMART, HDFCBANK and KOTAKBANK as of 2026-11-13.
- Rules come from SMC and auction concepts. No parameter was set from the outcome of any case.

## Inputs (all from the read, point in time)

| Input | Source |
|---|---|
| States and events | M, W, D state, last event, protected and weak levels (v2 G1) |
| Dealing range | W premium/discount: from the protected to the weak level (§3.5) |
| Zones | v3 zones, with their bands (kind, TF, lo, hi, at-break, fresh) and the strong flag (H3) |
| Liquidity | W and M EQH/EQL, unbroken W and M swings, D sweeps (v2 G3, G4) |
| Volatility | ATR(D) and ATR(W) at the read |

"Bullish band": demand, bull OB, bull FVG. "Bearish band": the mirror. Longs are described below; **shorts mirror every rule**.

## P1. Continuation setup (trade with the higher timeframes)

1. **Direction:** the W state. **The M state must not be the opposite.** If it is, there is no P1 trade.
2. **Entry zone:** the nearest strong zone below the price whose strong band is bullish (at a break, fresh). The **entry band** is that band: the order block or base itself, not the whole cluster.
3. **Location:** the entry price must be in W discount, below the equilibrium of the W dealing range.
4. **Entry:** a resting buy limit at the entry band's top (its near edge).
   - If the price is already inside the band, enter at the next open.
5. **Stop:** the band's low − 0.25 ATR(D).
6. **Target:** the W weak high. It must give **at least 2R**.
7. **Risk cap:** entry − stop ≤ 1.5 ATR(W). A wider risk is no trade ("zone too wide").

**A resting order is cancelled when any of these happens first:**
- **C1, structure flips:** W or M flips against the trade (a CHoCH). The read the order came from no longer holds. *(Added after HDFCBANK: a short placed with M, W and D down filled five sessions after W had turned up.)*
- **C2, zone broken:** a daily close beyond the band's far edge.
- **C3, missed:** the target trades before the entry fills.
- **C4, expiry:** 10 sessions pass without a fill.

## P2. Reversal setup: sweep then shift (trade against the higher timeframes)

The structure is trending down, but liquidity under it has been taken and the daily structure has turned. This is the S8 "sweep then shift" idea as a trade. It is written here and is not used until its own S8 test passes.

1. **Context:** W is down, and the price is at or below the W weak low (beyond the bottom of the W dealing range).
2. **Sweep:** a daily bar trades below an HTF liquidity level by at least 0.1 ATR(D) and **closes back above it**. HTF liquidity means a W or M EQL, the W or M weak low, or an unbroken W or M swing low.
3. **Shift:** a D CHoCH up within 10 sessions after the sweep.
4. **Entry band:** the D order block of that CHoCH (§3.3 applied to D bars, from the CHoCH's protected bar).
   - Resting buy limit at its top, valid 10 sessions.
   - Cancelled by C2 (a daily close below the sweep low) or C3.
5. **Stop:** the sweep's low − 0.25 ATR(D). The sweep low is the level that proves the read wrong.
6. **Target:** the W protected high (the level whose break would complete the reversal), or the first strong bearish zone if it is nearer. At least 2R.
7. **Risk cap:** 1.5 ATR(W). A reversal whose sweep low is further away than that is not taken.
8. **Size flag:** **half risk** (counter-trend). The amount stays the user's decision.

## P3. Managing a filled trade, and salvaging a wrong read

These rules are checked by code at every daily close. An exit they call is executed at the next open, or by the resting stop.

**While the trade is open:**
1. **Hard stop.** It rests at the exchange (GTT) from the fill. It is moved only in the trade's favour, never widened.
2. **Break-even.** At a daily close at or beyond +1R, the stop moves to the entry.
3. **Trail.** After break-even, while D is in the trade's direction: the stop moves to just beyond the D protected level (± 0.25 ATR(D)), whenever that is tighter.
4. **Thesis exit (salvage before the stop):** exit at the next open, whatever the P&L, when:
   - **E1:** W flips against the trade (a CHoCH). This is the HTF read failing.
   - **E2 (P1 trades):** the price closes inside an opposing **strong** zone and D then makes a CHoCH against the trade. This is the move stalling where the map said supply or demand sits.
   - **E3 (P2 trades):** the price closes back below the swept level. The sweep has turned into a break.
5. **Time.** Exit at the close of session 40.
6. **Gap through the stop.** The fill is at the open. The slippage is recorded.

**When the read turns out wrong (stopped out, or E1–E3):**
7. **The zone is finished.** A broken zone has already left the map (H2). No re-entry on it, and no averaging down. Adding to a loser is never a playbook action.
8. **Read the stock again before any new trade.** The failure is information: a broken zone plus a structure flip is how reversals begin.
   - A new trade may come only from a new P1 or P2 setup on the new read.
   - **Stop-and-reverse is allowed only when P2's conditions hold** in the other direction. Never on instinct.
9. **Book circuit breaker:** 3 losing trades in a row across the book means no new entries for 5 sessions. Use that time to review the reads the losses came from. *(Proposed; the user's call, like all sizing and risk limits.)*
10. **Futures specifics:**
    - Shorts on F&O stocks go through futures. `scripts/pick_structure.py` chooses the structure.
    - L1 levels are cash prices: shift them by the futures basis and show the shift (design §3).
    - Roll before expiry under the same plan.

## P4. What the playbook outputs for a read

- **SETUP:** the orders (P1 or P2): entry, stop, target, R multiple, cancel conditions, and the half-risk flag where it applies.
- **WAIT:** the bias and the condition that would create a setup (for example "a W CHoCH up above X", or "a rally into the 805–843 band").
- **NO TRADE:** the reason: timeframes disagree, no strong zone, entry not in discount or premium, under 2R, or zone too wide.
- **For an open position:** HOLD, MOVE STOP (to what), or EXIT (which rule).

## Parameters (fixed here, not tuned)

| Parameter | Value | Why |
|---|---|---|
| Stop buffer | 0.25 ATR(D) | Clear of the noise of one daily bar |
| Minimum reward | 2R | A 1:2 trade breaks even at 33% wins |
| Risk cap | 1.5 ATR(W) | About a normal week's range and a half |
| Entry validity | 10 sessions | Two trading weeks |
| Time exit | 40 sessions | About two months, the life of a W swing |
| Break-even trigger | +1R | |
| Sweep depth | 0.1 ATR(D) | v2 G4's tolerance |
| Shift window | 10 sessions | Two trading weeks |
| Circuit breaker | 3 losses, 5 sessions | Proposed; user's call |

## Testing

- **First:** code P1–P4 with unit tests on synthetic bars, then apply them to the 15 round 1 reads as a walk-through.
- **Then:** pre-register the playbook test for S8 before any universe run, with hypotheses, pass criteria and a placebo control committed first. The placebo is the same rules with entry bands at random price levels of the same width.
- **No P&L verdict** from the 15 reads or from any discussion case.
