---
title: 'EMT on NIFTY BANK 5-minute — phase 1 results (index points)'
ingested: 2026-10-26
origin: '/home/ubuntu/quantos/obsidian_vault/QuantOS/raw/_inbox/EMT_VWAP_RESULTS_BANKNIFTY.md'
checksum: dc5f7c2b8e59dde884566eb0b0a398ca807596f53372aff67c0d8e9e32d6381c
body_checksum: 3b43dadb2782abfeb6a0fd5a20f710269edff983fdeb88ffbe8ad6f68cdcffeb
tags:
  - source/strategies
quantos:
  layer: raw
  immutable: true
---

# EMT on NIFTY BANK 5-minute — phase 1 results (index points)

> [!info] Ingested source
> Filed 2026-10-26 from `/home/ubuntu/quantos/obsidian_vault/QuantOS/raw/_inbox/EMT_VWAP_RESULTS_BANKNIFTY.md`. Do not edit — wiki pages cite this
> file's contents, and `vault lint` re-hashes it to check.

Rules: docs/EMT_VWAP_METHODOLOGY.md. Data 2025-10-27 to 2026-10-26 (247 sessions, 18482 bars). IS 2025-10-27..2026-04-27, OOS 2026-04-28..2026-10-26. Costs: 5 pts per round trip unless stated.

**Verdict (primary `vwap_ema`): FAIL: OOS k=0.5, n=921, net -3.80 pts/trade, PF 0.88 (bar: n>=40, net>0, PF>=1.2)**

## Variant `vwap_ema` (primary)

| | n | win | gross pts/trade | net pts/trade | net total | PF | t | max DD | avg risk pts | target/stop/eod |
|---|---|---|---|---|---|---|---|---|---|---|
| IS k=0.5 | 925 | 39% | -4.66 | -9.66 | -8932 | 0.72 | -3.87 | 9435 | 58.7 | 357/547/21 |
| IS k=1 | 758 | 34% | -5.42 | -10.42 | -7895 | 0.72 | -3.50 | 8592 | 61.2 | 255/482/21 |
| IS k=1.5 | 559 | 30% | -6.08 | -11.08 | -6192 | 0.73 | -2.92 | 6995 | 63.0 | 159/379/21 |
| IS k=2 | 399 | 25% | -10.39 | -15.39 | -6140 | 0.67 | -3.17 | 6810 | 64.4 | 88/291/20 |
| OOS k=0.5 | 921 | 41% | +1.20 | -3.80 | -3502 | 0.88 | -1.49 | 4919 | 57.7 | 372/522/27 |
| OOS k=1 | 748 | 40% | +2.94 | -2.06 | -1543 | 0.94 | -0.67 | 3355 | 59.1 | 276/445/27 |
| OOS k=1.5 | 547 | 35% | +3.39 | -1.61 | -879 | 0.96 | -0.40 | 2915 | 61.4 | 171/349/27 |
| OOS k=2 | 399 | 29% | -1.77 | -6.77 | -2703 | 0.85 | -1.34 | 3977 | 61.0 | 92/281/26 |

Chosen on IS: k=0.5. OOS at other costs:

| | n | win | gross pts/trade | net pts/trade | net total | PF | t | max DD | avg risk pts | target/stop/eod |
|---|---|---|---|---|---|---|---|---|---|---|
| OOS k=0.5 cost 2.5 | 921 | 42% | +1.20 | -1.30 | -1200 | 0.96 | -0.51 | 3388 | 57.7 | 372/522/27 |
| OOS k=0.5 cost 10 | 921 | 39% | +1.20 | -8.80 | -8107 | 0.75 | -3.45 | 9055 | 57.7 | 372/522/27 |
| OOS k=0.5 longs | 490 | 38% | -3.79 | -8.79 | -4308 | 0.74 | -2.59 | 4674 | 57.9 | 179/293/18 |
| OOS k=0.5 shorts | 431 | 44% | +6.87 | +1.87 | +805 | 1.06 | +0.49 | 2004 | 57.4 | 193/229/9 |

## Variant `vwap` (comparison)

