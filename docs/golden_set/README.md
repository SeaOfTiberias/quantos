# Market Map golden set (sprint S4)

Charts the user annotates, to test whether the map sees what the user sees
(`docs/MARKET_MAP_ENGINE_DESIGN.md` §6.1). The rules are NOT fitted to these marks
(user, 2026-11-04): `docs/MARKET_MAP_DEFINITIONS.md` v1 is frozen first, then scored
against the marks by its §9 fidelity test. A miss is reported as a miss.

- **Mark without reading the definitions,** so the marks stay your own reading.
- Hand the charts over only after v1 is committed and approved.
- HDFCBANK and SUPREMEIND were discussed before v1 was written: still mark them, but
  they illustrate and are never scored.

## Per chart: two files

- `<SYMBOL>_<TF>_<YYYY-MM-DD>.png`: one screenshot with the symbol, timeframe and
  date visible. **Crop out every positions, holdings, order or account panel first.**
  Account data never goes into the repo.
- `<SYMBOL>_<TF>_<YYYY-MM-DD>.md`: the note, in this shape:

```markdown
# XYZ, weekly, 2026-11-02
Source: TradingView | Zerodha. Read as of the close of 2026-11-02.

| Level / zone | Type | Why you marked it | Would you act on it? |
|---|---|---|---|
| 100–104 | (your type) | (your reason) | yes / no |

Structure: HTF trend up / down / range, and the swing that defines it.
Not marked but worth saying: (anything the chart shows that you ignore, and why)
```

Types to use where they fit (add your own if none fits): demand, supply, strong
low/high, weak low/high, EQH/EQL (poor high/low), order block, BOS, CHoCH,
premium/discount, CPR (daily/weekly/monthly), Camarilla, money zone / value area,
POC, two-day relationship.

## The set

10-20 scored charts, chosen by you, across stocks and indices, uptrends, downtrends and
ranges, plus HDFCBANK and SUPREMEIND (unscored). Pick charts we haven't discussed.
