---
tags:
  - strategy/momentum
  - trading/vcp
  - algo/feature-extraction
  - screening/trend-template
quantos:
  id: minervini_vcp
  label: Minervini
  timeframe: daily
---

# Mark Minervini's Volatility Contraction Pattern (VCP)

## 🔎 Core Mechanics: The Anatomy of a VCP Setup
The VCP is defined strictly by the **progressive reduction of price volatility and volume** over a period of weeks to months.

```
  Price High
     │       ╭╮             
     │      ╭╯╰╮    ╭╮      
     │     ╭╯  ╰╮  ╭╯╰╮  ╭╮ ───► Pivot Point (Entry)
     │    ╭╯    ╰╮╭╯  ╰╮╭╯╰╮
     │   ╭╯      ╰╯    ╰╯  ╰  ◄── Price Tightening (Supply Absorbed)
     │  ╭╯
     └─────────────────────────────────────────────── Time
     
  Volume
     │   █▄          
     │   ███▄        ▄      
     │   █████▄     ██▄    ▄  ──► Volume Dry-up (No Sellers Left)
     └───────────────────────────────────────────────
```

- **The Contractions (T):** A typical VCP displays between **2 to 6 contractions** (labeled as 2T, 3T, 4T, etc.).
- **The Mathematical Proportions:** Each successive pullback must decrease in magnitude—typically reducing by roughly half of the previous correction. For instance, a textbook 3T setup compresses from **20% → 10% → 5%**.
- **Volume Behaviour:** Volume must dry up significantly on the downside of each contraction, demonstrating that retail sellers are exhausted. 

---

## 📋 The 7-Point Selection Checklist (SEPA Trend Template)

| Requirement Category | Metric / Condition | Mathematical Formula |
| :--- | :--- | :--- |
| **Trend Stage** | Confirmed Stage 2 Uptrend | `Close > SMA(50) > SMA(150) > SMA(200)` |
| **MA Trajectory** | 200 SMA Sloping Upwards | `SMA(200)[t] > SMA(200)[t-20]` (Slope > 0 for 1-3 months) |
| **Proximity to Highs** | Near Blue Sky Territory | `Close >= Highest(High, 252) * 0.75` (Within 25% of 52-W High) |
| **Distance from Lows** | Cleared out Bottoming Formations | `Close >= Lowest(Low, 252) * 1.25` (At least 25% off 52-W Low) |
| **Relative Strength** | Structural Index Outperformance | `RS_Rating >= 70` (Ideally 90+) |
| **The Pivot Point** | Entry Activation Point | Trigger on a breakout crossing the tightest contraction's ceiling. |

---

## ⚙️ Machine-checkable rules

The block below is what QuantOS actually evaluates. It is the table above,
transcribed into the rule DSL — see `docs/OBSIDIAN_VAULT_INTEGRATION.md` for the
grammar. Every rule must hold for this note to return `PASS`; they are
conjunctive, exactly as the SEPA checklist intends.

```quantos-rules
# Trend stage — the Stage 2 stack, read as one chained comparison
close > sma(50) > sma(150) > sma(200)

# MA trajectory — 200-day higher than it was ~1 month (20 sessions) ago
sma(200) > sma(200)[20]

# Proximity to highs — within 25% of the 52-week high
close >= high(252) * 0.75

# Distance from lows — at least 25% above the 52-week low.
# 1.25, not 2.00. Trend Template criterion #7 is "at least 25 percent above
# its 52-week low"; the 100% figure comes from his parenthetical that the
# best selections are often 100-300% off their lows before they advance.
# That is an observation about winners, not the filter. See the caveat below.
close >= low(252) * 1.25

# Relative strength — requires a cross-sectional rating to be supplied.
# Without one this rule is UNEVALUABLE and the audit returns
# INSUFFICIENT_DATA rather than passing. See the caveat below.
rs_rating >= 70

# Volume Dry-Up Index — the tightest gate in the whole template. Most names
# that clear everything above will still fail here, which is the point: it
# fires only in the pivot's quiet zone.
volume_sma(5) / volume_sma(50) < 0.40
```

### Caveats that matter when reading a verdict

- **`rs_rating` is injected, not computed.** It cannot be derived from one
  symbol's own bars. The momentum shortlist supplies a percentile of *its*
  52-week-high ranking, which is **not** IBD's RS Rating — different measure,
  different population. The `>= 70` threshold here was written for IBD's
  number, so treat a pass on this line as directional, not equivalent.
- **The contraction count is not encoded.** "2 to 6 contractions, each roughly
  half the last" is the actual heart of a VCP and this rule block does not
  test it — the DSL has no pattern-matching over swing structure. What is
  encoded is the trend template plus the volume dry-up, i.e. the *context* a
  VCP forms in. A `PASS` here means "this name is in the right condition for a
  VCP", never "a VCP is present".
- **Daily bars.** `sma(150)` stands in for the 30-week average. See
  [[Stan_Weinstein_Stage_Analysis]] for the same substitution and why.
- **The distance-from-lows threshold was 2.00 until 2026-08-14.** That is what
  the first version of this note transcribed, and it silently voided the whole
  template: it demands the stock has already doubled off its 52-week low, so
  it rejected names in exactly the condition the rest of the checklist selects
  for. RADICO — first by momentum in the Alpha 50, +86% off its low, passing
  every other price rule — failed on this line alone. Corrected to 1.25, the
  published criterion. Kept in writing because a threshold this consequential
  should not be able to change back without someone reading why.

---

## 🗂 External Engineering References
- **Open-Source Python Frameworks:** Reference base configurations via the [icedevil2001/mark_minervini_stock_screener](https://github.com/icedevil2001/mark_minervini_stock_screener) or the complete algorithmic evaluation setups on [carlamHS/vcp_screener](https://github.com/carlamHS/vcp_screener).
- **Live Scanning Engines:** Active market screeners utilizing these parameters are trackable on the [Screener India Stage 2 VCP Setup Hub](https://www.screener.in/screens/2808965/stage-2-vcp-setup-minervini-style/).
