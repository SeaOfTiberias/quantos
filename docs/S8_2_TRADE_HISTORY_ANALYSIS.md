# S8-2 Fyers Automation Trade-History Retrospective

**21 same-day round trips analysed** (Intraday/Intraday BO NIFTY options only; 2 Overnight-product trades excluded from these stats -- they're manual overrides of the stated same-day exit rule, reported separately below).

## Overall

- Win rate: 10/21 = 48%
- Total gross P&L: Rs2,633
- Average win: Rs1,676
- Average loss: Rs-1,284
- Time-stop exits (>=3:09pm): 3/21

## Per-trade P&L (checking whether losses actually ride to the -Rs2000 cap)

| Date | Symbol | Side | Hold (min) | P&L (Rs) | Exit type |
|---|---|---|---|---|---|
| 2026-05-26 | NIFTY2660224000CE | CE (bullish) | 4 | 78 | other/manual |
| 2026-05-26 | NIFTY26MAY23950PE | PE (bearish) | 2 | -338 | other/manual |
| 2026-05-27 | NIFTY2660224050PE | PE (bearish) | 22 | 484 | other/manual |
| 2026-05-27 | NIFTY2660224100PE | PE (bearish) | 41 | -1,189 | other/manual |
| 2026-05-27 | NIFTY2660224100PE | PE (bearish) | 31 | -1,710 | other/manual |
| 2026-05-29 | NIFTY2660223900CE | CE (bullish) | 6 | -972 | other/manual |
| 2026-05-29 | NIFTY2660224100PE | PE (bearish) | 1 | -169 | other/manual |
| 2026-05-29 | NIFTY2660224100PE | PE (bearish) | 57 | -1,459 | other/manual |
| 2026-06-24 | NIFTY26JUN23900CE | CE (bullish) | 12 | 2,223 | P&L cap |
| 2026-06-25 | NIFTY26JUN24150CE | CE (bullish) | 115 | 2,048 | P&L cap |
| 2026-06-29 | NIFTY26JUN24100CE | CE (bullish) | 61 | -2,022 | P&L cap |
| 2026-06-30 | NIFTY26JUN23950CE | CE (bullish) | 4 | 2,181 | P&L cap |
| 2026-07-02 | NIFTY2670724100CE | CE (bullish) | 21 | 2,057 | P&L cap |
| 2026-07-07 | NIFTY2670724450PE | PE (bearish) | 155 | 1,375 | TIME (3:10pm) |
| 2026-07-09 | NIFTY2671424050CE | CE (bullish) | 67 | 2,080 | P&L cap |
| 2026-07-10 | NIFTY2671424200CE | CE (bullish) | 345 | -224 | TIME (3:10pm) |
| 2026-07-13 | NIFTY2671424000PE | PE (bearish) | 39 | -2,044 | P&L cap |
| 2026-07-14 | NIFTY2671424150CE | CE (bullish) | 230 | -2,002 | TIME (3:10pm) |
| 2026-07-15 | NIFTY2672124150CE | CE (bullish) | 11 | 2,028 | P&L cap |
| 2026-07-16 | NIFTY2672124150CE | CE (bullish) | 219 | -1,999 | P&L cap |
| 2026-07-17 | NIFTY2672124200CE | CE (bullish) | 58 | 2,207 | P&L cap |

## Question 1: would a faster invalidation exit have helped?

Of 21 trades with usable NIFTY 5-min data, **5 had the EMA9/EMA21 crossover reverse AGAINST the position before the actual exit** (i.e. the signal that triggered entry had already failed, but the position was held anyway until the P&L cap or 3:10pm) — averaging 155 minutes of extra hold time after invalidation.
  - 2026-06-29 NIFTY26JUN24100CE: crossover reversed at 11:20 IST, actual exit at 11:35 IST (16 min later, trade P&L was Rs-2,022)
  - 2026-07-07 NIFTY2670724450PE: crossover reversed at 14:40 IST, actual exit at 15:10 IST (30 min later, trade P&L was Rs1,375)
  - 2026-07-10 NIFTY2671424200CE: crossover reversed at 09:35 IST, actual exit at 15:10 IST (335 min later, trade P&L was Rs-224)
  - 2026-07-14 NIFTY2671424150CE: crossover reversed at 12:05 IST, actual exit at 15:10 IST (185 min later, trade P&L was Rs-2,002)
  - 2026-07-16 NIFTY2672124150CE: crossover reversed at 09:30 IST, actual exit at 12:58 IST (209 min later, trade P&L was Rs-1,999)

## Question 2: would a trailing stop have captured more?

Of 21 trades, **3 gave back more than 20% of the underlying's peak favourable move** between entry and the actual exit — a trailing stop on the underlying (approximating the option's premium path) would plausibly have locked in more on these:
  - 2026-05-29 NIFTY2660224100PE: underlying moved 26.3 pts favourably at best, gave back 53% of that by exit (trade P&L Rs-1,459)
  - 2026-07-10 NIFTY2671424200CE: underlying moved 34.0 pts favourably at best, gave back 47% of that by exit (trade P&L Rs-224)
  - 2026-07-16 NIFTY2672124150CE: underlying moved 46.0 pts favourably at best, gave back 105% of that by exit (trade P&L Rs-1,999)

## Overnight (manual override) trades — excluded above, reported separately

| Date | Symbol | Hold | P&L (Rs) |
|---|---|---|---|
| 2026-04-28 | NIFTY26APR24050CE | 0.1h | -764 |
| 2026-05-26 | NIFTY26MAY24000PE | 1.0h | 2,606 |

## Caveats

- Gross P&L only (Fyers brokerage/STT/GST not deducted here — small relative to these P&L swings, S8-4's backtest will apply the real options cost model).
- The underlying-move analysis approximates option premium behaviour from NIFTY's own 5-min path, not the option's own tick data (no historical options price/IV source exists in this repo yet) — directionally informative, not exact rupee figures.
- Small sample. This grounds S8-4's exit-rule design; it isn't itself a backtest verdict.
