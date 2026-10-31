# Techno-Funda momentum (without Piotroski): pre-registration (2026-11-01)

Written before any return is computed. Candidate: an Upasani-style screen of growing, high-margin small and mid caps trading near their all-time high, held with momentum exits. The Piotroski filter is **left out**, because real balance-sheet data only starts in Nov 2022 (see `docs/TECHNO_FUNDA_DATA_AUDIT.md`). This is therefore **not** the full Upasani screen, and results are reported under this name.

What has been seen so far: price-filter counts only (`docs/TECHNO_FUNDA_SIGNAL_COUNT.md`, commit c863880). No returns, P&L or holding outcomes have been computed for any version of this rule.

**Data rule (the user's instruction):** every input is real, point-in-time data. Nothing is imputed, proxied or guessed. If an input is missing for a stock on a day, that stock is not eligible that day. If a data gate below fails, the run stops and the failure is reported. It is not worked around.

## Universe, each trading day t

A stock is eligible on day t only if all of these hold:

1. **NSE, EQ series.** ETFs are excluded (symbol ends in BEES or contains ETF).
2. **Not a financial-format filer.** Its latest usable results filing has `bank` = N and `indAs` = "Ind-AS New". Banks (B), NBFCs (F / "NBFC-IND") and non-Ind-AS filers (banks, insurers) are excluded, because OPM and the margin figures are not defined for their statements. Brokers, exchanges and AMCs that file the standard Ind-AS format stay in.
3. **Market cap above ₹100 Cr and below ₹20,000 Cr** on day t's close.
4. **Liquidity:** the 50-day mean daily traded value is above ₹50 lakh.

## Data sources and how each input is built

**Prices.** NSE daily equity bhavcopies, 2010-01-01 to 2026-10-23, EQ series.
- **Splits and bonuses:** back-adjusted with NSE's corporate-actions list for 2010–2026, using the same factor rules as `scripts/backtest_darvas_atr_stop_oos.py` (bonus a:b → b/(a+b), face-value split X→Y → Y/X).
- **Overnight moves of −35% or worse that NSE's list does not explain:** adjusted **only if** the company's own filings confirm it. That means the face value or share count changes across that date by the same ratio, within 4%. Otherwise the stock's history before that date is dropped, and its record restarts at the gap. No fraction is guessed.
- **Symbol changes:** chained with NSE's symbol-change file. ISIN is used as a cross-check.

**All-time high (ATH).** The running maximum of the adjusted daily high.
- For a stock whose first 2010+ bar is on or after its listing, this is the true ATH.
- For a stock that traded before 2010, its raw (unadjusted) 2000–2009 high from the bhavcopy is an upper bound on its adjusted pre-2010 high, because splits and bonuses only scale old prices down. If that bound is at or below the adjusted 2010+ high so far, the ATH is known. Otherwise the stock's ATH is **unknown** and it is not eligible until its post-2010 high exceeds the bound.

**Fundamentals.** NSE results XBRL, filings broadcast 2018-04-01 to 2026-10-23.
- **Consolidated or standalone:** consolidated where filed, otherwise standalone. A comparison is only made between filings of the same type. If the types don't match, the stock is ineligible.
- **No look-ahead:** a filing is usable on day t only if it was broadcast on a calendar day **before** t. A revised filing replaces the original only from its own broadcast date.
- **Quarterly figures** use the filing's own-quarter context (OneD).

**Definitions:**
- **Profit growth** = (PAT_q − PAT_q−4) / PAT_q−4, using the latest usable quarter. It needs both quarters' PAT to be **positive**, since growth from a loss is undefined. Pass: **> 15%**.
- **OPM (TTM)** = Σ(revenue − (total expenses − D&A − finance costs)) / Σ revenue, over the last 4 consecutive usable quarters. Pass: **> 15%**.
- **Market cap** = shares × close_t.
  - **Shares** = paid-up equity capital / face value, from the latest usable filing.
  - Splits and bonuses with an ex-date between that filing's period end and t are applied to the share count. These come from NSE's list.

## Signal (at the close of day t; uses only data up to t)

The stock is eligible, and:
- **T1:** close > 0.85 × ATH
- **T2:** 50 < RSI14 (Wilder) < 65
- **T3:** close > previous close
- **T4:** volume > the 5-day mean volume, including day t
- **F1:** profit growth > 15%
- **F2:** OPM (TTM) > 15%

## Portfolio rules

- **Capital and slots:** start with ₹10,00,000, with at most **15 positions**.
  - Each new position is sized at NAV / 15 at entry (6.7%, inside the spec's 7–10% cap) and bought in whole shares.
  - Money not invested sits in cash earning **0%**, because no historical cash-yield series is on hand.
- **Entries:** signals at close t are bought at the **open of t+1**.
  - If there are more signals than free slots, take the highest close / ATH first, then alphabetical.
  - A stock already held is not bought again.
  - If the stock has no bar on t+1, the entry is skipped.
- **Exits:** checked at close t, sold at the open of t+1, on the first of:
  - close < EMA20;
  - close ≤ 0.93 × entry fill price (the 7% hard stop, on the close);
  - RSI14 < 45;
  - close < 0.75 × ATH.
- **Missing bars:** if the stock has no bar on t+1, the exit happens at its next open.
  - If the stock is delisted while held, the exit is at its last close.
  - Exited stocks may re-enter on a later signal.
- **Rotation:** slots freed by exits at t+1 can be filled by entries at the same t+1 open.
- **Returns are price returns,** for both the strategy and the benchmark. Dividends are ignored on both sides.

## Costs (each leg)

- **Spec cost:** 0.1% of turnover.
- **Statutory charges:** the delivery stack from `core/risk/costs.py`: STT 0.1% on both legs, stamp duty 0.015% on the buy, exchange, SEBI and GST at the rates there.
- **Slippage:** 10 bps.

## Benchmark

An **equal-weight index of the same eligible universe** (rules 1–4 above, no signal filters). It is rebalanced daily, as the plain average of the eligible stocks' close-to-close returns, and has **no costs**. A small/mid-cap strategy is compared against a small/mid-cap baseline, not Nifty 500.

## Periods

- **Start: 2019-07-01.** This is the first date when profit growth and TTM OPM can be built from filings back to FY2018.
- **Development:** 2019-07-01 to 2024-10-22. It is reported in full, but no rule is tuned on it. Every rule above is frozen now.
- **Held-out test:** 2024-10-23 to 2026-10-23, the final 2 years.

## Data gates (checked and reported before the backtest runs)

- **D1. Price coverage:** bhavcopies for every NSE trading day from 2010-01-01 to 2026-10-23, and raw bhavcopies for 2000–2009 (ATH bounds). Any missing day is listed. More than 5 missing days in 2019–2026 is a stop.
- **D2. Corporate actions:** NSE's list for 2010–2026 is fetched. The number of unexplained −35% gaps, and how each was resolved (confirmed from filings, or history dropped), is reported.
- **D3. Filing parse checks**, using each filing's own figures:
  - revenue + other income − total expenses is within 1% of reported profit before exceptional items and tax;
  - the quarter figures (OneD) for Q1–Q4 sum to the full-year figure (FourD) in the Q4 filing.
  - Fewer than 95% of the checked filings passing is a stop.
- **D4. Coverage:** the share of non-financial, in-band, liquid stock-days that have computable F1 and F2 inputs, by year. Below 70% in any year from 2019 on is a stop.
- **D5. Financial classification:** the `bank` and `indAs` fields are present in filings from every year 2018–2026. If they are absent in some years, it is a stop, and the user decides what to do. No substitute classification is used.

## Pass criteria (Base costs, held-out test period; all must hold)

- **P1. Annualised Sharpe > 0.80.** Daily NAV returns, risk-free rate 0, ×√252.
- **P2. Max drawdown < 20%,** on daily closing NAV.
- **P3. CAGR above the equal-weight universe benchmark** over the same dates.

PASS means paper trading forward. **No capital without the user's explicit go-ahead.**

One further check, from the Darvas lesson: **P4. a 90% CI of daily excess return over the benchmark, by week-block bootstrap (10,000 draws, seed 20261101), has its lower end above 0.** If P1–P3 hold but P4 does not, the verdict is "PASS, not capital-ready".

FAIL is reported as FAIL. None of the thresholds, filters, exits, slot count or ranking is re-tuned in this round.

## Reported but not part of pass/fail

- **Development-period results**, plus the full-period and per-year figures.
- **Trade statistics:** CAGR, Sharpe, Sortino, max drawdown, win rate, average win / average loss, number of trades, average hold, exposure %, total costs paid.
- **Context indexes:** Nifty 500 and Nifty Smallcap 250 over the same dates, where real index data can be fetched.
- **The layers without fundamentals:** price filters only, and price + F1 only. Each is run under the same rules, to show what each layer adds.

## Amendment 1 (2026-11-01, approved by the user before any return was computed)

**What changed at NSE:** NSE's results feed (`corporates-financial-results`) is nearly empty from April 2025. From then on, results are filed as "Integrated Filing - Financials" (`/api/integrated-filing-results`). Those records carry no `bank` / `indAs` fields, so gate D5 as written would stop.

**The amended rule:** for integrated filings, the financial-format classification is read from the XBRL file name. That name is the format the company filed under, the same fact the old fields recorded.

- `INTEGRATED_FILING_INDAS_*`: the standard format, eligible.
- `INTEGRATED_FILING_NBFC_INDAS_*`, `_NONINDAS_*`, `_GI_*`, `_LI_*` (NBFC, non-Ind-AS, general and life insurers): excluded, as rule 2 excludes them in the old feed.

Old-feed filings (to March 2025) still use `bank` / `indAs`. A stock's eligibility follows its latest usable filing, whichever feed it came from.

D5 now checks that every filing from 2018 to 2026 has a classification: the fields for the old feed, the file-name prefix for the integrated feed. Any filing with neither is reported, and that stock is ineligible while it is the latest filing.

Nothing else in the pre-registration changes.

## Piotroski (forward only)

From the FY2025 annual results (filed April–May 2025), a standard F-score can be built from real filings. It will be computed and logged alongside this rule for the stocks that qualify. Its own pre-registration comes when it has enough history. It has no part in this verdict.
