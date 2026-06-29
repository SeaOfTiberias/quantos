# QuantOS — Railway Environment Variables

Set these in the Railway dashboard under your service → **Variables**.

---

## Required

| Variable | Description | Example |
|---|---|---|
| `ANTHROPIC_API_KEY` | Your Claude API key | `sk-ant-...` |
| `WEBHOOK_SECRET` | Secret shared with TradingView | Any strong random string |
| `CALLMEBOT_PHONE` | Your WhatsApp number (international format) | `+917xxxxxxxxx` |
| `CALLMEBOT_API_KEY` | Your CallMeBot API key | `xxxxxxx` |

## Recommended

| Variable | Default | Description |
|---|---|---|
| `MIN_CONFLUENCE_SCORE` | `70` | Minimum Darvas confluence to pass Claude |
| `REGIME_CACHE_TTL` | `900` | Regime cache duration in seconds (15 min) |
| `ENVIRONMENT` | `production` | `development` or `production` |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

## Optional (Sprint 2+)

| Variable | Description |
|---|---|
| `DATABASE_URL` | Postgres URL (Railway provides this if you add a Postgres plugin) |
| `DEFAULT_USER_ID` | User ID for single-tenant mode (multi-tenant in v2) |
| `QUANTOS_API_URL` | Your Railway deployment URL (used by monitor.py) |

---

## Railway Postgres (Sprint 2)

1. In Railway dashboard → **New** → **Database** → **PostgreSQL**
2. Railway auto-injects `DATABASE_URL` into your service
3. Run migrations: `railway run alembic upgrade head`

---

## TradingView Webhook Setup

1. In TradingView → Alert → **Webhook URL**: `https://your-app.railway.app/webhook/tradingview`
2. Alert message (JSON):
```json
{
  "symbol":           "{{ticker}}",
  "action":           "{{strategy.order.action}}",
  "price":            {{close}},
  "timeframe":        "{{interval}}",
  "strategy":         "darvas_breakout",
  "confluence_score": {{plot_0}},
  "secret":           "YOUR_WEBHOOK_SECRET"
}
```
3. `YOUR_WEBHOOK_SECRET` must match `WEBHOOK_SECRET` in Railway variables.

---

## Verify deployment

```bash
# Health check
curl https://your-app.railway.app/health

# Operational status
curl https://your-app.railway.app/status

# Test webhook (replace URL and secret)
curl -X POST https://your-app.railway.app/webhook/tradingview \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "RELIANCE",
    "action": "BUY",
    "price": 2950.00,
    "timeframe": "1h",
    "strategy": "darvas_breakout",
    "confluence_score": 85,
    "secret": "YOUR_WEBHOOK_SECRET"
  }'
```

Expected response:
```json
{
  "signal_id": "SIG-DARV-XXXXXXXX",
  "symbol": "RELIANCE",
  "action": "BUY",
  "status": "PENDING_CONFIRMATION",
  "confidence_score": 78.5,
  "message": "Signal pending WhatsApp confirmation"
}
```
