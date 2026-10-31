# Techno-Funda momentum: data audit (2026-11-01)

The user's instruction for this candidate: use only data we actually have, with no made-up or substitute inputs. This audit checks every input the spec needs against live NSE sources before the pre-registration is written. Probes were small random samples of real filings and archive files. The sample counts are given so the evidence can be judged.

## What exists

| Input | Real source | Usable from | Evidence |
|---|---|---|---|
| Daily OHLCV, every NSE EQ stock incl. delisted | NSE equity bhavcopy archive | 2000 | Files fetched for 2000-01-03, 2005-01-03, 2010-01-04, 2015-01-05; 2016-01..2026-10 already cached (2,668 days) |
| Split/bonus adjustment | NSE corporate-actions API | 2010 | Q1 2010: 158 actions (16 bonus/split); Q1 2015: 176 (22). Q1 2005: 12 rows, clearly incomplete |
| Quarterly P&L: net profit, revenue, total expenses, D&A, finance costs, materials, purchases, inventory change | NSE results XBRL (every listed company) | FY2018 filings (May 2018) | 70/70 sampled filings across 2018-2022 carry all of these |
| Share count (paid-up capital / face value) → market cap | Same filings | May 2018 | 70/70 sampled filings |
| Operating cash flow | Same filings, half-yearly and annual | May 2021 | 0/23 before 2021; 12/12 in May 2021; 9/10 Nov 2021 |
| Balance sheet: total assets, current assets/liabilities, non-current borrowings, equity | Same filings, half-yearly and annual | Half-year to Sep 2022 (filed Nov 2022) | 0/58 before Nov 2022; 9/10 Nov 2022; 10/10 May 2023; 377/377 May 2024 annual filings (337 with current assets, the rest financials) |

Every filing carries exactly one balance-sheet date (377/377 May-2024 annual filings), with no prior-year column.

## What this means for each filter

- **OPM, YoY profit growth, market cap:** real from 2018. Growth needs the same quarter a year earlier, so from 2019.
- **All-time high:** adjusted prices are real from 2010. For stocks listed before 2010, the raw pre-2010 high is an upper bound on the adjusted pre-2010 high, because splits and bonuses only scale old prices down. If that raw high is below the 2010+ adjusted high, the true ATH is known. If not, the stock's ATH is marked unknown and it is not eligible. No guessed adjustment is applied.
- **Piotroski F-score (standard definition):** ROA and asset turnover use beginning-of-year assets, and ΔROA needs last year's ROA. That needs the March 2022 balance sheet, which is not in any XBRL filing. The first fully standard score is the FY2025 annual result, filed April–May 2025. A Piotroski test therefore covers about May 2025 to Oct 2026, roughly 17 months.
- **Banks, NBFCs, insurers:** gross margin and current ratio are not defined in their statements, and OPM has no standard meaning for them. So Piotroski and OPM cannot be computed from real figures for them.

## Not available (no substitutes used)

- Balance sheets before Sep 2022, and so Piotroski before May 2025. Paid point-in-time sources (CMIE Prowess, Ace Equity) or the MCA annual-filing XBRL would be needed. None is on hand.
- Split/bonus history before 2010.
- Screener.in / Trendlyne / StockEdge Piotroski: no public API, and their histories are restated (not point-in-time).
