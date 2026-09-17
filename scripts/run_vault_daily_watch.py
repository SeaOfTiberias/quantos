#!/usr/bin/env python3
"""
QuantOS — Vault Daily Watch: Telegram Alert on a Human-Written Rule Passing
──────────────────────────────────────────────────────────────────────
Answers the "can a strategy this project has already tested be run
discretionarily, on days conditions actually look right" half of the
2026-09-17 strategy-database request. The other half -- database and a
published report -- is `obsidian_vault/QuantOS/wiki/` (see
docs/VAULT_DAILY_WATCH.md for the full design and why this script does NOT
execute anything.

Per fire, for each `agent/config.yaml`'s `vault.watches` entry
({note, symbol, label}): fetch `symbol`'s recent daily candles, audit them
against `note` via `core/vault/gates.py`'s existing fail-closed machinery
(the same one that gates the options webhook and the rotation pilot), and
send a Telegram alert ONLY on a real PASS. FAIL and INSUFFICIENT_DATA are
silent by design -- a strategy this project's own history shows fails most
days should not page the user most days.

This script imports nothing from core/execution/ or any order-placing
module. There is no code path here that can place an order, size a
position, or flip a dry_run flag -- a PASS is information, never an
instruction. `vault.watches` can only ever point at a note in `brain/`,
which is human-authored only (the vault's own SCHEMA.md) -- so every
condition this script can ever alert on is one the user wrote and chose to
watch, never one an agent proposed or generated.

Usage:
    python scripts/run_vault_daily_watch.py
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.main import load_config  # noqa: E402
from cloud.api.notifier import send_telegram  # noqa: E402
from core.brokers import get_broker  # noqa: E402
from core.vault.gates import audit_gate  # noqa: E402
from core.vault.models import Verdict  # noqa: E402

DAILY_LOOKBACK_DAYS = 400   # comfortably covers any quantos-rules window (e.g. sma(200))


def _format_alert(label: str, symbol: str, note: str) -> str:
    today = datetime.now(timezone.utc).date().isoformat()
    return (
        f"🔔 Vault watch: *{label}*\n"
        f"{symbol} passes `{note}` as of {today}.\n"
        f"Information only -- no order was placed. Reply in the cockpit/vault "
        f"if you want to act on it."
    )


def main() -> int:
    config = load_config("agent/config.yaml")
    vault_cfg = config.get("vault", {}) or {}
    if not vault_cfg.get("watch_enabled", False):
        print("vault.watch_enabled is false in agent/config.yaml -- nothing to do.")
        return 0

    watches = vault_cfg.get("watches") or []
    if not watches:
        print("vault.watch_enabled is true but vault.watches is empty -- nothing to check.")
        return 0

    broker = get_broker(config)
    if not broker.connect():
        print("ERROR: broker connect() failed -- check the Fyers token.")
        return 1

    now_utc = datetime.now(timezone.utc)
    from_date = now_utc - timedelta(days=DAILY_LOOKBACK_DAYS)

    alerts_sent = 0
    for watch in watches:
        note = watch.get("note")
        symbol = watch.get("symbol")
        label = watch.get("label") or note
        if not note or not symbol:
            print(f"  skipping malformed watch entry (needs note + symbol): {watch}")
            continue

        try:
            daily = broker.get_historical_data(symbol, "1d", from_date, now_utc)
        except Exception as e:
            print(f"  {label}: history fetch failed ({e}) -- self-healing, will retry next fire.")
            continue

        decision = audit_gate(symbol, daily, [note])
        print(f"  {label} ({symbol} vs {note}): {decision.verdict.value} -- {decision.reason}")

        if decision.allowed and decision.verdict == Verdict.PASS:
            delivered = asyncio.run(send_telegram(_format_alert(label, symbol, note)))
            if delivered:
                alerts_sent += 1
            else:
                print(f"  {label}: PASS but Telegram delivery failed -- see notifier logs.")

    print(f"\n{alerts_sent} alert(s) sent, {len(watches)} watch(es) checked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
