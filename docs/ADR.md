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
