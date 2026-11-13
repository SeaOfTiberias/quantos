# How to think through a trade from the map

The procedure, and the reasons behind it, for turning the market map into positions. Written 2026-11-13, when the user handed this job to Claude: "you are now to look at this data and suggest positions, strategies, counter strategies; you are not to dance around that responsibility."

**Use it for any trade or position discussion.** It does not replace the standing rules in `CLAUDE.md` (pause, order gateway, user release) or the playbook rules (`docs/MARKET_PLAYBOOK_V1.md`). It is the thinking that sits between them.

Each step gives the rule, then **Why**: the result or mistake that taught it, with a date. Dated lessons are evidence; update this file when a new one lands. Do not quietly drop old ones.

---

## 0. Who decides what (read this first, every time)

**The job is judgment, not strategy discovery** (user, 2026-11-13). Claude picks the stocks and the side, decides where *not* to trade, sets the backup plan, and adjusts as the market moves, acting as the trader's analyst. The map and the playbook are the inputs; the thinking is Claude's.

- **The user's gates, and only these** (CLAUDE.md):
  - the user releases every real order (`qorder.py --yes`);
  - capital, size and `dry_run` change only with the user's go-ahead;
  - the trading pause.

  State them in one line. Don't re-argue them.
- **Claude's decisions:** everything else. Book changes, cancels, drops, guards, priorities and adjustments are decided and recorded, not proposed for approval. Do not invent new gates ("needs pre-registration before use", "your call", "approve this first") for judgment calls.
- **Pre-registration is for research claims** (does P1 beat a placebo?), not for trading judgment. Judgment is held to account by the forward record (step 8): every call is written down before its outcome and scored after.

**The evidence below sets conviction and size, not permission.** Untested rules mean small size and tight salvage, not silence.

| Claim | Status |
|---|---|
| Any of ~20 strategy candidates has a demonstrated edge | **No.** S7-3: PF 0.75–1.11. Candidates 9–21 failed or were closed. The best near-miss is Darvas ATR-stop: OOS PF 1.46, but its CI spans 0, so not capital-ready. |
| The old 100-day price-map zones beat random levels | **No.** 60.1% vs a placebo's 61.1% (S3, 2026-11-04). FAILED. |
| The L1 HTF map (v1) zones beat random levels | **Untested.** "Strong" is not selective (73% of zones are strong). |
| Playbook v1 P1 (continuation) makes money, net of costs | **Untested.** The S8 test (prereg 1cebb0f, amendment 282f95f) is running. |
| Playbook v1 P2 (sweep then shift) | **Untested.** Marked "not for use until its S8 test passes". |
| The salvage rules (C1–C4, E1–E3, break-even) limit damage | **Some evidence, 4 fills** (walk-through f5b8a23): E1 cut JSL to −0.11R, break-even saved KEI, C1 cancelled the HDFCBANK short. |
| The user's discretionary exits | **Beat the plan once** (SUPREMEIND, 2026-10-30). Measure overrides; don't dismiss them. |

So size every position as a reasoned bet on untested rules. Hiding behind "untested" is the failure mode the user called out (2026-11-13: "for the past 5 months you have been dancing around that"). Overselling the rules as an edge is the other failure mode (2026-10-30, Darvas pushed to real money on a thin edge). The answer to both is the same: make the call, size it small, and carry a salvage plan.

---

## 1. Read the index first, by hand if necessary

Read NIFTY (and BANKNIFTY for financials) on the **weekly** chart before any single stock:
- **Structure:** the last swing high and low; whether the last protected level has broken (a CHoCH).
- **Range:** where the price sits in the multi-month range.
- **Liquidity:** where the obvious equal highs and lows are.

The index is **not in the L1 store**, so this read is manual: pull weekly OHLC from `mcp__quantos__quote` / TradingView and write the levels down. (Gap: put NIFTY and BANKNIFTY in the store so `map_read` covers them.)

**Why:**
- On 2026-11-02 the HDFCBANK futures short (~₹16k loss) went into a 4-year weekly demand zone. The single-stock read ignored the higher-timeframe picture.
- On 2026-11-13 all eight book names moved with NIFTY on a −0.72% day. On index days single-stock levels don't matter, beta does.

**Conclusion it produced on 2026-11-13:**
- NIFTY made a double bottom at 22,180 (Mar and Oct), then a weekly close at 24,986, above the August lower high of 24,774. That is a weekly turn up.
- Bias: longs are the main book, shorts only as a hedge.

## 2. Scan the universe with the map, not by hand

