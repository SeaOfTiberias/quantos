# Forward book, 2026-11-13 (playbook v1, paper)

Written on the read date, **before any outcome**. Trading is paused (2026-11-02); this is a paper book that the user asked for ("suggest positions, strategies, counter strategies"). Nothing here is an order. A real order needs the user's release through `scripts/qorder.py --yes`.

- **Source:** L1 map v1 reads plus playbook v1 (`core/market_map/playbook.py`, rules in `docs/MARKET_PLAYBOOK_V1.md`).
- **Read:** as of 2026-11-13 on bars through 2026-11-12. The first session is 2026-11-13. Orders are valid for 10 sessions (C4).
- **Untested:** P1 and P2 are untested. The S8 test (pre-registration 1cebb0f, amendment 282f95f) is still running. P2 is marked "not for use until its S8 test passes".
- **Data:** `book.json` holds the 8 positions and all 197 setups from the top-500 scan (187 P1, 14 P2, some stocks with both).

## Market context (my read, not the map's; the index is not in the L1 store)

NIFTY weekly:
- A double bottom at 22,182.55 (week of 30 Mar) and 22,179.9 (week of 5 Oct).
- Then +8.4% in the week of 2 Nov, closing at 24,986, above the August lower high of 24,774. That is a weekly turn up (CHoCH).
- 25,116 on 13 Nov. The February highs are at 25,885 and 26,009.

Stocks lag the index: 276 of the 500 still read W down. So the scan leans short on P1 (continuation), while 13 of the 14 P2 setups (reversal) are longs. **The P2 longs agree with the index and the P1 shorts fight it.** So I made the longs the main book and kept a few shorts in the weakest names as a hedge.

## The book

**Main book: P2 longs, half risk.** Each stock swept an old weekly or monthly low, then turned up on the daily (D CHoCH up). The buy limit sits at the daily order block left by the turn.

| Stock | Swept | Shift | Buy / Stop / Target | R | Price 13 Nov |
|---|---|---|---|---|---|
| NTPC | W low 296.55 (2024-W03) to 292.05 on 10-23 | D CHoCH up 317.95 on 11-02 | 302.80 / 290.10 / 337.50 | 2.73 | 318.15 |
| DABUR | W low 357.55 (2019-W20) to 354.30 on 10-27 | D CHoCH up 393.15 on 11-04 | 361.45 / 351.90 / 395.45 | 3.56 | 381.75 |
| JIOFIN | W low 203.10 (2025-W15) to 202.51 on 10-23 | D CHoCH up 221.40 on 11-04 | 211.50 / 201.10 / 235.25 | 2.28 | 227.82 |
| DELHIVERY | M low 374.45 (2026-01) to 364.65 on 10-26 | D CHoCH up 424.50 on 11-05 | 389.95 / 361.30 / 498.00 | 3.77 | 437.45 |

**Hedge: P1 shorts, futures, one lot each.** M down and W down, sell limit at weekly supply. The levels are cash prices; shift each by the futures basis when an order is placed.

| Stock | M / W / D | Supply band | Sell / Stop / Target | R | Lot risk | Price 13 Nov |
|---|---|---|---|---|---|---|
| SIEMENS | down / down / down | W supply 3804–3954.3 (2026-W43) | 3804 / 3984.85 / 3180.60 | 3.45 | ₹31.6k (175) | 3654 |
| IREDA | down / down / up | W bear OB 124.41–128.50 (2026-W25) | 124.45 / 129.45 / 98.80 | 5.13 | ₹22.6k (4525) | 118.04 |
| HAVELLS | down / down / up | W bear OB 1254.3–1303.4 (2026-W33) | 1254.30 / 1311.30 / 999.20 | 4.48 | ₹28.5k (500) | 1161.30 |
| SBILIFE | down / down / up | W bear OB 1836.2–1910 (2026-W31) | 1836.20 / 1921.45 / 1607.70 | 2.68 | ₹32.0k (375) | 1786.80 |

SBILIFE: its W protected high is 1791.40. A weekly close above it flips W up, and C1 cancels the short before it fills.

**Left out:**
- MARUTI, MUTHOOTFIN and GODREJPROP: each P2 long's target equals the P1 short's entry. Trade them in sequence, not both sides at once.
- Further financials: the hedge already has enough.
- Illiquid non-F&O longs, including ANTELOPUS, a round 1 case.

**Salvage rules:** the playbook's own, run by code.
- Shorts: C1 cancels if W or M flips up. E1 exits at the next open after a W flip.
- Longs: C2 cancels on a daily close past the sweep low. E3 exits when the swept level fails.
- After any loss: no re-entry in a broken zone. Reversal only through a valid opposite setup.

**Book-level proposal (not in v1):**
- 3 losses in a row means 5 sessions with no new entries.
- A NIFTY weekly close below 24,774 means the index turn has failed: cancel the unfilled longs, and the shorts become the main book.

## What the first session showed (13 Nov; nothing filled)

All eight stocks fell 0.4–1.8% with NIFTY (−0.72%). Being resting limits, the longs moved toward their fills and the shorts away from theirs. This is one index day, not an outcome.

## Lessons: v2 rule candidates, untested, for pre-registration, not live use

1. **Limit fills track the index.** The longs fill only if the market falls and the shorts only if it rises. The book always leans against the index's latest move.
2. **Correlated setups are one bet.** All four P2 longs come from the same sweep week (10-23 to 10-27), the week NIFTY retested 22,180. Candidate rule: setups from the same sweep week, or the same index event, share one risk unit, so at most one or two of them fill.
3. **The index guard contradicts the deep longs.** These longs need falls of 4.8–10.9%. A ~5% NIFTY drop (to about 23,860) is below the 24,774 guard. So the most likely way they fill is the scenario where the index turn is failing. Candidate rule: cancel unfilled P2 longs when NIFTY *trades* below its turn level, not only on a weekly close.
4. **P2 misses V-turns** (also seen in the walk-through). After a sharp V, the order block is 2–7 ATR(D) below the price and rarely retested. Candidate entry: the first daily pullback to 50% of the shift leg, with the stop below the shift low. This is a new rule to pre-register and test, not a re-tune of P2.

## Scoring this book later

Score each position with `core.market_map.playbook.simulate(setup, daily, as_of=date(2026, 11, 13))` on the stock's daily bars, using the `book` entries in `book.json`. The P1 shorts need the strong opposing zones and states from the read for E2/E1. Report filled or unfilled, the C-code if cancelled, and R. No P&L verdict from 8 positions: this is a walk-forward record, as with `walk.md`.
