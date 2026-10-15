# QuantOS Strategy Specification: Single-Day Stock Surge Bear Call Spread (`S19_SURGE_BEAR_CALL`)

**Document Control**
- **Strategy ID:** `S19_SURGE_BEAR_CALL`
- **Asset Class:** Indian Equities (NSE F&O Stock Segment)
- **Strategy Class:** Volatility Mean-Reversion / IV Crush / Defined-Risk Credit Spread
- **Status:** Candidate Specification (Drafted for Backtesting & Stage 1/2 Screening)
- **Target Platform:** QuantOS Engine (Fyers API / Python Execution)

---

## 1. Executive Summary & Core Thesis

### 1.1 Strategy Motivation
When an F&O stock surges **+5% or more in a single trading session**, Out-Of-The-Money (OTM) call option premiums experience explosive expansion due to two simultaneous drivers:
1. **Directional Delta Surge:** Rapid upward spot price movement shifts OTM strikes closer to At-The-Money (ATM).
2. **Implied Volatility (IV) Expansion:** Panic buying of call options by momentum traders drives IV higher, inflating option Vega.

### 1.2 The Edge
While retail traders often buy high-IV calls during late-stage surges, institutional market makers sell overextended volatility. Once the initial surge exhausts itself, option premiums suffer a sharp **IV Crush** alongside natural **Theta time decay**, even if the underlying stock price remains sideways at elevated levels.

### 1.3 Why the Raw Strategy (Naked Calls) Fails
Selling raw, unhedged naked call options on a +5% stock surge is **structurally flawed** for a retail trader:
- **Post-Announcement Drift:** +5% moves driven by fundamental news (earnings, M&A) exhibit strong multi-day momentum, exposing naked call sellers to severe **negative Gamma** (accelerating losses).
- **Uncapped Tail Risk:** Naked short calls expose the account to unlimited loss potential during multi-day gap-ups.
- **Single-Lot Margin Cliff:** A single outlier move can cause margin calls, broker auto-liquidation, or account lockout.
- **SEBI Physical Delivery & F&O Ban Risk:** In-The-Money stock options in India are physically settled at expiry. Multi-day surges often land stocks in the **MWPL F&O Ban Period**, blocking position adjustments.

### 1.4 The QuantOS Solution
We restructure the concept into a **Risk-Defined Bear Call Spread** (`Sell OTM Call + Buy Higher OTM Call`), filtered by **Volume Profile VAH resistance**, **IV Rank / VRP spreads**, and sized using **Quarter-Kelly NAV rules**.

---

## 2. Strategy Architecture & Flowchart

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      STAGE 1: DAILY UNIVERSE SCANNER                    │
│  - Scan NSE F&O Stock Segment at 03:15 PM or Daily Close.               │
│  - Filter: Single-Day Spot Gain >= +5.0%.                               │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     v
┌─────────────────────────────────────────────────────────────────────────┐
│                      STAGE 2: FILTER & REGIME GATE                      │
│  1. Volume Profile Gate : Price at/above Yesterday's VAH / Resistance.   │
│  2. Volatility Gate    : IV Rank >= 75th percentile OR IV/HV >= 1.25.   │
│  3. Regulatory Gate    : Not in MWPL F&O Ban; DTE >= 5 Days.            │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     v (All Gates PASS)
┌─────────────────────────────────────────────────────────────────────────┐
│                 STAGE 3: LEG SELECTION & SIZING ENGINE                  │
│  - Short Leg : Sell OTM Call at ~20-30 Delta (or above resistance).     │
│  - Long Leg  : Buy OTM Call at ~10-15 Delta (Spread Width: 1-2 strikes).│
│  - Position Sizing: Quarter-Kelly NAV Model (Max Loss <= 8%-16% Equity).│
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     v
┌─────────────────────────────────────────────────────────────────────────┐
│                    STAGE 4: AUTOMATED RISK & EXIT MANAGEMENT             │
│  - Profit Target : Take Profit at 50% - 70% of Max Credit Received.    │
│  - Stop Loss     : Exit if Spread Loss >= 1.5x Credit OR Spot Close     │
│                    above Long Call Strike on 15m Chart.                │
│  - Time Exit     : Flatten 2 Days prior to Expiry Week (Delivery Risk). │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Screening & Filtering Criteria

To eliminate low-probability traps and false mean-reversions, candidates must pass all four criteria:

