# Candidate 18b filters — edge in index points?

Method and pre-registered rule: `scripts/test_orb_18b_filters_index_points.py` docstring, committed before this run. V0 exit rules; points are measured in the trade's direction; no option pricing.

| Index | Filter | Filtered N | Filtered pts/trade | Other N | Other pts/trade | Difference | p (one-sided) | Verdict |
|---|---|---|---|---|---|---|---|---|
| NIFTY | Monday/Friday | 417 | +2.07 | 639 | +1.55 | +0.52 | 0.463 | PRICING ARTIFACT |
| BANKNIFTY | gap > 0.3% | 618 | +4.73 | 605 | -2.05 | +6.78 | 0.320 | PRICING ARTIFACT |

Filtered subset alone (descriptive):

| Index | pts/trade | t | Net Rs/trade after futures costs | t (net) |
|---|---|---|---|---|
| NIFTY | +2.07 | 0.47 | -418 | -1.45 |
| BANKNIFTY | +4.73 | 0.43 | -322 | -0.97 |