| | n | win | gross pts/trade | net pts/trade | net total | PF | t | max DD | avg risk pts | target/stop/eod |
|---|---|---|---|---|---|---|---|---|---|---|
| IS k=0.5 | 971 | 40% | -4.29 | -9.29 | -9017 | 0.73 | -3.82 | 9564 | 60.5 | 394/555/22 |
| IS k=1 | 774 | 36% | -5.05 | -10.05 | -7777 | 0.73 | -3.39 | 8467 | 62.8 | 270/482/22 |
| IS k=1.5 | 564 | 30% | -6.67 | -11.67 | -6584 | 0.73 | -3.07 | 7311 | 64.3 | 161/382/21 |
| IS k=2 | 402 | 26% | -11.02 | -16.02 | -6440 | 0.66 | -3.30 | 7110 | 65.7 | 90/292/20 |
| OOS k=0.5 | 962 | 42% | +1.34 | -3.66 | -3517 | 0.89 | -1.47 | 4923 | 58.4 | 399/536/27 |
| OOS k=1 | 767 | 40% | +3.44 | -1.56 | -1197 | 0.96 | -0.51 | 3121 | 59.8 | 288/452/27 |
| OOS k=1.5 | 557 | 36% | +4.36 | -0.64 | -358 | 0.98 | -0.16 | 2371 | 62.3 | 179/351/27 |
| OOS k=2 | 405 | 30% | -0.59 | -5.59 | -2265 | 0.87 | -1.11 | 3601 | 62.0 | 97/282/26 |

Chosen on IS: k=0.5. OOS at other costs:

| | n | win | gross pts/trade | net pts/trade | net total | PF | t | max DD | avg risk pts | target/stop/eod |
|---|---|---|---|---|---|---|---|---|---|---|
| OOS k=0.5 cost 2.5 | 962 | 43% | +1.34 | -1.16 | -1112 | 0.96 | -0.46 | 3352 | 58.4 | 399/536/27 |
| OOS k=0.5 cost 10 | 962 | 40% | +1.34 | -8.66 | -8327 | 0.75 | -3.48 | 9339 | 58.4 | 399/536/27 |
| OOS k=0.5 longs | 508 | 39% | -4.21 | -9.21 | -4680 | 0.73 | -2.78 | 5046 | 58.6 | 188/302/18 |
| OOS k=0.5 shorts | 454 | 46% | +7.56 | +2.56 | +1163 | 1.09 | +0.69 | 1702 | 58.1 | 211/234/9 |

## Variant `ema` (comparison)

| | n | win | gross pts/trade | net pts/trade | net total | PF | t | max DD | avg risk pts | target/stop/eod |
|---|---|---|---|---|---|---|---|---|---|---|
| IS k=0.5 | 1028 | 54% | -0.55 | -5.55 | -5701 | 0.74 | -3.59 | 6169 | 57.8 | 619/409/0 |
| IS k=1 | 535 | 53% | +0.63 | -4.37 | -2339 | 0.83 | -1.64 | 2960 | 68.0 | 299/236/0 |
| IS k=1.5 | 250 | 51% | -1.84 | -6.84 | -1710 | 0.81 | -1.40 | 3306 | 89.3 | 130/120/0 |
| IS k=2 | 112 | 48% | -2.16 | -7.16 | -802 | 0.83 | -0.82 | 1865 | 116.1 | 55/57/0 |
| OOS k=0.5 | 1062 | 53% | -1.00 | -6.00 | -6377 | 0.72 | -4.26 | 6918 | 53.3 | 634/428/0 |
| OOS k=1 | 575 | 52% | -0.52 | -5.52 | -3176 | 0.79 | -2.38 | 3735 | 62.0 | 321/254/0 |
| OOS k=1.5 | 260 | 51% | -0.06 | -5.06 | -1315 | 0.84 | -1.21 | 1878 | 73.1 | 140/120/0 |
| OOS k=2 | 141 | 48% | -1.88 | -6.88 | -970 | 0.81 | -1.08 | 1532 | 78.4 | 72/69/0 |

Chosen on IS: k=1. OOS at other costs:

| | n | win | gross pts/trade | net pts/trade | net total | PF | t | max DD | avg risk pts | target/stop/eod |
|---|---|---|---|---|---|---|---|---|---|---|
| OOS k=1 cost 2.5 | 575 | 53% | -0.52 | -3.02 | -1739 | 0.88 | -1.30 | 2372 | 62.0 | 321/254/0 |
| OOS k=1 cost 10 | 575 | 50% | -0.52 | -10.52 | -6051 | 0.63 | -4.53 | 6497 | 62.0 | 321/254/0 |
| OOS k=1 longs | 293 | 51% | -3.91 | -8.91 | -2609 | 0.68 | -2.71 | 2844 | 65.3 | 161/132/0 |
| OOS k=1 shorts | 282 | 53% | +2.99 | -2.01 | -567 | 0.92 | -0.61 | 1325 | 58.6 | 160/122/0 |
