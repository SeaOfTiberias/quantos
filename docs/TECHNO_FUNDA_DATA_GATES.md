# Techno-Funda momentum: data gates

Run 2026-11-03 by `scripts/techno_funda_gates.py`. No returns computed. Filings loaded: 112805; symbols with 2000-2009 highs: 2025.

**Overall: STOP -- the backtest does not run**

**D1 price coverage: PASS**

- Calendar days (2015-01-01 .. 2026-08-18) with no bhavcopy: 1; in 2019+: 0 []
- Weekdays after the calendar's end (2026-08-18 .. 2026-10-23) with no file (NSE returned 404 = no session, but not verified against a calendar): ['2026-09-14', '2026-10-02', '2026-10-20']
- Files per year (no calendar before 2015; ~245-250 is a full year): 2000: 250, 2001: 248, 2002: 251, 2003: 251, 2004: 252, 2005: 249, 2006: 247, 2007: 249, 2008: 246, 2009: 242, 2010: 251, 2011: 247, 2012: 247, 2013: 248, 2014: 243, 2015: 247, 2016: 247, 2017: 248, 2018: 246, 2019: 245, 2020: 252, 2021: 248, 2022: 248, 2023: 246, 2024: 249, 2025: 249, 2026: 200

**D2 corporate actions: reported**

- Unexplained overnight moves of -35% or worse: 739; confirmed by the company's share count (adjusted): 5; record restarted: 734

| year | gaps | confirmed | restarted |
|---|---|---|---|
| 2010 | 10 | 0 | 10 |
| 2011 | 8 | 0 | 8 |
| 2012 | 6 | 0 | 6 |
| 2013 | 17 | 0 | 17 |
| 2014 | 16 | 0 | 16 |
| 2015 | 53 | 0 | 53 |
| 2016 | 125 | 0 | 125 |
| 2017 | 43 | 0 | 43 |
| 2018 | 33 | 0 | 33 |
| 2019 | 182 | 0 | 182 |
| 2020 | 73 | 0 | 73 |
| 2021 | 15 | 0 | 15 |
| 2022 | 15 | 0 | 15 |
| 2023 | 21 | 1 | 20 |
| 2024 | 27 | 0 | 27 |
| 2025 | 23 | 0 | 23 |
| 2026 | 72 | 4 | 68 |

**D3 filing parse checks: PASS** (99.0% of 59904 checked filings pass)

- (a) arithmetic: 59887 pass, 5 fail, 24 not checkable (an input missing)
- (b) Q4 quarters sum to full year: 11084 pass, 587 fail, 3858 Q4 filings not checkable (a quarter missing)
- Non-financial filings with no parsed figures (XBRL not downloaded, 404 or unparseable): 43865, of which parse errors: 1

**D4 coverage: STOP**

| year | in-band non-financial liquid stock-days | with growth + OPM inputs | liquid EQ stock-days with no filing yet | ... non-financial but no market cap |
|---|---|---|---|---|
| 2019 | 58762 | 43.8% | 3.1% | 12.7% |
| 2020 | 154420 | 57.3% | 3.7% | 2.4% |
| 2021 | 204138 | 88.0% | 4.0% | 1.2% |
| 2022 | 224519 | 79.0% | 4.1% | 2.2% |
| 2023 | 234395 | 72.4% | 3.9% | 1.0% |
| 2024 | 262795 | 86.4% | 4.0% | 1.4% |
| 2025 | 259245 | 88.4% | 5.3% | 1.5% |
| 2026 | 222674 | 88.1% | 8.0% | 1.1% |

**D5 classification: PASS**

| year | feed | filings | unclassified |
|---|---|---|---|
| 2018 | old | 7770 | 0 (0.00%) |
| 2019 | old | 10176 | 0 (0.00%) |
| 2020 | old | 11374 | 0 (0.00%) |
| 2021 | old | 11665 | 0 (0.00%) |
| 2022 | old | 11830 | 0 (0.00%) |
| 2023 | old | 13165 | 0 (0.00%) |
| 2024 | old | 14328 | 0 (0.00%) |
| 2025 | integrated | 12589 | 0 (0.00%) |
| 2025 | old | 3960 | 0 (0.00%) |
| 2026 | integrated | 15920 | 5 (0.03%) |
| 2026 | old | 28 | 0 (0.00%) |
