# Reviewer prompt: market map review, round 1

You are reviewing the reads of a stock-chart mapping engine. The engine draws market structure (BOS, CHoCH, protected and weak levels, sweeps), zones (supply and demand, order blocks, equal highs and lows, volume profile, period pivots) and a daily layer for NSE stocks. Your job is to check whether each item it drew follows its written definitions and matches the chart. You are not being asked whether to trade, and you should not give any trade advice.

## What you get

- `MARKET_MAP_DEFINITIONS.md`: the frozen definitions (v1) the engine is meant to implement. This is the only authority on what each item should be.
- `MARKET_MAP_REVIEW_ROUND1.md`: the review protocol.
- For each read `R##`:
  - `R##.json`, with these fields:
    - `symbol`, `as_of`: the read is for the session of `as_of`, using only bars completed before it;
    - `price`: the last close before `as_of`;
    - `lines`: the engine's text read;
    - `items`: the numbered items to judge;
    - `read`: the full output, for detail.
  - Bars, split- and bonus-adjusted, in the CSVs `R##_D.csv`, `R##_W.csv` and `R##_M.csv` (daily, ISO-week and calendar-month). They hold every bar the engine used and none after `as_of`.
  - The last 10 sessions of 5-minute bars, in `R##_m5.csv`.

## What to do for each read

1. **Read the bars yourself.** Compute from the CSVs wherever a definition can be checked: swings, BOS/CHoCH closes, ATR, pivots, CPR, value areas. Don't take the engine's numbers on trust. You may write and run code on the CSVs. Don't read the engine's source code: judge it only against the definitions and the bars.
2. **Judge every item in `items`** on two questions:
   - **rule:** does the item follow the v1 definition? Answer `Y`, `N` or `unclear`.
   - **chart:** does it match what a careful technical analyst sees on these bars at `as_of`? Answer `Y`, `N` or `unclear`.

   Add a short note for every `N` or `unclear`, saying what is wrong and what the right value would be, with a price and a date where you can.
3. **List what's missing:** levels or zones a careful analyst would mark on this chart that the read leaves out. Give each a type (from the definitions' terms where possible), a timeframe, a price or range, and why it matters.
4. **Give an overall verdict:** does the read describe this chart? Answer `yes`, `partly` or `no`, with one or two sentences on why.

Be specific and sceptical. An honest `N` is worth more than a polite `Y`. If a definition is ambiguous, say so and mark the item `unclear` rather than guessing.

## Output

For each read, write one JSON object:

```json
{"id": "R01", "reviewer": "<your name>",
 "items": [{"id": "R01.M.state", "rule": "Y", "chart": "Y", "note": ""}],
 "missing": [{"type": "EQL", "tf": "W", "price": "2420-2430", "note": "..."}],
 "overall": "partly", "overall_note": "..."}
```

Every id in `items` must appear exactly once.