Run `python scripts/playbook_scan.py --as-of <date> --out <file> --lots <fno lots>`. It gives every top-500 read with M/W/D states and the playbook's P1 and P2 plans. Then count:
- **W up vs W down:** stock breadth.
- **P1 setups by side:** what the continuation rules want.
- **P2 setups by side:** what the reversal rules want.

**Why:**
- The user built the map so positions come from rules, not from charts we happen to look at. Picking the names we discussed contaminates everything (2026-11-04: "definitions frozen from concepts, golden set tests them").
- A scan of all 500 also shows when **the stocks disagree with the index**, as on 2026-11-13: 276 of 500 still W down while NIFTY had turned up.

**How to read the disagreement:**
- P1 follows the stocks' own (lagging) weekly trend; P2 catches turns.
- When the index has just turned, **P1 will fight the index and P2 will agree with it.** Weight the side that agrees with step 1.

## 3. Triage: drop what can't or shouldn't fill

`core/market_map/triage.py` applies these and lists the reason for each drop:

| Drop | Rule | Why |
|---|---|---|
| Far | Entry more than 3 ATR(D) from the price | The order is valid for 10 sessions; 3 ATR(D) is about as far as a stock usually travels to a level in that time. A heuristic, untested. |
| Missed | The price is already at or past the target | The move happened without us. Chasing it changes the risk-reward (walk-through, 2026-11-13). |
| Short, no futures | No F&O lot | Cash shorts can't be held overnight in India. |
| Illiquid / not F&O longs | Judgement: low rank, thin volume | Fills and exits are unreliable. ANTELOPUS (rank 494) was also a round 1 case: contaminated. |
| Round 1 / discussed cases | Exclude | They shaped the definitions, so they can't vouch for them. |

On 2026-11-13: 187 P1 + 14 P2 setups went down to 32 actionable P1 + 3 P2. The other P2 longs were 2–7 ATR(D) away (see step 7, V-turns).

## 4. Build the book: main side, hedge side, caps

1. **Main side = the side the index structure agrees with.** Take the cleanest setups:
   - nearest to fill;
   - best R;
   - the deepest liquidity swept (a multi-year weekly low beats a recent daily one).
2. **Hedge side = the opposite side, only in the *relatively* weakest (or strongest) names.**
   - For shorts: M down, W down **and** D down. That stock is falling while the index rises (SIEMENS on 2026-11-13).
   - Names whose daily chart turned up with the market are weaker hedges; size them as one lot.
3. **Cap correlated exposure:**
   - **Sector:** no more than two financials. On 2026-11-13 the raw short list was SBILIFE, LICI, LICHSGFIN, MUTHOOTFIN, IDFCFIRSTB and CAMS: one bet on financials, not six.
   - **Event:** setups created by the same index event are one bet (step 7, lesson 2).
4. **Size:**
   - Give **risk per lot** (risk points × lot, from triage); the user decides the size.
   - P2 is half risk by rule.
   - Never change capital, position size or `dry_run` without the user's go-ahead in that session.

**Why:** with no demonstrated edge, the book's job is to keep a wrong read cheap. Cheap means hedged against the index, capped against correlated names, and small.

## 5. Check each stock for conflicts before including it

- **P2 target = P1 entry** (`triage.pairs`): the reversal long runs up into the continuation short's supply. These are **sequential**: take the long, and if it reaches its target, that's where the short starts. Never hold both at once. On 2026-11-13: MARUTI, MUTHOOTFIN, GODREJPROP, GMDCLTD.
- **About to flip:** if the price is near the W protected level, a weekly close beyond it flips W and C1 cancels the order. Note the level and the date of the deciding close. SBILIFE on 2026-11-13: W flips up on a weekly close above 1791.40; Friday's close was 1786.8.
- **Opposing strong zones** between entry and target: these are where E2 fires. A target beyond a strong opposing zone is a hope, not a plan.

## 6. Every position carries its salvage plan

State this with each position:
- **Before the fill:**
  - C1: W or M flips against → cancel.
  - C2: a daily close beyond the band's far edge → cancel.
  - C3: the target trades first → cancel.
  - C4: 10 sessions without a fill → cancel.
- **After the fill:**
  - The stop.
  - Break-even at +1R.
  - The trail on the D protected level.
  - E1: a W flip → exit at the next open.
  - E2: a strong opposing zone.
  - E3: the swept level fails, for P2.
  - A 40-session time exit.
- **After a loss:**
  - No re-entry in the broken zone.
  - The opposite side only through its own valid setup (a failed long that rallies into supply becomes a P1 short; never "flip because we were wrong").
