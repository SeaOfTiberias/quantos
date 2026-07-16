"""
QuantOS Local Agent
────────────────────
Runs on the customer's machine. Holds broker credentials locally.
Polls QuantOS cloud for CONFIRMED signals and executes orders via the
configured broker adapter. The Telegram "execute"/"skip" reply itself is
handled entirely on the cloud side (see cloud/api/main.py /webhook/telegram)
— this agent only ever talks REST to the cloud API (ADR-01: keys never
leave this machine).

ADR-01: Keys never leave this machine.
ADR-05: confirm_before_execute = True by default (human-in-loop on the
cloud side gates a signal from PENDING_CONFIRMATION to CONFIRMED before
this agent will ever see it).

Usage:
    python agent/main.py
    python agent/main.py --config path/to/config.yaml
"""

import argparse
import asyncio
import json
import logging
import sys
import time
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

# Allow running as `python agent/main.py` from the repo root — the script's
# own directory (agent/) is on sys.path by default, but the repo root
# (needed for `core.*` imports) is not.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests
import yaml

from agent import risk_guard
from agent.positions import (
    OpenPosition, load_open_positions, add_position, update_stop, remove_position,
)
from agent.discovery_watchlist import (
    load_watchlist, merge_scan_results, candidates_for_granular_scan,
    mark_fired, already_fired_today, mark_position_open, clear_position,
    check_add_candidates,
)
from core.darvas.box import next_trailing_stop
from core.darvas.scanner import DarvasScanner
from core.darvas.weekly_discovery import WeeklyDiscoveryScanner, DEFAULT_CONFIG as DISCOVERY_CONFIG
from core.regime.service import RegimeService, CACHE_TTL as REGIME_CACHE_TTL
from core.risk.correlation_service import CorrelationPortfolioService
from core.risk.correlation import CORRELATION_THRESHOLD

# How often (in poll ticks) to re-check open positions for trailing/closure.
# Kept slower than the 5s signal poll to avoid hammering the broker with
# historical-data calls for every open position.
TRAIL_EVERY_N_TICKS = 12  # ~60s at the default 5s poll_interval

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("quantos.agent")

# Tracks signal_ids this machine has already attempted to execute, so a
# crash/restart between "order placed" and "reported to cloud" can never
# result in the same signal being placed twice.
PROCESSED_SIGNALS_PATH = Path.home() / ".quantos" / "processed_signals.json"

# Stage A (weekly discovery, core/darvas/weekly_discovery.py) runs at most
# once per calendar day — this file just records the date of the last run.
LAST_DISCOVERY_PATH = Path.home() / ".quantos" / "last_discovery_scan.txt"

# Closed-trade history feeding Kelly sizing (core/risk/trade_history.py) —
# persisted because the agent restarts daily (Fyers token expiry) and the
# Kelly 20-trade minimum would otherwise never be reached.
TRADE_HISTORY_PATH = Path.home() / ".quantos" / "trade_history.json"

# NSE cash market hours (IST). Stage B (granular intraday timing via
# core/darvas/scanner.py) only makes sense while the market's open.
IST          = timezone(timedelta(hours=5, minutes=30))
MARKET_OPEN  = (9, 15)
MARKET_CLOSE = (15, 30)


def load_config(config_path: str) -> dict:
    path = Path(config_path)
    if not path.exists():
        logger.error(
            "Config not found at %s\n"
            "Copy agent/config.yaml.example to agent/config.yaml and fill in your values.",
            config_path
        )
        sys.exit(1)
    with open(path) as f:
        return yaml.safe_load(f)


def _load_processed_ids() -> set:
    if PROCESSED_SIGNALS_PATH.exists():
        try:
            return set(json.loads(PROCESSED_SIGNALS_PATH.read_text()))
        except (json.JSONDecodeError, OSError):
            return set()
    return set()


def _mark_processed(signal_id: str, processed: set) -> None:
    processed.add(signal_id)
    PROCESSED_SIGNALS_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROCESSED_SIGNALS_PATH.write_text(json.dumps(sorted(processed)))


def _report_outcome(cloud_url: str, headers: dict, signal_id: str,
                     endpoint: str, payload: dict) -> None:
    try:
        r = requests.post(f"{cloud_url}/signals/{signal_id}/{endpoint}",
                           json=payload, headers=headers, timeout=10)
        r.raise_for_status()
    except Exception as e:
        logger.error("[%s] Failed to report '%s' to cloud: %s", signal_id, endpoint, e)


def _report_halt(cloud_url: str, headers: dict, reason: str) -> None:
    """Relay a kill-switch halt to the cloud so it can Telegram-notify —
    the agent holds no bot token (ADR-01). Best-effort: a failed relay
    still leaves the local halt flag set, so entries stay refused; it just
    means the human doesn't get the push. Logged, not raised."""
    try:
        r = requests.post(f"{cloud_url}/agent/halt",
                          json={"reason": reason}, headers=headers, timeout=10)
        r.raise_for_status()
    except Exception as e:
        logger.error("Failed to relay halt to cloud (halt flag still set locally): %s", e)