| Filter Layer | Metric / Rule | Rationale |
| :--- | :--- | :--- |
| **Universe** | Liquid NSE F&O Stocks | Ensures adequate option market liquidity and quotes. |
| **Price Surge Trigger** | \\(\Delta \text{Price}_{1\text{D}} \ge +5.0\%\\) | Identifies single-day overextension and premium spikes. |
| **Structural Resistance Gate** | Spot Price \\(\ge\\) Yesterday's **Volume Profile VAH** or Major Resistance Zone | Avoids fading fresh, unconstrained 52-week breakout momentum; targets overextended moves into historical overhead supply. |
| **Volatility Quality Gate** | **IV Rank \\(\ge 75\text{th Percentile}\\)** OR **VRP Ratio (\\(\text{IV} / \text{HV}\\)) \\(\ge 1.25\\)** | Confirms option premiums are genuinely overpriced relative to historical price movement. |
| **Regulatory & Delivery Gate** | Stock **NOT** in MWPL F&O Ban AND **\\(\text{DTE} \ge 5\text{ Days}\\)** | Avoids physical delivery assignment risk and liquidity lockouts in F&O ban securities. |

---

## 4. Leg Selection & Execution Protocol

When a stock passes all screening gates, the QuantOS execution engine constructs a **Bear Call Spread**:

1. **Short Leg (Income Generator):**
   - **Strike Selection:** Out-Of-The-Money (OTM) Call strike corresponding to **20 to 30 Delta** (or the nearest strike immediately above the day's high / major technical resistance level).
   - **Action:** Sell 1 Lot.

2. **Long Leg (Tail-Risk Insurance):**
   - **Strike Selection:** Higher OTM Call strike corresponding to **10 to 15 Delta** (typically 1 to 2 strike intervals higher than the Short Leg).
   - **Action:** Buy 1 Lot.

3. **Spread Mechanics:**
   - **Net Position:** Credit Spread (Net Premium Collected).
   - **Max Profit:** \\(\text{Net Credit Received}\\) (achieved if stock closes below Short Call strike at expiry).
   - **Max Loss:** \\((\text{Spread Width} - \text{Net Credit}) \times \text{Lot Size}\\) (strictly capped).

---

## 5. Position Sizing & Account Risk Controls

### 5.1 Quarter-Kelly NAV Sizing Model
To prevent early loss streaks from creating margin lockouts or account wipeouts (as identified in the Stage 2 ORB audit), allocation is dynamically governed by a **Quarter-Kelly (0.25k)** NAV framework:

\\[\text{Lots} = \left\lfloor \frac{\text{Current NAV} \times \text{Kelly Fraction (0.25)}}{\text{Max Loss Per Spread Contract}} \right\rfloor\\]

- **Equity Allocation Target:** 8% to 16% of total account equity per trade.
- **Account Capital Floor:** Minimum required account equity = **₹1,00,000** to survive worst-case historical drawdown clusters.

### 5.2 Hard Portfolio Risk Controls
- **Daily Portfolio Kill-Switch:** If daily MTM losses reach **-5% of starting day equity**, the system writes `~/.quantos/halt`, cancels open pending orders, and blocks new entries.
- **Server-Side Stop Loss:** Exit orders are placed as server-side `SL-M` orders directly with the broker (Fyers/Zerodha API) to ensure instant execution without software polling delays.

---

## 6. Exit Parameters & Trade Lifecycle

Positions are monitored continuously and exited upon reaching any of the following four conditions:

1. **Profit Target (IV Crush / Theta Harvesting):**
   - **Condition:** Exit when spread value drops to **30% - 50% of original entry value** (harvesting 50% - 70% of maximum credit).
2. **Stop-Loss Protection (Gamma Risk Management):**
   - **Condition:** Exit if spread loss reaches **1.5x Net Credit Received**, OR if the underlying stock spot price closes above the **Long Call Strike** on a 15-minute chart.
3. **Time Decay / Expiry Gate:**
   - **Condition:** Flatten all open stock option spreads **2 trading days prior to expiry week** to avoid SEBI physical delivery margin spikes and illiquidity in expiring stock options.
4. **F&O Ban Preemption:**
   - **Condition:** Flatten position immediately if the underlying stock MWPL crosses 85% to avoid getting locked in a non-tradable F&O ban state.

---

## 7. Stage 1 & Stage 2 Validation Requirements

Before live deployment, `S19_SURGE_BEAR_CALL` must pass the mandatory QuantOS two-stage pipeline:

- **Stage 1 (Cheap Screening Pass):** Pooled trade logs over 3+ years must achieve **Profit Factor > 1.0** and **Sharpe Ratio > 0.5**.
- **Stage 2 (Real-NAV Equity Curve Stress Test):** Compounding equity curve simulation must verify:
  - No single-lot margin lockout events across capital tiers (₹100k, ₹250k, ₹500k).
  - Maximum Drawdown \\(\le 20\%\\).
  - Real-NAV Sharpe Ratio \\(\ge 1.0\\).
