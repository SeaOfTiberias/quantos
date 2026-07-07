# QuantOS Architecture Decision Record (ADR v1.0)

All decisions finalized. Do not change without updating this document and creating a new ADR version.

---

## ADR-01 · Deployment Model

**Decision:** Hybrid Cloud + Local Agent → architect for full SaaS

| Layer | What runs there | Why |
|---|---|---|
| Cloud core | Regime engine, Claude analyst, cockpit, scheduler | Always-on, centralised updates |
| Local agent | Thin Python process on customer machine | Broker keys never leave customer |

**Migration path:**
- v1: Hybrid (builds trust, no key custody on our servers)
- v2: Full SaaS with broker OAuth — trigger: SOC2 posture + track record established
- SEBI algo registration required before enabling full auto-execute

---

## ADR-02 · Broker Abstraction

**Decision:** `BrokerAdapter` abstract interface. Swap broker in one config line.

**Standard contract:** `place_order()` · `get_positions()` · `get_historical_data()` · `get_ltp()` · `get_funds()`

| Broker | Status |
|---|---|
| Fyers | ✅ v1 |
| Zerodha / Kite | ✅ v1 |
| Angel One SmartAPI | 🔜 v2 |
| Upstox | 🔜 v2 |

**Config:**
```yaml
broker: zerodha
credentials:
  api_key: xxx
  api_secret: xxx
```

---

## ADR-03 · Multi-Tenancy

**Decision:** `user_id` foreign key on every database table from day one. No retrofit later.

- Row-level security (RLS) in Postgres
- Per-user Claude API rate limits and cost tracking
- Anonymised cross-user strategy performance data (opt-in) as future moat

---

## ADR-04 · Claude API Cost Strategy

**Decision:** Cache aggressively · Batch intelligently · Rate-limit by tier

| Optimisation | Detail |
|---|---|
| Regime cache | 15-minute TTL — not recalculated per signal |
| Morning brief | Single batched Claude call at 8:30 AM IST covering regime + screener + brief |
| Pre-trade gate | Claude only called when confluence score ≥ 70 |
| Tier limits | Free: 20 calls/day · Pro: 200/day · Enterprise: unlimited |

---

## ADR-05 · Regulatory Posture

**Decision:** Human-in-loop by default. SEBI registration gates full auto-execute.

- Every signal triggers WhatsApp confirmation before order placement
- Auto-execute is an explicit opt-in, disabled by default
- No customer funds or broker credentials stored on QuantOS servers in v1
- Legal review required before external customer launch

---

## ADR-06 · Pricing

**Decision:** Freemium → Pro SaaS · Claude costs recovered at 2× markup within Pro tier

| Tier | Price | Includes |
|---|---|---|
| Free | ₹0 | Signals + screener only |
| Pro | ₹2,999/mo | Full AI analyst, options intelligence, Greeks panel, journal, cockpit |
| Enterprise | Custom | Multi-account, white-label, direct API access |

---

## ADR-07 · Two-Stage Darvas Pipeline

**Decision:** Split candidate *discovery* from entry *timing* into two scanners,
both running in the local agent, both funnelling into the existing
`/webhook/tradingview` pipeline rather than each having their own execution path.

| Stage | Module | Cadence | Job |
|---|---|---|---|
| A — Discovery | `core/darvas/weekly_discovery.py` | Once/day | Classic weekly-box scan across a broad symbol universe (`agent/universe.txt`); tiers candidates HOT/WARM/WATCH |
| B — Timing | `core/darvas/scanner.py` | Every few minutes, market hours only | Multi-timeframe (15m/1h/1d) confluence scan on Stage A's shortlist only — this is what times the actual entry |

**Why:** an earlier daily/weekly-only scanner (the user's prior DarvasTrader
project) found genuinely good candidates but surfaced them after price had
often already cleared the box — poor entry R:R, no time to react. Narrowing
a broad daily scan down to a shortlist, then re-timing that shortlist
intraday, fixes the lag without discarding either methodology.

