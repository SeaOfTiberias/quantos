# Strategy Specification: NIFTY 1H Bullish SMC Order Block + Session POC Options Strategy (v3)

## 1. Strategy Overview & Market Hypothesis
* **Instrument & Signal Timeframe:** `NSE:NIFTY` (Nifty 50 Spot Index) evaluated on **1-Hour (`1H`)** bars, paired with a **Daily (`1D`)** higher-timeframe trend filter.
* **Execution Vehicle:** Long-only **NIFTY Call Options (`CE`)**, targeting **ITM-2 (`100` points below spot, $\Delta \approx 0.65\text{–}0.70$)** on **next-week expiry (`7–8 DTE`)** to capture overnight gap-up momentum while minimizing theta decay.
* **Core Edge:** Institutional order flow leaves behind unmitigated demand zones (**Bullish Order Blocks**) following a confirmed structural breakout (**Break of Structure / Change of Character**). When Nifty is in an established daily uptrend (`Close > Daily 40 EMA`) and holding above its developing **Session Point of Control (`POC`)**, pullbacks into the prior Bullish Order Block during prime mid-morning (`10:00` bar close) or late-session (`14:00` bar close) windows yield high-probability 1-to-2-day continuation moves.

---

## 2. Universe, Session & Data Requirements
* **Underlying Signal Feed:** `NSE:NIFTY` Spot `1H` OHLC bars (IST exchange session `09:15–15:30`) and `1D` OHLC bars.
* **Options Execution Feed:** Historical NSE `NIFTY` Options Chain (`CE` contracts, `50`-point strike intervals, `75` lot size).
* **Session Reset:** Intraday Session POC variables reset on the first `1H` bar of each new trading day (`09:15 IST`).

---

## 3. Indicator Definitions & State Variables

1. **Higher-Timeframe (HTF) Trend Filter (`1D` — Non-Repainting):**
   * Uses the **previous completed trading day's** close (`Daily_Close[1]`) and exponential moving averages (`Daily_EMA_9[1]`, `Daily_EMA_40[1]`) to avoid lookahead bias.
   * **Condition:** $\text{HTF\_Bullish} = (\text{Daily\_Close}[1] > \text{Daily\_EMA\_40}[1]) \land (\text{Daily\_EMA\_9}[1] > \text{Daily\_EMA\_40}[1])$.

2. **Developing Session Point of Control (`Session_POC`):**
   * Resets at the start of every trading day (`isNewSession`).
   * Because spot index feeds (`NSE:NIFTY`) carry zero volume, bar weight is computed via price-range proxy:
     $$\text{Eff\_Vol}_t = \begin{cases} \text{Volume}_t & \text{if } \text{Volume}_t > 0 \\ (\text{High}_t - \text{Low}_t) + \text{tick\_size} & \text{if } \text{Volume}_t = 0 \end{cases}$$
   * Cumulative typical price ($\text{HLC3}_t = \frac{\text{High}_t + \text{Low}_t + \text{Close}_t}{3}$) and cumulative effective volume are tracked intraday:
     $$\text{Session\_POC}_t = \frac{\sum_{i=\text{open}}^{t} (\text{HLC3}_i \times \text{Eff\_Vol}_i)}{\sum_{i=\text{open}}^{t} \text{Eff\_Vol}_i}$$

3. **Average True Range (`ATR`):**
   * Standard 14-period ATR ($\text{ATR}_{14}$) calculated on `1H` bars.