def _check_and_set_halt(broker, sizer, open_positions, cloud_url, headers,
                        capital, max_daily_loss_pct, ltp=None) -> None:
    """Evaluate the automatic kill-switch triggers and, if one has fired,
    set the persistent halt flag and Telegram-notify exactly once. `ltp`
    (symbol→price), when supplied, adds open-position mark-to-market to the
    daily-loss check; without it only realized closed-trade P&L counts.

    Already-halted is a no-op (the flag persists and only a human clears
    it) so we never re-notify on every tick."""
    if risk_guard.is_halted():
        return
    reason = risk_guard.evaluate_halt_triggers(
        trades=sizer.get_trade_history(),
        open_positions=open_positions,
        capital=capital,
        max_daily_loss_pct=max_daily_loss_pct,
        ltp=ltp,
    )
    if reason:
        risk_guard.set_halt(reason)
        _report_halt(cloud_url, headers, reason)


def _size_and_place_order(broker, sizer, signal: dict, config: dict):
    """Kelly-size the position (core/risk/kelly.py) and place it via the
    broker adapter. Raises BrokerError if it can't be sized or placed.

    Places the entry as a plain MARKET order, then — if a stop_loss is
    known — immediately places a second, separate SL_M (stop-loss market)
    order in the opposite direction as the actual stop-loss leg. (An
    earlier version of this tried to use a single Fyers Cover Order for
    this; Fyers' v3 API rejects "CO" as a productType outright — CNC,
    MARGIN, INTRADAY, MTF are the only valid values — so two plain orders
    it is.) The trailing loop (_manage_open_positions) ratchets that SL_M
    order's trigger price up over the life of the position via
    broker.modify_stop_loss(sl_order_id, ...)."""
    from core.brokers.base import Order, OrderDirection, OrderType, ProductType, BrokerError

    symbol = signal["symbol"]
    action = signal["action"]
    price = float(signal["price"])
    stop_loss = signal.get("stop_loss")

    risk_cfg = config.get("risk", {})
    configured_product_type = ProductType[risk_cfg.get("product_type", "INTRADAY").upper()]
    assumed_stop_pct = float(risk_cfg.get("assumed_stop_pct", 0.015))

    funds = broker.get_funds()
    capital = funds.get("available") or 0

    # get_current_sizing falls back to a fixed 2% until 20+ closed trades
    # are on record (core/risk/kelly.py MIN_TRADES_FOR_KELLY) — this agent
    # doesn't yet persist closed-trade history across runs, so it will use
    # that fixed fallback until trade-history persistence is wired up.
    sizing = sizer.get_current_sizing(symbol, capital=capital)

    if not stop_loss:
        stop_loss = price * (1 - assumed_stop_pct if action == "BUY" else 1 + assumed_stop_pct)
        logger.warning(
            "[%s] Signal has no stop_loss — assuming %.2f%% (%.2f). "
            "Wire stop_loss into the TradingView alert for real Darvas-box stops.",
            signal["signal_id"], assumed_stop_pct * 100, stop_loss,
        )

    quantity = sizing.position_quantity(entry_price=price, stop_loss_price=stop_loss)

    # Trial-phase notional cap: risk-based sizing lets a tight stop blow the
    # position value up (quantity = risk ÷ stop-distance), so bound the ₹ value
    # of any single position regardless of stop distance. 0/absent = disabled.
    max_position_value = float(risk_cfg.get("max_position_value", 0) or 0)
    if max_position_value > 0 and price > 0:
        cap_qty = int(max_position_value / price)
        if cap_qty < quantity:
            logger.info(
                "[%s] Position capped by max_position_value=%.0f: qty %d → %d "
                "(price=%.2f, notional %.0f → %.0f)",
                signal["signal_id"], max_position_value, quantity, cap_qty,
                price, quantity * price, cap_qty * price,
            )
            quantity = cap_qty

    if quantity <= 0:
        raise BrokerError(
            f"Computed quantity {quantity} (capital={capital:.2f}, "
            f"size_pct={sizing.size_pct:.2%}, method={sizing.method}, "
            f"max_position_value={max_position_value:.0f}, price={price:.2f}) — "
            f"insufficient funds, stop-loss too tight, or price exceeds the cap"
        )

    entry_direction = OrderDirection.BUY if action == "BUY" else OrderDirection.SELL
    order = Order(
        symbol=symbol,
        direction=entry_direction,
        quantity=quantity,
        order_type=OrderType.MARKET,
        product_type=configured_product_type,
        tag=signal["signal_id"],
    )
    result = broker.place_order(order)

    # MARKET orders usually fill within seconds — poll briefly for the fill
    # price, but don't block the agent loop indefinitely if it's slow.
    fill_price = result.average_price
    for _ in range(5):
        if fill_price:
            break
        time.sleep(1)
        try:
            fill_price = broker.get_order_status(result.order_id).average_price
        except Exception:
            break
    if not fill_price:
        fill_price = price

    # Auto-exit (Task 4): place a separate SL_M stop order in the opposite
    # direction as the actual stop-loss leg. Disable via risk.auto_exit:
    # false in config (e.g. for CNC/delivery trades you intend to hold).
    auto_exit = bool(risk_cfg.get("auto_exit", True))
    sl_order_id = None
    if auto_exit:
        exit_direction = OrderDirection.SELL if entry_direction == OrderDirection.BUY else OrderDirection.BUY
        sl_order = Order(
            symbol=symbol,
            direction=exit_direction,
            quantity=quantity,
            order_type=OrderType.SL_M,
            product_type=configured_product_type,
            trigger_price=stop_loss,
            tag=f"{signal['signal_id']}-sl",
        )
        sl_result = broker.place_order(sl_order)
        sl_order_id = sl_result.order_id

    return result.order_id, quantity, fill_price, stop_loss, auto_exit, sl_order_id


