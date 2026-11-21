# Research data: what each result rests on, and where it lives

Started 2026-11-19 (user: "shouldn't all of these have been on the VM?"). Research runs on the PC because the VM is too small: 956 MB of RAM and 2 cores, against a 1.7 GB techno-funda panel and a 6,646-file bhavcopy archive. Until now their outputs stayed only on the PC, with no record of which file a result came from.

**The rule from now on:**
- Any file a pre-registration, a frozen rule or a committed result reads is copied to the VM under `~/.quantos/research/` and listed here with its sha256, when the result is committed.
- A results doc names the hash it used.
- If a file's hash ever differs from this list, the results that depend on it are suspect until re-checked.

Check a copy: `sha256sum ~/.quantos/research/<file>` (VM) or `sha256sum ~/.quantos/<file>` (PC).

## Decision-critical files (on the PC in `~/.quantos/`, copied to the VM in `~/.quantos/research/`)

| File | sha256 | Size | Made by | Used by |
|---|---|---|---|---|
| `darvas_atr_stop_oos_results.json` | `e6a7126302d43166bfd39372283a4ffe48614523b4854d58e96e7cde9b983782` | 1.7 MB | `scripts/backtest_darvas_atr_stop_oos.py`, 2026-10-05 (PC) | `docs/DARVAS_ATR_STOP_OOS_RESULTS.md` (the Bucket B PASS); `docs/DARVAS_GO_NO_GO_2026-11.md` + `DARVAS_GO_NO_GO_BANDS.json` (E2 thresholds); E3 discovery (re-entry, structural stop) |
| `darvas_atr_stop_results.json` | `f0d820ef5548a45e735b5a4c80666558d7f3ccbbce67e65d3cb4381cb60823b5` | 0.8 MB | `scripts/backtest_darvas_atr_stop.py`, 2026-09-24 (PC) | `docs/DARVAS_ATR_STOP_BACKTEST_RESULTS.md`; E3 confirmation 2024-26 |
| `research_e3_outputs_20261119.tgz` | `2533b404a729e5c93afc6505e61e1d3286f58a471d180ec5b3eae80e59dc6e03` | 4 MB | E3 runs, 2026-11-19 (PC): `research_darvas_reentry_20261119/` (calls, replay states, `reentry_entries.csv`) and `research_darvas_structural_stop_20261119/` (per-trade rows) | `docs/DARVAS_REENTRY_RESULTS_2026-11-19.md`, `docs/DARVAS_STRUCTURAL_STOP_RESULTS_2026-11-19.md` |
| `l1_snap_20261113.tgz` | `a03003d805e886923b07c6d8dae1f639e9a646b2b24ac912044793388d5947df` | 554 MB (767 MB unpacked) | A frozen copy of the VM's L1 store as of 2026-11-13 | the 2026-11-15/17 replays, E3 (both tests) |
| `smc_ob_1h/` (NIFTY_60, NIFTY_5, INDIAVIX_60, INDIAVIX_5, NIFTY_daily; hashes in its `SHA256SUMS`: NIFTY_60 `c75200873218f62676e7123bafa47509f7b6d82d2bf3c85046856318d9b18268`, NIFTY_5 `1f5092b4ac938f12eb735e294feb1e892a9e23fdc2aebdd91babfc4b45292444`, INDIAVIX_60 `0a2194a58db59cf08bb61feb29389a868240ce0017342491ddd151accaab29e3`, INDIAVIX_5 `8bf1861bff73d3ad226c9b9482f71a2c48b9f2f152b80ad3e3e8ae22c466d18a`, NIFTY_daily `89ed66310ca977d8b5a3c5105de6e69a08ba50baea0a2d3f06cc5b17aff34ac9`) | see column 1 | 17 MB | `scripts/research/smc_ob_1h_fetch.py`, 2026-11-22 (VM, Fyers; 2017-11-22..2026-11-20). Fyers' 9-year rolling window: cannot be re-fetched from 2017 later | `docs/NIFTY_SMC_OB_1H_PREREG_2026-11-22.md` |

## Large raw inputs (PC only; rebuildable from NSE, so not copied)

| What | Where | Rebuild |
|---|---|---|
| NSE daily equity bhavcopies 2016-2023 (6,646 files) | PC `data_cache/pead_nse/eq_bhavcopy_raw/` | `core/fundamentals/pead/eq_bhavcopy.py` fetch from NSE archives |
| NSE corporate actions 2010-2026 | PC `data_cache/nse_corporate_actions_*.json` (in the repo's data cache) | NSE corporate-actions download |
| Techno-funda price/fundamentals panel (1.7 GB) | PC | `scripts/techno_funda_*` fetch stages |

## Live data (VM only; the live jobs own it)

The L1 store (`~/.quantos/l1_store`, nightly), the 5-minute bars, the index bars, the option chains and the paper logs (Darvas, ORB, call plans). They are not listed here, except when a frozen snapshot of them feeds a result (as `l1_snap_20261113` does).

**Open question:** no VM backup is known. The VM copy protects against losing the PC, not against losing the VM, and the PC copy covers that the other way round. Off-machine backup of `~/.quantos/research/` (for example a periodic copy to cloud storage) is not set up.