4. **Smart Money Concepts (SMC) Market Structure & Bullish Order Block (`OB`):**
   * **Swing Pivots (`swingLen = 5`):**
     * $\text{Last\_Swing\_High}$ updates to $\text{High}_{t-5}$ whenever bar $t-5$ is a confirmed 5-bar left/right pivot high.
     * $\text{Last\_Swing\_Low}$ updates to $\text{Low}_{t-5}$ whenever bar $t-5$ is a confirmed 5-bar left/right pivot low.
   * **Market Structure State (`Market_Trend` $\in \{1, -1, 0\}$):**
     * **Bullish BOS / CHoCH:** Triggered when $\text{Close}_t$ crosses above $\text{Last\_Swing\_High}$. Sets $\text{Market\_Trend} = 1$.
     * **Bearish Structure Shift:** Triggered when $\text{Close}_t$ crosses below $\text{Last\_Swing\_Low}$. Sets $\text{Market\_Trend} = -1$.
   * **Bullish Order Block Creation (on Bullish BOS / CHoCH bar $t$):**
     * Scan backward from $i = 1$ to $8$ (`swingLen + 3`) to locate the **most recent bearish candle** ($\text{Close}_{t-i} < \text{Open}_{t-i}$) prior to the breakout leg. *(If none exists in that window, default to $i = 1$).*
     * Set $\text{Bull\_OB\_Top} = \text{High}_{t-i}$, $\text{Bull\_OB\_Bot} = \text{Low}_{t-i}$, and $\text{Bull\_OB\_Active} = \text{True}$.
   * **Order Block Invalidation:**
     * If $\text{Bull\_OB\_Active} = \text{True}$ and $\text{Close}_t < \text{Bull\_OB\_Bot}$, set $\text{Bull\_OB\_Active} = \text{False}$.

---

## 4. Entry Rules & Option Strike Selection

A **Long Signal** is evaluated at the **close** of a `1H` bar $t$ (executing at the **open** of bar $t+1$) when **all 6 conditions** are met simultaneously:

1. **Flat Position:** No active open position ($\text{Position\_Size} = 0$).
2. **HTF Regime:** $\text{HTF\_Bullish} = \text{True}$.
3. **Prime 1H Signal Window:** Bar $t$ timestamp is either the **`10:00` bar** (`10:15–11:15` candle, filling at `11:15`) or the **`14:00` bar** (`14:15–15:15` candle, filling at `15:15`).
4. **Bullish Market Structure:** $\text{Market\_Trend} = 1$.
5. **Session Value Alignment:** $\text{Close}_t > \text{Session\_POC}_t$.
6. **Bullish Order Block Retest & Rejection:**
   $$\text{Bull\_OB\_Active} = \text{True} \quad \land \quad \text{Low}_t \le \text{Bull\_OB\_Top} \quad \land \quad \text{Close}_t \ge \text{Bull\_OB\_Bot} \quad \land \quad \text{Close}_t > \text{Open}_t$$

### Order Execution & Strike Selection (at Open of Bar $t+1$)
* **Consume Order Block:** Set $\text{Bull\_OB\_Active} = \text{False}$ immediately so the same zone is not traded twice.
* **Spot Reference Levels:**
  * $\text{Entry\_Spot} = \text{Open}_{t+1}$ (or $\text{Close}_t$ in close-fill mode).
  * $\text{Raw\_Risk} = \text{Entry\_Spot} - (\text{Bull\_OB\_Bot} - 0.3 \times \text{ATR}_{14})$.
  * $\text{Initial\_Risk} = \min\big(\max(\text{Raw\_Risk},\; 0.8 \times \text{ATR}_{14}),\; 1.8 \times \text{ATR}_{14}\big)$ *(clamped between $0.8\times$ and $1.8\times$ ATR)*.
  * $\text{Spot\_SL} = \text{Entry\_Spot} - \text{Initial\_Risk}$.
  * $\text{Spot\_Target} = \text{Entry\_Spot} + 2.0 \times \text{Initial\_Risk}$ ($1:2\text{ R:R}$).
* **Option Contract Selection:**
  * $\text{ATM\_Strike} = \text{round}(\text{Entry\_Spot} / 50) \times 50$.
  * **Recommended Strike:** $\text{Strike} = \text{ATM\_Strike} - 100$ (**`ITM-2` Call**, $\Delta \approx 0.65\text{–}0.70$; optionally test $\text{ATM\_Strike} - 50$ for `ITM-1` or $\text{ATM\_Strike}$ for `ATM`).
  * **Expiry Selection:** Select the **next weekly expiry** with **$\ge 6$ calendar days to expiry (`DTE`)** at entry so a 2-day hold avoids expiry-week gamma/theta acceleration.

---

## 5. Exit & Trade Management Rules

