# QuantOS — AI-Powered Quant Trading Ecosystem

> Bloomberg. But Smarter.

QuantOS is an AI-native trading ecosystem for NSE Indian equities. It combines TradingView Premium signal generation, broker-agnostic order execution, and Claude AI for pre-trade analysis, regime detection, options strategy recommendation, and performance attribution.

---

## Architecture

```
quantos/
├── core/               # Shared logic — broker adapter, regime engine, Claude client, risk
│   ├── brokers/        # BrokerAdapter interface + Fyers/Zerodha implementations
│   ├── regime/         # Market regime classifier (Trending/Ranging/Volatile/Bearish)
│   ├── claude_client/  # Claude API wrapper with cost management + caching
│   └── risk/           # Kelly sizing, correlation checker, position limits
├── agent/              # Thin local agent (runs on customer machine, holds broker keys)
├── cloud/              # Cloud-hosted services (Railway → AWS)
│   ├── api/            # FastAPI webhook receiver (US-01)
│   ├── analyst/        # Claude pre-trade analyst (US-04)
│   └── scheduler/      # Morning brief, screener jobs, regime refresh
├── cockpit/            # React dashboard (US-13)
├── tests/
└── docs/               # ADRs, runbooks, API specs
```

### Deployment Model (ADR-01)
- **Cloud core** — regime engine, Claude analyst, cockpit, scheduler hosted on Railway
- **Local agent** — thin Python process on customer machine; broker keys never leave the customer
- **Migration path** — full SaaS (broker OAuth) once SOC2 posture established

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
- [ ] US-05: Market Regime Detection Engine
- [ ] US-15: Webhook Server Deployment

---

## License

Private — All rights reserved. © 2026 Greg / SeaOfTiberias.