def _is_market_hours(now_utc: datetime) -> bool:
    """NSE cash market: 9:15-15:30 IST, Monday-Friday."""
    now_ist = now_utc.astimezone(IST)
    if now_ist.weekday() >= 5:  # Sat/Sun
        return False
    open_t = now_ist.replace(hour=MARKET_OPEN[0], minute=MARKET_OPEN[1], second=0, microsecond=0)
    close_t = now_ist.replace(hour=MARKET_CLOSE[0], minute=MARKET_CLOSE[1], second=0, microsecond=0)
    return open_t <= now_ist <= close_t


def _should_run_discovery_today() -> bool:
    if not LAST_DISCOVERY_PATH.exists():
        return True
    try:
        return LAST_DISCOVERY_PATH.read_text().strip() != date.today().isoformat()
    except OSError:
        return True


def _mark_discovery_ran_today() -> None:
    LAST_DISCOVERY_PATH.parent.mkdir(parents=True, exist_ok=True)
    LAST_DISCOVERY_PATH.write_text(date.today().isoformat())


def _load_universe(path: str) -> list:
    """Parse the discovery universe file — comma/newline separated NSE
    symbols, '#' comment lines and inline comments ignored."""
    file_path = Path(path)
    if not file_path.exists():
        logger.warning("Discovery universe file not found: %s", path)
        return []
    symbols, seen = [], set()
    # Explicit utf-8: universe files are generated on Windows (cp1252 locale)
    # and read here on the Linux VM, where read_text() would otherwise default
    # to utf-8 and raise on any byte the generator's locale encoded differently.
    for line in file_path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        for sym in line.split(","):
            sym = sym.strip().upper()
            if sym and sym not in seen:
                seen.add(sym)
                symbols.append(sym)
    return symbols