All stop-loss, trailing, and take-profit levels are governed by the **underlying `NSE:NIFTY` spot price** (eliminating option bid-ask spike stop-outs) and executed immediately on the active Call option contract:

1. **Step 1 — Breakeven Lock (`+1.0R` Trigger):**
   * Whenever intrabar $\text{High}_t - \text{Entry\_Spot} \ge 1.0 \times \text{Initial\_Risk}$:
     $$\text{Spot\_SL} = \max(\text{Spot\_SL},\; \text{Entry\_Spot} + 5.0)$$
2. **Step 2 — ATR Ratchet Trailing Stop (`+1.4R` Trigger):**
   * Whenever intrabar $\text{High}_t - \text{Entry\_Spot} \ge 1.4 \times \text{Initial\_Risk}$:
     $$\text{Spot\_SL} = \max\big(\text{Spot\_SL},\; \text{Close}_t - 1.4 \times \text{ATR}_{14}\big)$$
3. **Step 3 — Higher Order Block Structure Trail:**
   * If a **new** Bullish BOS/CHoCH forms while in a trade and $\text{Bull\_OB\_Bot} > \text{Spot\_SL}$:
     $$\text{Spot\_SL} = \text{Bull\_OB\_Bot} - 0.3 \times \text{ATR}_{14}$$
4. **Hard Exits (Evaluated Intrabar on `1H` High/Low):**
   * **Stop-Loss Exit:** If $\text{Low}_t \le \text{Spot\_SL}$, exit option at market immediately.
   * **Take-Profit Exit (`2.0R`):** If $\text{High}_t \ge \text{Spot\_Target}$, exit option at market immediately.
5. **Time-Stop Exit (Theta Protection):**
   * If $\text{Bars\_Held} \ge 14$ hourly bars ($\approx 2$ trading days) and neither `Spot_SL` nor `Spot_Target` has been hit, **close the Call option at market** at the close of bar 14.

---

## 6. Parameter Table for Backtest Engine

| Parameter | Default Value | Suggested Grid-Search Range (for Actual Options Data) |
| :--- | :--- | :--- |
| `swingLen` | `5` | `4, 5, 6` |
| `atrLen` | `14` | `14` (fixed) |
| `atrBufferMult` | `0.3` | `0.2, 0.3, 0.5` |
| `minRiskAtrMult` | `0.8` | `0.8` (fixed) |
| `maxRiskAtrMult` | `1.8` | `1.5, 1.8, 2.0` |
| `rrRatio` | `2.0` | `1.8, 2.0, 2.5` |
| `beTriggerR` | `1.0` | `0.8, 1.0, 1.2` |
| `trailTriggerR` | `1.4` | `1.2, 1.4, 1.6` |
| `trailAtrMult` | `1.4` | `1.2, 1.4, 1.8` |
| `maxHoldBars` | `14` | `10, 14, 18` |
| `strikeOffset` | `-100` (`ITM-2`) | `-100 (ITM-2), -50 (ITM-1), 0 (ATM)` |
| `minDTE` | `6` calendar days | `5, 7, 10` |

---

## 7. Implementation Notes for Backtesting With Real Historical Options Data
* **Slippage & Transaction Costs:** Model realistic NSE options friction—**₹40–₹50 flat brokerage** per round trip plus **0.0625% STT** (on sell side), exchange/SEBI fees, and **1–2 ticks (`₹0.10–₹0.25`)** bid-ask slippage on `ITM-2` strikes.
* **Liquidity Guard:** When selecting `ITM-2` (`-100 pts`) on next-week expiry, verify in your historical options data that `Volume > 0` and `Bid-Ask Spread < 1.5%` of option premium; if `ITM-2` is illiquid in earlier years (e.g., `2015–2018` before weekly Nifty options became deep), automatically fall back to **`ITM-1` (`-50 pts`)** or **`ATM` (`0 pts`)**.
* **Spot-to-Option Intrabar Mapping:** Because `Spot_SL` and `Spot_Target` are evaluated on `NSE:NIFTY` `1H` bars, match the exact timestamp of the `1H` exit bar (or use 1-minute/5-minute sub-bar spot timestamps inside that hour if available in your engine) to pull the exact historical option exit price.