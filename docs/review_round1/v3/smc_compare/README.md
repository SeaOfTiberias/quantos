# v3 zones beside an SMC indicator (2026-11-13)

KEI, DMART, HDFCBANK and KOTAKBANK, read as of 2026-11-13 (daily bars to 2026-11-12) under definitions v3 (code f7bfa2b). The user chose the four stocks on 2026-11-13. HDFCBANK was kept out of the round 1 draw; it is here only for a visual comparison, not a score.

Untested markers, not signals. Trading is paused (2026-11-02).

## Files

- `v3_<SYMBOL>.png`: daily candles from 2025-01, with every v3 zone that meets the chart's price range.
  - **Colour:** blue = bullish band (demand, bull OB, bull FVG); orange = bearish band; grey = a zone made only of swing points.
  - **Strong** zones are darker with a border. **FVGs** are hatched.
  - **Left edge:** the zone's own band bar (order block, gap or base). For a swing-only zone, its oldest swing.
  - The zone runs to the right edge. The dashed line is the last close.
- `quantos_map_v3_zones.pine`: the same 55 zones as TradingView boxes (Pine v6, frozen values). To use it:
  - add it to a daily chart of one of the four symbols, next to the SMC indicator;
  - it draws nothing on other symbols;
  - inputs hide the ordinary zones or the text.

## What to compare

1. **Order blocks:** does each v3 OB match an SMC OB the indicator shows (same candle, same range)?
2. **Mitigation:** are the OBs the SMC indicator has deleted also gone from v3? Is anything v3 kept already mitigated there?
3. **FVGs:**
   - The SMC indicator's FVGs are usually on the chart's own timeframe, often with an auto threshold.
   - v3's are W and M only, at least 0.1 ATR wide, trimmed as they fill.
   - So expect fewer v3 gaps than on a daily chart. Compare with the indicator set to its HTF option (W) where it has one.
4. **Strong:** a strong zone should be a fresh OB or base where a BOS or CHoCH started. Does the SMC chart show a break there?
5. **Missing:** any zone the SMC indicator draws that v3 does not.

Differences go into a v4, written before any code, as with v2 and v3.
