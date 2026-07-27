"""
QuantOS — Candidate 15 (10:10 breakout) Data Feasibility Probe
────────────────────────────────────────────────────────────────
Answers one question before candidate 15's methodology is pre-registered:
is real historical INTRADAY (5m) option premium data fetchable from Fyers
for an EXPIRED BankNifty option contract, and how far back does it go?

The previous attempt at this probe (2026-07-26) hit the _fyers_symbol()
bug (core/brokers/fyers.py:73) instead of getting a real answer — that bug
is now fixed (any already-"NSE:"-prefixed symbol passes through unchanged
instead of getting "-EQ" appended). This script re-runs the probe for real.

Ground truth for each probe date comes from NSE's own F&O bhavcopy (see
core/options/vrp/bhavcopy.py, same pipeline the VRP candidate used), not
hand-guessed expiry/strike math — the bhavcopy's own FinInstrmNm column
*is* the Fyers symbol format (minus the "NSE:" prefix), confirmed live
2026-07-27 (e.g. "BANKNIFTY26AUG52700CE"). This sidesteps any ambiguity
about the Thursday->Tuesday monthly-expiry-day rule change (SEBI circular,
see docs/EXPIRY_DAY_EFFECT_GUTCHECK_METHODOLOGY.md) or historical
weekly-vs-monthly symbol formatting.

For each probe date, picks the nearest-expiry, ATM, actually-traded
(volume > 0) CE contract, then asks Fyers for that exact contract's 5m
candles across its own lifetime and reports how many real candles come
back.

Read-only, no orders placed, no input() prompts — safe to run
non-interactively.

Usage:
    python scripts/probe_option_intraday_depth.py
"""

import csv
import io
import sys
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml

from core.options.vrp import bhavcopy as bc

CONFIG_PATH = "agent/config.yaml"

# Vintages to probe, oldest-safe boundary is the bhavcopy new-format cutover
# (2024-01-01, see core/options/vrp/bhavcopy.py) so every probe date gets
# underlying_close for free and an unambiguous FinInstrmNm.
PROBE_MONTHS_AGO = [1, 3, 6, 12, 18, 24, 30]


def _load_bn_rows(d: date) -> list[dict]:
    raw = bc.fetch_raw(d)
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        names = zf.namelist()
        text = zf.read(names[0]).decode("utf-8")
    rows = list(csv.DictReader(io.StringIO(text)))
    return [r for r in rows
            if r.get("TckrSymb") == "BANKNIFTY" and r.get("FinInstrmTp") == "IDO"]


def _nearest_atm_traded_ce(rows: list[dict]) -> dict:
    liquid = [r for r in rows if float(r["TtlTradgVol"]) > 0]
    if not liquid:
        raise RuntimeError("no traded BANKNIFTY option rows on this date")
    near_expiry = min(r["XpryDt"] for r in liquid)
    candidates = [r for r in liquid if r["XpryDt"] == near_expiry and r["OptnTp"] == "CE"]
    spot = float(candidates[0]["UndrlygPric"])
    return min(candidates, key=lambda r: abs(float(r["StrkPric"]) - spot))


def _find_ground_truth(target: date, max_lookback_days: int = 7) -> tuple[date, dict]:
    """Bhavcopy has no row on weekends/holidays — walk backward to the
    nearest real trading day, same 404-as-holiday convention as
    core/options/vrp/bhavcopy.py's own callers."""
    d = target
    for _ in range(max_lookback_days):
        try:
            rows = _load_bn_rows(d)
            if rows:
                return d, _nearest_atm_traded_ce(rows)
        except bc.BhavcopyNotAvailable:
            pass
        d -= timedelta(days=1)
    raise RuntimeError(f"no BANKNIFTY bhavcopy found within {max_lookback_days} days back from {target}")


def main():
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)

    from core.brokers import get_broker
    from core.brokers.base import BrokerError

    broker = get_broker(config)
    print(f"Connecting to broker: {config.get('broker')}")
    try:
        broker.connect()
    except BrokerError as e:
        print(f"connect() failed: {e}")
        print("If this is an auth/token error, the stored token has likely "
              "expired — run the interactive fyers_auth.py refresh yourself "
              "in your own terminal, then re-run this script.")
        sys.exit(1)
    print(f"Broker connected.\n")

    today = date.today()
    results = []

    for months_ago in PROBE_MONTHS_AGO:
        target = today - timedelta(days=months_ago * 30)
        try:
            trade_date, contract = _find_ground_truth(target)
        except Exception as e:
            print(f"[{months_ago}mo ago, ~{target}] ground-truth lookup failed: {e}")
            results.append((months_ago, target, None, None, "ground-truth-failed", 0))
            continue

        fyers_symbol = f"NSE:{contract['FinInstrmNm']}"
        expiry = date.fromisoformat(contract["XpryDt"])
        strike = contract["StrkPric"]
        print(f"[{months_ago}mo ago] ground truth {trade_date}: {fyers_symbol} "
              f"(expiry {expiry}, strike {strike}, vol {contract['TtlTradgVol']})")

        # A contract's real tradeable life is roughly the prior ~35 calendar
        # days through expiry (monthly BankNifty contracts) — request a
        # window comfortably covering that, Fyers' own 100-day intraday cap
        # (see scripts/backtest_dow_theory_trend.py) is never hit here.
        from_dt = datetime.combine(expiry - timedelta(days=40), datetime.min.time(), tzinfo=timezone.utc)
        to_dt = datetime.combine(expiry + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)

        try:
            candles = broker.get_historical_data(fyers_symbol, "5m", from_dt, to_dt)
        except BrokerError as e:
            print(f"  get_historical_data() FAILED: {e}")
            results.append((months_ago, trade_date, fyers_symbol, expiry, "fetch-failed", 0))
            continue

        on_trade_date = [c for c in candles
                          if c.timestamp.astimezone(timezone.utc).date() == trade_date]
        status = "OK" if candles else "EMPTY"
        print(f"  {status}: {len(candles)} total candles "
              f"({candles[0].timestamp if candles else '-'} .. "
              f"{candles[-1].timestamp if candles else '-'}), "
              f"{len(on_trade_date)} candles on the ground-truth trade date itself")
        results.append((months_ago, trade_date, fyers_symbol, expiry, status, len(candles)))

    print("\n=== Summary ===")
    print(f"{'months_ago':>10}  {'trade_date':>10}  {'status':>8}  {'candles':>8}  symbol")
    for months_ago, trade_date, symbol, expiry, status, n in results:
        print(f"{months_ago:>10}  {str(trade_date):>10}  {status:>8}  {n:>8}  {symbol}")


if __name__ == "__main__":
    main()