- **Book level:**
  - 3 losses in a row → 5 sessions with no new entries.
  - The index guard: a level which, if broken, says the step 1 read was wrong. State what gets cancelled then.

Exits are placed by code (the position manager), never decided by a model.

**Why:** "it's ok to go wrong but not ok to not know how to salvage" (user, 2026-11-13). In the walk-through the salvage rules did more good than the entries: E1 on JSL, break-even on KEI, C1 on HDFCBANK.

## 7. Lessons that change how to read a book (keep adding)

1. **Resting limits fill against the index** (2026-11-13). Buy limits fill when the market falls and sell limits when it rises, so the book always leans against the index's latest move. Before calling a book "hedged", ask what it looks like after a 3% index move each way.
2. **Setups from one index event are one bet** (2026-11-13). All four P2 longs came from the 23–27 Oct sweep week, when NIFTY retested 22,180. They will fill together, on the same index dip.
3. **Check the index guard against the fills it guards** (2026-11-13). The longs needed falls of 4.8–10.9%; a ~5% NIFTY fall goes below the 24,774 guard. So the most likely way they fill is the scenario that says the turn failed. Either make the guard intraday or accept that most of these longs won't fill.
4. **P2 misses V-turns** (walk-through and 2026-11-13). After a sharp V, the order block is several ATR(D) below the price and rarely retested. P2 waits for a slow retest.
5. **Break-even without a working trail gives back winners** (KEI walk-through: +2.42R best, closed at 0R).
6. **The risk cap refuses wide HTF zones** (6 of 15 round 1 reads). "No trade: zone too wide" is common and correct. Don't loosen it in-session.
7. **One day is not an outcome** (2026-11-13). The user read a red day as "longs broke, shorts worked". Nothing had filled. Always state fill status before judging a plan.

**Use these lessons in judgment immediately.** Sweep-week grouping and an intraday index guard are book management, and they apply now (the 2026-11-13 book, amendment 1). Only a change to the playbook's own entry rules (for example a shallower P2 entry at 50% of the shift leg) goes through an S8-style test before it replaces a v1 rule, because that is a research claim about the rules.

## 8. Record before the outcome, score after

- Write the book to `docs/review_round1/v3/playbook/forward_<date>/` (book.md plus book.json with every setup), commit and push it **before** any fill.
- Score it after 10 sessions with `core.market_map.playbook.simulate`, and append the results to the same book.md.
- No P&L verdict from a handful of positions. The S8 test decides P1 and P2.
- Log each idea with `scripts/trade_ideas.py` where its format fits. Today it only takes close triggers on option spreads, not limit or futures plans (gap noted 2026-11-13).

**The daily routine** (`scripts/book_daily.py`, VM timer `quantos-book.timer`, 21:30 IST weekdays) does this every day without a session:
- It walks every open book (`core/market_map/book.py`): fills, cancels, exits and R, against the book's baseline.
- It reads NIFTY, BANKNIFTY and each book stock with the map. Index bars come from NSE's public index file, so no Fyers token is needed.
- A model (`core/market_map/book_judge.py`, given this document as its instructions) decides cancels of unfilled positions and index guards. On the Friday run, which reads for Monday, it also builds a new book from the triaged top-500 setups.
- Code validates every decision.
- Books and the journal are saved under `~/.quantos/books/`, and a summary goes to Telegram.

The model never exits a filled position and never sets a price.

**Why:**
- Pre-registration discipline: a failed test is reported as failed, not re-tuned in the same round.
- Commit results before reporting (2026-07).

---

## Worked example: the 2026-11-13 book

See `docs/review_round1/v3/playbook/forward_2026-11-13/book.md`.

| Step | Result |
|---|---|
| 1 | NIFTY weekly turned up (24,986 close > 24,774) → main book long |
| 2 | 500 reads: 276 W down; P1 187 setups (mostly short), P2 14 (13 long) → stocks lag the index |
| 3 | 32 actionable P1 + 3 near P2 |
| 4 | Main: P2 longs NTPC, DABUR, JIOFIN, DELHIVERY (half risk). Hedge: P1 shorts SIEMENS (D down too), IREDA, HAVELLS, SBILIFE, one lot each, ₹22.6k–32.0k lot risk. Financials capped. |
| 5 | MARUTI, MUTHOOTFIN, GODREJPROP left out (sequence pairs); SBILIFE weekly-close flip noted |
| 6 | Salvage rules per position, plus the NIFTY 24,774 guard |
| 7 | Day 1: nothing filled; lessons 1–3 and 7 came from reviewing this book |
| 8 | Committed 119d19f before any fill; score around 2026-11-27 |
