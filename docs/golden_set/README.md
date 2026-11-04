# Market Map golden set (sprint S4)

Charts the user annotates, so the map's definitions match what the user sees
(`docs/MARKET_MAP_ENGINE_DESIGN.md` §6.1). Each chart becomes a unit test: the
engine must reproduce the marked levels from bars before the chart's date.

## Per chart: two files

- `<SYMBOL>_<TF>_<YYYY-MM-DD>.png`: one screenshot with the symbol, timeframe and
  date visible. **Crop out every positions, holdings, order or account panel first.**
  Account data never goes into the repo.
- `<SYMBOL>_<TF>_<YYYY-MM-DD>.md`: the note, in this shape:

```markdown
# HDFCBANK, weekly, 2026-11-02
Source: TradingView | Zerodha. Read as of the close of 2026-11-02.

| Level / zone | Type | Why you marked it | Would you act on it? |
|---|---|---|---|
| 640–665 | demand (multi-year) | base 2022-24, three tests, left fast each time | yes: no shorts into it |
| 665 | strong low | made the BOS up in 2024 | yes |
| 735–742 | supply | ... | ... |

Structure: HTF trend up / down / range, and the swing that defines it.
Not marked but worth saying: (anything the chart shows that you ignore, and why)
```

Types to use where they fit (add your own if none fits): demand, supply, strong
low/high, weak low/high, EQH/EQL (poor high/low), order block, BOS, CHoCH,
premium/discount, CPR (daily/weekly/monthly), Camarilla, money zone / value area,
POC, two-day relationship.

## The set

HDFCBANK and SUPREMEIND first (the 2026-11-02 screenshots), then 10-20 charts in all,
across stocks and indices, uptrends, downtrends and ranges.
