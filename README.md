# QuantOS — AI-Powered Quant Trading Ecosystem

> Bloomberg. But Smarter.

QuantOS is an AI-native trading ecosystem for NSE Indian equities. It combines TradingView Premium signal generation, broker-agnostic order execution, and Claude AI for pre-trade analysis, regime detection, options strategy recommendation, and performance attribution.

---

## Architecture

```
quantos/
├── core/               # Shared logic — broker adapter, regime engine, Claude client, risk
│   ├── brokers/        # BrokerAdapter interface + Fyers/Zerodha implementations
│   ├── darvas/         # Two-stage Darvas pipeline — see below
│   ├── regime/         # Market regime classifier (Trending/Ranging/Volatile/Bearish)
│   ├── claude_client/  # Claude API wrapper with cost management + caching
│   └── risk/           # Kelly sizing, correlation checker, position limits
├── agent/              # Thin local agent (runs on customer machine, holds broker keys)
│   ├── discovery_watchlist.py  # Persistent Stage A watchlist store
│   └── universe.txt             # Symbols Stage A scans daily — edit freely
├── cloud/              # Cloud-hosted services (Railway → AWS)
│   ├── api/            # FastAPI webhook receiver (US-01)
│   ├── analyst/        # Claude pre-trade analyst (US-04)
│   └── scheduler/      # Morning brief, screener jobs, regime refresh
├── cockpit/            # React + Vite dashboard (US-13) — `cd cockpit && npm install && npm run dev`
├── tests/
└── docs/               # ADRs, runbooks, API specs
```

### Deployment Model (ADR-01)
- **Cloud core** — Claude analyst, cockpit, scheduler hosted on Railway
- **Local agent** — thin Python process on customer machine; broker keys never leave the customer.
  This is also where the regime engine actually runs (see ADR-09) — anything needing a live
  broker connection has to live here, not on Railway.
- **Migration path** — full SaaS (broker OAuth) once SOC2 posture established

### Two-Stage Darvas Pipeline (ADR-07)
Candidate discovery and intraday entry timing are deliberately split, both running
inside the local agent (broker access lives there, not on Railway):

- **Stage A — discovery** (`core/darvas/weekly_discovery.py`): once/day, scans
  `agent/universe.txt` on daily/weekly bars for classic Nicholas Darvas boxes,
  tiering candidates HOT/WARM/WATCH by proximity + volume. Persists to
  `agent/discovery_watchlist.py` (`~/.quantos/discovery_watchlist.json`).
- **Stage B — timing** (`core/darvas/scanner.py`): every few minutes during
  market hours, re-scans just Stage A's shortlist on 15m/1h/1d confluence to
  time the actual entry — this is what fixes "found the setup after price
  already cleared the box." A fired signal is POSTed to the same
  `/webhook/tradingview` endpoint TradingView's Pine Script alerts use, so it
  gets identical Claude pre-trade analysis, event-risk filtering, and Telegram
  human-in-loop confirmation (ADR-05) — just tagged
  `strategy: darvas_scanner_internal` to distinguish the source.
- The agent also syncs its watchlist to `GET/POST /discovery/watchlist` on the
  cloud API purely so the cockpit's **Discovery Watchlist** panel has
  something to read — enable with `scanner.enabled: true` in
  `agent/config.yaml` (see `agent/config.yaml.example`).

### Regime Engine Sync (ADR-09)
`core/regime/service.py`'s `RegimeService` (US-05: Nifty trend + India VIX +
market breadth → TRENDING_BULL/TRENDING_BEAR/RANGING/VOLATILE/UNCERTAIN) runs
in the local agent — same reasoning as the Darvas pipeline above, it needs a
live broker connection Railway never has. The agent refreshes it every ~15
minutes (matching its own ADR-04 cache TTL) and POSTs the result to
`POST /regime/sync`. `cloud/analyst/pre_trade.py`'s pre-trade analysis and
`POST /strategy/recommend`'s options strategy advisor both read the synced
regime instead of a hardcoded placeholder — no config flag, this runs
unconditionally whenever the agent is running.

---

## Quickstart

### Prerequisites
- Python 3.11+
- Node.js 18+ (cockpit only)
- Docker + Docker Compose (recommended for local dev)

### 1. Clone & configure
```bash
git clone https://github.com/SeaOfTiberias/quantos.git
cd quantos
cp .env.example .env
# Edit .env with your keys
```

### 2. Run with Docker
```bash
docker-compose up
```

### 3. Run locally (no Docker)
```bash
pip install -r requirements.txt
# Cloud API
uvicorn cloud.api.main:app --reload --port 8000
# Local agent (separate terminal)
python agent/main.py
```

### 4. Run the cockpit dashboard
```bash
cd cockpit
npm install
cp .env.example .env   # set VITE_CLOUD_API_URL if your Railway instance differs
npm run dev            # http://localhost:5173
```
`npm run build` produces a static `dist/` bundle for deployment. Every panel
except **Discovery Watchlist** still renders mock data (`cockpit/src/App.jsx`)
— wiring the rest of the dashboard to live cloud data is tracked separately.

---

## Configuration

All config lives in `agent/config.yaml`. Swap broker in one line:

```yaml
broker: fyers          # or: zerodha | angel_one | upstox
credentials:
  api_key: YOUR_KEY
  api_secret: YOUR_SECRET
risk:
  capital: 500000
  max_risk_per_trade: 0.02
  max_open_positions: 5
claude:
  tier: pro            # free | pro | enterprise
  min_confluence_score: 70
  regime_cache_ttl: 900
```

---

## Supported Brokers (ADR-02)

| Broker | Status | Notes |
|---|---|---|
| Fyers | ✅ v1 | Primary — Darvas system already built |
| Zerodha / Kite | ✅ v1 | Largest retail base, excellent API |
| Angel One SmartAPI | 🔜 v2 | |
| Upstox | 🔜 v2 | |

---

## Regulatory Posture (ADR-05)

QuantOS operates in **human-in-loop mode by default**. Every signal triggers a WhatsApp confirmation before any order is placed. Full auto-execute requires explicit opt-in and is gated behind SEBI algo trading registration.

---

## Pricing (ADR-06)

| Tier | Price | Features |
|---|---|---|
| Free | ₹0 | Signals + screener only |
| Pro | ₹2,999/mo | Full AI analyst, options intelligence, journal, cockpit |
| Enterprise | Custom | Multi-account, white-label, direct API |

---

## Backlog

Full product backlog: `docs/QuantOS_Backlog_v3.pptx` — 7 Epics, 19 User Stories, 106 story points.

Current sprint: **Sprint 1 — Foundation**
- [ ] US-01: TradingView → Fyers Webhook Bridge
- [ ] US-02: Multi-Timeframe Darvas Box Scanner
- [ ] US-04: Claude Pre-Trade Analyst
- [x] US-05: Market Regime Detection Engine
- [ ] US-15: Webhook Server Deployment

---

## License

Private — All rights reserved. © 2026 Greg / SeaOfTiberias.