**Both stages run in the local agent, not on Railway** — broker credentials
only ever live there (ADR-01), so discovery and timing can't run cloud-side.
A Stage B fire is POSTed to `/webhook/tradingview` tagged
`strategy: darvas_scanner_internal`, so it gets identical Claude analysis,
event-risk filtering, and Telegram confirmation (ADR-05) as a Pine Script
alert — no separate execution path to keep in sync. A same-day, same-symbol
dedup guard on the webhook prevents both sources firing on the same setup.

---

## ADR-08 · Discovery Watchlist Sync & Cockpit Build

**Decision:** The cockpit (`cockpit/`) is a real Vite + React app (not just a
source file) with one panel — Discovery Watchlist — wired to live data via a
new `GET/POST /discovery/watchlist` pair on the cloud API. Every other panel
remains mock data pending a separate effort to wire the rest of the dashboard.

- **POST** (agent → cloud) is guarded by the existing `X-Cloud-Secret`
  (`cloud/api/auth.py`, shared with `/signals*` to avoid a circular import).
- **GET** (cockpit → cloud) is intentionally unauthenticated, consistent with
  every other read-only router in this app (screener/risk/events/etc.) — the
  cockpit is a browser client, and embedding the cloud secret in frontend JS
  would defeat the point of guarding it.
- The watchlist itself never leaves the agent's machine as a system of
  record — the cloud copy is a disposable, wholesale-replaced mirror purely
  for display (`~/.quantos/discovery_watchlist.json` is the source of truth).

---

## ADR-09 · Regime Engine Sync (Agent → Cloud)

**Decision:** `core/regime/service.py`'s `RegimeService` (US-05, real Nifty
trend/VIX/breadth classification) runs in the local agent — the only
process with a connected broker (ADR-01) — and pushes its result to the
cloud via `POST /regime/sync` (`cloud/api/regime_routes.py`), the same
sync-mirror pattern ADR-08 established for the discovery watchlist.
`cloud/analyst/pre_trade.py` and `POST /strategy/recommend`
(`cloud/api/strategy_routes.py`) both read the synced result instead of
touching a broker directly.

**Why:** before this, `cloud/api/main.py` declared a `_regime_service = None`
global with a comment saying it'd be set "once broker adapter is ready" —
that never happened, because Railway can never hold a broker connection
(ADR-01). Two consequences: `pre_trade.py`'s `_get_regime()` was a
hardcoded stub feeding every trade signal a fake, static "TRENDING/
UPTREND/VIX 14.2" regardless of real conditions, and `/strategy/recommend`
503'd unconditionally since `_regime_service` was always `None`. Both bugs
trace to the same root cause and are fixed by the same sync.

The agent refreshes and syncs on a cadence matching `RegimeService`'s own
15-minute cache TTL (ADR-04) — each sync tick both keeps the cache fresh
and reflects it to the cloud. `get_synced_regime()` treats a sync older
than 30 minutes as unavailable (double the TTL — tolerates one missed
tick) and falls back to an explicitly-labeled `UNKNOWN` regime rather than
ever returning stale data silently.

**Bugs found while wiring this up** (same pattern as ADR-07's two-stage
pipeline): `RegimeService.__init__` built its `asyncio.Lock()` at
construction time, which breaks under the agent's `asyncio.run()`-per-tick
call pattern exactly like the `asyncio.Semaphore` bugs in
`weekly_discovery.py`/`scanner.py` — fixed by lazily rebinding the lock to
whichever loop is current. Separately, `core/regime/fetcher.py` requests
index symbols (`"NIFTY 50"`, `"INDIA VIX"`) that `FyersBroker` had never
been asked for before — it blindly formatted every symbol as an equity
(`NSE:{symbol}-EQ`); Fyers indices need `NSE:NIFTY50-INDEX` /
`NSE:INDIAVIX-INDEX` instead. Fixed in `core/brokers/fyers.py`.