def _sync_watchlist_to_cloud(cloud_url: str, headers: dict, discovery_watchlist: dict) -> None:
    """
    Push the local discovery watchlist to the cloud (cloud/api/discovery_routes.py)
    purely so the cockpit dashboard has something to display — the watchlist
    itself only ever lives on this machine (~/.quantos/discovery_watchlist.json),
    same "keys never leave this machine" reasoning as everything else here.
    Best-effort: a failed sync just means a stale cockpit view, not a
    functional problem, so it's logged and swallowed rather than raised.
    """
    entries = [asdict(e) for e in discovery_watchlist.values()]
    try:
        resp = requests.post(f"{cloud_url}/discovery/watchlist",
                              json={"entries": entries}, headers=headers, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        logger.error("Failed to sync discovery watchlist to cloud: %s", e)


def _sync_correlation_to_cloud(cloud_url: str, headers: dict, result) -> None:
    """Push one correlation gate decision to the cloud
    (cloud/api/correlation_routes.py) purely so the cockpit can show the gate
    working. Best-effort: a failed sync just means a stale display, never a
    functional problem, so it's logged and swallowed — same reasoning as
    _sync_watchlist_to_cloud."""
    payload = {
        "candidate_symbol": result.candidate_symbol,
        "is_blocked":       result.is_blocked,
        "max_correlation":  result.max_correlation,
        "correlated_with":  [c.symbol_b for c in result.correlated_with],
        "reason":           result.reason,
        "checked_at":       datetime.now(timezone.utc).isoformat(),
    }
    try:
        resp = requests.post(f"{cloud_url}/correlation/sync",
                             json=payload, headers=headers, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        logger.error("Failed to sync correlation decision to cloud: %s", e)


def _correlation_refusal_reason(corr_service, symbol: str, open_positions: dict,
                                threshold: float, cloud_url: str, headers: dict):
    """Correlation gate (S5-5 / P1-6). Returns a refusal string if `symbol` is
    too correlated (r>threshold) with an already-open position, else None.

    Runs agent-side because only the agent holds a broker to fetch the price
    history a correlation check needs (ADR-01). Each decision is best-effort
    synced to the cloud for cockpit display. Fails OPEN: if the check itself
    errors (data fetch failure, etc.), the entry is allowed rather than
    silently dropped — the gate reduces concentration risk, it isn't a
    safety-critical stop like the kill switch."""
    if corr_service is None:
        return None
    open_symbols = [p.symbol for p in open_positions.values()]
    if not open_symbols:
        return None
    try:
        result = asyncio.run(
            corr_service.check_candidate(symbol, open_symbols, threshold=threshold))
    except Exception as e:
        logger.error("Correlation check failed for %s — allowing entry: %s", symbol, e)
        return None

    _sync_correlation_to_cloud(cloud_url, headers, result)
    if result.is_blocked:
        return f"REFUSED by correlation gate: {result.reason}"
    return None


def _log_peak_rss(label: str) -> None:
    """Log this process's high-water-mark RSS.

    The agent OOM-killed itself twice on 2026-07-15 and the root cause is still
    unknown — the originally documented hypothesis (Stage A firing hundreds of
    concurrent DataFrame builds) is disproven, since the scanner is throttled to
    max_concurrent=2. Stage A has since gone from 247 to 500 symbols against a
    650MB cgroup cap, so the high-water mark after a scan is the one number that
    would actually narrow this down. Cheap enough to log unconditionally.

    `resource` is Unix-only and the agent runs on Linux, but the tests run on
    Windows — degrade to silence rather than guard every caller. ru_maxrss is
    KB on Linux (bytes on macOS; we don't deploy there).
    """
    try:
        import resource
        peak_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    except (ImportError, AttributeError, OSError):
        return
    logger.info("Memory: peak RSS %.0f MB after %s", peak_kb / 1024, label)


def _run_discovery_scan(broker, universe_path: str, discovery_watchlist: dict,
                         cloud_url: str, headers: dict) -> None:
    """
    Stage A: once-per-day weekly Darvas discovery scan across the
    configured universe (core/darvas/weekly_discovery.py) — the "Bloomberg
    terminal" candidate-finding half of the pipeline. Narrows a broad
    universe down to a short candidate shortlist that Stage B
    (_run_granular_scan, below) then times intraday entries on. Ported
    from the user's DarvasTrader project, but sourced from Fyers daily
    candles instead of yfinance so discovery and execution share one
    broker/data source.
    """
    symbols = _load_universe(universe_path)
    if not symbols:
        logger.warning("Discovery universe is empty (%s) — skipping Stage A scan.", universe_path)
        return

    logger.info("Stage A: scanning %d symbols from %s", len(symbols), universe_path)
    scanner = WeeklyDiscoveryScanner(broker)
    results = asyncio.run(scanner.scan_universe(symbols))
    # Logged before the empty-results raise below: a scan that failed systemically
    # is exactly when the memory number is most interesting.
    _log_peak_rss(f"Stage A ({len(symbols)} symbols)")

    if not results:
        # scan_universe swallows per-symbol exceptions (return_exceptions=True)
        # rather than raising, so a systemic failure (bad credentials, broker
        # outage, a bug in analyse_symbol) looks identical to a quiet day with
        # zero candidates unless we raise here ourselves. Every symbol failing
        # out of a non-empty universe is never a legitimate "no candidates
        # today" — raise so run_agent's except block does NOT mark today as
        # done, letting the next agent start retry instead of silently
        # skipping for 24h (this happened three times live: date_format,
        # event-loop binding, and history_days bugs each looked like "0
        # candidates" until this check existed).
        raise RuntimeError(
            f"Stage A scan produced 0 results out of {len(symbols)} symbols — "
            "treating as a systemic failure, not a quiet day."
        )

    add_candidates = check_add_candidates(discovery_watchlist, results)
    merge_scan_results(discovery_watchlist, results,
                        watchlist_days=DISCOVERY_CONFIG["watchlist_days"])

    candidates = candidates_for_granular_scan(discovery_watchlist)
    logger.info("Stage A complete: %d candidate(s) queued for Stage B timing: %s",
                len(candidates), ", ".join(candidates) or "none")

    for c in add_candidates:
        logger.info(
            "[ADD?] %s: new box ceiling %.2f is %.1f%% above your %.2f entry "
            "(status=%s, tier=%s) — consider adding to this winner",
            c["symbol"], c["new_ceiling"], c["gain_pct"], c["orig_entry"],
            c["status"], c["alert_tier"],
        )

    _sync_watchlist_to_cloud(cloud_url, headers, discovery_watchlist)


def _run_granular_scan(broker, cloud_url: str, headers: dict, webhook_secret: str,
                        discovery_watchlist: dict) -> None:
    """
    Stage B: time the actual intraday entry on Stage A's shortlist using
    the existing multi-timeframe confluence scanner
    (core/darvas/scanner.py) — unmodified. Any fired result is POSTed to
    the same /webhook/tradingview endpoint TradingView alerts already
    use, so it gets exactly the same Claude pre-trade analysis, event-risk
    filter, and Telegram human-in-loop confirmation as a Pine Script
    signal — just tagged with a different strategy name so the source is
    distinguishable in the signal history.
    """
    candidates = candidates_for_granular_scan(discovery_watchlist)
    if not candidates:
        return

    scanner = DarvasScanner(broker)
    results = asyncio.run(scanner.scan_watchlist(candidates))
    fired = [r for r in results if r.primary_signal is not None]

    any_fired = False
    for result in fired:
        if already_fired_today(discovery_watchlist, result.symbol):
            continue

        signal = result.primary_signal
        payload = {
            "symbol": result.symbol, "action": "BUY",
            "price": signal.breakout_price, "timeframe": signal.timeframe,
            "strategy": "darvas_scanner_internal",
            "confluence_score": result.confluence_score,
            "stop_loss": signal.box_bottom,
            "secret": webhook_secret,
            # Replay guard on the webhook: payloads without a fresh epoch-
            # seconds timestamp are rejected (cloud/api/main.py).
            "timestamp": time.time(),
        }
        try:
            resp = requests.post(f"{cloud_url}/webhook/tradingview", json=payload, timeout=10)
            resp.raise_for_status()
            body = resp.json()
            mark_fired(discovery_watchlist, result.symbol,
                       signal_id=body.get("signal_id", ""),
                       confluence=result.confluence_score,
                       signal_status=body.get("status", ""))
            any_fired = True
            logger.info("[Stage B] Fired internal signal for %s (confluence=%.0f)",
                        result.symbol, result.confluence_score)
        except Exception as e:
            logger.error("[Stage B] Failed to POST internal signal for %s: %s",
                         result.symbol, e)

    if any_fired:
        _sync_watchlist_to_cloud(cloud_url, headers, discovery_watchlist)


def _run_regime_sync(regime_service: RegimeService, cloud_url: str, headers: dict) -> None:
    """
    Refresh the market regime classification (core/regime/service.py — a
    cheap no-op call if still within its own 15-min cache, ADR-04) and
    push it to the cloud (cloud/api/regime_routes.py). Only the local
    agent ever holds a connected broker (ADR-01), so this is the only
    place RegimeService can actually run — before this was wired up,
    cloud/analyst/pre_trade.py fed every pre-trade analysis a hardcoded
    fake regime, and POST /strategy/recommend 503'd unconditionally.

    Runs regardless of scanner.enabled — regime informs every signal's
    pre-trade analysis (Pine Script or internal Stage B), not just the
    Darvas discovery pipeline.
    """
    result = asyncio.run(regime_service.get_regime())
    payload = {
        "regime": result.regime.value,
        "confidence": result.confidence,
        "allowed_strategies": result.allowed_strategies,
        "size_multiplier": result.size_multiplier,
        "timestamp": result.timestamp.isoformat(),
        "trend_signal": result.trend_signal,
        "vix_signal": result.vix_signal,
        "breadth_signal": result.breadth_signal,
        "advance_count": result.advance_count,
        "decline_count": result.decline_count,
        "unchanged_count": result.unchanged_count,
        "notes": result.notes,
    }
    resp = requests.post(f"{cloud_url}/regime/sync", json=payload, headers=headers, timeout=10)
    resp.raise_for_status()
    logger.info("Regime synced: %s (confidence=%.0f)", result.regime.value, result.confidence)


def _sync_positions_to_cloud(broker, cloud_url: str, headers: dict, positions: dict) -> None:
    """
    Push live open positions (qty/entry/LTP/PnL, already computed broker-
    side — core/brokers/base.py's Position) to the cloud so the cockpit can
    show a real Open Positions panel. Same reasoning as _run_regime_sync:
    only the agent holds a connected broker (ADR-01). Runs on its own tick
    (not gated on `positions` being non-empty) so the cloud mirror clears to
    an empty list once the last position closes, instead of showing stale
    rows forever.
    """
    try:
        live = broker.get_positions()
    except Exception as e:
        logger.error("Failed to fetch positions for cloud sync: %s", e)
        return

    strategy_by_symbol = {p.symbol: p.strategy for p in positions.values()}
    payload = {
        "positions": [
            {
                "symbol":   p.symbol,
                "qty":      p.quantity,
                "entry":    p.average_price,
                "ltp":      p.current_price,
                "pnl":      p.pnl,
                "pnl_pct":  p.pnl_percent,
                "strategy": strategy_by_symbol.get(p.symbol, "unknown"),
            }
            for p in live if p.quantity != 0
        ],
    }
    resp = requests.post(f"{cloud_url}/positions/sync", json=payload, headers=headers, timeout=10)
    resp.raise_for_status()


def _manage_open_positions(broker, cloud_url, headers, sizer, positions: dict,
                            discovery_watchlist: dict):
    """
    For every locally-tracked open position: check whether the broker still
    shows it open. If closed, record it as a ClosedTrade (this is what
    finally feeds TradeHistoryService.record_closed_trade() — the call site
    that's been missing since Task 2, so Kelly sizing can graduate off its
    fixed-2% fallback). If still open, re-run the Darvas box scan and trail
    the stop-loss up if a tighter one has formed.
    """
    from core.brokers.base import OrderStatus
    from core.risk.kelly import ClosedTrade

    try:
        live_positions = {p.symbol: p for p in broker.get_positions()}
    except Exception as e:
        logger.error("Failed to fetch live positions for trailing/close check: %s", e)
        return

    for signal_id, pos in list(positions.items()):
        live = live_positions.get(pos.symbol)
        still_open = live is not None and live.quantity != 0

        if not still_open:
            exit_price, exit_date = None, None
            try:
                history = broker.get_order_history()
                # The SL_M stop order is a real, separate order now (not a
                # bundled CO leg) — if it filled, that's the exit itself.
                sl_fill = next(
                    (o for o in history
                     if o.order_id == pos.sl_order_id and o.status == OrderStatus.EXECUTED),
                    None,
                )
                if sl_fill:
                    exit_price, exit_date = sl_fill.average_price, sl_fill.timestamp
                else:
                    # Closed some other way (e.g. manual square-off in the
                    # Fyers app) — fall back to the latest executed fill for
                    # this symbol, and cancel the now-orphaned stop order.
                    candidates = [
                        o for o in history
                        if o.symbol == pos.symbol
                        and o.order_id != pos.sl_order_id
                        and o.status == OrderStatus.EXECUTED
                    ]
                    if candidates:
                        latest = max(candidates, key=lambda o: o.timestamp)
                        exit_price, exit_date = latest.average_price, latest.timestamp
                    try:
                        broker.cancel_order(pos.sl_order_id)
                    except Exception:
                        pass
            except Exception as e:
                logger.error("[%s] Failed to read order history for exit fill: %s", signal_id, e)

            if exit_price is None:
                try:
                    exit_price = broker.get_ltp([pos.symbol]).get(pos.symbol, pos.current_stop)
                except Exception:
                    exit_price = pos.current_stop
            if exit_date is None:
                exit_date = datetime.now(timezone.utc)

            trade = ClosedTrade(
                trade_id=pos.signal_id,
                symbol=pos.symbol,
                entry_price=pos.entry_price,
                exit_price=exit_price,
                quantity=pos.quantity,
                direction=pos.direction,
                entry_date=datetime.fromisoformat(pos.entry_date),
                exit_date=exit_date,
                strategy=pos.strategy,
            )
            sizer.record_closed_trade(trade)
            _report_outcome(cloud_url, headers, signal_id, "closed", {
                "exit_price": exit_price, "pnl": trade.pnl, "reason": "stop_hit",
            })
            logger.info("[%s] Position closed: %s pnl=%.2f", signal_id, pos.symbol, trade.pnl)
            remove_position(positions, signal_id)
            clear_position(discovery_watchlist, pos.symbol)
            continue

        if pos.direction != "BUY":
            continue  # trailing only supported for long Darvas breakouts today

        try:
            to_date = datetime.now(timezone.utc)
            from_date = to_date - timedelta(days=5)
            candles = broker.get_historical_data(pos.symbol, pos.timeframe, from_date, to_date)
            new_stop = next_trailing_stop(candles, pos.current_stop)
        except Exception as e:
            logger.error("[%s] Failed to recompute trailing stop for %s: %s",
                         signal_id, pos.symbol, e)
            continue

        if new_stop:
            if broker.modify_stop_loss(pos.sl_order_id, new_stop):
                logger.info("[%s] Trailed stop for %s: %.2f -> %.2f",
                            signal_id, pos.symbol, pos.current_stop, new_stop)
                update_stop(positions, signal_id, new_stop)
            else:
                logger.error("[%s] Broker rejected stop trail for %s", signal_id, pos.symbol)


def run_agent(config: dict):
    from core.brokers import get_broker
    from core.risk import TradeHistoryService

    broker = get_broker(config)
    logger.info("Connecting to broker: %s", config.get("broker"))
    broker.connect()
    logger.info("Broker connected: %s", broker)

    cloud_url = config["cloud"]["api_url"].rstrip("/")
    cloud_secret = config["cloud"].get("api_secret", "")
    webhook_secret = config["cloud"].get("webhook_secret", "")
    headers = {"X-Cloud-Secret": cloud_secret} if cloud_secret else {}
    poll_interval = 5  # seconds

    scanner_cfg = config.get("scanner", {})
    scanner_enabled = bool(scanner_cfg.get("enabled", True))
    universe_path = scanner_cfg.get("universe_file", "agent/universe_nifty500.txt")
    granular_interval_min = float(scanner_cfg.get("granular_scan_interval_minutes", 5))
    granular_every_n_ticks = max(1, int(granular_interval_min * 60 / poll_interval))

    # Breadth (advance/decline) sample for regime classification (S5-4). Its own
    # config key, deliberately: until 2026-07-16 this reused scanner.universe_file,
    # so breadth was measured from whatever Stage A was hunting — a hand-curated
    # Chartink momentum list, re-curated daily. That sample was non-stationary
    # (regime moved when the file was edited, not when the market did) and biased
    # (momentum-selected names aren't a market cross-section), which made regime
    # readings incomparable across days. Falls back to scanner.universe_file so an
    # older config.yaml keeps working; empty/missing file → breadth degrades to a
    # neutral placeholder (see core/regime/fetcher.py MIN_BREADTH_SAMPLE).
    #
    # Size is not a concern: BrokerAdapter.get_quotes chunks at 50 symbols/call,
    # so a 500-name sample is ~10 batched calls once per REGIME_CACHE_TTL.
    regime_cfg = config.get("regime", {})
    breadth_path = regime_cfg.get("breadth_universe_file", universe_path)
    breadth_universe = _load_universe(breadth_path)
    logger.info("Regime breadth universe: %d symbols from %s",
                len(breadth_universe), breadth_path)
    regime_service = RegimeService(broker, breadth_universe=breadth_universe)
    regime_every_n_ticks = max(1, int(REGIME_CACHE_TTL / poll_interval))

    # Portfolio kill switch (S4-2 / P0-2). Limits come from the agent's own
    # config.yaml risk block — core/config/settings.py is a cloud module the
    # agent never imports, so the defaults here mirror its 5-position /
    # 5%-daily-loss values.
    risk_cfg = config.get("risk", {})
    max_open_positions = int(risk_cfg.get("max_open_positions", 5))
    max_daily_loss_pct = float(risk_cfg.get("max_daily_loss", 0.05))
    # Correlation gate (S5-5 / P1-6): refuse a new entry too correlated with an
    # open position. On by default; set risk.correlation_gate: false to disable,
    # risk.correlation_threshold to tune (default 0.75).
    correlation_gate = bool(risk_cfg.get("correlation_gate", True))
    correlation_threshold = float(
        risk_cfg.get("correlation_threshold", CORRELATION_THRESHOLD))
    # Day-start capital base for the daily-loss %. The agent restarts daily
    # (Fyers token expiry), so funds at startup ≈ start-of-day equity. Falls
    # back to the configured reference capital if the broker call fails.
    try:
        risk_capital = float(broker.get_funds().get("available")
                             or risk_cfg.get("capital", 500_000))
    except Exception as e:
        risk_capital = float(risk_cfg.get("capital", 500_000))
        logger.warning("Could not read broker funds for daily-loss base — "
                       "using configured capital %.2f: %s", risk_capital, e)

    # Dead-man's switch (ADR-01: no agent-side Telegram fallback). Repeated
    # cloud-poll failures with positions open get one loud CRITICAL log; the
    # actual protection is that stops are broker-resident SL_M orders that
    # survive agent death, so we keep managing them and never auto-flatten.
    deadman_poll_failures = max(1, int(5 * 60 / poll_interval))  # ~5 min
    poll_failures = 0
    deadman_alerted = False

    # Persisted so Kelly's 20-trade minimum survives the daily agent
    # restart (Fyers token expiry) — see core/risk/trade_history.py.
    sizer = TradeHistoryService(persist_path=TRADE_HISTORY_PATH)
    # Correlation gate needs the connected broker to fetch price history (ADR-01).
    corr_service = CorrelationPortfolioService(broker) if correlation_gate else None
    if correlation_gate:
        logger.info("Correlation gate ON (threshold r=%.2f).", correlation_threshold)
    processed = _load_processed_ids()
    open_positions = load_open_positions()
    discovery_watchlist = load_watchlist()
    tick = 0

    if risk_guard.is_halted():
        logger.critical(
            "Kill switch ACTIVE at startup — halt flag present (%s). New "
            "entries will be refused until it is manually cleared. Exit "
            "management continues normally.", risk_guard.read_halt_reason())

    logger.info("Agent running. Cloud: %s | Polling every %ds for CONFIRMED signals.",
                cloud_url, poll_interval)
    logger.info("Press Ctrl+C to stop.")

    if scanner_enabled:
        if not webhook_secret:
            logger.warning(
                "scanner.enabled but cloud.webhook_secret is not set — Stage B "
                "won't be able to POST internally-detected signals to "
                "/webhook/tradingview. Set it to match Railway's WEBHOOK_SECRET."
            )
        if _should_run_discovery_today():
            try:
                _run_discovery_scan(broker, universe_path, discovery_watchlist,
                                     cloud_url, headers)
                _mark_discovery_ran_today()
            except Exception as e:
                logger.error("Stage A discovery scan failed: %s", e)
        else:
            logger.info("Stage A discovery already ran today — skipping.")

    try:
        _run_regime_sync(regime_service, cloud_url, headers)
    except Exception as e:
        logger.error("Regime sync failed: %s", e)

    try:
        while True:
            try:
                resp = requests.get(
                    f"{cloud_url}/signals",
                    params={"status": "CONFIRMED", "limit": 20},
                    headers=headers, timeout=10,
                )
                resp.raise_for_status()
                signals = resp.json().get("signals", [])
                poll_failures = 0
                deadman_alerted = False
            except Exception as e:
                logger.error("Failed to poll /signals: %s", e)
                signals = []
                poll_failures += 1
                # Dead-man's switch (ADR-01): no agent-side Telegram fallback.
                # Log loudly once when the cloud has been unreachable for a
                # while with positions open, and keep managing stops — the
                # broker-resident SL_M orders are the actual protection.
                if (poll_failures >= deadman_poll_failures and open_positions
                        and not deadman_alerted):
                    logger.critical(
                        "DEAD-MAN: cloud unreachable for %d consecutive polls with "
                        "%d open position(s). NOT auto-flattening — broker-resident "
                        "SL_M stop orders survive agent death and remain the "
                        "protection. Continuing to manage stops locally.",
                        poll_failures, len(open_positions))
                    deadman_alerted = True

            # Kill switch (S4-2): checked every poll tick. Automatic triggers
            # (consecutive losses + realized daily loss) are cheap in-memory
            # checks; open-position MTM is folded in at the trailing cadence
            # below, where we already hold live prices.
            _check_and_set_halt(broker, sizer, open_positions, cloud_url, headers,
                                risk_capital, max_daily_loss_pct)

            for signal in signals:
                signal_id = signal["signal_id"]
                if signal_id in processed:
                    continue

                # Kill switch gate (S4-2): refuse the entry if halted or the
                # concurrent-position cap is hit. This overrides the human
                # "execute" confirmation that already promoted the signal to
                # CONFIRMED — it is a hard refusal layer on top of ADR-05.
                # Exit management is never gated here, so open positions keep
                # trailing/closing while halted.
                refusal = risk_guard.entry_refusal_reason(
                    open_positions, max_open_positions=max_open_positions)
                if refusal:
                    logger.warning("[%s] REFUSED entry (%s %s): %s",
                                   signal_id, signal["action"], signal["symbol"], refusal)
                    _mark_processed(signal_id, processed)
                    _report_outcome(cloud_url, headers, signal_id, "failed",
                                    {"reason": f"REFUSED by kill switch: {refusal}"})
                    continue

                # Correlation gate (S5-5): refuse an entry too correlated with an
                # already-open position so the book doesn't stack one factor bet
                # (e.g. a second bank breakout while the first bank is open).
                # Layered AFTER the kill switch, BEFORE the order is placed.
                corr_refusal = _correlation_refusal_reason(
                    corr_service, signal["symbol"], open_positions,
                    correlation_threshold, cloud_url, headers)
                if corr_refusal:
                    logger.warning("[%s] %s (%s %s)", signal_id, corr_refusal,
                                   signal["action"], signal["symbol"])
                    _mark_processed(signal_id, processed)
                    _report_outcome(cloud_url, headers, signal_id, "failed",
                                    {"reason": corr_refusal})
                    continue

                # Mark BEFORE placing the order — a crash after this point
                # but before place_order() simply drops the trade (safe);
                # a crash after place_order() but before reporting back
                # will not cause a duplicate order on restart.
                _mark_processed(signal_id, processed)

                logger.info("[%s] Executing %s %s @ %.2f",
                            signal_id, signal["action"], signal["symbol"], signal["price"])
                try:
                    order_id, quantity, fill_price, stop_loss, auto_exit, sl_order_id = _size_and_place_order(
                        broker, sizer, signal, config
                    )
                    _report_outcome(cloud_url, headers, signal_id, "executed", {
                        "order_id": order_id, "quantity": quantity,
                        "execution_price": fill_price,
                    })
                    logger.info("[%s] Executed: qty=%d @ %.2f (order %s)",
                                signal_id, quantity, fill_price, order_id)

                    if auto_exit:
                        add_position(open_positions, OpenPosition(
                            signal_id=signal_id,
                            symbol=signal["symbol"],
                            direction=signal["action"],
                            quantity=quantity,
                            entry_price=fill_price,
                            entry_date=datetime.now(timezone.utc).isoformat(),
                            timeframe=signal.get("timeframe", "15m"),
                            current_stop=stop_loss,
                            sl_order_id=sl_order_id,
                            strategy=signal.get("strategy", "darvas_breakout"),
                        ))
                        mark_position_open(discovery_watchlist, signal["symbol"],
                                            fill_price, quantity)
                except Exception as e:
                    logger.error("[%s] Execution failed: %s", signal_id, e)
                    _report_outcome(cloud_url, headers, signal_id, "failed",
                                    {"reason": str(e)})

            tick += 1
            if tick % TRAIL_EVERY_N_TICKS == 0:
                try:
                    _sync_positions_to_cloud(broker, cloud_url, headers, open_positions)
                except Exception as e:
                    logger.error("Positions sync failed: %s", e)

                if open_positions:
                    _manage_open_positions(broker, cloud_url, headers, sizer,
                                            open_positions, discovery_watchlist)
                    # Re-evaluate the daily-loss trigger with open-position MTM
                    # folded in (bleeding open positions can breach the circuit
                    # breaker even with no closed trade today). Only fetch LTP if
                    # there's still something open after the close sweep above.
                    if open_positions and not risk_guard.is_halted():
                        try:
                            ltp = broker.get_ltp([p.symbol for p in open_positions.values()])
                        except Exception as e:
                            logger.error("Could not fetch LTP for kill-switch MTM check: %s", e)
                            ltp = None
                        _check_and_set_halt(broker, sizer, open_positions, cloud_url,
                                            headers, risk_capital, max_daily_loss_pct, ltp=ltp)

            if (scanner_enabled and tick % granular_every_n_ticks == 0
                    and _is_market_hours(datetime.now(timezone.utc))):
                try:
                    _run_granular_scan(broker, cloud_url, headers, webhook_secret, discovery_watchlist)
                except Exception as e:
                    logger.error("Stage B granular scan failed: %s", e)

            if tick % regime_every_n_ticks == 0:
                try:
                    _run_regime_sync(regime_service, cloud_url, headers)
                except Exception as e:
                    logger.error("Regime sync failed: %s", e)

            time.sleep(poll_interval)

    except KeyboardInterrupt:
        logger.info("Agent stopped.")
        broker.disconnect()


def main():
    parser = argparse.ArgumentParser(description="QuantOS Local Agent")
    parser.add_argument(
        "--config",
        default="agent/config.yaml",
        help="Path to agent config file (default: agent/config.yaml)"
    )
    args = parser.parse_args()
    config = load_config(args.config)
    run_agent(config)


if __name__ == "__main__":
    main()
